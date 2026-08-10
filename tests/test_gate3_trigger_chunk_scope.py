"""Gate 3 A3.1 -- trigger chunk scope validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    responses: list[Any | None]

    def __post_init__(self) -> None:
        self._index = 0

    def run(self, _query: str, **kwargs: Any):
        chunk_id = kwargs.get("chunk_id")
        record = {"id": chunk_id} if self._index < len(self.responses) else None
        if self._index < len(self.responses):
            record = self.responses[self._index]
        self._index += 1
        return _FakeResult(record)


def test_rejects_duplicate_chunk_ids() -> None:
    session = _FakeSession(responses=[{"id": "c1"}, {"id": "c2"}])
    result = validate_trigger_chunk_scope(
        session,
        TriggerChunkScopeRequest(
            tenant_id="tenant-1",
            patient_id="pat-1",
            referral_id="rr-1",
            chunk_ids=["c1", "c1"],
        ),
    )
    assert result.ok is False
    assert any(err.code == "chunk_duplicate" for err in result.errors)


def test_rejects_unknown_chunk_out_of_scope() -> None:
    session = _FakeSession(responses=[None])
    result = validate_trigger_chunk_scope(
        session,
        TriggerChunkScopeRequest(
            tenant_id="tenant-1",
            patient_id="pat-1",
            referral_id="rr-1",
            chunk_ids=["c-unknown"],
        ),
    )
    assert result.ok is False
    assert any(err.code == "chunk_out_of_scope" for err in result.errors)


def test_preserves_trigger_order_for_valid_chunks() -> None:
    session = _FakeSession(responses=[{"id": "c3"}, {"id": "c1"}, {"id": "c2"}])
    result = validate_trigger_chunk_scope(
        session,
        TriggerChunkScopeRequest(
            tenant_id="tenant-1",
            patient_id="pat-1",
            referral_id="rr-1",
            chunk_ids=["c3", "c1", "c2"],
        ),
    )
    assert result.ok is True
    assert result.ordered_chunk_ids == ["c3", "c1", "c2"]


def test_accepts_list_based_graph_client() -> None:
    class _ListClient:
        def run(self, _query: str, **kwargs: Any):
            chunk_id = kwargs.get("chunk_id")
            return [{"id": chunk_id}] if chunk_id == "c1" else []

    result = validate_trigger_chunk_scope(
        _ListClient(),
        TriggerChunkScopeRequest(
            tenant_id="tenant-1",
            patient_id="pat-1",
            referral_id="rr-1",
            chunk_ids=["c1"],
        ),
    )
    assert result.ok is True
    assert result.ordered_chunk_ids == ["c1"]
