from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict


class EventLogger:
    """JSONL 事件日志。"""

    def __init__(self, workspace: str, trace_id: str):
        self.workspace = workspace
        self.trace_id = trace_id
        self.log_dir = os.path.join(workspace, ".gsa", "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        date = datetime.now().strftime("%Y%m%d")
        self.path = os.path.join(self.log_dir, f"{date}_{trace_id}.jsonl")

    def log(self, event_type: str, payload: Dict[str, Any]) -> None:
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "event": event_type,
            "trace_id": self.trace_id,
            "payload": payload,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
