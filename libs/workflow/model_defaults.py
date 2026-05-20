"""Shared defaults for validation and dry-run pipeline execution."""

from __future__ import annotations

import os
from typing import Any

_VALID_TIERS = frozenset({"small", "big", "max"})


def _is_validation_run(state: dict[str, Any]) -> bool:
    return bool(
        state.get("capture_validation_output")
        or state.get("validation_un_id")
        or state.get("validation_val_id")
    )


def apply_single_model_defaults(state: dict[str, Any]) -> None:
    """Pin validation runs to one Haiku LLM path (no NER, no dual-model judge).

    Mutates *state* in place. Production patient pipelines are unchanged.
    """
    if not _is_validation_run(state):
        return
    if not str(state.get("requested_model_mode") or "").strip():
        state["requested_model_mode"] = "llm"
    if not str(state.get("model_mode") or "").strip():
        state["model_mode"] = "llm"
    tier = str(state.get("model_tier") or "").strip().lower()
    if tier not in _VALID_TIERS:
        pipe_tier = (os.getenv("PIPELINE_MODEL_TIER") or "small").strip().lower()
        state["model_tier"] = pipe_tier if pipe_tier in _VALID_TIERS else "small"
