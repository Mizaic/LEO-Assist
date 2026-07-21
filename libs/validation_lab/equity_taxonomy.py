"""Fixed equity taxonomy tables for Validation Lab scenario variants.

Atlas: DI-EB716E68 / DO-A0ADDB38

Loads ethnicity and WHO/ECOG performance-status options from existing
NCDA SNOMED config JSON. Comorbidity bands and PLUS groups are fixed
enums. Core20 decile is a synthetic 1-10 pick (not a live postcode
lookup). PLUS groups are test-authoring vocabulary aligned to NHS
Core20PLUS5 policy, not a coded clinical taxonomy.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_ETHNICITY_PATH = _ROOT / "configs/snomed/snomed_ncda_ethnicity_mapping.json"
_PS_PATH = _ROOT / "configs/snomed/snomed_ncda_who_performance_status_mapping.json"

_COMORBIDITY_BANDS = ("none", "low", "moderate", "high")
_PLUS_GROUPS = (
    "ethnic_minority_community",
    "coastal_deprivation_community",
    "learning_disability_or_autism",
    "inclusion_health_group",
    "none",
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def ethnicity_options() -> tuple[dict[str, Any], ...]:
    """Return all NCDA ethnicity buckets as {key, concept_id, preferred_term}."""
    data = _load_json(_ETHNICITY_PATH)
    rows: list[dict[str, Any]] = []
    for key, mapping in (data.get("mappings") or {}).items():
        cid = mapping.get("concept_id")
        term = str(mapping.get("preferred_term") or "").strip()
        if cid is None or not term:
            continue
        rows.append(
            {
                "key": str(key),
                "concept_id": str(cid),
                "preferred_term": term,
            }
        )
    return tuple(rows)


@lru_cache(maxsize=1)
def performance_status_options() -> tuple[dict[str, Any], ...]:
    """Return WHO/ECOG grades 0-4 with concept ids from config."""
    data = _load_json(_PS_PATH)
    rows: list[dict[str, Any]] = []
    for key, mapping in (data.get("mappings") or {}).items():
        grade_str = str(key).rsplit(" ", 1)[-1]
        try:
            grade = int(grade_str)
        except ValueError:
            continue
        cid = mapping.get("concept_id")
        if cid is None:
            continue
        rows.append(
            {
                "grade": grade,
                "concept_id": str(cid),
                "preferred_term": str(mapping.get("preferred_term") or "").strip(),
                "key": str(key),
            }
        )
    rows.sort(key=lambda r: int(r["grade"]))
    return tuple(rows)


def comorbidity_band_options() -> tuple[str, ...]:
    """Return Charlson-aligned comorbidity burden bands."""
    return _COMORBIDITY_BANDS


def plus_group_options() -> tuple[str, ...]:
    """Return fixed Core20PLUS5 PLUS-group authoring vocabulary."""
    return _PLUS_GROUPS


def is_valid_core20_decile(decile: int | None) -> bool:
    """Return True when decile is an integer in 1..10 inclusive."""
    if decile is None:
        return False
    try:
        value = int(decile)
    except (TypeError, ValueError):
        return False
    return 1 <= value <= 10


def ethnicity_concept_ids() -> frozenset[str]:
    """Set of valid ethnicity concept ids for verify_patch."""
    return frozenset(str(r["concept_id"]) for r in ethnicity_options())


def performance_status_grades() -> frozenset[int]:
    """Set of valid WHO/ECOG grades for verify_patch."""
    return frozenset(int(r["grade"]) for r in performance_status_options())
