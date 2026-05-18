"""Tests for episode coding cypher writes (mock-driver level).

Atlas trace:
  DI: DI-885930F8 (canonical code persistence)
  DI: DI-E8FE404D (QA result persistence)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.cypher.episode_coding_queries import (
    WRITE_CANONICAL_CODE,
    WRITE_QA_RESULT,
    ensure_episode_coding_indexes,
    write_canonical_code,
    write_qa_result,
)


def _mock_session(returned_row: dict | None = None):
    session = MagicMock()
    result = MagicMock()
    result.single.return_value = returned_row
    session.run.return_value = result
    return session


def test_ensure_indexes_runs_three_statements():
    session = _mock_session()
    ensure_episode_coding_indexes(session)
    assert session.run.call_count == 3


def test_ensure_indexes_swallows_individual_failures():
    session = MagicMock()
    session.run.side_effect = [Exception("boom"), MagicMock(), MagicMock()]
    ensure_episode_coding_indexes(session)
    assert session.run.call_count == 3


def test_write_canonical_code_passes_params_and_returns_row():
    row = {"episode_id": "ep-1", "concept_id": "254837009"}
    session = _mock_session(returned_row=row)
    out = write_canonical_code(
        session,
        episode_id="ep-1",
        concept_id="254837009",
        display_name="Malignant tumor of breast",
        intent="confirmed",
        modifiers=["primary"],
        confidence=0.95,
        derivation_trace=["enc-1::254837009"],
    )
    assert out == row
    args, kwargs = session.run.call_args
    assert args[0] == WRITE_CANONICAL_CODE
    assert kwargs["episode_id"] == "ep-1"
    assert kwargs["concept_id"] == "254837009"
    assert kwargs["modifiers"] == ["primary"]
    assert kwargs["confidence"] == 0.95


def test_write_canonical_code_returns_none_on_error():
    session = MagicMock()
    session.run.side_effect = Exception("db down")
    out = write_canonical_code(
        session,
        episode_id="ep-1",
        concept_id="254837009",
        display_name="x",
        intent="confirmed",
        modifiers=[],
        confidence=0.9,
        derivation_trace=[],
    )
    assert out is None


def test_write_qa_result_computes_severity_max():
    session = _mock_session(returned_row={"qa_run_id": "run-1", "flag_count": 2})
    flags = [
        {
            "flag_id": "f-1",
            "code": "trajectory_inversion",
            "severity": "medium",
            "summary": "...",
            "encounter_ids": ["e-1", "e-2"],
            "citation": "...",
        },
        {
            "flag_id": "f-2",
            "code": "site_mismatch",
            "severity": "high",
            "summary": "...",
            "encounter_ids": ["e-3"],
            "citation": "...",
        },
    ]
    write_qa_result(
        session,
        episode_id="ep-1",
        qa_run_id="run-1",
        flags=flags,
        summary="2 flags",
    )
    args, kwargs = session.run.call_args
    assert args[0] == WRITE_QA_RESULT
    assert kwargs["severity_max"] == "high"
    assert kwargs["flag_count"] == 2


def test_write_qa_result_with_no_flags_uses_low_severity():
    session = _mock_session(returned_row={"qa_run_id": "run-1", "flag_count": 0})
    write_qa_result(
        session,
        episode_id="ep-1",
        qa_run_id="run-1",
        flags=[],
        summary="clean",
    )
    args, kwargs = session.run.call_args
    assert kwargs["severity_max"] == "low"
