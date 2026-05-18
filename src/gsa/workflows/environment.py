from __future__ import annotations

import os
from typing import Any

from gsa.github.gh import GhProvider
from gsa.llm.llm_client import load_config
from gsa.security.redaction import redact_secrets
from gsa.workflows.git_state import GitState
from gsa.workflows.trace_store import list_traces, read_trace


def llm_status(workspace: str) -> dict[str, Any]:
    cfg = load_config(workspace)
    provider = "Z.ai"
    if "open.bigmodel.cn" in cfg.base_url:
        provider = "BigModel"
    elif cfg.base_url:
        provider = "OpenAI-compatible"
    return {
        "configured": bool(cfg.api_key),
        "model": cfg.model,
        "base_url": cfg.base_url,
        "provider_label": provider,
    }


def get_environment(workspace: str) -> dict[str, Any]:
    workspace = os.path.abspath(workspace)
    git = GitState(workspace)
    gh = GhProvider(workspace)
    is_repo = git.is_repo()
    ahead_behind = git.ahead_behind() if is_repo else {"has_upstream": False, "ahead": 0, "behind": 0}
    files = git.changed_files() if is_repo else []
    auth = gh.auth_status()
    env = {
        "workspace": workspace,
        "git": {
            "is_repo": is_repo,
            "repo_root": git.repo_root() if is_repo else "",
            "branch": git.current_branch() if is_repo else "",
            "dirty": bool(files),
            "changed_count": len(files),
            "remote_url": git.remote_url() if is_repo else "",
            "upstream": ahead_behind.get("upstream", ""),
            "ahead": ahead_behind.get("ahead", 0),
            "behind": ahead_behind.get("behind", 0),
        },
        "github": {
            "gh_available": auth["available"],
            "authenticated": auth["authenticated"],
            "message": auth.get("message", ""),
        },
        "llm": llm_status(workspace),
        "recent_traces": list_traces(workspace, limit=8),
    }
    return redact_secrets(env)


def get_trace(workspace: str, trace_id: str) -> dict[str, Any] | None:
    return read_trace(workspace, trace_id)
