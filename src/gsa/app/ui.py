from __future__ import annotations

import os
import re
import uuid
from typing import Any, Dict, List, Optional

import streamlit as st

from gsa.agent.clarifier import clarify_questions
from gsa.agent.orchestrator import Orchestrator
from gsa.llm.llm_client import load_config


st.set_page_config(page_title="Git Safety Agent", layout="wide")


def _default_workspace() -> str:
    return os.environ.get("GSA_WORKSPACE", os.getcwd())


@st.cache_resource

def get_orchestrator(workspace: str) -> Orchestrator:
    return Orchestrator(workspace)


@st.cache_data

def get_tree_items(workspace: str, max_depth: int) -> List[str]:
    orch = get_orchestrator(workspace)
    data = orch.mcp.call_tool("file_list", {"dir": ".", "max_depth": max_depth})
    return data.get("items", [])


@st.cache_data

def get_git_graph(workspace: str, n: int, author: str, branch: str, path: str) -> str:
    orch = get_orchestrator(workspace)
    data = orch.mcp.call_tool(
        "git_log_graph",
        {
            "n": n,
            "author": author or None,
            "branch": branch or None,
            "path": path or None,
        },
    )
    return data.get("stdout", "")


def build_tree(items: List[str]) -> Dict[str, Any]:
    tree: Dict[str, Any] = {"__files__": []}
    for item in items:
        path = item.replace("./", "").strip()
        if not path or path in {".", "./"}:
            continue
        if path.endswith("/"):
            parts = path.strip("/").split("/")
            node = tree
            for p in parts:
                node = node.setdefault(p, {"__files__": []})
        else:
            parts = path.split("/")
            *dirs, fname = parts
            node = tree
            for d in dirs:
                node = node.setdefault(d, {"__files__": []})
            node.setdefault("__files__", []).append(fname)
    return tree


def render_tree(node: Dict[str, Any], base: str = "") -> None:
    dirs = sorted([k for k in node.keys() if k != "__files__"])
    files = sorted(node.get("__files__", []))
    for d in dirs:
        with st.expander(f"📁 {d}", expanded=False):
            render_tree(node[d], os.path.join(base, d) if base else d)
    for f in files:
        full_path = os.path.join(base, f) if base else f
        if st.button(f"📄 {f}", key=f"file_{full_path}"):
            st.session_state["preview_file"] = full_path


def append_message(role: str, content: str) -> None:
    st.session_state.setdefault("messages", []).append({"role": role, "content": content})


def render_messages() -> None:
    for msg in st.session_state.get("messages", []):
        with st.chat_message(msg["role"]):
            st.write(msg["content"])


def _friendly_error(errors: List[str], has_plan: bool) -> Optional[str]:
    if not errors:
        return None
    if has_plan:
        errors = [e for e in errors if "规划结果解析失败" not in e]
        if not errors:
            return None
    text = "\n".join(errors)
    if "BIGMODEL_API_KEY" in text:
        return "未检测到 API Key。请配置 BIGMODEL_API_KEY（环境变量或 config.yaml）。"
    if "timed out" in text or "超时" in text:
        return "LLM 调用超时，已自动降级为规则规划。请检查网络与 API Key。"
    if "LLM 调用失败" in text:
        return "LLM 调用失败，错误信息如下：\n" + text
    return "规划校验出现问题：\n" + text


def _plan_summary_text(plan) -> str:
    lines = [f"意图：{plan.intent}"]
    if not plan.steps:
        lines.append("未生成步骤。")
        return "\n".join(lines)
    lines.append("我将尝试执行以下步骤：")
    for idx, step in enumerate(plan.steps, 1):
        lines.append(
            f"{idx}. {step.tool}｜风险：{step.safety_level}｜原因：{step.safety_reason}"
        )
    if plan.needs_confirmation:
        lines.append("该计划包含写操作，需要 YES 确认。")
    return "\n".join(lines)


def _render_long_text(title: str, text: str, as_code: bool = False) -> None:
    if len(text) > 800:
        with st.expander(title, expanded=False):
            if as_code:
                st.code(text, language="text")
            else:
                st.write(text)
    else:
        if as_code:
            st.code(text, language="text")
        else:
            st.write(text)


