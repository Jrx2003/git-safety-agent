from __future__ import annotations

import os
import re
from dataclasses import asdict, is_dataclass
from typing import Any


REDACTED = "[REDACTED]"

_SECRET_VALUES: set[str] = set()
_SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|token|secret|password|authorization|credential)",
    re.IGNORECASE,
)
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*([^\s,'\"}]+)"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SK_RE = re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9._-]{8,}\b")
_COMMON_TOKEN_RE = re.compile(
    r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat|glpat|xoxb|xoxp|xoxa)-?[A-Za-z0-9_]{12,}\b"
)
_LONG_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9._-])(?=[A-Za-z0-9._+=-]{36,}\b)(?=.*[A-Za-z])(?=.*\d)"
    r"[A-Za-z0-9._+=-]{36,}(?![A-Za-z0-9._-])"
)


def register_secret(value: object) -> None:
    """Register a known secret value so later logs/reports can redact it."""
    if value is None:
        return
    text = str(value)
    if len(text) < 4:
        return
    _SECRET_VALUES.add(text)


def register_env_secrets() -> None:
    for key, value in os.environ.items():
        if _SENSITIVE_KEY_RE.search(key):
            register_secret(value)


def _redact_string(text: str) -> str:
    register_env_secrets()
    redacted = text
    for secret in sorted(_SECRET_VALUES, key=len, reverse=True):
        if secret and secret in redacted:
            redacted = redacted.replace(secret, REDACTED)
    redacted = _BEARER_RE.sub(f"Bearer {REDACTED}", redacted)
    redacted = _SK_RE.sub(REDACTED, redacted)
    redacted = _COMMON_TOKEN_RE.sub(REDACTED, redacted)
    redacted = _LONG_TOKEN_RE.sub(REDACTED, redacted)
    redacted = _ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", redacted)
    return redacted


def redact_secrets(value: Any) -> Any:
    """Recursively redact secrets from strings, mappings, lists and exceptions."""
    register_env_secrets()
    if isinstance(value, BaseException):
        return _redact_string(f"{value.__class__.__name__}: {value}")
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, bytes):
        return _redact_string(value.decode("utf-8", errors="replace"))
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _SENSITIVE_KEY_RE.search(key_text):
                out[key] = REDACTED
            else:
                out[key] = redact_secrets(item)
        return out
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, set):
        return {redact_secrets(item) for item in value}
    if is_dataclass(value):
        return redact_secrets(asdict(value))
    return value
