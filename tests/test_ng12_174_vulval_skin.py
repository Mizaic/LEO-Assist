"""NG12 1.7.4 must not treat vulval-site skin codes as cutaneous SCC.

NICE 1.7.4 is a skin-cancer pathway. NICE 1.5.17 owns vulval lump,
ulcer, or bleeding. Some vulval-site disorders sit under Skin lesion
95324001, so 1.7.4 can fire on a gynae 2WW.

Owner: AppropriatenessRule.logicJson excluded_concept_ids on the
Skin lesion leaf.

Atlas: UN-5F3BF083, DI-CDDA5214.
"""

from __future__ import annotations

from libs.guidelines.ng12_174_vulval_skin import (
    ERUPTION_OF_SKIN_ID,
    SKIN_LESION_ID,
    VULVAL_MELANOTIC_MACULE_ID,
    exclude_vulval_site_from_skin_lesion_leaf,
    skin_lesion_vulval_excluded_concept_ids,
)


def test_excluded_ids_are_vulval_site_not_the_skin_lesion_leaf() -> None:
    ids = skin_lesion_vulval_excluded_concept_ids()
    assert VULVAL_MELANOTIC_MACULE_ID in ids
    assert ERUPTION_OF_SKIN_ID in ids
    assert SKIN_LESION_ID not in ids


def test_helper_writes_ids_on_skin_lesion_leaf_only() -> None:
    tree = {
        "kind": "AND",
        "children": [
            {
                "kind": "CONCEPT",
                "criterion": {
                    "snomed_concept_id": SKIN_LESION_ID,
                    "primary_concept_id": SKIN_LESION_ID,
                    "preferred_term": "Skin lesion (disorder)",
                    "excluded_concept_ids": [],
                },
            },
            {
                "kind": "CONCEPT",
                "criterion": {
                    "snomed_concept_id": "201101007",
                    "preferred_term": "Actinic keratosis (disorder)",
                    "excluded_concept_ids": [],
                },
            },
        ],
    }
    out = exclude_vulval_site_from_skin_lesion_leaf(tree)
    skin = out["children"][0]["criterion"]["excluded_concept_ids"]
    other = out["children"][1]["criterion"]["excluded_concept_ids"]
    assert VULVAL_MELANOTIC_MACULE_ID in skin
    assert ERUPTION_OF_SKIN_ID in skin
    assert other == []
    assert tree["children"][0]["criterion"]["excluded_concept_ids"] == []


def test_helper_keeps_existing_skin_exclusions() -> None:
    tree = {
        "kind": "CONCEPT",
        "criterion": {
            "primary_concept_id": SKIN_LESION_ID,
            "snomed_concept_id": SKIN_LESION_ID,
            "excluded_concept_ids": ["399912005"],
        },
    }
    out = exclude_vulval_site_from_skin_lesion_leaf(tree)
    ids = out["criterion"]["excluded_concept_ids"]
    assert ids[0] == "399912005"
    assert VULVAL_MELANOTIC_MACULE_ID in ids