def _is_code_like(text: str, query: str) -> bool:
    if "```" in text:
        return True
    if re.search(r"\b(代码|code|函数|类)\b", query):
        return True
    if re.search(r"\b(def |class |import |from |if __name__|@)\b", text):
        return True
    return False


def _render_qa_answer(answer: str, sources: List[str], query: str) -> None:
    if not answer:
        st.write("未返回答案。")
        return
    if "```" in answer:
        if len(answer) > 800:
            with st.expander("展开回答", expanded=False):
                st.markdown(answer)
        else:
            st.markdown(answer)
    else:
        _render_long_text("展开回答", answer, as_code=_is_code_like(answer, query))
    if sources:
        with st.expander("参考文件", expanded=False):
            st.write("\n".join([f"- {s}" for s in sources]))


def _handle_chat_request(orch: Orchestrator, user_input: str, chat_mode: str) -> None:
    pending_questions = st.session_state.get("pending_questions")
    base_input = st.session_state.get("pending_base_input", "")

    with st.chat_message("assistant"):
        with st.spinner("正在规划..."):
            if chat_mode == "索引问答":
                res = orch.mcp.call_tool("index_qa", {"query": user_input, "top_k": 6})
                if not res.get("ok", True):
                    if "索引不存在" in str(res.get("error")):
                        msg = (
                            "索引尚未构建。索引会把本地文件切片并建立向量检索，"
                            "使模型能基于源码准确回答问题。"
                        )
                        st.session_state["need_index"] = True
                        st.session_state["need_index_msg"] = msg
                    else:
                        msg = res.get("error", "索引问答失败")
                    st.write(msg)
                    append_message("assistant", msg)
                else:
                    answer = res.get("answer", "")
                    sources = res.get("sources", [])
                    snippets = res.get("snippets", [])
                    _render_qa_answer(answer, sources, user_input)
                    if snippets:
                        with st.expander("相关片段", expanded=False):
                            for snip in snippets:
                                src = snip.get("source") or "未知来源"
                                text = snip.get("content", "")
                                st.markdown(f"**{src}**")
                                if _is_code_like(text, user_input):
                                    st.code(text, language="text")
                                else:
                                    st.write(text)
                    msg = answer
                    if sources:
                        msg += "\n\n参考文件：\n" + "\n".join([f"- {s}" for s in sources])
                    append_message("assistant", msg)
                return

            if pending_questions:
                combined = base_input + "\n补充信息: " + user_input
                st.session_state["pending_questions"] = []
            else:
                combined = user_input
                st.session_state["pending_base_input"] = user_input

            orch.use_llm = True
            result = orch.plan(combined)
            st.session_state["last_plan_result"] = result

            msg = _friendly_error(result.errors, has_plan=bool(result.plan))
            if msg:
                st.write(msg)
                append_message("assistant", msg)

            if result.plan:
                if result.plan.questions:
                    qs = clarify_questions(result.plan.questions)
                    msg2 = "我需要进一步澄清：\n" + qs
                    st.write(msg2)
                    append_message("assistant", msg2)
                    st.session_state["pending_questions"] = result.plan.questions
                else:
                    msg2 = _plan_summary_text(result.plan)
                    st.write(msg2)
                    append_message("assistant", msg2)


def _handle_quick_action(orch: Orchestrator, action: str) -> None:
    with st.chat_message("assistant"):
        with st.spinner("正在规划..."):
            if action == "repo_summarize":
                res = orch.mcp.call_tool("repo_summarize", {})
                if not res.get("ok", True) and "索引不存在" in str(res.get("error")):
                    msg = (
                        "索引尚未构建。索引会把本地文件切片并建立向量检索，"
                        "使模型能基于源码准确回答问题。"
                    )
                    st.session_state["need_index"] = True
                    st.session_state["need_index_msg"] = msg
                else:
                    msg = res.get("summary", "") if res.get("ok", True) else res.get("error", "概览失败")
                st.write(msg)
                append_message("assistant", msg)
                return
            if action == "organize_suggestions":
                res = orch.mcp.call_tool("organize_suggestions", {})
                if not res.get("ok", True) and "索引不存在" in str(res.get("error")):
                    msg = (
                        "索引尚未构建。索引会把本地文件切片并建立向量检索，"
                        "使模型能基于源码准确回答问题。"
                    )
                    st.session_state["need_index"] = True
                    st.session_state["need_index_msg"] = msg
                else:
                    if not res.get("ok", True):
                        msg = res.get("error", "整理建议失败")
                    else:
                        msg = res.get("suggestions", "")
                        st.session_state["last_suggestions"] = msg
                st.write(msg)
                append_message("assistant", msg)
                return
            msg = "未知操作"
            st.write(msg)
            append_message("assistant", msg)


