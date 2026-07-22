"""Helpers for deterministic durable stage replay tests (G5.2)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def stage_output_hash(output: dict[str, Any]) -> str:
    """Stable SHA-256 over sorted JSON for replay comparison."""
    payload = json.dumps(output, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# Recorded LLM extraction responses keyed by window input hash prefix.
RECORDED_LLM_EXTRACTION: dict[str, list[dict[str, Any]]] = {
    "win1": [
        {
            "concept_id": "365756003",
            "text": "creatinine",
            "chunk_id": "c0",
            "sentence_id": "s0",
            "assertion": "present",
        },
        {
            "concept_id": "73211009",
            "text": "diabetes",
            "chunk_id": "c1",
            "sentence_id": "s1",
            "assertion": "present",
        },
    ],
    "win2": [
        {
            "concept_id": "38341003",
            "text": "hypertension",
            "chunk_id": "c2",
            "sentence_id": "s2",
            "assertion": "present",
        },
    ],
}

RECORDED_POST_PROCESSING: dict[str, Any] = {
    "entities": RECORDED_LLM_EXTRACTION["win1"] + RECORDED_LLM_EXTRACTION["win2"],
    "post_processed": True,
}
