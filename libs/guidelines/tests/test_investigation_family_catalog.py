"""InvestigationFamily catalog is the shared already-done family surface.

Atlas trace: DI-B3B44F09
"""

from __future__ import annotations

from libs.guidelines.investigation_family import (
    curated_family_ids,
    evidence_ids_for_action,
)
from libs.guidelines.investigation_family_catalog import (
    family_ids_for_concept,
    index_family_rows,
)


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
