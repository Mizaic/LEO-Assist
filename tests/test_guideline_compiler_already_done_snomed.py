"""Compiler populates already_done_evidence_ids from SNOMED ontology at compile time.

Without SNOMED data the already-done check only matches the exact procedure
code. A patient who has an abnormal USS *finding* will never have the USS
*procedure* code, so the check silently fails and the USS recommendation
fires even when the scan has been done.

The fix threads the Neo4j session into _compiled_action_item so the compiler
can query SNOMED at build time and pre-populate already_done_evidence_ids
with related finding and observable codes.

Atlas trace:
  DI: DI-B3B44F09  (already-done evidence ids)
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B3B44F09")
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Fake Neo4j session helpers
# ---------------------------------------------------------------------------

def _fake_session_returning(related_row: dict):
    """Fake session whose .run() returns a single row matching related_row."""

    class _FakeRecord:
        def __init__(self, data):
            self._data = data

        def __iter__(self):
            return iter(self._data.items())

        def get(self, key, default=None):
            return self._data.get(key, default)

        def __getitem__(self, key):
            return self._data[key]

    class _FakeResult:
        def __init__(self, row):
            self._row = row

        def single(self):
            return _FakeRecord(self._row)

        def __iter__(self):
            yield _FakeRecord(self._row)

    class _FakeSession:
        def run(self, query, **kwargs):
            return _FakeResult(related_row)

    return _FakeSession()


# A USS-like procedure: has an observable (pelvic scan result) that is
# interpreted_by_findings = Abnormal USS (168750003)
_USS_RELATED_ROW = {
    "interpreted_by_findings": [
        {
            "id": "168750003",
            "fsn": "Abnormal ultrasound (finding)",
            "semantic_tag": "finding",
            "rel": "interpreted_by_findings",
        }
    ],
    "has_components": [
        {
            "id": "399034003",
            "fsn": "Pelvis ultrasound result (observable entity)",
            "semantic_tag": "observable entity",
            "rel": "has_components",
        }
    ],
    "component_of_procedures": [],
    "interprets_observables": [],
    "associated_findings": [],
    "finding_sites": [],
    "procedure_sites": [],
}


# ---------------------------------------------------------------------------
# Tests for _compiled_action_item
# ---------------------------------------------------------------------------


class TestCompiledActionItemSnomed:
    def test_without_session_only_contains_self(self):
        """No session -> evidence ids = just the procedure concept itself."""
        from services.terminology_api.app.services.guideline_compiler import (
            GuidelineCompiler,
        )

        item = {"concept_id": "241491008", "name": "USS abdomen pelvis", "strength": "routine"}
        result = GuidelineCompiler._compiled_action_item(item, "241491008", session=None)

        assert result["already_done_evidence_ids"] == ["241491008"]

    def test_with_session_includes_snomed_neighbours(self):
        """Session provided -> evidence ids include SNOMED-related findings."""
        from services.terminology_api.app.services.guideline_compiler import (
            GuidelineCompiler,
        )

        session = _fake_session_returning(_USS_RELATED_ROW)
        item = {"concept_id": "241491008", "name": "USS abdomen pelvis", "strength": "routine"}
        result = GuidelineCompiler._compiled_action_item(item, "241491008", session=session)

        ids = set(result["already_done_evidence_ids"])
        assert "241491008" in ids, "procedure itself must always be in evidence ids"
        assert "168750003" in ids, "interpreted_by finding must be in evidence ids"
        assert "399034003" in ids, "HAS_COMPONENT observable must be in evidence ids"

    def test_session_failure_falls_back_to_self_only(self):
        """SNOMED query failure is silent -- evidence ids fall back to procedure only."""
        from services.terminology_api.app.services.guideline_compiler import (
            GuidelineCompiler,
        )

        class _FailingSession:
            def run(self, *args, **kwargs):
                raise ConnectionError("Neo4j unreachable")

        item = {"concept_id": "241491008", "name": "USS", "strength": "routine"}
        result = GuidelineCompiler._compiled_action_item(
            item, "241491008", session=_FailingSession()
        )

        assert "241491008" in result["already_done_evidence_ids"]


# ---------------------------------------------------------------------------
# Integration: action_already_done fires when evidence ids overlap patient
# ---------------------------------------------------------------------------


class TestAlreadyDoneFiresViaPrecompiledEvidence:
    def test_abnormal_uss_finding_suppresses_uss_recommendation(self):
        """Pre-compiled evidence ids containing 168750003 suppress USS when patient has it."""
        from libs.guidelines.action_already_done import action_already_done

        action = {
            "concept_id": "241491008",
            "name": "USS abdomen pelvis",
            "strength": "routine",
            "already_done_evidence_ids": ["241491008", "168750003", "399034003"],
        }
        # Patient has 168750003 (Abnormal USS finding) but NOT the procedure code.
        patient_codes = ["168750003"]

        assert action_already_done(action, patient_codes, observations=None) is True

    def test_unrelated_finding_does_not_suppress(self):
        """A different finding code does not falsely suppress the USS action."""
        from libs.guidelines.action_already_done import action_already_done

        action = {
            "concept_id": "241491008",
            "name": "USS abdomen pelvis",
            "strength": "routine",
            "already_done_evidence_ids": ["241491008", "168750003"],
        }
        # Patient has a totally unrelated code.
        patient_codes = ["73211009"]  # Diabetes mellitus

        assert action_already_done(action, patient_codes, observations=None) is False
