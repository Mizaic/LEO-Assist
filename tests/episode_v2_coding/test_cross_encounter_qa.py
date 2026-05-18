"""Tests for cross-encounter QA.

Atlas trace:
  DI: DI-E8FE404D
"""

from __future__ import annotations

from datetime import date

from libs.pipeline_graph.subgraphs.coding_qa import (
    CodedEntityRecord,
    EpisodeMeta,
    run_cross_encounter_qa,
)


def _rec(
    encounter_id: str,
    *,
    occurred_on: date,
    concept_id: str,
    intent: str,
    site_key: str = "breast",
    role: str = "diagnosis",
):
    return CodedEntityRecord(
        encounter_id=encounter_id,
        occurred_on=occurred_on,
        concept_id=concept_id,
        display_name="",
        site_key=site_key,
        intent=intent,
        role=role,
    )


def _meta(suspected_site: str = "breast"):
    return EpisodeMeta(
        episode_id="ep-1", suspected_site=suspected_site, intent="confirmed"
    )


def test_trajectory_inversion_detected():
    records = [
        _rec("e-1", occurred_on=date(2024, 3, 1), concept_id="254837009", intent="confirmed"),
        _rec("e-2", occurred_on=date(2024, 4, 1), concept_id="395557000", intent="suspected"),
    ]
    flags = run_cross_encounter_qa(records, episode=_meta())
    codes = [f.code for f in flags]
    assert "trajectory_inversion" in codes


def test_no_trajectory_inversion_when_only_suspected_then_confirmed():
    records = [
        _rec("e-1", occurred_on=date(2024, 3, 1), concept_id="395557000", intent="suspected"),
        _rec("e-2", occurred_on=date(2024, 4, 1), concept_id="254837009", intent="confirmed"),
    ]
    flags = run_cross_encounter_qa(records, episode=_meta())
    assert all(f.code != "trajectory_inversion" for f in flags)


def test_code_contradiction_detected_when_no_rule_out():
    records = [
        _rec("e-1", occurred_on=date(2024, 3, 1), concept_id="109888004", intent="confirmed"),
        _rec("e-2", occurred_on=date(2024, 3, 8), concept_id="266569009", intent="suspected"),
    ]
    flags = run_cross_encounter_qa(records, episode=_meta())
    assert any(f.code == "code_contradiction" for f in flags)


def test_code_contradiction_resolved_by_rule_out():
    records = [
        _rec("e-1", occurred_on=date(2024, 3, 1), concept_id="109888004", intent="confirmed"),
        _rec("e-2", occurred_on=date(2024, 3, 8), concept_id="266569009", intent="ruled_out"),
    ]
    flags = run_cross_encounter_qa(records, episode=_meta())
    assert all(f.code != "code_contradiction" for f in flags)


def test_site_mismatch_detected():
    records = [
        _rec(
            "e-1",
            occurred_on=date(2024, 3, 1),
            concept_id="254837009",
            intent="confirmed",
            site_key="lung",
        )
    ]
    flags = run_cross_encounter_qa(records, episode=_meta(suspected_site="breast"))
    assert any(f.code == "site_mismatch" for f in flags)


def test_unknown_site_records_are_ignored_for_site_mismatch():
    records = [
        _rec(
            "e-1",
            occurred_on=date(2024, 3, 1),
            concept_id="254837009",
            intent="confirmed",
            site_key="unknown",
        )
    ]
    flags = run_cross_encounter_qa(records, episode=_meta(suspected_site="breast"))
    assert all(f.code != "site_mismatch" for f in flags)


def test_empty_records_returns_no_flags():
    flags = run_cross_encounter_qa([], episode=_meta())
    assert flags == []
