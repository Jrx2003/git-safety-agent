from __future__ import annotations

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


SafetyLevel = Literal["low", "medium", "high"]


class Step(BaseModel):
    """单步执行计划。"""

    tool: str = Field(..., description="MCP 工具名")
    args: Dict[str, object] = Field(default_factory=dict, description="结构化参数")
    safety_level: SafetyLevel = Field(..., description="风险等级")
    safety_reason: str = Field(..., description="风险原因")
    dry_run: bool = Field(default=True, description="是否为试运行")


class Plan(BaseModel):
    """完整执行计划。"""

    intent: str = Field(..., description="用户意图")
    assumptions: List[str] = Field(default_factory=list, description="假设")
    questions: List[str] = Field(default_factory=list, description="澄清问题")
    needs_confirmation: bool = Field(default=False, description="是否需要二次确认")
    steps: List[Step] = Field(default_factory=list, description="步骤列表")


class PlanResult(BaseModel):
    """计划生成与校验结果。"""

    plan: Optional[Plan] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    trace_id: str = ""
