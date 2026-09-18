"""InvestigationFamily catalog is the shared already-done family surface.

Atlas trace: DI-B3B44F09
"""

from __future__ import annotations

from libs.guidelines.action_already_done import action_already_done
from libs.guidelines.investigation_family import (
    curated_family_ids,
    evidence_ids_for_action,
)
from libs.guidelines.investigation_family_catalog import (
    CA125_FAMILY_ID,
    CA125_MEMBER_IDS,
    FIT_FAMILY_ID,
    FIT_MEMBER_IDS,
    PELVIC_US_MEMBER_IDS,
    SHARED_FAMILIES,
    family_ids_for_concept,
    index_family_rows,
    seed_family_rows,
)

CA125_ACTION = {
    "concept_id": "909121000000107",
    "name": "Measurement of cancer antigen 125 in serum specimen (procedure)",
    "strength": "consider",
}
PELVIC_US_ACTION = {
    "concept_id": "418394000",
    "name": "Ultrasound scan of abdomen and pelvis (procedure)",
    "strength": "offer",
}
FIT_KIT_ACTION = {
    "concept_id": "149421000000109",
    "name": "Provision of faecal immunochemical test kit (procedure)",
    "strength": "offer",
}


def test_index_maps_each_member_to_the_whole_family() -> None:
    rows = [
        {
            "family_id": "pelvic-us",
            "members": ["418394000", "24848001", "426491001"],
        }
    ]
    index = index_family_rows(rows)
    assert family_ids_for_concept("24848001", index) == {
        "418394000",
        "24848001",
        "426491001",
    }
    assert family_ids_for_concept("73211009", index) == set()


def test_pelvic_codes_are_not_hardcoded_without_catalog() -> None:
    assert curated_family_ids("418394000") == set()
    assert "24848001" not in evidence_ids_for_action("418394000")


def test_catalog_family_adds_evidence_ids() -> None:
    families = {"418394000": {"418394000", "24848001", "426491001"}}
    ids = evidence_ids_for_action("418394000", families=families)
    assert "24848001" in ids
    assert "426491001" in ids


def test_load_family_index_from_session() -> None:
    from libs.guidelines.investigation_family_catalog import load_family_index

    class _Session:
        def run(self, query, **kwargs):
            return [
                {
                    "family_id": "pelvic-us",
                    "members": ["418394000", "24848001"],
                }
            ]

    index = load_family_index(_Session())
    assert "24848001" in index["418394000"]


def test_load_family_index_empty_when_lookup_fails() -> None:
    from libs.guidelines.investigation_family_catalog import load_family_index

    class _Failing:
        def run(self, query, **kwargs):
            raise ConnectionError("down")

    assert load_family_index(None) == {}
    assert load_family_index(_Failing()) == {}


def test_seed_rows_cover_every_shared_family() -> None:
    rows = seed_family_rows()
    assert {row["family_id"] for row in rows} == {
        family["family_id"] for family in SHARED_FAMILIES
    }
    for row in rows:
        assert row["members"], f"{row['family_id']} has no members"


def test_serum_ca125_result_marks_the_ca125_action_done() -> None:
    """NHS 4568668417: CA125 6 ku/L on 2 Jun 2026 means 1.5.3 is complete."""
    families = index_family_rows(seed_family_rows())
    assert action_already_done(
        CA125_ACTION, ["1000461000000109"], [], families=families
    )
    assert action_already_done(
        CA125_ACTION, ["1027511000000100"], [], families=families
    )


def test_ca125_substance_code_does_not_mark_the_action_done() -> None:
    """A substance code is not evidence that the test was carried out."""
    families = index_family_rows(seed_family_rows())
    assert "103084007" not in CA125_MEMBER_IDS
    assert not action_already_done(CA125_ACTION, ["103084007"], [], families=families)


def test_transvaginal_pelvis_scan_marks_the_ultrasound_action_done() -> None:
    """NHS 4568668417: US pelvis on 24 Jun 2026 means 1.5.2 is complete."""
    families = index_family_rows(seed_family_rows())
    assert "315011000000105" in PELVIC_US_MEMBER_IDS
    assert action_already_done(
        PELVIC_US_ACTION, ["315011000000105"], [], families=families
    )


def test_abdomen_only_scan_does_not_cover_abdomen_and_pelvis() -> None:
    """An abdomen scan leaves the pelvis unimaged, so the action stands."""
    families = index_family_rows(seed_family_rows())
    assert "45036003" not in PELVIC_US_MEMBER_IDS
    assert not action_already_done(
        PELVIC_US_ACTION, ["45036003"], [], families=families
    )


def test_fit_family_is_seeded_not_only_a_packaged_fallback() -> None:
    """The graph owns the FIT family; Python keeps only the fallback."""
    families = index_family_rows(seed_family_rows())
    assert FIT_FAMILY_ID in {family["family_id"] for family in SHARED_FAMILIES}
    assert "149421000000109" in FIT_MEMBER_IDS
    assert "1049361000000101" in FIT_MEMBER_IDS
    assert action_already_done(
        FIT_KIT_ACTION, ["1049361000000101"], [], families=families
    )


def test_family_ids_are_distinct() -> None:
    ids = [family["family_id"] for family in SHARED_FAMILIES]
    assert len(ids) == len(set(ids))
    assert CA125_FAMILY_ID in ids
