from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict
import inspect


@dataclass
class ToolSpec:
    name: str
    description: str
    func: Callable[..., Dict[str, Any]]


class ToolRegistry:
    """工具注册表。"""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, name: str, description: str, func: Callable[..., Dict[str, Any]]) -> None:
        self._tools[name] = ToolSpec(name=name, description=description, func=func)

    def list_tools(self) -> Dict[str, Dict[str, str]]:
        return {name: {"description": spec.description} for name, spec in self._tools.items()}

    def call(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self._tools:
            raise ValueError(f"未注册工具：{name}")
        func = self._tools[name].func
        sig = inspect.signature(func)
        if any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
            return func(**args)
        filtered = {k: v for k, v in (args or {}).items() if k in sig.parameters}
        return func(**filtered)

    def names(self):
        return list(self._tools.keys())
