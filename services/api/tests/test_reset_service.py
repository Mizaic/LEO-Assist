"""Tests for reset service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.models.neo4j_schema import (
    CLEANUP_PATIENT_SHORTCUTS_FOR_CONCEPTS,
    DELETE_ENCOUNTER_DOCUMENTS,
    LIST_ENCOUNTER_DOCUMENT_CONCEPT_IDS,
)
from libs.cypher.cleanup_queries import (
    RESET_PATIENT_DOCUMENTS,
    RESET_PATIENT_DIRECT_SEMANTIC,
)
from app.services.reset_service import reset_encounter, reset_patient


def _make_encounter_session_sides(concept_ids=("111", "222")):
    """Build mock side_effect list for a full successful reset_encounter call."""
    return [
        [{"encounter_id": "e1"}],  # GET_ENCOUNTER
        MagicMock(single=MagicMock(return_value={"concept_ids": list(concept_ids)})),
        MagicMock(
            single=MagicMock(return_value={"deleted": 3})
        ),  # DELETE_ENCOUNTER_DOCUMENTS
        MagicMock(
            single=MagicMock(return_value={"deleted": 1})
        ),  # DELETE_ENCOUNTER_EPISODE_LINKS
        [
            {"shortcuts_deleted": 1},
            {"shortcuts_deleted": 2},
        ],  # CLEANUP_PATIENT_SHORTCUTS
        MagicMock(
            single=MagicMock(return_value={"deleted": 4})
        ),  # RESET_ENCOUNTER_REVIEW_QUEUE
        MagicMock(single=MagicMock(return_value={"llm_usage_deleted": 2})),
        MagicMock(single=MagicMock(return_value={"decisions_deleted": 5})),
        MagicMock(single=MagicMock(return_value={"encounters_cleared": 1})),
    ]


class TestResetPatient:
    """Tests for reset_patient()."""

    def test_returns_combined_deleted_count(self) -> None:
        session = MagicMock()
        session.run.side_effect = [
            [{"patient_id": "p1", "encounter_count": 2}],  # GET_PATIENT
            MagicMock(single=MagicMock(return_value={"links_deleted": 5})),
            MagicMock(single=MagicMock(return_value={"direct_deleted": 2})),
        ]
        result = reset_patient("p1", session)
        assert result["patient_id"] == "p1"
        assert result["links_deleted"] == 7
        assert "error" not in result

    def test_patient_not_found_returns_error(self) -> None:
        session = MagicMock()
        session.run.return_value = []
        result = reset_patient("nonexistent", session)
        assert result["error"] == "patient_not_found"
        assert result["links_deleted"] == 0

    def test_none_record_returns_zero(self) -> None:
        session = MagicMock()
        session.run.side_effect = [
            [{"patient_id": "p1", "encounter_count": 2}],
            MagicMock(single=MagicMock(return_value=None)),
            MagicMock(single=MagicMock(return_value={"direct_deleted": 0})),
        ]
        result = reset_patient("p1", session)
        assert result["links_deleted"] == 0

    def test_documents_query_uses_rel_type_syntax(self) -> None:
        """RESET_PATIENT_DOCUMENTS must use collect/UNWIND pattern (atomic count)."""
        assert "collect(r)" in RESET_PATIENT_DOCUMENTS
        assert "UNWIND" in RESET_PATIENT_DOCUMENTS
        assert "links_deleted" in RESET_PATIENT_DOCUMENTS
        # Old double-MATCH pattern must be gone
        assert RESET_PATIENT_DOCUMENTS.count("MATCH") == 1

    def test_direct_semantic_query_uses_rel_type_filter(self) -> None:
        """RESET_PATIENT_DIRECT_SEMANTIC must filter by relationship type, not node label."""
        assert "HAS_FINDING" in RESET_PATIENT_DIRECT_SEMANTIC
        assert "HAS_DISORDER" in RESET_PATIENT_DIRECT_SEMANTIC
        assert "HAS_CONCEPT" in RESET_PATIENT_DIRECT_SEMANTIC
        # Old label-based filter must be gone
        assert "SnomedConcept" not in RESET_PATIENT_DIRECT_SEMANTIC


class TestResetEncounter:
    """Tests for reset_encounter()."""

    def test_returns_all_cleanup_counts(self) -> None:
        session = MagicMock()
        session.run.side_effect = _make_encounter_session_sides()
        result = reset_encounter("p1", "e1", session)
        assert result["patient_id"] == "p1"
        assert result["encounter_id"] == "e1"
        assert result["links_deleted"] == 3
        assert result["episode_links_deleted"] == 1
        assert result["shortcuts_deleted"] == 3
        assert result["review_queue_deleted"] == 4
        assert result["llm_usage_deleted"] == 2
        assert result["coding_decisions_deleted"] == 5

    def test_encounter_not_found_returns_error(self) -> None:
        session = MagicMock()
        session.run.return_value = []
        result = reset_encounter("p1", "missing", session)
        assert result["error"] == "encounter_not_found"
        assert result["episode_links_deleted"] == 0
        assert result["links_deleted"] == 0

    def test_no_concepts_skips_shortcut_cleanup(self) -> None:
        """If the encounter had no DOCUMENTS links, shortcut cleanup is skipped."""
        session = MagicMock()
        session.run.side_effect = [
            [{"encounter_id": "e1"}],
            MagicMock(single=MagicMock(return_value={"concept_ids": []})),
            MagicMock(single=MagicMock(return_value={"deleted": 0})),
            MagicMock(single=MagicMock(return_value={"deleted": 0})),
            # No shortcut call
            MagicMock(single=MagicMock(return_value={"deleted": 0})),
            MagicMock(single=MagicMock(return_value={"llm_usage_deleted": 0})),
            MagicMock(single=MagicMock(return_value={"decisions_deleted": 0})),
            MagicMock(single=MagicMock(return_value={"encounters_cleared": 1})),
        ]
        reset_encounter("p1", "e1", session)
        shortcut_calls = [
            c
            for c in session.run.call_args_list
            if c.args and c.args[0] == CLEANUP_PATIENT_SHORTCUTS_FOR_CONCEPTS
        ]
        assert shortcut_calls == []

    def test_scopes_deletes_to_correct_encounter_and_concepts(self) -> None:
        session = MagicMock()
        session.run.side_effect = _make_encounter_session_sides()

        reset_encounter("p1", "e1", session)

        docs_calls = [
            c
            for c in session.run.call_args_list
            if c.args and c.args[0] == DELETE_ENCOUNTER_DOCUMENTS
        ]
        assert len(docs_calls) == 1
        assert docs_calls[0].kwargs["patient_id"] == "p1"
        assert docs_calls[0].kwargs["encounter_id"] == "e1"

        concept_calls = [
            c
            for c in session.run.call_args_list
            if c.args and c.args[0] == LIST_ENCOUNTER_DOCUMENT_CONCEPT_IDS
        ]
        assert len(concept_calls) == 1
        assert concept_calls[0].kwargs["encounter_id"] == "e1"

        shortcut_calls = [
            c
            for c in session.run.call_args_list
            if c.args and c.args[0] == CLEANUP_PATIENT_SHORTCUTS_FOR_CONCEPTS
        ]
        assert len(shortcut_calls) == 1
        assert shortcut_calls[0].kwargs["concept_ids"] == ["111", "222"]
