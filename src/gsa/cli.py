from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Optional

from gsa.agent.orchestrator import Orchestrator


def _read_input(text: Optional[str]) -> str:
    if text:
        return text
    return sys.stdin.read().strip()


def cmd_plan(args: argparse.Namespace) -> None:
    orch = Orchestrator(args.workspace, use_llm=args.use_llm)
    user_input = _read_input(args.input)
    result = orch.plan(user_input)
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


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
        print("计划需要 YES 确认，已执行 Dry-run。")
    result = orch.execute(plan_result.plan, plan_result.trace_id, confirmed=args.yes)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_ui(args: argparse.Namespace) -> None:
    env = os.environ.copy()
    env["GSA_WORKSPACE"] = args.workspace
    import gsa.app.ui as ui_module

    ui_path = os.path.abspath(ui_module.__file__)
    subprocess.run(["streamlit", "run", ui_path], env=env)


def cmd_api(args: argparse.Namespace) -> None:
    env = os.environ.copy()
    env["GSA_WORKSPACE"] = args.workspace
    subprocess.run(["uvicorn", "gsa.app.api:app", "--host", "0.0.0.0", "--port", str(args.port)], env=env)


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
    print(json.dumps(res, ensure_ascii=False, indent=2))


def cmd_clear_memory(args: argparse.Namespace) -> None:
    orch = Orchestrator(args.workspace, use_llm=False)
    orch.memory.clear()
    print("记忆已清空")


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
    p_api.add_argument("--port", type=int, default=8000)
    p_api.set_defaults(func=cmd_api)

    p_index = sub.add_parser("index-build", help="构建索引")
    p_index.add_argument("--include-globs", nargs="*", default=["**/*"])
    p_index.add_argument("--exclude-globs", nargs="*", default=["**/.git/**", "**/.gsa/**"])
    p_index.add_argument("--chunk-size", type=int, default=800)
    p_index.add_argument("--overlap", type=int, default=100)
    p_index.add_argument("--dry-run", action="store_true", default=False)
    p_index.set_defaults(func=cmd_index_build)

    p_clear = sub.add_parser("clear-memory", help="清空记忆")
    p_clear.set_defaults(func=cmd_clear_memory)

    args = parser.parse_args()
    if not getattr(args, "cmd", None):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
