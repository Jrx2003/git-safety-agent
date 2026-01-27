from __future__ import annotations

from typing import Dict, Tuple


RISK_MAP = {
    "git_status": ("low", "只读操作"),
    "git_diff": ("low", "只读操作"),
    "git_log": ("low", "只读操作"),
    "git_branch_list": ("low", "只读操作"),
    "git_remote_list": ("low", "只读操作"),
    "git_show": ("low", "只读操作"),
    "git_log_graph": ("low", "只读操作"),
    "file_list": ("low", "只读操作"),
    "file_read": ("low", "只读操作"),
    "file_search": ("low", "只读操作"),
    "index_build": ("low", "只读索引构建"),
    "index_status": ("low", "只读操作"),
    "index_search": ("low", "只读操作"),
    "repo_summarize": ("low", "只读操作"),
    "organize_suggestions": ("low", "只读操作"),
    "git_init": ("medium", "初始化仓库会创建 .git 目录"),
    "git_add": ("medium", "会修改暂存区"),
    "git_commit": ("medium", "会创建提交"),
    "git_switch": ("medium", "切换分支可能影响工作区"),
    "git_create_branch": ("medium", "创建分支"),
    "git_delete_branch": ("high", "删除分支"),
    "git_stash_push": ("medium", "保存工作区变更"),
    "git_stash_pop": ("high", "恢复暂存可能引发冲突"),
    "git_merge": ("high", "合并可能引发冲突"),
    "file_write": ("high", "写入文件"),
    "file_patch": ("high", "修改文件"),
}


def assess_risk(tool: str, args: Dict[str, object]) -> Tuple[str, str]:
    base = RISK_MAP.get(tool)
    if not base:
        return "medium", "未知工具，默认中风险"

    level, reason = base
    if tool == "git_delete_branch":
        if bool(args.get("force")):
            return "high", "强制删除分支，风险更高"
    if tool == "git_switch":
        if args.get("create"):
            return "medium", "创建并切换分支"
    if tool in {"file_write", "file_patch"} and args.get("path"):
        return "high", f"写入/修改文件 {args.get('path')}"
    return level, reason
