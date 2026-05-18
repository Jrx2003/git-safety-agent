from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from typing import Optional

from gsa.agent.orchestrator import Orchestrator
from gsa.security.redaction import redact_secrets
from gsa.workflows import (
    execute_issue_branch,
    execute_push_pr,
    execute_safe_commit,
    get_environment,
    get_trace,
    plan_issue_branch,
    plan_pr_readiness,
    plan_push_pr,
    plan_safe_commit,
)
from gsa.workflows.trace_store import list_traces


def _read_input(text: Optional[str]) -> str:
    if text:
        return text
    return sys.stdin.read().strip()


def _print_json(value: object) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    print(json.dumps(redact_secrets(value), ensure_ascii=False, indent=2))


def cmd_plan(args: argparse.Namespace) -> None:
    orch = Orchestrator(args.workspace, use_llm=args.use_llm)
    user_input = _read_input(args.input)
    result = orch.plan(user_input)
    _print_json(result)


def cmd_run(args: argparse.Namespace) -> None:
    orch = Orchestrator(args.workspace, use_llm=args.use_llm)
    user_input = _read_input(args.input)
    plan_result = orch.plan(user_input)
    if plan_result.errors:
        print("\n".join(plan_result.errors))
        return
    if not plan_result.plan:
        print("未生成计划")
        return
    if plan_result.plan.needs_confirmation and not args.yes:
        print("计划需要 YES 确认，已执行试运行。")
    result = orch.execute(plan_result.plan, plan_result.trace_id, confirmed=args.yes)
    _print_json(result)


def cmd_ui(args: argparse.Namespace) -> None:
    env = os.environ.copy()
    env["GSA_WORKSPACE"] = args.workspace
    import gsa.app.ui as ui_module

    ui_path = os.path.abspath(ui_module.__file__)
    cmd = ["streamlit", "run", ui_path]
    try:
        import watchdog  # type: ignore

        cmd.append("--server.fileWatcherType=watchdog")
    except Exception:
        pass
    subprocess.run(cmd, env=env)


def cmd_api(args: argparse.Namespace) -> None:
    env = os.environ.copy()
    env["GSA_WORKSPACE"] = args.workspace
    subprocess.run(["uvicorn", "gsa.app.api:app", "--host", args.host, "--port", str(args.port)], env=env)


def cmd_web(args: argparse.Namespace) -> None:
    env = os.environ.copy()
    env["GSA_WORKSPACE"] = args.workspace
    env["VITE_GSA_API_BASE"] = f"http://127.0.0.1:{args.api_port}"
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    web_dir = os.path.join(repo_root, "web")
    api_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "gsa.app.api:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(args.api_port),
    ]
    web_cmd = [
        "npm",
        "--prefix",
        web_dir,
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        str(args.web_port),
    ]
    if not os.path.exists(os.path.join(web_dir, "package.json")):
        print("缺少 web/package.json，请先安装 React 工作台文件。")
        return
    print(f"API: http://127.0.0.1:{args.api_port}")
    print(f"Web: http://127.0.0.1:{args.web_port}")
    api_proc = subprocess.Popen(api_cmd, env=env)
    web_proc = subprocess.Popen(web_cmd, env=env)
    try:
        web_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (web_proc, api_proc):
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
        for proc in (web_proc, api_proc):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def cmd_index_build(args: argparse.Namespace) -> None:
    orch = Orchestrator(args.workspace, use_llm=False)
    res = orch.mcp.call_tool(
        "index_build",
        {
            "include_globs": args.include_globs,
            "exclude_globs": args.exclude_globs,
            "chunk_size": args.chunk_size,
            "overlap": args.overlap,
            "dry_run": args.dry_run,
        },
    )
    _print_json(res)


def cmd_clear_memory(args: argparse.Namespace) -> None:
    orch = Orchestrator(args.workspace, use_llm=False)
    orch.memory.clear()
    print("记忆已清空")


def cmd_env(args: argparse.Namespace) -> None:
    _print_json(get_environment(args.workspace))


def cmd_commit_plan(args: argparse.Namespace) -> None:
    _print_json(plan_safe_commit(args.workspace, selected_paths=args.paths, message=args.message))


def cmd_commit(args: argparse.Namespace) -> None:
    plan = plan_safe_commit(args.workspace, selected_paths=args.paths, message=args.message)
    if not args.yes:
        _print_json(plan)
        print("未传入 --yes，仅生成计划。")
        return
    _print_json(
        execute_safe_commit(
            args.workspace,
            trace_id=plan.trace_id,
            confirmed=True,
            selected_paths=args.paths,
            message=args.message,
        )
    )


def cmd_issue_branch(args: argparse.Namespace) -> None:
    plan = plan_issue_branch(args.workspace, issue=args.issue)
    if not args.yes:
        _print_json(plan)
        print("未传入 --yes，仅生成计划。")
        return
    _print_json(execute_issue_branch(args.workspace, trace_id=plan.trace_id, confirmed=True))


