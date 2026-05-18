from __future__ import annotations

from typing import Any

from gsa.security.redaction import redact_secrets
from gsa.safety.policy import is_sensitive_path
from gsa.workflows.git_state import GitState
from gsa.workflows.schema import CommandPreview, RiskItem, WorkflowExecutionResult, WorkflowPlan, blocked_plan
from gsa.workflows.trace_store import load_latest_plan, new_trace_id, save_plan, save_result
from gsa.workflows.utils import command_git, default_commit_message, has_blocking_risk, sensitive_file_risks, short_error


WORKFLOW_TYPE = "safe_commit"


def plan_safe_commit(
    workspace: str,
    selected_paths: list[str] | None = None,
    message: str | None = None,
    trace_id: str | None = None,
) -> WorkflowPlan:
    trace_id = trace_id or new_trace_id()
    git = GitState(workspace)
    if not git.is_repo():
        plan = blocked_plan(trace_id, WORKFLOW_TYPE, "当前 workspace 不是 git 仓库。", next_action="在仓库目录启动 GSA，或先运行 git init。")
        save_plan(workspace, plan)
        return plan

    files = git.changed_files()
    if selected_paths:
        wanted = set(selected_paths)
        files_for_plan = [item for item in files if item.get("path") in wanted]
    else:
        files_for_plan = files

    if not files:
        plan = WorkflowPlan(
            trace_id=trace_id,
            workflow_type=WORKFLOW_TYPE,
            status="blocked",
            summary="工作区干净，没有可提交改动。",
            risks=[
                RiskItem(
                    level="low",
                    message="没有检测到 staged 或 unstaged 文件。",
                    blocking=True,
                    recommended_action="先完成本地修改，再重新生成提交计划。",
                )
            ],
            data={"branch": git.current_branch(), "files": [], "status_signature": git.status_signature()},
        )
        save_plan(workspace, plan)
        return plan

    selected = selected_paths or [str(item["path"]) for item in files_for_plan if not is_sensitive_path(str(item["path"]))]
    risks = sensitive_file_risks(files_for_plan)
    if not selected:
        risks.append(
            RiskItem(
                level="high",
                message="没有可安全提交的文件。",
                blocking=True,
                recommended_action="移除敏感文件或明确修改提交范围。",
            )
        )
    commit_message = (message or "").strip() or default_commit_message(files_for_plan)
    if not commit_message:
        risks.append(
            RiskItem(
                level="medium",
                message="缺少 commit message。",
                blocking=True,
                recommended_action="填写明确的提交信息。",
            )
        )

    staged = [item for item in files if item.get("staged")]
    unstaged = [item for item in files if item.get("unstaged")]
    status = "blocked" if has_blocking_risk(risks) else "ready"
    command_preview = []
    if selected:
        command_preview.append(
            CommandPreview(
                command=command_git(["add", "--", *selected]),
                description="只暂存用户选择且通过敏感文件检查的文件。",
                destructive=False,
            )
        )
    if commit_message:
        command_preview.append(
            CommandPreview(
                command=command_git(["commit", "-m", commit_message]),
                description="创建本地 commit，不 push。",
                destructive=False,
            )
        )

    diff_paths = selected or [str(item.get("path", "")) for item in files_for_plan]
    plan = WorkflowPlan(
        trace_id=trace_id,
        workflow_type=WORKFLOW_TYPE,
        status=status,
        summary="提交计划已生成，执行前会重新校验工作区状态。" if status == "ready" else "提交计划被阻止，请先处理风险。",
        risks=risks,
        command_preview=command_preview,
        requires_confirmation=status == "ready",
        data=redact_secrets(
            {
                "branch": git.current_branch(),
                "files": files,
                "staged_files": staged,
                "unstaged_files": unstaged,
                "selected_paths": selected,
                "message": commit_message,
                "diff_summary": git.diff(staged=False, paths=diff_paths),
                "staged_diff_summary": git.diff(staged=True, paths=diff_paths),
                "status_signature": git.status_signature(),
            }
        ),
    )
    save_plan(workspace, plan)
    return plan


def execute_safe_commit(
    workspace: str,
    trace_id: str,
    confirmed: bool,
    selected_paths: list[str] | None = None,
    message: str | None = None,
) -> WorkflowExecutionResult:
    if not confirmed:
        result = WorkflowExecutionResult(
            trace_id=trace_id,
            ok=False,
            summary="执行被拒绝：需要 confirmed=true。",
            errors=["写操作必须由用户确认。"],
            next_actions=["勾选确认框后重新执行。"],
        )
        save_result(workspace, result)
        return result

    previous = load_latest_plan(workspace, trace_id)
    if not previous:
        result = WorkflowExecutionResult(
            trace_id=trace_id,
            ok=False,
            summary="未找到对应 plan，请重新生成。",
            errors=["缺少 plan trace。"],
            next_actions=["重新生成 Safe Commit 计划。"],
        )
        save_result(workspace, result)
        return result

    data: dict[str, Any] = previous.get("data") or {}
    selected = selected_paths or data.get("selected_paths") or []
    commit_message = (message or data.get("message") or "").strip()
    git = GitState(workspace)
    current_signature = git.status_signature()
    if current_signature != data.get("status_signature"):
        result = WorkflowExecutionResult(
            trace_id=trace_id,
            ok=False,
            summary="执行前校验失败：工作区状态已变化。",
            errors=["当前 branch、HEAD 或文件状态与 plan 时不一致。"],
            next_actions=["重新生成提交计划后再执行。"],
        )
        save_result(workspace, result)
        return result

    replan = plan_safe_commit(workspace, selected_paths=list(selected), message=commit_message, trace_id=trace_id)
    if replan.status != "ready":
        result = WorkflowExecutionResult(
            trace_id=trace_id,
            ok=False,
            summary="执行前重新校验后仍被阻止。",
            errors=[risk.message for risk in replan.risks if risk.blocking],
            next_actions=["处理风险后重新生成计划。"],
        )
        save_result(workspace, result)
        return result

    add_res = git.add(list(selected))
    commands = [add_res.command]
    if not add_res.ok:
        result = WorkflowExecutionResult(
            trace_id=trace_id,
            ok=False,
            summary="git add 失败。",
            executed_commands=commands,
            errors=[short_error(add_res.stderr or add_res.stdout)],
            next_actions=["检查文件路径和 git 状态后重新生成计划。"],
        )
        save_result(workspace, result)
        return result

    commit_res = git.commit(commit_message)
    commands.append(commit_res.command)
    if not commit_res.ok:
        result = WorkflowExecutionResult(
            trace_id=trace_id,
            ok=False,
            summary="git commit 失败。",
            executed_commands=commands,
            errors=[short_error(commit_res.stderr or commit_res.stdout)],
            next_actions=["检查暂存区和 commit message 后重新生成计划。"],
        )
        save_result(workspace, result)
        return result

    commit_hash = git.head()
    result = WorkflowExecutionResult(
        trace_id=trace_id,
        ok=True,
        summary=f"提交成功：{commit_hash}",
        executed_commands=commands,
        data={"commit_hash": commit_hash, "message": commit_message},
        next_actions=["可继续生成 Push & Draft PR 计划。"],
    )
    save_result(workspace, result)
    return result
