"""Exclude rash and vulval-site codes from the NG12 1.7.4 Skin lesion leaf.

NICE 1.7.4 is cutaneous squamous cell carcinoma. Eruption of skin is
a rash tree, not SCC suspicion. NICE 1.5.17 owns vulval lump, ulcer,
or bleeding. Some vulval-site disorders also sit under Skin lesion
95324001. That is too wide.

Owner: AppropriatenessRule.logicJson excluded_concept_ids.
Evaluate must not import this. Live match shape lives on the rule.

Atlas trace: UN-5F3BF083, DI-CDDA5214.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

SKIN_LESION_ID = "95324001"
ERUPTION_OF_SKIN_ID = "271807003"
VULVAL_MELANOTIC_MACULE_ID = "717732009"

# Authored roots under Skin lesion. Compile also drops IS_A children.
_VULVAL_SITE_EXCLUSIONS = (
    ERUPTION_OF_SKIN_ID,  # Eruption of skin (rash tree)
    "1287518000",  # Abrasion of skin of vulva
    "402841001",  # Angiokeratoma of vulva
    "403373008",  # Apocrine miliaria of vulva
    "717731002",  # Basal cell carcinoma of vulva
    "9742005",  # Blister of vulva without infection
    "399990001",  # Bowenoid papulosis of vulva
    "402946005",  # Condylomata lata of vulva
    "403371005",  # Fordyce spots of vulva
    "198227006",  # Furuncle of vulva
    "721180007",  # Lichen planopilaris of vulva
    "237112004",  # Lichen planus of vulva
    "402437008",  # Localized bullous pemphigoid of vulva
    "448300007",  # Malignant melanoma of skin of vulva
    "254898001",  # Paget's disease of vulva
    "313351009",  # Squamous cell carcinoma in situ of skin of vulva
    "402941000",  # Syphilitic chancre of vulva
    "276873004",  # Vulval intraepithelial neoplasia grade 1
    "276874005",  # Vulval intraepithelial neoplasia grade 2
    VULVAL_MELANOTIC_MACULE_ID,  # Vulval melanotic macule
    "402912009",  # Vulval verrucous carcinoma of Buschke-Lowenstein
    "238705003",  # Vulvovaginal hypermelanosis
)


def skin_lesion_vulval_excluded_concept_ids() -> list[str]:
    return list(_VULVAL_SITE_EXCLUSIONS)


def exclude_vulval_site_from_skin_lesion_leaf(
    tree: dict[str, Any],
) -> dict[str, Any]:
    """Return a copy with vulval-site ids on the Skin lesion leaf."""
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
    if primary != SKIN_LESION_ID:
        return
    current = [str(x) for x in (crit.get("excluded_concept_ids") or []) if x]
    crit["excluded_concept_ids"] = list(
        dict.fromkeys([*current, *_VULVAL_SITE_EXCLUSIONS])
    )
