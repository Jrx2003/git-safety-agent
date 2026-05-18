from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Iterable

from gsa.security.redaction import redact_secrets


PROTECTED_BRANCHES = {"main", "master", "develop"}


@dataclass
class GitCommandResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    command: str = ""


def shell_join(parts: Iterable[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


class GitState:
    def __init__(self, workspace: str):
        self.workspace = os.path.abspath(workspace)

    def run(self, args: list[str], timeout: int = 30) -> GitCommandResult:
        cmd = ["git", "-C", self.workspace] + args
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            return GitCommandResult(False, stderr="未找到 git 命令", returncode=127, command=shell_join(cmd))
        except subprocess.TimeoutExpired:
            return GitCommandResult(False, stderr="git 命令超时", returncode=124, command=shell_join(cmd))
        return GitCommandResult(
            ok=proc.returncode == 0,
            stdout=redact_secrets(proc.stdout),
            stderr=redact_secrets(proc.stderr),
            returncode=proc.returncode,
            command=shell_join(cmd),
        )

    def is_repo(self) -> bool:
        return self.run(["rev-parse", "--is-inside-work-tree"]).stdout.strip() == "true"

    def repo_root(self) -> str:
        res = self.run(["rev-parse", "--show-toplevel"])
        return res.stdout.strip() if res.ok else self.workspace

    def current_branch(self) -> str:
        res = self.run(["branch", "--show-current"])
        if res.ok and res.stdout.strip():
            return res.stdout.strip()
        detached = self.run(["rev-parse", "--short", "HEAD"])
        return f"detached@{detached.stdout.strip()}" if detached.ok else ""

    def status_porcelain(self) -> list[str]:
        res = self.run(["status", "--porcelain=v1", "-uall", "--", ".", ":!.gsa"])
        if not res.ok:
            return []
        return [line for line in res.stdout.splitlines() if line.strip()]

    def status_signature(self) -> dict[str, object]:
        return {
            "branch": self.current_branch(),
            "status": self.status_porcelain(),
            "head": self.head(),
        }

    def changed_files(self) -> list[dict[str, object]]:
        files: list[dict[str, object]] = []
        for line in self.status_porcelain():
            if len(line) < 4:
                continue
            index_status = line[0]
            worktree_status = line[1]
            raw_path = line[3:]
            path = raw_path.split(" -> ", 1)[-1]
            files.append(
                {
                    "path": path,
                    "raw": line,
                    "staged": index_status != " " and index_status != "?",
                    "unstaged": worktree_status != " " or index_status == "?",
                    "index_status": index_status,
                    "worktree_status": worktree_status,
                }
            )
        return files

    def has_dirty(self) -> bool:
        return bool(self.status_porcelain())

    def diff(self, staged: bool = False, paths: list[str] | None = None, max_chars: int = 12000) -> str:
        args = ["diff", "--stat"]
        if staged:
            args.insert(1, "--staged")
        if paths:
            args.extend(["--", *paths])
        stat = self.run(args).stdout.strip()

        detail_args = ["diff"]
        if staged:
            detail_args.append("--staged")
        if paths:
            detail_args.extend(["--", *paths])
        detail = self.run(detail_args).stdout
        merged = (stat + "\n\n" + detail).strip()
        if len(merged) > max_chars:
            merged = merged[:max_chars] + "\n...<diff truncated>"
        return redact_secrets(merged)

    def head(self) -> str:
        res = self.run(["rev-parse", "--short", "HEAD"])
        return res.stdout.strip() if res.ok else ""

    def full_head(self) -> str:
        res = self.run(["rev-parse", "HEAD"])
        return res.stdout.strip() if res.ok else ""

    def upstream(self) -> str:
        res = self.run(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
        return res.stdout.strip() if res.ok else ""

    def ahead_behind(self) -> dict[str, object]:
        upstream = self.upstream()
        if not upstream:
            return {"has_upstream": False, "ahead": 0, "behind": 0, "upstream": ""}
        res = self.run(["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
        if not res.ok:
            return {"has_upstream": True, "ahead": 0, "behind": 0, "upstream": upstream, "error": res.stderr}
        parts = res.stdout.strip().split()
        ahead = int(parts[0]) if len(parts) >= 1 and parts[0].isdigit() else 0
        behind = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
        return {"has_upstream": True, "ahead": ahead, "behind": behind, "upstream": upstream}

    def default_branch(self) -> str:
        res = self.run(["symbolic-ref", "refs/remotes/origin/HEAD", "--short"])
        if res.ok and res.stdout.strip():
            return res.stdout.strip().replace("origin/", "", 1)
        for branch in ("main", "master", "develop"):
            if self.branch_exists(branch):
                return branch
        return "HEAD"

    def branch_exists(self, branch: str) -> bool:
        local = self.run(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"])
        return local.ok

    def remote_url(self) -> str:
        res = self.run(["remote", "get-url", "origin"])
        return redact_secrets(res.stdout.strip()) if res.ok else ""

    def add(self, paths: list[str]) -> GitCommandResult:
        return self.run(["add", "--", *paths])

    def commit(self, message: str) -> GitCommandResult:
        return self.run(["commit", "-m", message], timeout=60)

    def switch_create(self, branch: str, start_point: str = "HEAD") -> GitCommandResult:
        return self.run(["switch", "-c", branch, start_point])

    def push(self, branch: str, set_upstream: bool) -> GitCommandResult:
        if set_upstream:
            return self.run(["push", "-u", "origin", branch], timeout=120)
        return self.run(["push"], timeout=120)
