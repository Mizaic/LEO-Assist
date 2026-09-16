"""Exclude organ cysts from the NG12 abdominal-mass leaf.

NICE 1.3.1 and 1.5.1 mean a palpable or imaging abdominal mass.
SNOMED puts Cyst of pancreas and Cyst of kidney under Abdominal mass.
That is too wide.

Owner: AppropriatenessRule.logicJson excluded_concept_ids.
Evaluate must not import this. Live match shape lives on the rule.

Atlas trace: UN-5F3BF083, DI-CDDA5214, DO-51F0FE8C, VT-0AD6DA01.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

ABDOMINAL_MASS_ID = "271860004"
PELVIC_MASS_ID = "74285003"
CYST_OF_PANCREAS_ID = "31258000"
CYST_OF_KIDNEY_ID = "722223000"

# Authored ids. Compile also drops IS_A children of these.
_ORGAN_CYST_EXCLUSIONS = (
    CYST_OF_PANCREAS_ID,
    CYST_OF_KIDNEY_ID,
)


def abdominal_mass_cyst_excluded_concept_ids() -> list[str]:
    return list(_ORGAN_CYST_EXCLUSIONS)


def exclude_organ_cysts_from_abdominal_mass_leaf(
    tree: dict[str, Any],
) -> dict[str, Any]:
    """Return a copy with organ-cyst ids on the Abdominal mass leaf."""
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
    primary = str(
        crit.get("primary_concept_id") or crit.get("snomed_concept_id") or ""
    )
    if primary != ABDOMINAL_MASS_ID:
        return
    current = [str(x) for x in (crit.get("excluded_concept_ids") or []) if x]
    crit["excluded_concept_ids"] = list(
        dict.fromkeys([*current, *_ORGAN_CYST_EXCLUSIONS])
    )
