"""VT-LEO-AI-148 -- Diagnosis-aware open-episode rescue + first_seen_date persistence.

DI-LEO-AI-150: Verifies _rescue_diagnosis_for_open_episode helper and the
_build_open_episode rescue wiring.
DI-LEO-AI-145 (defect fix): Verifies first_seen_date is now persisted on
the EpisodeOfCare node when _build_open_episode runs.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from services.analysis_worker.app.analyzers.episode_builder import (
    _config as cfg,
)
from services.analysis_worker.app.analyzers.episode_builder._builder import (
    _build_open_episode,
    _rescue_diagnosis_for_open_episode,
)
from services.analysis_worker.app.analyzers.episode_builder._types import (
    BuildContext,
    EpisodeBuildResult,
    _SpecialistClaim,
)


def _diag_anchor(
    enc_id: str,
    enc_date: str,
    *,
    concept_name: str = "Malignant tumour of breast",
    assertion: str = "present",
    is_pathway_completion: bool = False,
) -> dict[str, Any]:
    return {
        "encounter_id": enc_id,
        "encounter_date": enc_date,
        "concept_name": concept_name,
        "assertion": assertion,
        "is_pathway_completion": is_pathway_completion,
    }


# ---------------------------------------------------------------------------
# VT-148-TC-001..004: _rescue_diagnosis_for_open_episode helper
# ---------------------------------------------------------------------------
class TestRescueHelper:
    def test_picks_earliest_in_window_diagnosis(self):
        ref_date = date(2025, 1, 10)
        anchors = [
            _diag_anchor("d-001", "2025-04-10"),
            _diag_anchor("d-002", "2025-02-09"),
        ]
        result = _rescue_diagnosis_for_open_episode(anchors, "breast", ref_date)
        assert result is not None
        rescue_date, rescue_anchors = result
        assert rescue_date == date(2025, 2, 9)
        assert [a["encounter_id"] for a in rescue_anchors] == ["d-002"]

    def test_returns_none_when_no_anchors(self):
        assert _rescue_diagnosis_for_open_episode([], "breast", date(2025, 1, 1)) is None

    def test_returns_none_when_anchor_before_ref(self):
        ref_date = date(2025, 5, 1)
        anchors = [_diag_anchor("d-001", "2025-04-30")]
        assert (
            _rescue_diagnosis_for_open_episode(anchors, "breast", ref_date) is None
        )

    def test_returns_none_when_anchor_after_window(self):
        ref_date = date(2025, 1, 1)
        out_of_window = (
            ref_date + timedelta(days=cfg.STALE_HARD_DAYS + 1)
        ).isoformat()
        anchors = [_diag_anchor("d-001", out_of_window)]
        assert (
            _rescue_diagnosis_for_open_episode(anchors, "breast", ref_date) is None
        )

    def test_returns_none_when_ref_date_none(self):
        anchors = [_diag_anchor("d-001", "2025-02-01")]
        assert _rescue_diagnosis_for_open_episode(anchors, "breast", None) is None

    def test_lung_diagnosis_on_breast_referral_returns_none(self):
        anchors = [
            _diag_anchor(
                "d-001", "2025-02-09", concept_name="Malignant tumour of lung"
            )
        ]
        assert (
            _rescue_diagnosis_for_open_episode(anchors, "breast", date(2025, 1, 10))
            is None
        )

    def test_unknown_diagnosis_matches_any_site(self):
        anchors = [
            _diag_anchor(
                "d-001",
                "2025-02-09",
                concept_name="Cancer (unspecified)",
            )
        ]
        result = _rescue_diagnosis_for_open_episode(
            anchors, "breast", date(2025, 1, 10)
        )
        assert result is not None
        assert result[1][0]["encounter_id"] == "d-001"

    def test_same_site_diagnosis_matches(self):
        anchors = [_diag_anchor("d-001", "2025-02-09")]
        result = _rescue_diagnosis_for_open_episode(
            anchors, "breast", date(2025, 1, 10)
        )
        assert result is not None
        assert result[1][0]["encounter_id"] == "d-001"

    def test_possible_assertion_does_not_trigger(self):
        anchors = [_diag_anchor("d-001", "2025-02-09", assertion="possible")]
        assert (
            _rescue_diagnosis_for_open_episode(anchors, "breast", date(2025, 1, 10))
            is None
        )

    def test_pathway_completion_does_not_trigger(self):
        anchors = [
            _diag_anchor("d-001", "2025-02-09", is_pathway_completion=True)
        ]
        assert (
            _rescue_diagnosis_for_open_episode(anchors, "breast", date(2025, 1, 10))
            is None
        )


# ---------------------------------------------------------------------------
# VT-148-TC-005..007: _build_open_episode rescue + first_seen_date persistence
# ---------------------------------------------------------------------------
class _AnchorsStub:
    """Minimal stand-in for AnchorResult used in the build_open_episode tests."""

    def __init__(
        self,
        diagnosis_anchors: list[dict[str, Any]] | None = None,
        first_seen_anchors: list[dict[str, Any]] | None = None,
        treatment_anchors: list[dict[str, Any]] | None = None,
        first_presentation_anchors: list[dict[str, Any]] | None = None,
        specialist_outcome_letter_anchors: list[dict[str, Any]] | None = None,
        benign_closure_anchors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.diagnosis_anchors = diagnosis_anchors or []
        self.first_seen_anchors = first_seen_anchors or []
        self.treatment_anchors = treatment_anchors or []
        self.first_presentation_anchors = first_presentation_anchors or []
        self.specialist_outcome_letter_anchors = (
            specialist_outcome_letter_anchors or []
        )
        self.benign_closure_anchors = benign_closure_anchors or []


def _make_ctx(anchors: _AnchorsStub) -> tuple[BuildContext, MagicMock, list]:
    """Build a BuildContext with a MagicMock patient_client.

    Returns (ctx, patient_client_mock, episode_ids_list).
    """
    client = MagicMock()
    client.run.return_value = []
    result = EpisodeBuildResult(patient_id="P-1")
    episode_ids: list[str] = []
    ctx = BuildContext(
        patient_id="P-1",
        anchors=anchors,
        patient_client=client,
        domain_id="oncology",
        result=result,
        episode_ids=episode_ids,
        phantom_sites=set(),
    )
    return ctx, client, episode_ids


def _capture_merge_call(client: MagicMock) -> dict:
    """Return the kwargs of the first MERGE_EPISODE call made on client."""
    for call in client.run.call_args_list:
        args, kwargs = call
        if args and "MERGE (ep:EpisodeOfCare" in args[0]:
            return kwargs
    raise AssertionError("MERGE episode call not found")


def _capture_link_call(client: MagicMock) -> dict | None:
    """Return the kwargs of the LINK_ENCOUNTERS call, if any."""
    for call in client.run.call_args_list:
        args, kwargs = call
        if args and "MATCH (ep:EpisodeOfCare" in args[0] and "IS_PART_OF" in args[0]:
            return kwargs
    return None


class TestBuildOpenEpisodeRescue:
    REF_DATE = "2025-01-10"
    DIAG_DATE = "2025-02-09"

    def _group(self) -> list[dict[str, Any]]:
        return [
            {
                "encounter_id": "ref-001",
                "encounter_date": self.REF_DATE,
                "concept_name": "Suspected breast cancer referral",
            }
        ]

    def test_rescue_promotes_status_to_completed(self):
        anchors = _AnchorsStub(
            diagnosis_anchors=[
                _diag_anchor("d-001", self.DIAG_DATE),
            ],
        )
        ctx, client, _ = _make_ctx(anchors)
        _build_open_episode(ctx, "breast", self._group(), _SpecialistClaim())

        kwargs = _capture_merge_call(client)
        assert kwargs["status"] == "completed"
        assert kwargs["end_date"] == self.DIAG_DATE
        assert kwargs["hitl_flag"] is True
        assert "Auto-completed: confirmed cancer diagnosis" in (
            kwargs["hitl_reason"] or ""
        )

    def test_rescue_writes_diagnosis_confirmed_link(self):
        anchors = _AnchorsStub(
            diagnosis_anchors=[
                _diag_anchor("d-001", self.DIAG_DATE),
            ],
        )
        ctx, client, _ = _make_ctx(anchors)
        _build_open_episode(ctx, "breast", self._group(), _SpecialistClaim())

        link_kwargs = _capture_link_call(client)
        assert link_kwargs is not None, "LINK_ENCOUNTERS not called"
        link_types = {
            (e["encounter_id"], e["milestone_type"])
            for e in link_kwargs["encounters"]
        }
        assert ("d-001", "diagnosis_confirmed") in link_types
        assert ("ref-001", "referral") in link_types

    def test_no_rescue_when_no_diagnosis_anchor(self):
        anchors = _AnchorsStub()
        ctx, client, _ = _make_ctx(anchors)
        _build_open_episode(ctx, "breast", self._group(), _SpecialistClaim())

        kwargs = _capture_merge_call(client)
        assert kwargs["status"] == "in_progress"
        assert kwargs["end_date"] is None

    def test_no_rescue_when_diagnosis_outside_window(self):
        out_of_window = (
            date(2025, 1, 10) + timedelta(days=cfg.STALE_HARD_DAYS + 30)
        ).isoformat()
        anchors = _AnchorsStub(
            diagnosis_anchors=[_diag_anchor("d-001", out_of_window)],
        )
        ctx, client, _ = _make_ctx(anchors)
        _build_open_episode(ctx, "breast", self._group(), _SpecialistClaim())

        kwargs = _capture_merge_call(client)
        assert kwargs["status"] == "in_progress"

    def test_no_rescue_when_diagnosis_specific_other_site(self):
        anchors = _AnchorsStub(
            diagnosis_anchors=[
                _diag_anchor(
                    "d-001",
                    self.DIAG_DATE,
                    concept_name="Malignant tumour of lung",
                )
            ],
        )
        ctx, client, _ = _make_ctx(anchors)
        _build_open_episode(ctx, "breast", self._group(), _SpecialistClaim())

        kwargs = _capture_merge_call(client)
        assert kwargs["status"] == "in_progress"


class TestFirstSeenDatePersistedOpenEpisode:
    """DI-LEO-AI-145 defect fix: first_seen_date must be persisted on
    the EpisodeOfCare node, not silently discarded after _write_episode.
    """

    def _group(self) -> list[dict[str, Any]]:
        return [
            {
                "encounter_id": "ref-001",
                "encounter_date": "2025-01-10",
                "concept_name": "Fast track referral for suspected breast cancer",
            }
        ]

    def test_first_seen_date_persisted_when_anchor_present(self):
        anchors = _AnchorsStub(
            first_seen_anchors=[
                {
                    "encounter_id": "fs-001",
                    "encounter_date": "2025-01-24",
                    "concept_name": "Text: first seen at fast-track/2WW clinic",
                }
            ],
        )
        ctx, client, _ = _make_ctx(anchors)
        _build_open_episode(ctx, "breast", self._group(), _SpecialistClaim())

        kwargs = _capture_merge_call(client)
        assert kwargs["first_seen_date"] == "2025-01-24"

    def test_first_seen_date_none_when_no_anchor(self):
        anchors = _AnchorsStub()
        ctx, client, _ = _make_ctx(anchors)
        _build_open_episode(ctx, "breast", self._group(), _SpecialistClaim())

        kwargs = _capture_merge_call(client)
        assert kwargs["first_seen_date"] is None
