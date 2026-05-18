from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


WorkflowStatus = Literal["ready", "blocked", "needs_input"]
RiskLevel = Literal["low", "medium", "high"]


class RiskItem(BaseModel):
    level: RiskLevel = "low"
    message: str
    blocking: bool = False
    recommended_action: str = ""


class CommandPreview(BaseModel):
    command: str
    description: str = ""
    destructive: bool = False


class WorkflowPlan(BaseModel):
    trace_id: str
    workflow_type: str
    status: WorkflowStatus
    summary: str
    risks: list[RiskItem] = Field(default_factory=list)
    command_preview: list[CommandPreview] = Field(default_factory=list)
    requires_confirmation: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class WorkflowExecutionResult(BaseModel):
    trace_id: str
    ok: bool
    summary: str
    executed_commands: list[str] = Field(default_factory=list)
    github_urls: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


def blocked_plan(
    trace_id: str,
    workflow_type: str,
    summary: str,
    risks: list[RiskItem] | None = None,
    data: dict[str, Any] | None = None,
    next_action: str = "",
) -> WorkflowPlan:
    if risks is None:
        risks = [
            RiskItem(
                level="high",
                message=summary,
                blocking=True,
                recommended_action=next_action,
            )
        ]
    return WorkflowPlan(
        trace_id=trace_id,
        workflow_type=workflow_type,
        status="blocked",
        summary=summary,
        risks=risks,
        requires_confirmation=False,
        data=data or {},
    )
