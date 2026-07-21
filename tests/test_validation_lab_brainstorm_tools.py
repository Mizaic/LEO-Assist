"""Tests for Validation Lab brainstorm tool wrappers.

Atlas: DI-EB716E68 / DO-A0ADDB38 / VT-C6B93AF0
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_search_snomed_returns_candidates() -> None:
    from libs.validation_lab.brainstorm_tools import search_snomed

    fake = MagicMock()
    fake.search.return_value = [
        {
            "concept_id": "123",
            "preferred_term": "Acne fulminans",
            "semantic_tag": "disorder",
        }
    ]
    with patch(
        "libs.validation_lab.brainstorm_tools.TerminologyClient",
        return_value=fake,
    ):
        rows = search_snomed("acne fulminans")
    assert rows[0]["concept_id"] == "123"
    fake.search.assert_called_once()


def test_search_snomed_empty_query_returns_empty() -> None:
    from libs.validation_lab.brainstorm_tools import search_snomed

    assert search_snomed("  ") == []


def test_search_snomed_passes_semantic_tags() -> None:
    from libs.validation_lab.brainstorm_tools import search_snomed

    fake = MagicMock()
    fake.search.return_value = []
    with patch(
        "libs.validation_lab.brainstorm_tools.TerminologyClient",
        return_value=fake,
    ):
        search_snomed("CA125", semantic_tags=["observable_entity"])
    kwargs = fake.search.call_args.kwargs
    assert kwargs.get("semantic_tags") == ["observable_entity"]


def test_search_snomed_soft_fails() -> None:
    from libs.validation_lab.brainstorm_tools import search_snomed

    fake = MagicMock()
    fake.search.side_effect = RuntimeError("down")
    with patch(
        "libs.validation_lab.brainstorm_tools.TerminologyClient",
        return_value=fake,
    ):
        assert search_snomed("x") == []


def test_search_guidelines_filters_by_title() -> None:
    from libs.validation_lab.brainstorm_tools import search_guidelines

    with patch(
        "libs.validation_lab.brainstorm_tools._list_loaded_guidelines",
        return_value=[
            {"code": "NG12", "title": "Suspected cancer: recognition and referral"},
            {"code": "NG146", "title": "Osteoporosis fracture risk"},
        ],
    ):
        hits = search_guidelines("osteoporosis")
    assert len(hits) == 1
    assert hits[0]["code"] == "NG146"


def test_search_guidelines_soft_fails() -> None:
    from libs.validation_lab.brainstorm_tools import search_guidelines

    with patch(
        "libs.validation_lab.brainstorm_tools._list_loaded_guidelines",
        side_effect=RuntimeError("kg down"),
    ):
        assert search_guidelines("x") == []