def cmd_push_pr(args: argparse.Namespace) -> None:
    plan = plan_push_pr(args.workspace, title=args.title, body=args.body, draft=args.draft)
    if not args.yes:
        _print_json(plan)
        print("未传入 --yes，仅生成计划。")
        return
    _print_json(
        execute_push_pr(
            args.workspace,
            trace_id=plan.trace_id,
            confirmed=True,
            title=args.title,
            body=args.body,
            draft=args.draft,
        )
    )


def cmd_pr_ready(args: argparse.Namespace) -> None:
    _print_json(plan_pr_readiness(args.workspace, pr=args.pr))


def cmd_trace_list(args: argparse.Namespace) -> None:
    _print_json(list_traces(args.workspace, limit=args.limit))


def cmd_trace_show(args: argparse.Namespace) -> None:
    trace = get_trace(args.workspace, args.trace_id)
    if not trace:
        print("trace 不存在")
        return
    _print_json(trace)


def main() -> None:
    parser = argparse.ArgumentParser(prog="gsa")
    parser.add_argument("--workspace", default=os.getcwd())
    sub = parser.add_subparsers(dest="cmd")

    p_plan = sub.add_parser("plan", help="生成计划")
    p_plan.add_argument("--input")
    p_plan.add_argument("--use-llm", action=argparse.BooleanOptionalAction, default=True)
    p_plan.set_defaults(func=cmd_plan)

    p_run = sub.add_parser("run", help="生成并执行")
    p_run.add_argument("--input")
    p_run.add_argument("--use-llm", action=argparse.BooleanOptionalAction, default=True)
    p_run.add_argument("--yes", action="store_true", default=False)
    p_run.set_defaults(func=cmd_run)

    p_ui = sub.add_parser("ui", help="启动 GUI")
    p_ui.set_defaults(func=cmd_ui)

    p_api = sub.add_parser("api", help="启动 API")
    p_api.add_argument("--host", default="0.0.0.0")
    p_api.add_argument("--port", type=int, default=8000)
    p_api.set_defaults(func=cmd_api)

    p_web = sub.add_parser("web", help="启动 React 工作台和 API")
    p_web.add_argument("--api-port", type=int, default=8000)
    p_web.add_argument("--web-port", type=int, default=5173)
    p_web.set_defaults(func=cmd_web)

    p_index = sub.add_parser("index-build", help="构建索引")
    p_index.add_argument("--include-globs", nargs="*", default=["**/*"])
    p_index.add_argument("--exclude-globs", nargs="*", default=["**/.git/**", "**/.gsa/**"])
    p_index.add_argument("--chunk-size", type=int, default=800)
    p_index.add_argument("--overlap", type=int, default=100)
    p_index.add_argument("--dry-run", action="store_true", default=False)
    p_index.set_defaults(func=cmd_index_build)

    p_clear = sub.add_parser("clear-memory", help="清空记忆")
    p_clear.set_defaults(func=cmd_clear_memory)

    p_env = sub.add_parser("env", help="查看 GSA 环境状态")
    p_env.set_defaults(func=cmd_env)

    p_commit_plan = sub.add_parser("commit-plan", help="生成 Safe Commit 计划")
    p_commit_plan.add_argument("--paths", nargs="*")
    p_commit_plan.add_argument("--message")
    p_commit_plan.set_defaults(func=cmd_commit_plan)

    p_commit = sub.add_parser("commit", help="执行 Safe Commit")
    p_commit.add_argument("--paths", nargs="*")
    p_commit.add_argument("--message")
    p_commit.add_argument("--yes", action="store_true", default=False)
    p_commit.set_defaults(func=cmd_commit)

    p_issue = sub.add_parser("issue-branch", help="从 GitHub issue 创建分支")
    p_issue.add_argument("issue")
    p_issue.add_argument("--yes", action="store_true", default=False)
    p_issue.set_defaults(func=cmd_issue_branch)

    p_push = sub.add_parser("push-pr", help="push 当前分支并创建 Draft PR")
    p_push.add_argument("--title")
    p_push.add_argument("--body")
    p_push.add_argument("--draft", action=argparse.BooleanOptionalAction, default=True)
    p_push.add_argument("--yes", action="store_true", default=False)
    p_push.set_defaults(func=cmd_push_pr)

    p_ready = sub.add_parser("pr-ready", help="检查 PR readiness")
    p_ready.add_argument("pr", nargs="?")
    p_ready.set_defaults(func=cmd_pr_ready)

    p_trace = sub.add_parser("trace", help="查看 workflow trace")
    trace_sub = p_trace.add_subparsers(dest="trace_cmd")
    p_trace_list = trace_sub.add_parser("list", help="列出最近 trace")
    p_trace_list.add_argument("--limit", type=int, default=25)
    p_trace_list.set_defaults(func=cmd_trace_list)
    p_trace_show = trace_sub.add_parser("show", help="显示单个 trace")
    p_trace_show.add_argument("trace_id")
    p_trace_show.set_defaults(func=cmd_trace_show)

    args = parser.parse_args()
    if not getattr(args, "cmd", None):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
