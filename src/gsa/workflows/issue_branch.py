from __future__ import annotations

from gsa.github.gh import GhProvider
from gsa.workflows.git_state import GitState
from gsa.workflows.schema import CommandPreview, RiskItem, WorkflowExecutionResult, WorkflowPlan, blocked_plan
from gsa.workflows.trace_store import load_latest_plan, new_trace_id, save_plan, save_result
from gsa.workflows.utils import command_git, issue_branch_name, short_error


WORKFLOW_TYPE = "issue_branch"


def plan_issue_branch(workspace: str, issue: str, trace_id: str | None = None) -> WorkflowPlan:
    trace_id = trace_id or new_trace_id()
    git = GitState(workspace)
    gh = GhProvider(workspace)
    risks: list[RiskItem] = []

    if not git.is_repo():
        plan = blocked_plan(trace_id, WORKFLOW_TYPE, "当前 workspace 不是 git 仓库。", next_action="在仓库目录启动 GSA。")
        save_plan(workspace, plan)
        return plan
    if git.has_dirty():
        risks.append(
            RiskItem(
                level="high",
                message="当前工作区有未提交改动，默认不创建 issue 分支。",
                blocking=True,
                recommended_action="先提交、stash 或清理改动。",
            )
        )
    auth = gh.auth_status()
    if not auth["available"]:
        risks.append(RiskItem(level="high", message="未找到 gh CLI。", blocking=True, recommended_action="安装 GitHub CLI。"))
    elif not auth["authenticated"]:
        risks.append(
            RiskItem(level="high", message="GitHub CLI 未登录。", blocking=True, recommended_action="运行 gh auth login。")
        )

    issue_data = None
    issue_error = ""
    if not risks:
        issue_data, issue_error = gh.issue_view(issue)
        if not issue_data:
            risks.append(
                RiskItem(
                    level="high",
                    message=f"无法读取 issue：{short_error(issue_error)}",
                    blocking=True,
                    recommended_action="确认 issue 编号/URL 和 gh 登录状态。",
                )
            )

    branch = issue_branch_name(issue_data or {"number": issue, "title": "work"})
    if git.branch_exists(branch):
        risks.append(
            RiskItem(
                level="high",
                message=f"本地分支已存在：{branch}",
                blocking=True,
                recommended_action="切换并复用已有分支，或修改分支名后重新生成计划。",
            )
        )

    status = "blocked" if any(risk.blocking for risk in risks) else "ready"
    base = git.default_branch()
    plan = WorkflowPlan(
        trace_id=trace_id,
        workflow_type=WORKFLOW_TYPE,
        status=status,
        summary="Issue 分支计划已生成。" if status == "ready" else "Issue 分支计划被阻止。",
        risks=risks,
        command_preview=[
            CommandPreview(
                command=command_git(["switch", "-c", branch, base]),
                description="基于默认分支创建本地 issue 分支。",
            )
        ]
        if status == "ready"
        else [],
        requires_confirmation=status == "ready",
        data={
            "issue": issue_data,
            "issue_input": issue,
            "branch": branch,
            "base": base,
            "status_signature": git.status_signature(),
        },
    )
    save_plan(workspace, plan)
    return plan


def execute_issue_branch(workspace: str, trace_id: str, confirmed: bool) -> WorkflowExecutionResult:
    if not confirmed:
        result = WorkflowExecutionResult(
            trace_id=trace_id,
            ok=False,
            summary="执行被拒绝：需要 confirmed=true。",
            errors=["写操作必须由用户确认。"],
            next_actions=["确认计划后重新执行。"],
        )
        save_result(workspace, result)
        return result
    previous = load_latest_plan(workspace, trace_id)
    if not previous:
        result = WorkflowExecutionResult(trace_id=trace_id, ok=False, summary="未找到对应 plan，请重新生成。", errors=["缺少 plan trace。"])
        save_result(workspace, result)
        return result
    data = previous.get("data") or {}
    git = GitState(workspace)
    if git.status_signature() != data.get("status_signature"):
        result = WorkflowExecutionResult(
            trace_id=trace_id,
            ok=False,
            summary="执行前校验失败：git 状态已变化。",
            errors=["当前 branch、HEAD 或工作区状态与 plan 时不一致。"],
            next_actions=["重新生成 Issue Branch 计划。"],
        )
        save_result(workspace, result)
        return result
    branch = str(data.get("branch") or "")
    base = str(data.get("base") or "HEAD")
    if git.has_dirty() or git.branch_exists(branch):
        result = WorkflowExecutionResult(
            trace_id=trace_id,
            ok=False,
            summary="执行前重新校验后被阻止。",
            errors=["工作区变脏或目标分支已存在。"],
            next_actions=["清理工作区或重新生成计划。"],
        )
        save_result(workspace, result)
        return result
    res = git.switch_create(branch, base)
    if not res.ok:
        result = WorkflowExecutionResult(
            trace_id=trace_id,
            ok=False,
            summary="创建分支失败。",
            executed_commands=[res.command],
            errors=[short_error(res.stderr or res.stdout)],
            next_actions=["检查 base 分支是否存在后重新生成计划。"],
        )
        save_result(workspace, result)
        return result
    result = WorkflowExecutionResult(
        trace_id=trace_id,
        ok=True,
        summary=f"已创建并切换到分支：{branch}",
        executed_commands=[res.command],
        data={"branch": branch, "base": base},
        next_actions=["在该分支完成修改后生成 Safe Commit 计划。"],
    )
    save_result(workspace, result)
    return result
