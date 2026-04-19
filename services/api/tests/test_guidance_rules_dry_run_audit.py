"""VT-LEO-AI-517 TC-002 / TC-003: guidance dry-run :AuditEvent
persistence (DI-LEO-AI-518).

The synchronous ``POST /guidance/rules/test/{recommendation_id}``
endpoint must persist a parallel
``:AuditEvent {type:'PipelineRun', subtype:'guidance_rule_dry_run'}``
on every call, carrying the four canonical token / cost properties and
a ``would_write`` boolean. Failures are best-effort -- the AuditEvent
write must never bubble out of the helper.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from app.routers.guidance_rules import _DRY_RUN_AUDIT_EVENT, _write_dry_run_audit_event


class _CapturingClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._fail = fail
        self.closed = False

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append((query, params))
        if self._fail:
            raise RuntimeError("simulated neo4j failure")
        return []

    def close(self) -> None:
        self.closed = True


def test_tc002_dry_run_endpoint_writes_audit_event() -> None:
    client = _CapturingClient()
    with patch(
        "app.routers.guidance_rules.CodingGraphClient", return_value=client
    ):
        _write_dry_run_audit_event(
            recommendation_id="rec-test-dry-001",
            guideline_id="ng12",
            coded={"some": "result"},
            errors=[],
            llm_tokens={
                "input_tokens": 1500,
                "output_tokens": 320,
                "cached_input_tokens": 0,
                "llm_calls": 2,
            },
        )

    assert client.closed is True
    audit_calls = [c for c in client.calls if "AuditEvent" in c[0]]
    assert len(audit_calls) == 1, "expected exactly one AuditEvent merge per dry-run"
    query, params = audit_calls[0]
    assert query is _DRY_RUN_AUDIT_EVENT
    assert params["llm_input_tokens"] == 1500
    assert params["llm_output_tokens"] == 320
    assert params["llm_cached_tokens"] == 0
    assert params["llm_calls"] == 2
    assert params["status"] == "completed"
    assert params["recommendation_id"] == "rec-test-dry-001"
    assert params["would_write"] is True


def test_tc002b_dry_run_would_write_false_on_terminology_failure() -> None:
    client = _CapturingClient()
    with patch(
        "app.routers.guidance_rules.CodingGraphClient", return_value=client
    ):
        _write_dry_run_audit_event(
            recommendation_id="rec-test-dry-002",
            guideline_id="ng12",
            coded=None,
            errors=["terminology_api_unavailable"],
            llm_tokens={"input_tokens": 100, "output_tokens": 50, "llm_calls": 1},
        )

    audit_calls = [c for c in client.calls if "AuditEvent" in c[0]]
    assert len(audit_calls) == 1
    _, params = audit_calls[0]
    assert params["status"] == "failed"
    assert params["would_write"] is False
    assert params["error_count"] == 1
    assert "terminology_api_unavailable" in (params["first_error"] or "")


def test_tc003_audit_event_failure_does_not_raise() -> None:
    client = _CapturingClient(fail=True)
    with patch(
        "app.routers.guidance_rules.CodingGraphClient", return_value=client
    ):
        _write_dry_run_audit_event(
            recommendation_id="rec-test-dry-003",
            guideline_id="ng12",
            coded={"some": "result"},
            errors=[],
            llm_tokens={"input_tokens": 10, "output_tokens": 5, "llm_calls": 1},
        )

    assert client.closed is True
