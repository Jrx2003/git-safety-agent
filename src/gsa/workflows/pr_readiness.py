from __future__ import annotations

from gsa.github.gh import GhProvider
from gsa.workflows.git_state import GitState
from gsa.workflows.schema import RiskItem, WorkflowPlan
from gsa.workflows.trace_store import new_trace_id, save_plan
from gsa.workflows.utils import short_error


WORKFLOW_TYPE = "pr_readiness"


def plan_pr_readiness(workspace: str, pr: str | None = None, trace_id: str | None = None) -> WorkflowPlan:
    trace_id = trace_id or new_trace_id()
    git = GitState(workspace)
    gh = GhProvider(workspace)
    risks: list[RiskItem] = []
    data: dict[str, object] = {}

    if not git.is_repo():
        risks.append(RiskItem(level="high", message="当前 workspace 不是 git 仓库。", blocking=True, recommended_action="在仓库目录启动 GSA。"))
    auth = gh.auth_status()
    if not auth["available"]:
        risks.append(RiskItem(level="high", message="未找到 gh CLI。", blocking=True, recommended_action="安装 GitHub CLI。"))
    elif not auth["authenticated"]:
        risks.append(RiskItem(level="high", message="GitHub CLI 未登录。", blocking=True, recommended_action="运行 gh auth login。"))

    pr_data = None
    checks: list[dict[str, object]] = []
    unresolved_threads: int | None = None
    if not risks:
        pr_data, pr_error = gh.pr_view(pr)
        if not pr_data:
            risks.append(
                RiskItem(
                    level="high",
                    message=f"无法读取 PR：{short_error(pr_error)}",
                    blocking=True,
                    recommended_action="确认 PR 编号/URL，或当前分支已有 PR。",
                )
            )
        else:
            checks, checks_error = gh.pr_checks(pr)
            if checks_error:
                risks.append(
                    RiskItem(
                        level="medium",
                        message=f"无法读取 PR checks：{short_error(checks_error)}",
                        blocking=False,
                        recommended_action="可在 GitHub 页面确认 CI 状态。",
                    )
                )
            unresolved_threads, threads_error = gh.unresolved_review_threads(pr_data.get("number", ""))
            if unresolved_threads is None and threads_error:
                risks.append(
                    RiskItem(
                        level="medium",
                        message=f"无法读取 unresolved review threads：{short_error(threads_error)}",
                        blocking=False,
                        recommended_action="可在 GitHub 页面确认 review thread 状态。",
                    )
                )

    failed_checks = [item for item in checks if str(item.get("state", "")).upper() in {"FAILURE", "FAILED", "ERROR", "CANCELLED"}]
    pending_checks = [item for item in checks if str(item.get("state", "")).upper() in {"PENDING", "QUEUED", "IN_PROGRESS", "WAITING"}]
    if failed_checks:
        risks.append(
            RiskItem(
                level="high",
                message=f"{len(failed_checks)} 个 CI/check 失败。",
                blocking=True,
                recommended_action="先修复失败检查，再重新评估。",
            )
        )
    review_decision = str((pr_data or {}).get("reviewDecision") or "")
    if review_decision == "CHANGES_REQUESTED":
        risks.append(
            RiskItem(
                level="medium",
                message="PR review 状态为 Changes requested。",
                blocking=False,
                recommended_action="处理 review comments 后重新评估。",
            )
        )
    if unresolved_threads:
        risks.append(
            RiskItem(
                level="medium",
                message=f"存在 {unresolved_threads} 个 unresolved review threads。",
                blocking=False,
                recommended_action="解决或回复 review threads 后重新评估。",
            )
        )
    if pending_checks:
        risks.append(
            RiskItem(
                level="medium",
                message=f"{len(pending_checks)} 个 CI/check 仍在运行。",
                blocking=False,
                recommended_action="等待检查完成后重新评估。",
            )
        )
    if git.is_repo():
        ahead_behind = git.ahead_behind()
        data["ahead_behind"] = ahead_behind
        if ahead_behind.get("ahead", 0):
            risks.append(
                RiskItem(
                    level="medium",
                    message=f"本地还有 {ahead_behind.get('ahead')} 个未推送提交。",
                    blocking=False,
                    recommended_action="先 push 当前分支。",
                )
            )
        if git.has_dirty():
            risks.append(
                RiskItem(
                    level="medium",
                    message="本地工作区有未提交改动。",
                    blocking=False,
                    recommended_action="提交或清理后重新评估。",
                )
            )

    if any(risk.blocking for risk in risks):
        status = "blocked"
        summary = "Blocked：存在必须先处理的阻塞项。"
    elif risks:
        status = "needs_input"
        summary = "Needs action：PR 没有硬阻塞，但仍有后续动作。"
    else:
        status = "ready"
        summary = "Ready：未发现 CI、review 或本地状态阻塞项。"

    data.update(
        {
            "pr": pr_data,
            "checks": checks,
            "failed_checks": failed_checks,
            "pending_checks": pending_checks,
            "unresolved_review_threads": unresolved_threads,
            "next_actions": [risk.recommended_action for risk in risks if risk.recommended_action],
        }
    )
    plan = WorkflowPlan(
        trace_id=trace_id,
        workflow_type=WORKFLOW_TYPE,
        status=status,
        summary=summary,
        risks=risks,
        requires_confirmation=False,
        data=data,
    )
    save_plan(workspace, plan)
    return plan
