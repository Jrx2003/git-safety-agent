import os
import pytest

from gsa.safety.policy import PolicyError, ensure_in_workspace


def test_ensure_in_workspace_allows_child(tmp_path):
    workspace = tmp_path
    child = workspace / "a.txt"
    assert ensure_in_workspace(str(workspace), str(child)).startswith(str(workspace))


def test_ensure_in_workspace_blocks_escape(tmp_path):
    workspace = tmp_path
    with pytest.raises(PolicyError):
        ensure_in_workspace(str(workspace), "/etc/passwd")
