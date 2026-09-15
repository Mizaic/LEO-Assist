"""Exclude vulval-site pain from the NG12 1.5.2 pelvic-pain leaf.

NICE 1.5.2 is internal pelvic or abdominal pain (ovarian symptoms).
SNOMED puts Vulval pain under Pain in pelvis. That is too wide.

Owner: AppropriatenessRule.logicJson excluded_concept_ids.
Evaluate must not import this. Live match shape lives on the rule.

Atlas trace: UN-5F3BF083, DI-185DE0CE, DO-5899D7BE, VT-2082C55B.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

PELVIC_PAIN_ID = "30473006"
VULVAL_PAIN_ID = "162145001"
OVARIAN_PAIN_ID = "279028009"

# Exact ids. The compiler subtracts these, not their children.
_VULVAL_SITE_EXCLUSIONS = (
    "162145001",  # Vulval pain
    "275321000",  # Vulva sore
    "37488003",  # Vulvovaginal pain
    "238968009",  # Vulvodynia
    "33563008",  # Essential vulvodynia
    "23189007",  # Idiopathic vulvodynia
    "1348331009",  # Chronic pain of vestibule of vulva
    "1348334001",  # Chronic vestibule pain provoked by contact
    "313344000",  # Vulval superficial dyspareunia
)


def pelvic_pain_excluded_concept_ids() -> list[str]:
    return list(_VULVAL_SITE_EXCLUSIONS)


def exclude_vulval_site_from_pelvic_leaf(tree: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with vulval-site ids on the Pain in pelvis leaf."""
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
    if primary != PELVIC_PAIN_ID:
        return
    current = [str(x) for x in (crit.get("excluded_concept_ids") or []) if x]
    merged = list(dict.fromkeys([*current, *_VULVAL_SITE_EXCLUSIONS]))
    crit["excluded_concept_ids"] = merged
