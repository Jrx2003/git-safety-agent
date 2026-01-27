from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Dict, List, Optional


class MCPClient:
    """最小 MCP 客户端（stdio JSON-RPC）。"""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "gsa.mcp.server", "--workspace", workspace],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._id = 0

    def _send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.proc.stdin or not self.proc.stdout:
            raise RuntimeError("MCP 进程不可用")
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            req["params"] = params
        self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("MCP 连接中断")
            try:
                resp = json.loads(line)
            except Exception:
                continue
            if resp.get("id") == self._id:
                if resp.get("error"):
                    raise RuntimeError(resp["error"].get("message"))
                return resp.get("result")

    def list_tools(self) -> List[str]:
        data = self._send("tools/list")
        return list((data.get("tools") or {}).keys())

    def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return self._send("tools/call", {"name": name, "args": args})

    def list_resources(self) -> List[Dict[str, Any]]:
        data = self._send("resources/list")
        return data.get("resources", [])

    def read_resource(self, uri: str) -> Dict[str, Any]:
        return self._send("resources/read", {"uri": uri})

    def close(self) -> None:
        if self.proc:
            self.proc.terminate()
