"""Synthetic tenant id for Validation Lab pipeline runs.

Atlas trace:
  DI: DI-FE423B8D
  DO: DO-158BE606
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-FE423B8D")

Validation Lab cases are single-tenant synthetic graphs. Production
referral traffic carries a real tenant id for chunk scope checks; lab
runs use a fixed sentinel so durable steps can reuse the same loaders
without failing closed on missing tenant metadata.
"""

from __future__ import annotations

from typing import Any

VALIDATION_LAB_TENANT_ID = "validation-lab"


def is_validation_lab_source(value: str | None) -> bool:
    return str(value or "").strip().startswith(VALIDATION_LAB_TENANT_ID)


def validation_lab_source_from_state(state: dict[str, Any]) -> str:
    ctx = state.get("context") if isinstance(state.get("context"), dict) else {}
    for candidate in (state.get("source"), ctx.get("source")):
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def is_validation_lab_pipeline_state(state: dict[str, Any]) -> bool:
    return is_validation_lab_source(validation_lab_source_from_state(state))
