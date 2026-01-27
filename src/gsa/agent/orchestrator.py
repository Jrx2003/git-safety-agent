from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from gsa.agent.memory import MemoryStore
from gsa.agent.planner import Planner
from gsa.agent.schema import Plan, PlanResult
from gsa.mcp.client import MCPClient
from gsa.observability.logger import EventLogger
from gsa.observability.report import write_run_report
from gsa.observability.trace import new_trace_id
from gsa.safety.confirmer import apply_confirmation
from gsa.safety.validator import validate_plan


class Orchestrator:
    """核心编排器：规划 -> 校验 -> 执行 -> 总结。"""

    def __init__(self, workspace: str, use_llm: bool = True):
        self.workspace = workspace
        self.use_llm = use_llm
        self.memory = MemoryStore(workspace)
        self.planner = Planner(workspace)
        self.mcp = MCPClient(workspace)

    def plan(self, user_input: str) -> PlanResult:
        trace_id = new_trace_id()
        logger = EventLogger(self.workspace, trace_id)
        logger.log("RUN_START", {"workspace": self.workspace})
        logger.log("USER_INPUT", {"text": user_input})
        logger.log("MEMORY_LOADED", {"persistent": self.memory.persist.__dict__})

        plan_result = self.planner.plan(user_input, use_llm=self.use_llm)
        plan_result.trace_id = trace_id
        if plan_result.plan:
            # 更新会话记忆
            self.memory.session.last_plan = plan_result.plan.model_dump()
            for step in plan_result.plan.steps:
                if step.tool in {"git_switch", "git_create_branch", "git_delete_branch"}:
                    branch = step.args.get("branch") or step.args.get("name")
                    if isinstance(branch, str):
                        self.memory.session.recent_branch = branch
            errors = validate_plan(plan_result.plan, self.mcp.list_tools())
            plan_result.errors.extend(errors)
            logger.log("PLAN_GENERATED", plan_result.plan.model_dump())
            logger.log("PLAN_VALIDATED", {"errors": errors})
        else:
            logger.log("PLAN_GENERATED", {"error": plan_result.errors})
        return plan_result

    def execute(self, plan: Plan, trace_id: str, confirmed: bool = False) -> Dict[str, Any]:
        logger = EventLogger(self.workspace, trace_id)
        results: List[Dict[str, Any]] = []
        apply_confirmation(plan, confirmed)

        for step in plan.steps:
            payload = {"tool": step.tool, "args": step.args, "dry_run": step.dry_run}
            if step.dry_run:
                logger.log("STEP_DRYRUN", payload)
            else:
                logger.log("USER_CONFIRM", {"confirmed": True, "tool": step.tool})
            try:
                resp = self.mcp.call_tool(step.tool, step.args | {"dry_run": step.dry_run})
                results.append({"tool": step.tool, "ok": True, "result": resp})
                logger.log("STEP_EXECUTED", {"tool": step.tool, "result": resp})
                if step.tool in {"file_write", "file_patch", "file_read"}:
                    path = step.args.get("path")
                    if isinstance(path, str):
                        self.memory.session.recent_files.append(path)
            except Exception as exc:
                results.append({"tool": step.tool, "ok": False, "error": str(exc)})
                logger.log("STEP_REJECTED", {"tool": step.tool, "error": str(exc)})
                break

        summary = self._summarize_results(results)
        write_run_report(self.workspace, trace_id, summary, results)
        self.memory.record_op(summary)
        logger.log("RUN_SUMMARY", {"summary": summary})
        return {
            "trace_id": trace_id,
            "summary": summary,
            "results": results,
        }

    def _summarize_results(self, results: List[Dict[str, Any]]) -> str:
        if not results:
            return "未执行任何步骤。"
        ok = sum(1 for r in results if r.get("ok"))
        return f"共执行 {len(results)} 步，成功 {ok} 步。"
