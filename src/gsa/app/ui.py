from __future__ import annotations

import os
import sys
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


def _llm_status_text(workspace: str) -> str:
    cfg = load_config(workspace)
    if cfg.api_key:
        return "LLM 已配置（glm-4.7 / zai-sdk）"
    return "LLM 未配置，请设置 BIGMODEL_API_KEY"


def _friendly_error(errors: List[str]) -> Optional[str]:
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


def main():
    st.title("Git Safety Agent")

    if "workspace" not in st.session_state:
        st.session_state["workspace"] = _default_workspace()
    workspace = st.session_state["workspace"]

    orch = get_orchestrator(workspace)

    with st.sidebar:
        st.header("工作区")
        st.caption(f"当前：{workspace}")
        st.caption(f"Python：{sys.executable}")
        ws_input = st.text_input("切换工作区", value=workspace)
        if st.button("应用工作区"):
            if not os.path.isdir(ws_input):
                st.error("路径不存在或不可访问")
            else:
                st.session_state["workspace"] = ws_input
                st.cache_data.clear()
                st.rerun()

        st.caption(_llm_status_text(workspace))
        st.caption(f"Base URL: {load_config(workspace).base_url}")
        st.caption("提示：默认使用 LLM；若失败将自动降级。")

        if orch.memory.persist.common_workspaces:
            st.caption("常用工作区")
            st.code("\n".join(orch.memory.persist.common_workspaces[-5:]))

        st.divider()
        st.header("目录结构")
        depth = st.slider("展开深度", 1, 6, 3)
        query = st.text_input("快速搜索路径")
        if st.button("刷新目录"):
            st.cache_data.clear()
        items = get_tree_items(workspace, depth)
        if query:
            items = [i for i in items if query in i]
        tree = build_tree(items)
        render_tree(tree)

        st.divider()
        st.header("Git 历史（图形）")
        n = st.slider("提交数量", 5, 80, 30)
        branch = st.text_input("分支过滤（可选）", value="")
        author = st.text_input("作者过滤（可选）", value="")
        path = st.text_input("文件路径过滤（可选）", value="")
        if st.button("刷新历史"):
            st.cache_data.clear()
        graph = get_git_graph(workspace, n, author, branch, path)
        st.code(graph, language="text")

    st.subheader("对话区")

    user_input = st.chat_input("输入自然语言任务...")
    if user_input:
        pending_questions = st.session_state.get("pending_questions")
        base_input = st.session_state.get("pending_base_input", "")
        if pending_questions:
            combined = base_input + "\n补充信息: " + user_input
            append_message("user", f"补充回答：{user_input}")
            st.session_state["pending_questions"] = []
        else:
            combined = user_input
            append_message("user", user_input)
            st.session_state["pending_base_input"] = user_input

        with st.spinner("正在规划..."):
            orch.use_llm = True
            result = orch.plan(combined)
            st.session_state["last_plan_result"] = result

        msg = _friendly_error(result.errors)
        if msg:
            append_message("assistant", msg)

        if result.plan:
            if result.plan.questions:
                qs = clarify_questions(result.plan.questions)
                append_message("assistant", "我需要进一步澄清：\n" + qs)
                st.session_state["pending_questions"] = result.plan.questions
            else:
                append_message("assistant", _plan_summary_text(result.plan))

    render_messages()

    plan_result = st.session_state.get("last_plan_result")
    if plan_result and plan_result.plan:
        with st.expander("查看计划 JSON", expanded=False):
            st.json(plan_result.plan.model_dump())

        st.subheader("执行控制")
        confirmed = st.checkbox("我已阅读风险并确认执行（YES）", value=False)
        col_run, col_dry = st.columns(2)
        with col_run:
            if st.button("执行计划"):
                with st.spinner("执行中..."):
                    exec_res = orch.execute(plan_result.plan, plan_result.trace_id, confirmed=confirmed)
                    st.session_state["exec_result"] = exec_res
        with col_dry:
            if st.button("仅 Dry-run"):
                with st.spinner("Dry-run..."):
                    exec_res = orch.execute(plan_result.plan, plan_result.trace_id, confirmed=False)
                    st.session_state["exec_result"] = exec_res

    exec_result = st.session_state.get("exec_result")
    if exec_result:
        st.subheader("执行结果")
        st.json(exec_result)
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

    st.subheader("文件预览")
    preview_path = st.session_state.get("preview_file", "")
    file_path = st.text_input("输入文件路径进行只读预览", value=preview_path)
    auto_preview = st.checkbox("自动预览（点击目录树文件后自动显示）", value=True)
    if file_path:
        st.session_state["preview_file"] = file_path
    if file_path and auto_preview:
        content = orch.mcp.call_tool("file_read", {"path": file_path})
        if not content.get("ok", True):
            st.error(content.get("error", "读取失败"))
        else:
            st.code(content.get("content", ""), language="text")
    elif st.button("预览文件") and file_path:
        content = orch.mcp.call_tool("file_read", {"path": file_path})
        if not content.get("ok", True):
            st.error(content.get("error", "读取失败"))
        else:
            st.code(content.get("content", ""), language="text")

    st.subheader("索引与建议")
    col_a, col_b = st.columns(2)
    with col_a:
        dry = st.checkbox("索引 Dry-run", value=False)
        if st.button("构建索引"):
            res = orch.mcp.call_tool(
                "index_build",
                {"include_globs": ["**/*"], "exclude_globs": [], "dry_run": dry},
            )
            st.json(res)
        if st.button("查看索引状态"):
            res = orch.mcp.call_tool("index_status", {})
            st.json(res)
    with col_b:
        if st.button("仓库概览"):
            res = orch.mcp.call_tool("repo_summarize", {})
            st.json(res)
        if st.button("整理建议"):
            res = orch.mcp.call_tool("organize_suggestions", {})
            st.json(res)


if __name__ == "__main__":
    main()
