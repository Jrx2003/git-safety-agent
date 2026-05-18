from __future__ import annotations

import re
from typing import Any

from gsa.safety.policy import is_sensitive_path
from gsa.workflows.schema import RiskItem


def slugify(text: str, max_len: int = 48) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return (text[:max_len].strip("-") or "work")


def issue_branch_name(issue: dict[str, Any]) -> str:
    number = str(issue.get("number") or "issue")
    title = str(issue.get("title") or "work")
    labels = [str(label.get("name", "")).lower() for label in issue.get("labels") or [] if isinstance(label, dict)]
    prefix = "fix" if any(label in {"bug", "bugfix", "fix"} for label in labels) else "issue"
    return f"{prefix}/{number}-{slugify(title)}"


def default_commit_message(files: list[dict[str, Any]]) -> str:
    paths = [str(item.get("path", "")) for item in files if item.get("path")]
    if not paths:
        return ""
    if len(paths) == 1:
        return f"Update {paths[0]}"
    roots = sorted({path.split("/", 1)[0] for path in paths})
    if len(roots) == 1:
        return f"Update {roots[0]}"
    return f"Update {len(paths)} files"


def sensitive_file_risks(files: list[dict[str, Any]]) -> list[RiskItem]:
    risks: list[RiskItem] = []
    for item in files:
        path = str(item.get("path", ""))
        if is_sensitive_path(path):
            risks.append(
                RiskItem(
                    level="high",
                    message=f"敏感文件默认禁止进入工作流：{path}",
                    blocking=True,
                    recommended_action="移出提交范围，或用专门的 secret 管理方案处理。",
                )
            )
    return risks


def has_blocking_risk(risks: list[RiskItem]) -> bool:
    return any(risk.blocking for risk in risks)


def command_git(args: list[str]) -> str:
    from gsa.workflows.git_state import shell_join

    return shell_join(["git", *args])


def short_error(text: str, fallback: str = "操作失败") -> str:
    text = (text or "").strip()
    if not text:
        return fallback
    return text if len(text) <= 400 else text[:400] + "...<truncated>"
