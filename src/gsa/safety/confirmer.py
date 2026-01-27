from __future__ import annotations

from typing import Iterable

from gsa.agent.schema import Plan


def needs_confirmation(plan: Plan) -> bool:
    if plan.needs_confirmation:
        return True
    return False


def apply_confirmation(plan: Plan, confirmed: bool) -> None:
    if confirmed:
        for step in plan.steps:
            if step.safety_level in {"medium", "high"}:
                step.dry_run = False
