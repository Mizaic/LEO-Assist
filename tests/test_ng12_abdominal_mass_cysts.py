"""NG12 must not treat organ cysts as an abdominal mass.

NHS 4464115160: Cyst of pancreas 31258000 and Cyst of kidney 722223000
are SNOMED children of Abdominal mass 271860004. That fired 1.3.1 (FIT)
and 1.5.1 (gynaecology 2WW) with no abdominal mass in the notes.

NHS 4568668417: Cyst of ovary 79883001 sits under Mass of uterine
adnexa 445039006, also a child of Abdominal mass. That fired 1.3.1
FIT with no coded abdominal mass. Pelvic mass 74285003 is a
different 1.5.1 leaf, not a child of Abdominal mass.

Owner: AppropriatenessRule.logicJson excluded_concept_ids on the
Abdominal mass leaf.

Atlas: UN-5F3BF083, DI-CDDA5214, DO-51F0FE8C, VT-0AD6DA01.
"""

from __future__ import annotations

from libs.guidelines.ng12_abdominal_mass_cysts import (
    ABDOMINAL_MASS_ID,
    CYST_OF_KIDNEY_ID,
    CYST_OF_OVARY_ID,
    CYST_OF_PANCREAS_ID,
    MASS_OF_UTERINE_ADNEXA_ID,
    PELVIC_MASS_ID,
    abdominal_mass_cyst_excluded_concept_ids,
    exclude_organ_cysts_from_abdominal_mass_leaf,
)


def test_excluded_ids_are_organ_cysts_and_adnexal_mass() -> None:
    ids = abdominal_mass_cyst_excluded_concept_ids()
    assert ids == [
        CYST_OF_PANCREAS_ID,
        CYST_OF_KIDNEY_ID,
        MASS_OF_UTERINE_ADNEXA_ID,
        CYST_OF_OVARY_ID,
    ]
    assert ABDOMINAL_MASS_ID not in ids
    assert PELVIC_MASS_ID not in ids


def test_helper_writes_ids_on_abdominal_mass_leaf_only() -> None:
    tree = {
        "kind": "OR",
        "children": [
            {
                "kind": "CONCEPT",
                "criterion": {
                    "snomed_concept_id": ABDOMINAL_MASS_ID,
                    "preferred_term": "Abdominal mass (finding)",
                    "excluded_concept_ids": [],
                },
            },
            {
                "kind": "CONCEPT",
                "criterion": {
                    "snomed_concept_id": PELVIC_MASS_ID,
                    "preferred_term": "Mass of pelvic structure (finding)",
                    "excluded_concept_ids": ["65576009"],
                },
            },
        ],
    }
    out = exclude_organ_cysts_from_abdominal_mass_leaf(tree)
    mass = out["children"][0]["criterion"]["excluded_concept_ids"]
    pelvic = out["children"][1]["criterion"]["excluded_concept_ids"]
    assert mass == [
        CYST_OF_PANCREAS_ID,
        CYST_OF_KIDNEY_ID,
        MASS_OF_UTERINE_ADNEXA_ID,
        CYST_OF_OVARY_ID,
    ]
    assert pelvic == ["65576009"]
    assert tree["children"][0]["criterion"]["excluded_concept_ids"] == []


def test_helper_keeps_existing_mass_exclusions() -> None:
    tree = {
        "kind": "CONCEPT",
        "criterion": {
            "primary_concept_id": ABDOMINAL_MASS_ID,
            "snomed_concept_id": ABDOMINAL_MASS_ID,
            "excluded_concept_ids": ["65576009"],
        },
    }
    out = exclude_organ_cysts_from_abdominal_mass_leaf(tree)
    assert out["criterion"]["excluded_concept_ids"] == [
        "65576009",
        CYST_OF_PANCREAS_ID,
        CYST_OF_KIDNEY_ID,
        MASS_OF_UTERINE_ADNEXA_ID,
        CYST_OF_OVARY_ID,
    ]
