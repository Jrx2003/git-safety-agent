import os
import pytest

from gsa.safety.policy import PolicyError, ensure_in_workspace, is_sensitive_path


def test_ensure_in_workspace_allows_child(tmp_path):
    workspace = tmp_path
    child = workspace / "a.txt"
    assert ensure_in_workspace(str(workspace), str(child)).startswith(str(workspace))


def test_ensure_in_workspace_blocks_escape(tmp_path):
    workspace = tmp_path
    with pytest.raises(PolicyError):
        ensure_in_workspace(str(workspace), "/etc/passwd")


def test_sensitive_path_patterns_cover_env_keys_and_tokens():
    assert is_sensitive_path(".env")
    assert is_sensitive_path(".env.production")
    assert not is_sensitive_path(".env.example")
    assert is_sensitive_path("private.pem")
    assert is_sensitive_path("deploy.key")
    assert is_sensitive_path("id_rsa")
    assert is_sensitive_path("tokens.json")
