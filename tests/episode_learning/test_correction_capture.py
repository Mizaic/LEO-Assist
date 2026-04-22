"""Unit tests for libs/episode_learning/correction_capture.py."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from libs.episode_learning.correction_capture import (
    CorrectionEvent,
    capture_corrections_from_audit,
)


def _row(**overrides):
    base = {
        "id": "audit-1",
        "type": "EpisodeManualAttach",
        "subtype": "episode_manual_edit",
        "actor_email": "qa@example.com",
        "actor_role": "qa-ra-lead",
        "episode_id": "ep-1",
        "patient_id": "p-1",
        "before_json": json.dumps({"suspected_site": "breast"}),
        "after_json": json.dumps({"suspected_site": "breast", "status": "open"}),
        "notes": "manual",
        "correction_target": "detector_boundary",
        "created_at_iso": "2026-04-22T10:00:00+00:00",
    }
    base.update(overrides)
    return base


def test_basic_capture_returns_normalised_event():
    events = capture_corrections_from_audit([_row()])
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, CorrectionEvent)
    assert ev.audit_id == "audit-1"
    assert ev.correction_target == "detector_boundary"
    assert ev.site_key == "breast"
    assert ev.label == 1
    assert ev.captured_at == datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc)


def test_invalid_correction_target_is_coerced_to_other():
    events = capture_corrections_from_audit(
        [_row(correction_target="garbage_value")]
    )
    assert events[0].correction_target == "other"


def test_missing_required_keys_drops_row():
    events = capture_corrections_from_audit(
        [
            _row(id=""),
            _row(type=""),
            _row(episode_id=""),
            _row(),
        ]
    )
    assert [e.audit_id for e in events] == ["audit-1"]


def test_revert_event_label_is_zero():
    events = capture_corrections_from_audit(
        [_row(type="EpisodeManualRevert")]
    )
    assert events[0].label == 0


def test_site_key_falls_back_to_unknown_when_absent():
    events = capture_corrections_from_audit(
        [_row(before_json="", after_json="")]
    )
    assert events[0].site_key == "unknown"


def test_naive_datetime_string_gets_utc_tz():
    events = capture_corrections_from_audit(
        [_row(created_at_iso="2026-04-22T10:00:00")]
    )
    assert events[0].captured_at.tzinfo is not None


def test_dict_before_after_handled_directly():
    events = capture_corrections_from_audit(
        [
            _row(
                before_json={"suspected_site": "lung"},
                after_json={"suspected_site": "lung"},
            )
        ]
    )
    assert events[0].site_key == "lung"
