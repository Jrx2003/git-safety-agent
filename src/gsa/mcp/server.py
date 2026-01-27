from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

from gsa.mcp.registry import ToolRegistry
from gsa.tools.file_impl import FileTool
from gsa.tools.git_impl import GitTool
from gsa.tools.index_impl import IndexTool


class MCPServer:
    """最小 MCP 兼容服务（stdio JSON-RPC 风格）。"""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self.registry = ToolRegistry()
        self.file_tool = FileTool(workspace)
        self.git_tool = GitTool(workspace)
        self.index_tool = IndexTool(workspace)
        self._register_tools()

    def _register_tools(self) -> None:
        # Git 只读
        self.registry.register("git_status", "查看 git 状态", self.git_tool.status)
        self.registry.register("git_diff", "查看 git diff", self.git_tool.diff)
        self.registry.register("git_log", "查看 git 日志", self.git_tool.log)
        self.registry.register("git_log_graph", "图形化日志", self.git_tool.log_graph)
        self.registry.register("git_branch_list", "列出分支", self.git_tool.branch_list)
        self.registry.register("git_remote_list", "列出远端", self.git_tool.remote_list)
        self.registry.register("git_show", "查看对象", self.git_tool.show)

        # Git 写操作
        self.registry.register("git_init", "初始化仓库", self.git_tool.init_repo)
        self.registry.register("git_add", "暂存文件", self.git_tool.add)
        self.registry.register("git_commit", "提交", self.git_tool.commit)
        self.registry.register("git_switch", "切换分支", self.git_tool.switch)
        self.registry.register("git_create_branch", "创建分支", self.git_tool.create_branch)
        self.registry.register("git_delete_branch", "删除分支", self.git_tool.delete_branch)
        self.registry.register("git_stash_push", "stash 保存", self.git_tool.stash_push)
        self.registry.register("git_stash_pop", "stash 恢复", self.git_tool.stash_pop)
        self.registry.register("git_merge", "合并分支", self.git_tool.merge)

        # 文件工具
        self.registry.register("file_list", "列出目录", self.file_tool.list_dir)
        self.registry.register("file_read", "读取文件", self.file_tool.read)
        self.registry.register("file_write", "写入文件", self.file_tool.write)
        self.registry.register("file_patch", "补丁修改", self.file_tool.patch)
        self.registry.register("file_search", "搜索内容", self.file_tool.search)

        # 索引工具
        self.registry.register("index_build", "构建索引", self.index_tool.build)
        self.registry.register("index_status", "索引状态", self.index_tool.status)
        self.registry.register("index_search", "索引搜索", self.index_tool.search)
        self.registry.register("repo_summarize", "仓库概览", self.index_tool.repo_summarize)
        self.registry.register("organize_suggestions", "整理建议", self.index_tool.organize_suggestions)

    def handle(self, request: Dict[str, Any]) -> Dict[str, Any]:
        method = request.get("method")
        req_id = request.get("id")
        try:
            if method == "tools/list":
                result = {"tools": self.registry.list_tools()}
            elif method == "tools/call":
                params = request.get("params") or {}
                name = params.get("name")
                args = params.get("args") or {}
                result = self.registry.call(name, args)
            elif method == "resources/list":
                result = {"resources": self._resources_list()}
            elif method == "resources/read":
                params = request.get("params") or {}
                result = self._resources_read(params.get("uri"))
            else:
                raise ValueError("未知方法")
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"message": str(exc)}}

    def _resources_list(self):
        return [
            {"uri": "workspace/info", "description": "工作区信息"},
            {"uri": "index/status", "description": "索引状态"},
            {"uri": "logs/recent", "description": "最近日志"},
            {"uri": "dir/summary", "description": "目录概要"},
        ]

    def _resources_read(self, uri: str):
        if uri == "workspace/info":
            return {
                "uri": uri,
                "content": {
                    "workspace": self.workspace,
                    "files": len(os.listdir(self.workspace)) if os.path.exists(self.workspace) else 0,
                },
            }
        if uri == "index/status":
            return {"uri": uri, "content": self.index_tool.status()}
        if uri == "logs/recent":
            log_dir = os.path.join(self.workspace, ".gsa", "logs")
            files = []
            if os.path.exists(log_dir):
                files = sorted(os.listdir(log_dir))[-5:]
            return {"uri": uri, "content": {"files": files}}
        if uri == "dir/summary":
            return {"uri": uri, "content": self.file_tool.summary()}
        raise ValueError("未知资源")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    server = MCPServer(args.workspace)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        resp = server.handle(req)
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
