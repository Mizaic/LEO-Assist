"""Save a missed-word teaching example from the engineer panel.

Atlas trace:
  DI: DI-4A012A59
  DO: DO-E7824FED
"""

from __future__ import annotations

import json
import re
from typing import Any

from libs.pipeline.document_quality import form_fingerprint
from libs.pipeline.extraction_learning_store import (
    ensure_learning_writers,
    persist_review_learning,
)
from libs.utils.deidentify import deidentify_text

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def sentence_for_span(letter: str, span: str) -> str:
    needle = (span or "").strip()
    text = letter or ""
    if not needle:
        return ""
    for part in _SENTENCE_SPLIT.split(text.strip()):
        if needle.lower() in part.lower():
            return part.strip()
    return _window_around_span(text, needle)


def save_span_few_shot(
    *,
    span: str,
    letter: str,
    semantic_tag: str = "finding",
    assertion: str = "present",
) -> dict[str, Any]:
    clean_span = (span or "").strip()
    if not clean_span:
        raise ValueError("empty span")
    sentence = sentence_for_span(letter, clean_span)
    clean = deidentify_text(sentence)
    fingerprint = form_fingerprint(sentence)
    few_shot = {
        "input": clean,
        "output": json.dumps(
            {
                "terms": [
                    {
                        "text": clean_span,
                        "semantic_tag": semantic_tag or "finding",
                        "assertion": assertion or "present",
                    }
                ]
            },
            ensure_ascii=True,
        ),
        "deidentified": True,
        "category": "missed_span",
        "fingerprint": fingerprint,
    }
    ensure_learning_writers()
    persist_review_learning(
        fingerprint_name=f"learned-{fingerprint}",
        fingerprint=fingerprint,
        few_shot=few_shot,
    )
    return few_shot


def _window_around_span(text: str, needle: str) -> str:
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return needle
    start = max(0, idx - 80)
    end = min(len(text), idx + len(needle) + 80)
    return text[start:end].strip()
