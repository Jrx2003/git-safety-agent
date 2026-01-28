from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Dict, List, Optional

from gsa.agent.schema import Plan, PlanResult, Step
from gsa.llm.llm_client import LLMClient, LLMKeyMissing, load_config
from gsa.llm.prompts import PLANNER_SYSTEM_PROMPT
from gsa.safety.risk import assess_risk


class RulePlanner:
    """无 Key 时的规则规划器（仅用于 demo/测试）。"""

    def plan(self, user_input: str) -> Plan:
        text = user_input.strip()
        steps: List[Step] = []
        questions: List[str] = []
        assumptions: List[str] = []
        intent = "解析用户指令"
        needs_confirmation = False

        blocked = ["reset --hard", "clean -fd", "push --force", "push -f"]
        if any(b in text for b in blocked):
            questions.append("检测到危险指令（reset --hard/clean -fd/force push），已被策略禁止。请改用更安全方案。")
            return Plan(
                intent=intent,
                assumptions=assumptions,
                questions=questions,
                needs_confirmation=True,
                steps=[],
            )

        def add_step(tool: str, args: Dict[str, object], dry_run: bool = True) -> None:
            level, reason = assess_risk(tool, args)
            nonlocal needs_confirmation
            if level in {"medium", "high"}:
                needs_confirmation = True
            steps.append(
                Step(
                    tool=tool,
                    args=args,
                    safety_level=level,
                    safety_reason=reason,
                    dry_run=dry_run,
                )
            )

        # 只读类
        wants_log = bool(re.search(r"日志|log|历史|最近提交|提交历史|提交记录", text))
        if re.search(r"状态|status", text):
            add_step("git_status", {}, dry_run=True)
        if wants_log:
            add_step("git_log", {"n": 10}, dry_run=True)
        if re.search(r"差异|diff", text):
            add_step("git_diff", {"staged": False}, dry_run=True)
        if re.search(r"分支列表|分支", text) and "切换" not in text:
            add_step("git_branch_list", {}, dry_run=True)

        # 写操作
        if re.search(r"初始化仓库|创建仓库|建立仓库|初始化\\s*git|git\\s*repo|git\\s*init", text, re.IGNORECASE):
            add_step("git_init", {}, dry_run=True)

        commit_trigger = bool(re.search(r"(提交(代码|改动|修复|到仓库)?|commit)", text))
        commit_intent = commit_trigger and not wants_log and not re.search(r"提交历史|提交日志|提交记录|历史提交|最近提交", text)
        if commit_intent:
            msg_match = re.search(r"提交[:：]\s*(.+)", text)
            if not msg_match:
                questions.append("提交信息是什么？例如：提交: 修复登录按钮")
            else:
                add_step("git_commit", {"message": msg_match.group(1).strip()}, dry_run=True)

        if re.search(r"暂存|add", text):
            paths = ["."]
            if re.search(r"全部|所有", text):
                add_step("git_add", {"paths": paths, "allow_all": True}, dry_run=True)
            else:
                questions.append("要暂存哪些文件？请提供路径")

        if re.search(r"切换分支|checkout|switch", text):
            m = re.search(r"切换分支[:：]?\s*(\S+)", text)
            if not m:
                questions.append("要切换到哪个分支？")
            else:
                add_step("git_switch", {"branch": m.group(1).strip(), "create": False}, dry_run=True)

        if re.search(r"创建分支|新建分支", text):
            m = re.search(r"分支[:：]?\s*(\S+)", text)
            if not m:
                questions.append("新分支名称是什么？")
            else:
                add_step("git_create_branch", {"name": m.group(1).strip(), "from_ref": "HEAD"}, dry_run=True)

        if re.search(r"删除分支", text):
            m = re.search(r"删除分支[:：]?\s*(\S+)", text)
            if not m:
                questions.append("要删除哪个分支？")
            else:
                add_step("git_delete_branch", {"name": m.group(1).strip(), "force": False}, dry_run=True)

        if re.search(r"索引|搜索|总结|整理建议", text):
            add_step("index_status", {}, dry_run=True)
            if re.search(r"构建|建立", text):
                add_step("index_build", {"include_globs": ["**/*"], "exclude_globs": []}, dry_run=True)
            if re.search(r"搜索", text):
                add_step("index_search", {"query": "项目概览", "top_k": 5}, dry_run=True)
            if re.search(r"总结|概览", text):
                add_step("repo_summarize", {}, dry_run=True)
            if re.search(r"整理建议", text):
                add_step("organize_suggestions", {}, dry_run=True)

        if not steps and not questions:
            questions.append("请说明想执行的 Git 或文件操作，以及是否需要试运行。")

        return Plan(
            intent=intent,
            assumptions=assumptions,
            questions=questions,
            needs_confirmation=needs_confirmation,
            steps=steps,
        )


class Planner:
    """LLM + 规则混合规划器。"""

    def __init__(self, workspace: Optional[str] = None):
        self.workspace = workspace
        self.rule_planner = RulePlanner()
        self._config = load_config(workspace)
        self._model_override: Optional[str] = None

    def set_model(self, model: Optional[str]) -> None:
        self._model_override = model

    def _get_llm_client(self) -> LLMClient:
        cfg = self._config
        if self._model_override:
            cfg = replace(self._config, model=self._model_override)
        return LLMClient(cfg)

    def plan(self, user_input: str, use_llm: bool = True) -> PlanResult:
        if not use_llm:
            return PlanResult(plan=self.rule_planner.plan(user_input))

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]
        try:
            client = self._get_llm_client()
            text = client.chat_text(messages, temperature=0.2, max_tokens=2048)
        except LLMKeyMissing as exc:
            plan = self.rule_planner.plan(user_input)
            if plan.steps and all(s.safety_level == "low" for s in plan.steps):
                plan.questions = []
            return PlanResult(errors=[str(exc)], plan=plan)
        except Exception as exc:
            msg = str(exc)
            name = exc.__class__.__name__
            if name in {"APITimeoutError", "TimeoutError"} or "timed out" in msg or "timeout" in msg or "超时" in msg:
                plan = self.rule_planner.plan(user_input)
                if plan.steps and all(s.safety_level == "low" for s in plan.steps):
                    plan.questions = []
                return PlanResult(errors=[f"LLM 调用超时：{exc}"], plan=plan)
            return PlanResult(errors=[f"LLM 调用失败：{exc}"], plan=None)

        try:
            data = json.loads(text)
            plan = Plan.model_validate(data)
            return PlanResult(plan=plan)
        except Exception as exc:
            return PlanResult(errors=[f"规划结果解析失败：{exc}"], plan=self.rule_planner.plan(user_input))
