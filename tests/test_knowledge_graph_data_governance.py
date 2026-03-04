"""Tests for Knowledge Graph data governance boundary.

VT-LEO-AI-014: No patient personal data in the Knowledge Graph.
DPA DC-DPA-002 clauses 5.3, 6.2: No reviewer identity in Knowledge Graph.

These tests verify that the writeback paths strip reviewer identity
and do not pass patient-identifiable data to the Knowledge Graph.
"""

from __future__ import annotations

import json
import re


def _make_candidate(
    terms: list[dict],
    reviewer: str = "test.reviewer@nhs.net",
) -> dict:
    sentences = [{"sentence_id": "s0", "terms": terms}]
    return {
        "c": {
            "candidate_id": "c1",
            "patient_id": "p1",
            "encounter_id": "enc1",
            "sentences_json": json.dumps(sentences),
        },
        "reviewer": reviewer,
    }


class TestTerminologyApiWritebackNoReviewerLeak:
    """Terminology API writeback must not leak reviewer identity."""

    def test_approved_by_is_source_tag(self):
        from services.terminology_api.app.services.writeback_service import (
            _extract_surface_form_rows,
        )

        candidate = _make_candidate(
            [
                {
                    "text": "CXR",
                    "coding": {"snomed_concept_id": "399208008", "score": 0.9},
                }
            ],
            reviewer="sarah.williams@gp-practice.nhs.uk",
        )
        rows, _ = _extract_surface_form_rows([candidate])

        assert len(rows) == 1
        assert rows[0]["approved_by"] == "hitl_approved"

    def test_no_email_in_any_field(self):
        from services.terminology_api.app.services.writeback_service import (
            _extract_surface_form_rows,
        )

        candidate = _make_candidate(
            [
                {
                    "text": "BP check",
                    "coding": {"snomed_concept_id": "75367002", "score": 0.85},
                }
            ],
            reviewer="alice.jones@hospital.nhs.uk",
        )
        rows, _ = _extract_surface_form_rows([candidate])
        row_str = json.dumps(rows)

        assert "alice" not in row_str.lower()
        assert "jones" not in row_str.lower()
        assert "nhs.uk" not in row_str.lower()

    def test_multiple_candidates_all_stripped(self):
        from services.terminology_api.app.services.writeback_service import (
            _extract_surface_form_rows,
        )

        candidates = [
            _make_candidate(
                [
                    {
                        "text": "headache",
                        "coding": {"snomed_concept_id": "25064002", "score": 0.9},
                    }
                ],
                reviewer="dr.a@nhs.net",
            ),
            _make_candidate(
                [
                    {
                        "text": "cough",
                        "coding": {"snomed_concept_id": "49727002", "score": 0.8},
                    }
                ],
                reviewer="dr.b@trust.nhs.uk",
            ),
        ]
        rows, stats = _extract_surface_form_rows(candidates)

        assert stats.candidates_scanned == 2
        for row in rows:
            assert row["approved_by"] == "hitl_approved"
            assert "@" not in json.dumps(row)


class TestApiWritebackNoReviewerLeak:
    """API-side writeback must not leak reviewer identity."""

    def test_approved_by_is_source_tag(self):
        from services.api.app.services.terminology_writeback_service import (
            _extract_surface_form_rows,
        )

        candidate = _make_candidate(
            [
                {
                    "text": "chest pain",
                    "coding": {"snomed_concept_id": "29857009", "score": 0.95},
                }
            ],
            reviewer="dr.smith@practice.nhs.uk",
        )
        rows, _ = _extract_surface_form_rows([candidate])

        assert len(rows) == 1
        assert rows[0]["approved_by"] == "hitl_approved"
        assert "dr.smith" not in json.dumps(rows)

    def test_no_reviewer_identity_in_any_row_field(self):
        from services.api.app.services.terminology_writeback_service import (
            _extract_surface_form_rows,
        )

        candidate = _make_candidate(
            [
                {
                    "text": "diabetes",
                    "coding": {"snomed_concept_id": "73211009", "score": 0.9},
                }
            ],
            reviewer="jane.doe@gp.nhs.uk",
        )
        rows, _ = _extract_surface_form_rows([candidate])
        row_str = json.dumps(rows)

        email_pattern = re.compile(r"[\w.\-+]+@[\w.\-]+\.\w+")
        assert not email_pattern.search(row_str)


class TestManualMappingDefaultCreatedBy:
    """Manual mapping endpoint must not default to a user-identifiable value."""

    def test_default_created_by_is_process_name(self):
        from services.api.app.routers.terminology import UpsertMappingRequest

        req = UpsertMappingRequest(
            normalized="chest x ray",
            form="chest X-ray",
            concept_id="399208008",
        )
        assert req.created_by == "manual_mapping"
        assert "@" not in req.created_by
