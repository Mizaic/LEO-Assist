"""Tests for canonical episode code derivation.

Atlas trace:
  DI: DI-885930F8
"""

from __future__ import annotations

from datetime import date

from libs.pipeline.canonical_episode_code import derive_canonical_code
from libs.pipeline_graph.subgraphs.coding_qa import CodedEntityRecord


def _rec(
    encounter_id: str,
    *,
    occurred_on: date,
    concept_id: str,
    intent: str,
    site_key: str = "breast",
    role: str = "diagnosis",
    display: str = "",
):
    return CodedEntityRecord(
        encounter_id=encounter_id,
        occurred_on=occurred_on,
        concept_id=concept_id,
        display_name=display or concept_id,
        site_key=site_key,
        intent=intent,
        role=role,
    )


def test_returns_none_for_empty_records():
    assert derive_canonical_code([], suspected_site="breast") is None


def test_returns_none_when_no_on_site_records():
    records = [
        _rec("e-1", occurred_on=date(2024, 3, 1), concept_id="123", intent="confirmed", site_key="lung")
    ]
    assert derive_canonical_code(records, suspected_site="breast") is None


def test_picks_confirmed_when_available():
    records = [
        _rec("e-1", occurred_on=date(2024, 3, 1), concept_id="395557000", intent="suspected"),
        _rec("e-2", occurred_on=date(2024, 4, 1), concept_id="254837009", intent="confirmed"),
    ]
    code = derive_canonical_code(records, suspected_site="breast")
    assert code is not None
    assert code.intent == "confirmed"
    assert code.concept_id == "254837009"


def test_picks_most_specific_concept_among_confirmed():
    records = [
        _rec("e-1", occurred_on=date(2024, 3, 1), concept_id="123", intent="confirmed"),
        _rec("e-2", occurred_on=date(2024, 3, 5), concept_id="123456789", intent="confirmed"),
    ]
    code = derive_canonical_code(records, suspected_site="breast")
    assert code is not None
    assert code.concept_id == "123456789"


def test_falls_back_to_suspected_when_no_confirmed():
    records = [
        _rec("e-1", occurred_on=date(2024, 3, 1), concept_id="395557000", intent="suspected"),
    ]
    code = derive_canonical_code(records, suspected_site="breast")
    assert code is not None
    assert code.intent == "suspected"
    assert code.concept_id == "395557000"


def test_derivation_trace_lists_supporting_encounters():
    records = [
        _rec("e-1", occurred_on=date(2024, 3, 1), concept_id="254837009", intent="confirmed"),
        _rec("e-2", occurred_on=date(2024, 3, 5), concept_id="254837009", intent="confirmed"),
    ]
    code = derive_canonical_code(records, suspected_site="breast")
    assert code is not None
    assert len(code.derivation_trace) == 2
    assert all("254837009" in t for t in code.derivation_trace)


def test_confidence_higher_for_confirmed_than_suspected():
    confirmed = derive_canonical_code(
        [
            _rec("e-1", occurred_on=date(2024, 3, 1), concept_id="254837009", intent="confirmed"),
        ],
        suspected_site="breast",
    )
    suspected = derive_canonical_code(
        [
            _rec("e-1", occurred_on=date(2024, 3, 1), concept_id="395557000", intent="suspected"),
        ],
        suspected_site="breast",
    )
    assert confirmed is not None and suspected is not None
    assert confirmed.confidence > suspected.confidence
