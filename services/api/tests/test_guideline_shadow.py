"""Unit tests for the historic guideline shadow-diff (DI-8DD23CE2).

Fixture-vs-candidate comparison was retired with the TestPatient
library. Only the real-patient ("historic") comparison survives here.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services import guideline_shadow as shadow


def _eval_side_effect(payload, **kwargs):
    version = kwargs.get("ruleset_version")
    if version == "v-cand":
        return {"matched_rules": [{"rule_id": "r1"}, {"rule_id": "r2"}]}
    return {"matched_rules": [{"rule_id": "r1"}, {"rule_id": "r3"}]}


def test_shadow_diff_reports_gained_and_lost_without_activate():
    patient_graph = MagicMock()
    with (
        patch.object(
            shadow,
            "_read_source_payload",
            return_value=shadow.ShadowPatientPayload(
                codes=["123"], age=50, sex="female", name="historic:p1"
            ),
        ),
        patch.object(
            shadow,
            "_evaluate_against_terminology",
            side_effect=_eval_side_effect,
        ),
    ):
        report = shadow.shadow_diff(
            patient_graph,
            candidate_version="v-cand",
            baseline_version=None,
            source_patient_ids=["p1"],
            scope_type="global",
            scope_id="default",
        )

    assert report["live_pointer_unchanged"] is True
    assert report["candidate_version"] == "v-cand"
    assert report["baseline_version"] == "current"
    assert report["changed_count"] == 1
    row = report["results"][0]
    assert row["gained"] == ["r2"]
    assert row["lost"] == ["r3"]
    assert row["unchanged"] == ["r1"]


def test_shadow_diff_requires_candidate_version():
    with pytest.raises(ValueError, match="candidate_version"):
        shadow.shadow_diff(MagicMock(), candidate_version="", source_patient_ids=["p1"])


def test_shadow_diff_requires_source_patient_ids():
    with pytest.raises(ValueError, match="source_patient_ids"):
        shadow.shadow_diff(MagicMock(), candidate_version="v1", source_patient_ids=[])


def test_shadow_diff_missing_source_patient_reports_error_row():
    patient_graph = MagicMock()
    with patch.object(shadow, "_read_source_payload", return_value=None):
        report = shadow.shadow_diff(
            patient_graph,
            candidate_version="v1",
            source_patient_ids=["missing"],
        )
    assert report["error_count"] == 1
    assert report["results"][0]["error"] == "Source patient not found"


def test_list_source_patients_delegates_to_patient_graph():
    patient_graph = MagicMock()
    patient_graph.run.return_value = [{"id": "p1", "display_name": "p1", "encounter_count": 3}]
    rows = shadow.list_source_patients(patient_graph, limit=10)
    assert rows == [{"id": "p1", "display_name": "p1", "encounter_count": 3}]
    patient_graph.run.assert_called_once()
