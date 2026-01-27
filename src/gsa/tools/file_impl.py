from __future__ import annotations

import difflib
import os
from typing import Dict, List

from gsa.safety.policy import PolicyError, deny_if_sensitive, ensure_in_workspace


class FileTool:
    """文件读写工具（严格 sandbox）。"""

    def __init__(self, workspace: str):
        self.workspace = workspace

    def _safe_path(self, path: str) -> str:
        target = ensure_in_workspace(self.workspace, path)
        deny_if_sensitive(target)
        return target

    def list_dir(self, dir: str = ".", max_depth: int = 2, dry_run: bool = True) -> Dict[str, object]:
        root = self._safe_path(dir)
        result: List[str] = []
        for current, dirs, files in os.walk(root):
            depth = os.path.relpath(current, root).count(os.sep)
            if depth > max_depth:
                dirs[:] = []
                continue
            rel = os.path.relpath(current, root)
            result.append(f"{rel}/")
            for name in files:
                result.append(os.path.join(rel, name))
        return {"ok": True, "items": result}

    def summary(self) -> Dict[str, object]:
        items = self.list_dir(".", max_depth=1).get("items", [])
        return {"ok": True, "items": items}

    def read(self, path: str, max_chars: int = 4000, dry_run: bool = True) -> Dict[str, object]:
        target = self._safe_path(path)
        if not os.path.exists(target):
            return {"ok": False, "error": "文件不存在"}
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if len(content) > max_chars:
            content = content[:max_chars] + "\n...<内容截断>"
        return {"ok": True, "content": content}

    def write(self, path: str, content: str, dry_run: bool = True) -> Dict[str, object]:
        target = self._safe_path(path)
        old = ""
        if os.path.exists(target):
            with open(target, "r", encoding="utf-8", errors="ignore") as f:
                old = f.read()
        diff = "\n".join(
            difflib.unified_diff(
                old.splitlines(),
                content.splitlines(),
                fromfile=path,
                tofile=path,
                lineterm="",
            )
        )
        if dry_run:
            return {"ok": True, "dry_run": True, "diff": diff}
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "diff": diff}

    def patch(self, path: str, unified_diff: str, dry_run: bool = True) -> Dict[str, object]:
        target = self._safe_path(path)
        if not os.path.exists(target):
            return {"ok": False, "error": "文件不存在"}
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            old = f.read()
        # 简单应用：仅支持整文件替换型 diff
        if not unified_diff:
            return {"ok": False, "error": "diff 为空"}
        if dry_run:
            return {"ok": True, "dry_run": True, "diff": unified_diff}
        # 使用系统 patch 应用 unified diff，失败则拒绝
        import subprocess

        proc = subprocess.run(
            ["patch", "-p0", target],
            input=unified_diff,
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            return {"ok": False, "error": "diff 无法应用", "stderr": proc.stderr}
        return {"ok": True, "diff": unified_diff, "stdout": proc.stdout}

    def search(self, pattern: str, dir: str = ".", max_results: int = 50, dry_run: bool = True) -> Dict[str, object]:
        root = self._safe_path(dir)
        hits: List[Dict[str, object]] = []
        for current, _, files in os.walk(root):
            for name in files:
                path = os.path.join(current, name)
                try:
                    deny_if_sensitive(path)
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for idx, line in enumerate(f):
                            if pattern in line:
                                hits.append({
                                    "file": os.path.relpath(path, root),
                                    "line": idx + 1,
                                    "text": line.strip(),
                                })
                                if len(hits) >= max_results:
                                    return {"ok": True, "hits": hits}
                except PolicyError:
                    continue
                except Exception:
                    continue
        return {"ok": True, "hits": hits}
