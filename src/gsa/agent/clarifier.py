from __future__ import annotations

from typing import List


def clarify_questions(questions: List[str]) -> str:
    """将问题整理成适合 UI 展示的文本。"""
    if not questions:
        return ""
    return "\n".join([f"- {q}" for q in questions])
