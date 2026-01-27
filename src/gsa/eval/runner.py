from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import yaml

from gsa.agent.orchestrator import Orchestrator


def load_cases(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def evaluate_case(orch: Orchestrator, case: Dict[str, Any]) -> Dict[str, Any]:
    result = {
        "name": case.get("name"),
        "input": case.get("input"),
        "passed": True,
        "errors": [],
    }
    plan_result = orch.plan(case.get("input", ""))
    plan = plan_result.plan
    if not plan:
        result["passed"] = False
        result["errors"].append("未生成计划")
        return result

    expect_tools = set(case.get("expect_tool_contains", []) or [])
    if expect_tools:
        actual = set(step.tool for step in plan.steps)
        if not expect_tools.issubset(actual):
            result["passed"] = False
            result["errors"].append(f"缺少工具：{expect_tools - actual}")

    expect_questions = case.get("expect_questions")
    if expect_questions is not None:
        if bool(plan.questions) != bool(expect_questions):
            result["passed"] = False
            result["errors"].append("questions 与预期不符")

    expect_confirm = case.get("expect_needs_confirmation")
    if expect_confirm is not None:
        if plan.needs_confirmation != bool(expect_confirm):
            result["passed"] = False
            result["errors"].append("needs_confirmation 与预期不符")

    return result


def main() -> None:
    workspace = os.getcwd()
    orch = Orchestrator(workspace, use_llm=False)
    cases = load_cases(os.path.join(os.path.dirname(__file__), "test_cases.yaml"))
    results = [evaluate_case(orch, c) for c in cases]
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print(json.dumps({"passed": passed, "total": total, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
