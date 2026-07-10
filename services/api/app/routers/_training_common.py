"""Shared helpers used by more than one training/* router module.

Atlas trace:
  DO: DO-236545C8
  Also implements: DO-2D2CE052, DO-54397CCD, DO-6CD07544, DO-94D87FA7, DO-A35D2D57, DO-B88D4941, DO-BA2B7A99
  DI: DI-2D9F5064, DI-37B3DC71, DI-3EA60D5A, DI-54D00E21, DI-6EFD68D0, DI-A0579B64, DI-AF5A1668, DI-D2D0117E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

Extracted from services/api/app/routers/training.py (2026-07 CTO peer-review
item 2: core-api router decomposition). Pure move, no behaviour change --
existing DO/DI trace headers carried over unchanged.

_enrich_items_entities_with_pt_cache is used by training_candidates and training_gold_labels. UpdateEntitiesRequest is used by training_labels and training_gold_labels. _VALID_ENTITY_LABELS is used by training_labels, coding_review, and training_gold_labels. Extracted here during the item-2 discovery pass to avoid duplication or cross-router imports for genuinely cross-cutting helpers.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from libs.terminology.preferred_terms import (
    hydrate_entities_json_items_with_pt_cache,
)

logger = logging.getLogger(__name__)


def _enrich_items_entities_with_pt_cache(
    session: Any,
    items: list[dict[str, Any]],
) -> None:
    hydrate_entities_json_items_with_pt_cache(session=session, items=items)


class UpdateEntitiesRequest(BaseModel):
    entities: list[dict[str, Any]]


_VALID_ENTITY_LABELS: frozenset[str] = frozenset(
    {
        "disorder",
        "finding",
        "procedure",
        "observable_entity",
        "qualifier_value",
        "substance",
        "medicinal_product",
        "clinical_drug",
        "situation",
        "event",
        "body_structure",
        "tumor_staging",
        "assessment_scale",
        "staging_scale",
        "regime_therapy",
        "record_artifact",
        "physical_object",
        "organism",
        "morphologic_abnormality",
        "occupation",
        "attribute",
        "environment",
        "product",
        "X_TEMPORAL",
        "X_DOSAGE",
        "X_FREQUENCY",
        "X_ROUTE",
    }
)
