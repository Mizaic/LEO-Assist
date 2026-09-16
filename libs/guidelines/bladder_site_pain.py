"""Exclude urinary-bladder pain from NG12 abdominal and pelvic pain leaves.

NICE 1.3.1 and 1.5.2 mean abdominal or internal pelvic pain.
SNOMED puts Pain of urinary bladder under both parents. That is too wide.

Owner: AppropriatenessRule.logicJson excluded_concept_ids.
Evaluate must not import this. Live match shape lives on the rule.

Atlas trace: UN-5F3BF083.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

ABDOMINAL_PAIN_ID = "21522001"
PELVIC_PAIN_ID = "30473006"
BLADDER_PAIN_ID = "15803009"
GALLBLADDER_PAIN_ID = "102628000"

_TARGET_LEAF_IDS = (ABDOMINAL_PAIN_ID, PELVIC_PAIN_ID)

# Authored ids. Compile also drops IS_A children of these.
_BLADDER_SITE_EXCLUSIONS = (
    "15803009",  # Pain of urinary bladder
    "16580691000119107",  # Chronic urinary bladder pain
    "38731000087104",  # Chronic primary bladder pain syndrome
    "6744007",  # Painful urinary bladder spasm
    "16844001",  # Painful urging to urinate
)


def bladder_site_excluded_concept_ids() -> list[str]:
    return list(_BLADDER_SITE_EXCLUSIONS)


def exclude_bladder_site_from_pain_leaves(tree: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with bladder-site ids on abdominal and pelvic pain leaves."""
    out = deepcopy(tree)
    _apply_exclusions(out)
    return out


def _apply_exclusions(node: dict[str, Any]) -> None:
    if str(node.get("kind") or "").upper() == "CONCEPT":
        _patch_leaf(node)
        return
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _apply_exclusions(child)


def _patch_leaf(node: dict[str, Any]) -> None:
    crit = node.get("criterion")
    if not isinstance(crit, dict):
        return
    primary = str(crit.get("primary_concept_id") or crit.get("snomed_concept_id") or "")
    if primary not in _TARGET_LEAF_IDS:
        return
    current = [str(x) for x in (crit.get("excluded_concept_ids") or []) if x]
    merged = list(dict.fromkeys([*current, *_BLADDER_SITE_EXCLUSIONS]))
    crit["excluded_concept_ids"] = merged
