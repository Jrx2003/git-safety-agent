from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List


def write_run_report(workspace: str, trace_id: str, summary: str, steps: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.join(workspace, ".gsa"), exist_ok=True)
    changes_path = os.path.join(workspace, ".gsa", "changes.md")
    with open(changes_path, "w", encoding="utf-8") as f:
        f.write(f"# 本次执行摘要\n\n")
        f.write(f"- trace_id: {trace_id}\n")
        f.write(f"- 时间: {datetime.now().isoformat(timespec='seconds')}\n\n")
        f.write(summary + "\n")

    last_run_path = os.path.join(workspace, ".gsa", "last_run_summary.json")
    with open(last_run_path, "w", encoding="utf-8") as f:
        json.dump({
            "trace_id": trace_id,
            "summary": summary,
            "steps": steps,
            "time": datetime.now().isoformat(timespec="seconds"),
        }, f, ensure_ascii=False, indent=2)
