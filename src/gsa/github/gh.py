from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from gsa.security.redaction import redact_secrets
from gsa.workflows.git_state import shell_join


ISSUE_OR_PR_RE = re.compile(r"(?:issues|pull)/(\d+)|#?(\d+)")


@dataclass
class GhCommandResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    command: str = ""

    def json(self) -> Any:
        try:
            return json.loads(self.stdout or "{}")
        except Exception:
            return None


def parse_number(value: str) -> str:
    match = ISSUE_OR_PR_RE.search(value.strip())
    return next((group for group in match.groups() if group), value.strip()) if match else value.strip()


class GhProvider:
    def __init__(self, workspace: str):
        self.workspace = workspace

    def available(self) -> bool:
        return shutil.which("gh") is not None

    def run(self, args: list[str], timeout: int = 45) -> GhCommandResult:
        if not self.available():
            return GhCommandResult(False, stderr="未找到 gh CLI", returncode=127, command="gh " + shell_join(args))
        cmd = ["gh", *args]
        try:
            proc = subprocess.run(cmd, cwd=self.workspace, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return GhCommandResult(False, stderr="gh 命令超时", returncode=124, command=shell_join(cmd))
        return GhCommandResult(
            ok=proc.returncode == 0,
            stdout=redact_secrets(proc.stdout),
            stderr=redact_secrets(proc.stderr),
            returncode=proc.returncode,
            command=shell_join(cmd),
        )

    def auth_status(self) -> dict[str, Any]:
        if not self.available():
            return {"available": False, "authenticated": False, "message": "未找到 gh CLI"}
        res = self.run(["auth", "status"])
        text = (res.stdout + "\n" + res.stderr).strip()
        return {
            "available": True,
            "authenticated": res.ok,
            "message": redact_secrets(text),
        }

    def issue_view(self, issue: str) -> tuple[dict[str, Any] | None, str]:
        number = parse_number(issue)
        res = self.run(
            [
                "issue",
                "view",
                number,
                "--json",
                "number,title,body,labels,state,url",
            ]
        )
        if not res.ok:
            return None, redact_secrets(res.stderr or res.stdout or f"无法读取 issue {number}")
        data = res.json()
        return data if isinstance(data, dict) else None, ""

    def existing_pr_for_branch(self, branch: str) -> tuple[list[dict[str, Any]], str]:
        res = self.run(["pr", "list", "--head", branch, "--json", "number,title,url,state,isDraft"])
        if not res.ok:
            return [], redact_secrets(res.stderr or res.stdout)
        data = res.json()
        return data if isinstance(data, list) else [], ""

    def repo_info(self) -> tuple[dict[str, Any] | None, str]:
        res = self.run(["repo", "view", "--json", "owner,name"])
        if not res.ok:
            return None, redact_secrets(res.stderr or res.stdout)
        data = res.json()
        return data if isinstance(data, dict) else None, ""

    def pr_view(self, pr: str | None = None) -> tuple[dict[str, Any] | None, str]:
        args = [
            "pr",
            "view",
        ]
        if pr:
            args.append(parse_number(pr))
        args.extend(
            [
                "--json",
                "number,title,state,url,isDraft,mergeStateStatus,reviewDecision,headRefName,baseRefName,statusCheckRollup",
            ]
        )
        res = self.run(args)
        if not res.ok:
            return None, redact_secrets(res.stderr or res.stdout or "无法读取 PR")
        data = res.json()
        return data if isinstance(data, dict) else None, ""

    def pr_checks(self, pr: str | None = None) -> tuple[list[dict[str, Any]], str]:
        args = ["pr", "checks"]
        if pr:
            args.append(parse_number(pr))
        args.extend(["--json", "name,state,link,bucket,description,startedAt,completedAt"])
        res = self.run(args)
        if not res.ok:
            return [], redact_secrets(res.stderr or res.stdout)
        data = res.json()
        return data if isinstance(data, list) else [], ""

    def unresolved_review_threads(self, pr_number: str | int) -> tuple[int | None, str]:
        repo, repo_error = self.repo_info()
        if not repo:
            return None, repo_error or "无法读取 repo 信息"
        owner = (repo.get("owner") or {}).get("login") if isinstance(repo.get("owner"), dict) else ""
        name = repo.get("name") or ""
        if not owner or not name:
            return None, "repo 信息缺少 owner/name"
        query = """
        query($owner: String!, $name: String!, $number: Int!) {
          repository(owner: $owner, name: $name) {
            pullRequest(number: $number) {
              reviewThreads(first: 100) {
                nodes {
                  isResolved
                }
              }
            }
          }
        }
        """
        res = self.run(
            [
                "api",
                "graphql",
                "-f",
                f"query={query}",
                "-f",
                f"owner={owner}",
                "-f",
                f"name={name}",
                "-F",
                f"number={int(pr_number)}",
            ]
        )
        if not res.ok:
            return None, redact_secrets(res.stderr or res.stdout)
        data = res.json()
        try:
            nodes = data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
            return sum(1 for node in nodes if not node.get("isResolved")), ""
        except Exception:
            return None, "无法解析 unresolved review threads"

    def pr_create(self, title: str, body: str, draft: bool = True) -> tuple[str, str, str]:
        args = ["pr", "create", "--title", title, "--body", body]
        if draft:
            args.append("--draft")
        res = self.run(args, timeout=120)
        if not res.ok:
            return "", redact_secrets(res.stderr or res.stdout or "创建 PR 失败"), res.command
        url = (res.stdout or "").strip().splitlines()[-1] if res.stdout.strip() else ""
        return redact_secrets(url), "", res.command
