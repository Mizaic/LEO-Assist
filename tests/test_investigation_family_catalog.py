"""The investigation-family catalogue, checked without touching Neo4j.

An InvestigationFamily answers one question: does this coded fact prove
the recommended test was already carried out? Getting a member wrong
either leaves a completed test looking outstanding, or marks an
outstanding test as done. The second is the dangerous one.

Atlas: DI-B3B44F09.
"""

from __future__ import annotations

from libs.guidelines.investigation_family_catalog import (
    CA125_FAMILY_ID,
    FIT_FAMILY_ID,
    PELVIC_US_FAMILY_ID,
    SHARED_FAMILIES,
    family_ids_for_concept,
    index_family_rows,
    seed_family_rows,
)


def _index():
    return index_family_rows(seed_family_rows())


def test_every_approved_ca125_surface_form_target_counts() -> None:
    """All three approved "CA 125" mappings must prove the test was done.

    The knowledge graph holds three approved SurfaceForms for the phrase
    "CA 125", resolving to 80529009, 909121000000107 and
    1027511000000100. Which one the resolver picks is not something the
    referral controls, so if any is missing from the family, whether a
    completed test reads as done becomes a coin toss.
    """
    index = _index()
    for concept_id in ("80529009", "909121000000107", "1027511000000100"):
        proven = family_ids_for_concept(concept_id, index)
        assert (
            "1000461000000109" in proven
        ), f"{concept_id} is an approved CA 125 mapping but proves nothing"


def test_a_suspected_cancer_situation_is_not_evidence_of_a_test() -> None:
    """397682005 is a suspicion, not a measurement.

    A real referral coded a normal CA 125 of 6 ku/L to "Malignant
    neoplasm of female genital organ suspected". Even so, that concept
    must never count as proof the test happened.
    """
    assert family_ids_for_concept("397682005", _index()) == set()


def test_a_substance_code_is_not_evidence_of_a_test() -> None:
    """Naming the analyte is not the same as measuring it."""
    assert family_ids_for_concept("103084007", _index()) == set()


def test_an_abdomen_only_scan_does_not_prove_the_pelvis_was_imaged() -> None:
    assert PELVIC_US_FAMILY_ID not in family_ids_for_concept("45036003", _index())


def test_each_family_is_self_consistent() -> None:
    """Every member of a family proves every other member."""
    index = _index()
    for family in SHARED_FAMILIES:
        for member in family["members"]:
            assert family_ids_for_concept(member, index) >= set(family["members"])


def test_the_three_missed_investigations_all_have_a_family() -> None:
    assert {PELVIC_US_FAMILY_ID, CA125_FAMILY_ID, FIT_FAMILY_ID} == {
        family["family_id"] for family in SHARED_FAMILIES
    }
