from gsa.agent.schema import Plan, Step
from gsa.safety.validator import validate_plan


def test_write_requires_confirmation():
    plan = Plan(
        intent="test",
        assumptions=[],
        questions=[],
        needs_confirmation=False,
        steps=[
            Step(
                tool="git_commit",
                args={"message": "x"},
                safety_level="medium",
                safety_reason="提交",
                dry_run=True,
            )
        ],
    )
    errors = validate_plan(plan, ["git_commit"])
    assert any("needs_confirmation" in e for e in errors)
