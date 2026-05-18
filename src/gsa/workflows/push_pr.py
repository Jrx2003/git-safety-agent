from __future__ import annotations

from gsa.github.gh import GhProvider
from gsa.workflows.git_state import GitState, PROTECTED_BRANCHES
from gsa.workflows.schema import CommandPreview, RiskItem, WorkflowExecutionResult, WorkflowPlan
from gsa.workflows.trace_store import load_latest_plan, new_trace_id, save_plan, save_result
from gsa.workflows.utils import command_git, short_error


WORKFLOW_TYPE = "push_pr"


def plan_push_pr(
    workspace: str,
    title: str | None = None,
    body: str | None = None,
    draft: bool = True,
    trace_id: str | None = None,
) -> WorkflowPlan:
    trace_id = trace_id or new_trace_id()
    git = GitState(workspace)
    gh = GhProvider(workspace)
    risks: list[RiskItem] = []

    if not git.is_repo():
        plan = WorkflowPlan(
            trace_id=trace_id,
            workflow_type=WORKFLOW_TYPE,
            status="blocked",
            summary="当前 workspace 不是 git 仓库。",
            risks=[RiskItem(level="high", message="当前 workspace 不是 git 仓库。", blocking=True, recommended_action="在仓库目录启动 GSA。")],
            data={},
        )
        save_plan(workspace, plan)
        return plan

    branch = git.current_branch()
    if branch in PROTECTED_BRANCHES:
        risks.append(
            RiskItem(
                level="high",
                message=f"保护分支禁止直接 push/开 PR：{branch}",
                blocking=True,
                recommended_action="先从 issue 或功能分支开始工作。",
            )
        )
    if git.has_dirty():
        risks.append(
            RiskItem(
                level="high",
                message="存在未提交改动，默认阻止 push 和 PR。",
                blocking=True,
                recommended_action="先提交或清理工作区。",
            )
        )
    auth = gh.auth_status()
    if not auth["available"]:
        risks.append(RiskItem(level="high", message="未找到 gh CLI。", blocking=True, recommended_action="安装 GitHub CLI。"))
    elif not auth["authenticated"]:
        risks.append(RiskItem(level="high", message="GitHub CLI 未登录。", blocking=True, recommended_action="运行 gh auth login。"))

    ahead_behind = git.ahead_behind()
    if ahead_behind.get("behind", 0):
        risks.append(
            RiskItem(
                level="high",
                message=f"本地分支落后 upstream {ahead_behind.get('behind')} 个提交。",
                blocking=True,
                recommended_action="先 pull/rebase 并重新生成计划。",
            )
        )

    existing_prs: list[dict[str, object]] = []
    existing_error = ""
    if auth["available"] and auth["authenticated"] and branch:
        existing_prs, existing_error = gh.existing_pr_for_branch(branch)
        if existing_prs:
            url = existing_prs[0].get("url", "")
            risks.append(
                RiskItem(
                    level="medium",
                    message=f"当前分支已有 PR：{url}",
                    blocking=True,
                    recommended_action="复用已有 PR，不重复创建。",
                )
            )
        elif existing_error:
            risks.append(
                RiskItem(
                    level="medium",
                    message=f"无法检测已有 PR：{short_error(existing_error)}",
                    blocking=True,
                    recommended_action="确认 gh repo 权限后重新生成计划。",
                )
            )

    pr_title = (title or "").strip() or f"Draft PR: {branch}"
    pr_body = (body or "").strip() or "Created by GSA after local safety checks."
    has_upstream = bool(ahead_behind.get("has_upstream"))
    push_args = ["push"] if has_upstream else ["push", "-u", "origin", branch]
    command_preview = [
        CommandPreview(command=command_git(push_args), description="推送当前分支到远端。"),
        CommandPreview(
            command="gh pr create --draft --title <title> --body <body>" if draft else "gh pr create --title <title> --body <body>",
            description="创建 Draft PR，不 merge，不 request review。",
        ),
    ]
    status = "blocked" if any(risk.blocking for risk in risks) else "ready"
    plan = WorkflowPlan(
        trace_id=trace_id,
        workflow_type=WORKFLOW_TYPE,
        status=status,
        summary="Push + Draft PR 计划已生成。" if status == "ready" else "Push + Draft PR 计划被阻止。",
        risks=risks,
        command_preview=command_preview if status == "ready" else [],
        requires_confirmation=status == "ready",
        data={
            "branch": branch,
            "ahead_behind": ahead_behind,
            "existing_prs": existing_prs,
            "title": pr_title,
            "body": pr_body,
            "draft": draft,
            "has_upstream": has_upstream,
            "status_signature": git.status_signature(),
        },
    )
    save_plan(workspace, plan)
    return plan


def execute_push_pr(
    workspace: str,
    trace_id: str,
    confirmed: bool,
    title: str | None = None,
    body: str | None = None,
    draft: bool = True,
) -> WorkflowExecutionResult:
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
            next_actions=["重新生成 Push & Draft PR 计划。"],
        )
        save_result(workspace, result)
        return result

    pr_title = (title or data.get("title") or "").strip()
    pr_body = (body or data.get("body") or "").strip()
    replan = plan_push_pr(workspace, title=pr_title, body=pr_body, draft=draft, trace_id=trace_id)
    if replan.status != "ready":
        result = WorkflowExecutionResult(
            trace_id=trace_id,
            ok=False,
            summary="执行前重新校验后被阻止。",
            errors=[risk.message for risk in replan.risks if risk.blocking],
            next_actions=["处理阻塞项后重新生成计划。"],
        )
        save_result(workspace, result)
        return result

    data = replan.data
    branch = str(data.get("branch") or "")
    push_res = git.push(branch=branch, set_upstream=not bool(data.get("has_upstream")))
    commands = [push_res.command]
    if not push_res.ok:
        result = WorkflowExecutionResult(
            trace_id=trace_id,
            ok=False,
            summary="git push 失败。",
            executed_commands=commands,
            errors=[short_error(push_res.stderr or push_res.stdout)],
            next_actions=["检查远端权限、网络和 upstream 状态后重新生成计划。"],
        )
        save_result(workspace, result)
        return result

    gh = GhProvider(workspace)
    url, error, command = gh.pr_create(pr_title, pr_body, draft=draft)
    commands.append(command)
    if error:
        result = WorkflowExecutionResult(
            trace_id=trace_id,
            ok=False,
            summary="创建 Draft PR 失败。",
            executed_commands=commands,
            errors=[short_error(error)],
            next_actions=["确认 gh 登录状态和仓库权限后重新生成计划。"],
        )
        save_result(workspace, result)
        return result

    result = WorkflowExecutionResult(
        trace_id=trace_id,
        ok=True,
        summary="Draft PR 已创建。",
        executed_commands=commands,
        github_urls=[url] if url else [],
        data={"pr_url": url, "title": pr_title, "draft": draft},
        next_actions=["运行 PR Readiness 检查。"],
    )
    save_result(workspace, result)
    return result
