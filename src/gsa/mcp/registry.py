from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


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
        return self._tools[name].func(**args)

    def names(self):
        return list(self._tools.keys())
