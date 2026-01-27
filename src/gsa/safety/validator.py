from __future__ import annotations

from typing import Iterable, List, Set

from gsa.agent.schema import Plan
from gsa.safety.policy import limit_write_steps


WRITE_TOOLS = {
    "git_init",
    "git_add",
    "git_commit",
    "git_switch",
    "git_create_branch",
    "git_delete_branch",
    "git_stash_push",
    "git_stash_pop",
    "git_merge",
    "file_write",
    "file_patch",
}


class PlanValidationError(ValueError):
    pass


def validate_plan(plan: Plan, registered_tools: Iterable[str]) -> List[str]:
    errors: List[str] = []
    tools: Set[str] = set(registered_tools)

    if not plan.steps and not plan.questions:
        errors.append("steps 为空时必须提供 questions")

    for step in plan.steps:
        if step.tool not in tools:
            errors.append(f"未注册工具：{step.tool}")

    write_steps = [s for s in plan.steps if s.tool in WRITE_TOOLS]
    if write_steps:
        try:
            limit_write_steps(len(write_steps))
        except Exception as exc:
            errors.append(str(exc))
        if not plan.needs_confirmation:
            errors.append("存在写操作但 needs_confirmation=false")
        for s in write_steps:
            if s.safety_level not in {"medium", "high"}:
                errors.append(f"写操作风险等级必须为 medium/high：{s.tool}")
            if not s.safety_reason:
                errors.append(f"写操作缺少安全原因：{s.tool}")

    return errors