def main():
    st.title("Git Safety Agent")
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] { width: 360px !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if "workspace" not in st.session_state:
        st.session_state["workspace"] = _default_workspace()
    workspace = st.session_state["workspace"]

    orch = get_orchestrator(workspace)
    pending_request = st.session_state.get("pending_request")
    pending_request_handled = st.session_state.get("pending_request_handled", False)
    pending_quick = st.session_state.get("pending_quick_action")
    pending_quick_handled = st.session_state.get("pending_quick_action_handled", False)
    busy = bool(
        st.session_state.get("processing", False)
        or (pending_request and not pending_request_handled)
        or (pending_quick and not pending_quick_handled)
    )

    with st.sidebar:
        with st.expander("模型配置", expanded=True):
            cfg = load_config(workspace)
            base_options = {
                "国内（open.bigmodel.cn）": "https://open.bigmodel.cn/api/paas/v4/",
                "海外（api.z.ai）": "https://api.z.ai/api/paas/v4/",
            }
            current_url = st.session_state.get("base_url_override") or cfg.base_url
            base_index = 0 if "open.bigmodel.cn" in current_url else 1
            col_a, col_b = st.columns(2)
            with col_a:
                base_label = st.selectbox("接口地址", list(base_options.keys()), index=base_index)
            with col_b:
                model = st.selectbox(
                    "模型选择",
                    ["glm-4.7", "glm-4.7-flash"],
                    index=0 if cfg.model == "glm-4.7" else 1,
                )
            selected_url = base_options[base_label]
            st.session_state["base_url_override"] = selected_url
            os.environ["BIGMODEL_BASE_URL"] = selected_url
            orch.planner.set_base_url(selected_url)
            orch.planner.set_model(model)

        with st.expander("对话", expanded=True):
            chat_mode = st.radio(
                "模式",
                ["计划执行", "索引问答"],
                horizontal=True,
            )
            st.session_state["chat_mode"] = chat_mode
            col_q1, col_q2 = st.columns(2)
            with col_q1:
                if st.button("一键仓库概览"):
                    append_message("user", "一键仓库概览")
                    st.session_state["pending_quick_action"] = {"id": uuid.uuid4().hex, "action": "repo_summarize"}
                    st.session_state["pending_quick_action_handled"] = False
                    st.rerun()
            with col_q2:
                if st.button("一键整理建议"):
                    append_message("user", "一键整理建议")
                    st.session_state["pending_quick_action"] = {"id": uuid.uuid4().hex, "action": "organize_suggestions"}
                    st.session_state["pending_quick_action_handled"] = False
                    st.rerun()

            with st.form("sidebar_chat", clear_on_submit=True, border=False):
                user_input = st.text_input("输入自然语言任务", placeholder="输入自然语言任务...", disabled=busy, label_visibility="collapsed")
                send = st.form_submit_button("发送", disabled=busy, use_container_width=True)
            if send and user_input.strip():
                prefix = "计划执行" if chat_mode == "计划执行" else "索引问答"
                append_message("user", f"{prefix}：{user_input}")
                st.session_state["pending_request"] = {
                    "id": uuid.uuid4().hex,
                    "input": user_input,
                    "mode": chat_mode,
                }
                st.session_state["pending_request_handled"] = False
                st.rerun()

        with st.expander("工作区", expanded=False):
            st.caption(f"当前：{workspace}")
            ws_input = st.text_input("切换工作区", value=workspace)
            if st.button("应用工作区"):
                if not os.path.isdir(ws_input):
                    st.error("路径不存在或不可访问")
                else:
                    st.session_state["workspace"] = ws_input
                    st.cache_data.clear()
                    st.rerun()

        with st.expander("目录结构", expanded=False):
            query = st.text_input("快速搜索路径")
            preview_enabled = st.checkbox("启用文件预览", value=True)
            st.session_state["preview_enabled"] = preview_enabled
            if st.button("刷新目录"):
                st.cache_data.clear()
            items = get_tree_items(workspace, 3)
            if query:
                items = [i for i in items if query in i]
            tree = build_tree(items)
            render_tree(tree)

        with st.expander("Git 历史", expanded=False):
            n = st.slider("提交数量", 5, 80, 30)
            branch = st.text_input("分支过滤（可选）", value="")
            author = st.text_input("作者过滤（可选）", value="")
            path = st.text_input("文件路径过滤（可选）", value="")
            if st.button("刷新历史"):
                st.cache_data.clear()
            graph = get_git_graph(workspace, n, author, branch, path)
            st.code(graph, language="text")

    with st.container():
        messages = st.session_state.get("messages", [])
        if messages:
            st.subheader("对话区")
            render_messages()
        else:
            st.markdown(
                """
                <div style="text-align:center;padding:6rem 0 3rem;">
                  <h3>欢迎使用 Git Safety Agent</h3>
                  <p>输入自然语言指令，我会先规划再执行，确保操作可控可回溯。</p>
                  <p>你可以尝试：</p>
                  <p>• 初始化 Git 仓库 • 查看最近提交历史 • 一键仓库概览 • 一键整理建议</p>
                  <p>切换到“索引问答”模式，还可以就源码提问。</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if pending_request and not pending_request_handled:
            req = st.session_state.get("pending_request", {})
            st.session_state["processing"] = True
            try:
                _handle_chat_request(orch, req.get("input", ""), req.get("mode", "计划执行"))
            finally:
                st.session_state["processing"] = False
                st.session_state["pending_request_handled"] = True
                st.session_state["pending_request"] = None
                st.session_state["post_handle_rerun"] = True

        if pending_quick and not pending_quick_handled:
            qa = st.session_state.get("pending_quick_action", {})
            st.session_state["processing"] = True
            try:
                _handle_quick_action(orch, qa.get("action", ""))
            finally:
                st.session_state["processing"] = False
                st.session_state["pending_quick_action_handled"] = True
                st.session_state["pending_quick_action"] = None
                st.session_state["post_handle_rerun"] = True

        suggestions = st.session_state.get("last_suggestions")
        if suggestions:
            if st.button("根据最近整理建议生成执行计划"):
                with st.chat_message("user"):
                    st.write("请根据最近整理建议生成可执行计划")
                append_message("user", "请根据最近整理建议生成可执行计划")
                prompt = "以下是整理建议，请生成可执行的计划步骤：\n" + suggestions
                with st.chat_message("assistant"):
                    with st.spinner("正在规划..."):
                        orch.use_llm = True
                        result = orch.plan(prompt)
                        st.session_state["last_plan_result"] = result
                        msg = _friendly_error(result.errors, has_plan=bool(result.plan))
                        if msg:
                            st.write(msg)
                            append_message("assistant", msg)
                        if result.plan:
                            if result.plan.questions:
                                qs = clarify_questions(result.plan.questions)
                                msg2 = "我需要进一步澄清：\n" + qs
                                st.write(msg2)
                                append_message("assistant", msg2)
                                st.session_state["pending_questions"] = result.plan.questions
                            else:
                                msg2 = _plan_summary_text(result.plan)
                                st.write(msg2)
                                append_message("assistant", msg2)

        plan_result = st.session_state.get("last_plan_result")
        selected_plan = None
        if plan_result and plan_result.plan:
            with st.expander("查看计划 JSON", expanded=False):
                st.json(plan_result.plan.model_dump())

            st.subheader("执行控制")
            st.caption("选择要执行的步骤（可多选）")
            selected_indices: List[int] = []
            for i, step in enumerate(plan_result.plan.steps):
                key = f"step_select_{plan_result.trace_id}_{i}"
                label = f"{i+1}. {step.tool}｜风险：{step.safety_level}｜原因：{step.safety_reason}"
                checked = st.checkbox(label, value=True, key=key)
                if checked:
                    selected_indices.append(i)

            if selected_indices:
                selected_steps = [s for idx, s in enumerate(plan_result.plan.steps) if idx in selected_indices]
                needs_confirm = any(s.safety_level in {"medium", "high"} for s in selected_steps)
                selected_plan = plan_result.plan.model_copy(
                    update={"steps": selected_steps, "needs_confirmation": needs_confirm}
                )
            else:
                st.warning("请至少选择一条步骤再执行。")

            confirmed = st.checkbox("我已阅读风险并确认执行（YES）", value=False)
            col_run, col_dry = st.columns(2)
            with col_run:
                if st.button("执行计划", disabled=not selected_plan):
                    with st.spinner("执行中..."):
                        exec_res = orch.execute(selected_plan, plan_result.trace_id, confirmed=confirmed)
                        st.session_state["exec_result"] = exec_res
            with col_dry:
                if st.button("仅试运行", disabled=not selected_plan):
                    with st.spinner("试运行中..."):
                        exec_res = orch.execute(selected_plan, plan_result.trace_id, confirmed=False)
                        st.session_state["exec_result"] = exec_res

    exec_result = st.session_state.get("exec_result")
    if exec_result:
        st.subheader("执行结果")
        st.info(exec_result.get("summary", ""))
        st.caption("执行明细")
        for item in exec_result.get("results", []):
            tool = item.get("tool", "")
            ok = item.get("ok", False)
            st.write(f"- {tool}：{'成功' if ok else '失败'}")
        with st.expander("错误摘要", expanded=False):
            has_error = False
            for item in exec_result.get("results", []):
                tool = item.get("tool", "")
                if not item.get("ok"):
                    st.markdown(f"**{tool}**")
                    st.write(item.get("error", "未知错误"))
                    has_error = True
                    continue
                result = item.get("result", {})
                stderr = result.get("stderr")
                if stderr:
                    st.markdown(f"**{tool}**")
                    st.code(stderr, language="text")
                    has_error = True
            if not has_error:
                st.write("无错误。")
        st.info(f"trace_id: {exec_result.get('trace_id')}")
        log_path = os.path.join(orch.workspace, ".gsa", "logs")
        st.info(f"日志目录：{log_path}")
        try:
            files = sorted(os.listdir(log_path))
            if files:
                latest = os.path.join(log_path, files[-1])
                with open(latest, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()[-50:]
                st.code("\n".join(lines), language="json")
        except Exception:
            pass

        if st.session_state.get("need_index"):
            st.subheader("索引提示")
            st.info(st.session_state.get("need_index_msg", "需要先构建索引。"))
            if st.button("构建索引"):
                with st.spinner("正在构建索引..."):
                    res = orch.mcp.call_tool(
                        "index_build",
                        {"include_globs": ["**/*"], "exclude_globs": [], "dry_run": False},
                    )
                if res.get("ok", True):
                    msg = (
                        f"索引已构建：文档 {res.get('docs')}，"
                        f"切片 {res.get('chunks')}。请重新提问。"
                    )
                    st.session_state["need_index"] = False
                    st.session_state["need_index_msg"] = ""
                else:
                    msg = res.get("error", "索引构建失败")
                st.write(msg)
                append_message("assistant", msg)

        if st.session_state.get("post_handle_rerun"):
            st.session_state["post_handle_rerun"] = False
            st.rerun()

    preview_enabled = st.session_state.get("preview_enabled", True)
    preview_path = st.session_state.get("preview_file", "")
    if preview_enabled and preview_path:
        st.subheader("文件预览")
        st.caption(f"预览：{preview_path}")
        content = orch.mcp.call_tool("file_read", {"path": preview_path})
        if not content.get("ok", True):
            st.error(content.get("error", "读取失败"))
        else:
            text = content.get("content", "")
            if not text:
                st.info("文件为空或无法显示（可能为二进制或内容过大）。")
            else:
                st.text_area("文件内容预览", text, height=260, disabled=True, label_visibility="collapsed")


if __name__ == "__main__":
    main()
