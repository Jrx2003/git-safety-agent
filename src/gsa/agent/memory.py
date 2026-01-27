from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class SessionMemory:
    workspace: str = ""
    last_plan: Optional[Dict[str, object]] = None
    recent_files: List[str] = field(default_factory=list)
    recent_branch: str = ""
    preferences: Dict[str, object] = field(default_factory=dict)


@dataclass
class PersistentMemory:
    recent_ops: List[str] = field(default_factory=list)
    default_dry_run: bool = True
    common_workspaces: List[str] = field(default_factory=list)
    index_config: Dict[str, object] = field(default_factory=dict)


class MemoryStore:
    """会话 + 持久化记忆管理。"""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self.session = SessionMemory(workspace=workspace)
        self.persist = PersistentMemory()
        self.path = os.path.join(workspace, ".gsa", "memory.json")
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.persist = PersistentMemory(**data)
        except Exception:
            return

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(asdict(self.persist), f, ensure_ascii=False, indent=2)

    def clear(self) -> None:
        self.persist = PersistentMemory()
        if os.path.exists(self.path):
            os.remove(self.path)

    def record_op(self, summary: str) -> None:
        self.persist.recent_ops.append(summary)
        self.persist.recent_ops = self.persist.recent_ops[-20:]
        if self.workspace not in self.persist.common_workspaces:
            self.persist.common_workspaces.append(self.workspace)
        self.save()
