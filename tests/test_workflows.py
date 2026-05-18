import subprocess

from gsa.workflows.git_state import PROTECTED_BRANCHES
from gsa.workflows.safe_commit import execute_safe_commit, plan_safe_commit
from gsa.workflows.utils import issue_branch_name, slugify


def run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def test_slug_and_issue_branch_name():
    assert slugify("Fix: API key leak!") == "fix-api-key-leak"
    branch = issue_branch_name({"number": 42, "title": "Fix API key leak", "labels": [{"name": "bug"}]})
    assert branch.startswith("fix/42-")


def test_protected_branch_defaults():
    assert {"main", "master", "develop"} <= PROTECTED_BRANCHES


def test_safe_commit_plan_and_execute(tmp_path):
    run(["git", "init"], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], tmp_path)
    run(["git", "config", "user.name", "Test User"], tmp_path)
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")

    plan = plan_safe_commit(str(tmp_path), message="Add readme")

    assert plan.status == "ready"
    assert plan.requires_confirmation is True
    assert "README.md" in plan.data["selected_paths"]

    denied = execute_safe_commit(str(tmp_path), trace_id=plan.trace_id, confirmed=False)
    assert denied.ok is False

    result = execute_safe_commit(str(tmp_path), trace_id=plan.trace_id, confirmed=True)

    assert result.ok is True
    assert result.data["commit_hash"]


def test_safe_commit_rejects_state_change_before_execute(tmp_path):
    run(["git", "init"], tmp_path)
    run(["git", "config", "user.email", "test@example.com"], tmp_path)
    run(["git", "config", "user.name", "Test User"], tmp_path)
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")

    plan = plan_safe_commit(str(tmp_path), message="Add a")
    (tmp_path / "b.txt").write_text("b\n", encoding="utf-8")
    result = execute_safe_commit(str(tmp_path), trace_id=plan.trace_id, confirmed=True)

    assert result.ok is False
    assert "状态已变化" in result.summary
