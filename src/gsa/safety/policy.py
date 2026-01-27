from __future__ import annotations

import os
from typing import Iterable, List, Tuple

BLOCKED_GIT_ARGS = {
    "reset --hard",
    "clean -fd",
    "push --force",
    "push -f",
    "checkout -- .",
}

SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    "id_rsa",
    "id_ed25519",
    "secrets.json",
    "tokens.json",
}


class PolicyError(RuntimeError):
    pass


def realpath(path: str) -> str:
    return os.path.realpath(os.path.abspath(path))


def ensure_in_workspace(workspace: str, target: str) -> str:
    """确保路径不逃逸 workspace。"""
    root = realpath(workspace)
    target_path = realpath(os.path.join(root, target)) if not os.path.isabs(target) else realpath(target)
    if not target_path.startswith(root + os.sep) and target_path != root:
        raise PolicyError(f"路径越界：{target}")
    return target_path


def deny_if_sensitive(path: str) -> None:
    name = os.path.basename(path)
    if name in SENSITIVE_NAMES:
        raise PolicyError(f"拒绝访问敏感文件：{name}")


def validate_git_args(args: Iterable[str]) -> None:
    joined = " ".join(args)
    for blocked in BLOCKED_GIT_ARGS:
        if blocked in joined:
            raise PolicyError(f"禁止危险 git 操作：{blocked}")


def limit_write_steps(total_steps: int) -> None:
    if total_steps > 10:
        raise PolicyError("单次写操作步骤超过 10，已拒绝")


def split_paths(paths: Iterable[str]) -> Tuple[List[str], List[str]]:
    safe: List[str] = []
    denied: List[str] = []
    for p in paths:
        try:
            deny_if_sensitive(p)
            safe.append(p)
        except PolicyError:
            denied.append(p)
    return safe, denied
