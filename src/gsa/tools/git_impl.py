from __future__ import annotations

import subprocess
from typing import Dict, List, Optional

from gsa.safety.policy import PolicyError, validate_git_args


class GitTool:
    """Git 工具实现（含防误用）。"""

    def __init__(self, workspace: str):
        self.workspace = workspace

    def _run(self, args: List[str]) -> subprocess.CompletedProcess:
        validate_git_args(args)
        return subprocess.run(
            ["git", "-C", self.workspace] + args,
            capture_output=True,
            text=True,
        )

    def _ensure_repo(self) -> Optional[str]:
        proc = self._run(["rev-parse", "--is-inside-work-tree"])
        if proc.returncode != 0:
            return proc.stderr.strip() or "当前目录不是 git 仓库"
        return None

    # 只读
    def status(self, dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        proc = self._run(["status", "-sb"])
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def diff(self, staged: bool = False, paths: Optional[List[str]] = None, dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        args = ["diff"]
        if staged:
            args.append("--staged")
        if paths:
            args.extend(paths)
        proc = self._run(args)
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def log(self, n: int = 10, limit: Optional[int] = None, dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        if limit is not None:
            n = limit
        n = min(max(int(n), 1), 50)
        proc = self._run(["log", f"-{n}", "--pretty=format:%h|%an|%ad|%s", "--date=short"])
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def log_graph(
        self,
        n: int = 30,
        limit: Optional[int] = None,
        author: Optional[str] = None,
        path: Optional[str] = None,
        branch: Optional[str] = None,
        dry_run: bool = True,
    ) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        if limit is not None:
            n = limit
        n = min(max(int(n), 1), 80)
        args = [
            "log",
            f"-{n}",
            "--oneline",
            "--graph",
            "--decorate",
        ]
        if branch:
            args.append(f"--branches={branch}")
        else:
            args.append("--all")
        if author:
            args.append(f"--author={author}")
        if path:
            args.extend(["--", path])
        proc = self._run(args)
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def branch_list(self, dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        proc = self._run(["branch", "-a"])
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def remote_list(self, dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        proc = self._run(["remote", "-v"])
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def show(self, ref: str = "HEAD", dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        proc = self._run(["show", "--stat", "--oneline", ref])
        out = proc.stdout
        if len(out) > 4000:
            out = out[:4000] + "\n...<输出截断>"
        return {"ok": proc.returncode == 0, "stdout": out, "stderr": proc.stderr}

    def init_repo(self, dry_run: bool = True) -> Dict[str, object]:
        proc = self._run(["rev-parse", "--is-inside-work-tree"])
        if proc.returncode == 0:
            return {"ok": False, "error": "当前目录已是 git 仓库"}
        if dry_run:
            return {"ok": True, "dry_run": True, "cmd": "git init"}
        proc = self._run(["init"])
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    # 写操作
    def add(self, paths: List[str], allow_all: bool = False, dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        if not paths:
            return {"ok": False, "error": "未提供 paths"}
        if "." in paths and not allow_all:
            return {"ok": False, "error": "禁止默认 add .，请显式 allow_all=true"}
        proc_files = self._run(["status", "--porcelain"])
        files = [line[3:] for line in proc_files.stdout.splitlines() if line.strip()]
        if dry_run:
            return {"ok": True, "dry_run": True, "files": files, "cmd": "git add"}
        proc = self._run(["add"] + paths)
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def commit(self, message: str, dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        if not message:
            return {"ok": False, "error": "缺少提交信息"}
        staged = self._run(["diff", "--cached", "--name-only"]).stdout.strip().splitlines()
        if not staged:
            return {"ok": False, "error": "暂存区为空，无法提交"}
        if dry_run:
            return {"ok": True, "dry_run": True, "staged": staged, "message": message}
        proc = self._run(["commit", "-m", message])
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def switch(self, branch: str, create: bool = False, allow_dirty: bool = False, dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        if not branch:
            return {"ok": False, "error": "缺少分支名"}
        status = self._run(["status", "--porcelain"]).stdout.strip().splitlines()
        if status and not allow_dirty:
            return {
                "ok": False,
                "error": "当前有未提交改动，默认拒绝切换。可选择先 stash/commit。",
                "dirty_files": status,
            }
        cmd = ["switch"]
        if create:
            cmd += ["-c", branch]
        else:
            cmd.append(branch)
        if dry_run:
            return {"ok": True, "dry_run": True, "cmd": "git " + " ".join(cmd)}
        proc = self._run(cmd)
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def create_branch(self, name: str, from_ref: str = "HEAD", dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        if not name:
            return {"ok": False, "error": "缺少分支名"}
        if dry_run:
            return {"ok": True, "dry_run": True, "cmd": f"git branch {name} {from_ref}"}
        proc = self._run(["branch", name, from_ref])
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def delete_branch(self, name: str, force: bool = False, dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        if not name:
            return {"ok": False, "error": "缺少分支名"}
        flag = "-D" if force else "-d"
        if dry_run:
            return {"ok": True, "dry_run": True, "cmd": f"git branch {flag} {name}"}
        proc = self._run(["branch", flag, name])
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def stash_push(self, message: str = "", dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        cmd = ["stash", "push"]
        if message:
            cmd += ["-m", message]
        if dry_run:
            return {"ok": True, "dry_run": True, "cmd": "git " + " ".join(cmd)}
        proc = self._run(cmd)
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def stash_pop(self, index: int = 0, dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        ref = f"stash@{{{index}}}"
        if dry_run:
            return {"ok": True, "dry_run": True, "cmd": f"git stash pop {ref}"}
        proc = self._run(["stash", "pop", ref])
        return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}

    def merge(self, target_branch: str, dry_run: bool = True) -> Dict[str, object]:
        err = self._ensure_repo()
        if err:
            return {"ok": False, "error": err}
        if not target_branch:
            return {"ok": False, "error": "缺少目标分支"}
        if dry_run:
            return {"ok": True, "dry_run": True, "cmd": f"git merge {target_branch}"}
        proc = self._run(["merge", target_branch])
        if proc.returncode != 0:
            conflicts = self._run(["diff", "--name-only", "--diff-filter=U"]).stdout.splitlines()
            return {
                "ok": False,
                "error": "合并出现冲突",
                "conflicts": conflicts,
                "suggestion": "请手动解决冲突后 git add + git commit。",
            }
        return {"ok": True, "stdout": proc.stdout, "stderr": proc.stderr}
