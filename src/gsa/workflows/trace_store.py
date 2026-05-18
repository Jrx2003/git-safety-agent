from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

from gsa.security.redaction import redact_secrets


TRACE_DIR = os.path.join(".gsa", "workflows")


def new_trace_id() -> str:
    return uuid4().hex


def _trace_dir(workspace: str) -> str:
    path = os.path.join(workspace, TRACE_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def trace_path(workspace: str, trace_id: str) -> str:
    safe_id = "".join(ch for ch in trace_id if ch.isalnum() or ch in {"-", "_"})
    return os.path.join(_trace_dir(workspace), f"{safe_id}.json")


def append_trace_event(workspace: str, trace_id: str, event: str, payload: Any) -> None:
    path = trace_path(workspace, trace_id)
    record = {
        "trace_id": trace_id,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "events": [],
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                old = json.load(f)
            if isinstance(old, dict):
                record.update(old)
                record["events"] = list(old.get("events") or [])
        except Exception:
            pass
    record["updated_at"] = datetime.now().isoformat(timespec="seconds")
    record["events"].append(
        {
            "time": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "payload": redact_secrets(payload),
        }
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(redact_secrets(record), f, ensure_ascii=False, indent=2)


def save_plan(workspace: str, plan: Any) -> None:
    payload = plan.model_dump() if hasattr(plan, "model_dump") else plan
    append_trace_event(workspace, payload["trace_id"], "plan", payload)


def save_result(workspace: str, result: Any) -> None:
    payload = result.model_dump() if hasattr(result, "model_dump") else result
    append_trace_event(workspace, payload["trace_id"], "execute", payload)


def load_latest_plan(workspace: str, trace_id: str) -> dict[str, Any] | None:
    path = trace_path(workspace, trace_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    for event in reversed(data.get("events") or []):
        if event.get("event") == "plan":
            payload = event.get("payload")
            return payload if isinstance(payload, dict) else None
    return None


def list_traces(workspace: str, limit: int = 25) -> list[dict[str, Any]]:
    directory = _trace_dir(workspace)
    items: list[dict[str, Any]] = []
    for name in os.listdir(directory):
        if not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        events = data.get("events") or []
        latest = events[-1] if events else {}
        latest_payload = latest.get("payload") if isinstance(latest, dict) else {}
        items.append(
            redact_secrets(
                {
                    "trace_id": data.get("trace_id") or name[:-5],
                    "updated_at": data.get("updated_at"),
                    "latest_event": latest.get("event") if isinstance(latest, dict) else "",
                    "workflow_type": latest_payload.get("workflow_type", "")
                    if isinstance(latest_payload, dict)
                    else "",
                    "summary": latest_payload.get("summary", "")
                    if isinstance(latest_payload, dict)
                    else "",
                    "ok": latest_payload.get("ok") if isinstance(latest_payload, dict) else None,
                    "status": latest_payload.get("status", "") if isinstance(latest_payload, dict) else "",
                }
            )
        )
    items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return items[:limit]


def read_trace(workspace: str, trace_id: str) -> dict[str, Any] | None:
    path = trace_path(workspace, trace_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return redact_secrets(json.load(f))
    except Exception:
        return None
