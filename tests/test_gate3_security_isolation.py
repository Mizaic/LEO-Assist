"""Gate 5 G5.8 -- security and isolation for trigger chunks and recall tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from libs.sbar.recall_tools import RecallScope, RecallToolRegistry
from libs.sbar.trigger_chunk_scope import (
    TriggerChunkScopeRequest,
    validate_trigger_chunk_scope,
)


@dataclass
class _FakeResult:
    record: Any | None = None

    def single(self):
        return self.record


@dataclass
class _FakeSession:
    """Returns per-chunk scope rows; None means out of scope."""

    scope_map: dict[str, bool]

    def run(self, _query: str, **kwargs: Any):
        chunk_id = str(kwargs.get("chunk_id") or "")
        if self.scope_map.get(chunk_id):
            return _FakeResult({"id": chunk_id})
        return _FakeResult(None)


def test_rejects_missing_tenant_before_graph_lookup() -> None:
    session = _FakeSession(scope_map={"c1": True})
    result = validate_trigger_chunk_scope(
        session,
        TriggerChunkScopeRequest(
            tenant_id="",
            patient_id="pat-1",
            referral_id="rr-1",
            chunk_ids=["c1"],
        ),
    )
    assert result.ok is False
    assert any(err.code == "tenant_missing" for err in result.errors)


def test_rejects_missing_patient_before_graph_lookup() -> None:
    session = _FakeSession(scope_map={"c1": True})
    result = validate_trigger_chunk_scope(
        session,
        TriggerChunkScopeRequest(
            tenant_id="tenant-1",
            patient_id="",
            referral_id="rr-1",
            chunk_ids=["c1"],
        ),
    )
    assert result.ok is False
    assert any(err.code == "patient_missing" for err in result.errors)


def test_rejects_chunk_linked_to_different_tenant() -> None:
    session = _FakeSession(scope_map={"c1": False})
    result = validate_trigger_chunk_scope(
        session,
        TriggerChunkScopeRequest(
            tenant_id="tenant-a",
            patient_id="pat-1",
            referral_id="rr-1",
            chunk_ids=["c1"],
        ),
    )
    assert result.ok is False
    assert any(err.code == "chunk_out_of_scope" for err in result.errors)


def test_rejects_chunk_from_other_referral_in_same_tenant() -> None:
    session = _FakeSession(scope_map={"c-other": False, "c-mine": True})
    result = validate_trigger_chunk_scope(
        session,
        TriggerChunkScopeRequest(
            tenant_id="tenant-1",
            patient_id="pat-1",
            referral_id="rr-mine",
            chunk_ids=["c-mine", "c-other"],
        ),
    )
    assert result.ok is False
    assert any(
        err.code == "chunk_out_of_scope" and err.chunk_id == "c-other"
        for err in result.errors
    )


def test_recall_fetch_rejects_cross_referral_chunk_without_side_effect() -> None:
    secret = {"id": "c-secret", "text": "other referral PHI"}
    scope = RecallScope(
        tenant_id="t1",
        patient_id="p1",
        referral_id="rr-allowed",
        run_id="run-iso-1",
        allowed_chunk_ids=frozenset({"c-allowed"}),
    )
    registry = RecallToolRegistry(
        scope=scope,
        list_coded_facts=lambda: [],
        fetch_chunk=lambda cid: secret if cid == "c-secret" else {"id": cid},
        find_referral_reason=lambda: None,
    )
    assert registry.fetch_chunk_scoped("c-secret") is None
    assert registry.fetch_chunk_scoped("c-allowed") == {"id": "c-allowed"}
    assert registry.fetch_count == 1
    assert registry.audit_log[-2]["tool_result"]["error"] == "chunk_out_of_manifest"


def test_recall_list_coded_facts_does_not_increment_fetch_budget() -> None:
    scope = RecallScope(
        tenant_id="t1",
        patient_id="p1",
        referral_id="rr-1",
        run_id="run-iso-2",
        allowed_chunk_ids=frozenset({"c1"}),
    )
    registry = RecallToolRegistry(
        scope=scope,
        list_coded_facts=lambda: [{"code": "123"}],
        fetch_chunk=lambda cid: {"id": cid},
        find_referral_reason=lambda: None,
    )
    facts = registry.list_coded_facts_scoped()
    assert len(facts) == 1
    assert registry.fetch_count == 0


def test_recall_audit_log_carries_run_id_for_traceability() -> None:
    scope = RecallScope(
        tenant_id="t1",
        patient_id="p1",
        referral_id="rr-1",
        run_id="run-audit-99",
        allowed_chunk_ids=frozenset({"c1"}),
    )
    registry = RecallToolRegistry(
        scope=scope,
        list_coded_facts=lambda: [],
        fetch_chunk=lambda cid: None,
        find_referral_reason=lambda: None,
    )
    registry.fetch_chunk_scoped("c-outside")
    assert registry.audit_log[-1]["run_id"] == "run-audit-99"
