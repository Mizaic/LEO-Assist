"""Tests for `libs/audit/audit_emitter.py`.

Atlas trace:
  DO: DO-33C5C951
  DI: DI-B46AD5CE

Verifies the AuditEvent payloads emitted for every event type are valid
FHIR R4B AuditEvent shapes, contain the documented DICOM type codes, and
that the network POST is fire-and-forget (no exception propagated to the
caller even when the FHIR API is unreachable).
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from libs.audit.audit_emitter import (
    _build_event,
    emit_access_event,
    emit_application_event,
    emit_auth_event,
    emit_model_event,
    emit_ods_closure_alert,
    emit_ods_sync_summary,
    emit_pipeline_event,
)


def _wait_for_threads(timeout: float = 1.0) -> None:
    """Best-effort wait for any spawned daemon threads from emit_*."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if threading.active_count() <= 2:
            return
        time.sleep(0.02)


class TestBuildEvent:
    def test_resource_type_is_audit_event(self):
        e = _build_event(
            type_code="110114", type_display="User Authentication",
            outcome="0", agent_email="x@y", agent_role=None,
            source_service="core-api",
        )
        assert e["resourceType"] == "AuditEvent"

    def test_type_block_uses_dicom_system(self):
        e = _build_event(
            type_code="110114", type_display="User Authentication",
            outcome="0", agent_email=None, agent_role=None,
            source_service="core-api",
        )
        assert e["type"]["system"] == (
            "http://dicom.nema.org/resources/ontology/DCM"
        )
        assert e["type"]["code"] == "110114"

    def test_agent_falls_back_to_system_when_email_missing(self):
        e = _build_event(
            type_code="X", type_display="Y", outcome="0",
            agent_email=None, agent_role=None, source_service="svc",
        )
        assert e["agent"][0]["who"]["display"] == "system"
        assert e["agent"][0]["requestor"] is True

    def test_agent_role_omitted_when_not_provided(self):
        e = _build_event(
            type_code="X", type_display="Y", outcome="0",
            agent_email="a@b", agent_role=None, source_service="svc",
        )
        assert "role" not in e["agent"][0]

    def test_agent_role_added_when_provided(self):
        e = _build_event(
            type_code="X", type_display="Y", outcome="0",
            agent_email="a@b", agent_role="qa-ra-lead",
            source_service="svc",
        )
        assert e["agent"][0]["role"] == [{"text": "qa-ra-lead"}]

    def test_entity_omitted_when_no_entity_id(self):
        e = _build_event(
            type_code="X", type_display="Y", outcome="0",
            agent_email="a@b", agent_role=None, source_service="svc",
        )
        assert "entity" not in e

    def test_entity_added_when_id_provided(self):
        e = _build_event(
            type_code="X", type_display="Y", outcome="0",
            agent_email="a@b", agent_role=None, source_service="svc",
            entity_id="PAT-9", entity_type="patient",
        )
        assert e["entity"][0]["what"]["identifier"]["value"] == "PAT-9"
        assert e["entity"][0]["type"]["display"] == "patient"


class TestEmitterShapes:
    """Each emitter wires the right DICOM code into _build_event."""

    @pytest.mark.parametrize("emitter,kwargs,expected_code", [
        (emit_auth_event, {"outcome": "0", "agent_email": "x@y"}, "110114"),
        (emit_access_event, {"outcome": "0", "agent_email": "x@y"}, "110110"),
        (emit_model_event, {"outcome": "0", "action": "load"}, "110153"),
        (emit_pipeline_event, {"outcome": "0", "patient_id": "P1"}, "110112"),
        (emit_application_event, {"outcome": "0"}, "110153"),
    ])
    def test_emitter_uses_documented_dicom_code(self, emitter, kwargs,
                                                expected_code):
        with patch("libs.audit.audit_emitter._emit_async") as mock_emit:
            emitter(**kwargs)
        mock_emit.assert_called_once()
        event = mock_emit.call_args.args[0]
        assert event["type"]["code"] == expected_code


class TestOdsEmitters:
    def test_ods_sync_summary_uses_success_outcome(self):
        with patch("libs.audit.audit_emitter._emit_async") as mock_emit:
            emit_ods_sync_summary(
                run_id="R1", checked=10, mismatches=0,
                closures=0, errors=0, aborted=False,
            )
        event = mock_emit.call_args.args[0]
        assert event["outcome"] == "0"
        assert "complete" in event["entity"][0]["type"]["display"] or \
               "ods-sync-run" in event["entity"][0]["type"]["display"]

    def test_ods_sync_summary_uses_failure_outcome_when_aborted(self):
        with patch("libs.audit.audit_emitter._emit_async") as mock_emit:
            emit_ods_sync_summary(
                run_id="R1", checked=10, mismatches=2,
                closures=1, errors=3, aborted=True,
            )
        event = mock_emit.call_args.args[0]
        assert event["outcome"] == "8"

    def test_ods_closure_alert_uses_minor_failure_outcome(self):
        with patch("libs.audit.audit_emitter._emit_async") as mock_emit:
            emit_ods_closure_alert(
                org_id="O1", org_name="Acme GP",
                ods_code="X12", run_id="R1",
            )
        event = mock_emit.call_args.args[0]
        assert event["outcome"] == "4"


class TestFireAndForget:
    """`_emit_async` MUST never raise to the caller, even when httpx fails."""

    def test_emit_does_not_raise_on_network_failure(self):
        with patch(
            "libs.audit.audit_emitter.httpx.post",
            side_effect=ConnectionError("refused"),
        ):
            emit_auth_event(outcome="0", agent_email="x@y")
            _wait_for_threads()

    def test_emit_runs_post_in_background_thread(self):
        post_started = threading.Event()

        def _fake_post(*a, **kw):
            post_started.set()
            return MagicMock(status_code=200)

        with patch("libs.audit.audit_emitter.httpx.post",
                   side_effect=_fake_post):
            emit_auth_event(outcome="0", agent_email="x@y")
            assert post_started.wait(timeout=2.0)
