"""Regression: DocumentReference chunk expansion must use business ids.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE

neo4j.graph.Node.id is the legacy integer identity. Using it as
Chunk.id makes MATCH (c:Chunk {id: $source_id}) miss, so SBAR
Background resolves to empty text and Assessment sees 0 codes.
"""

from __future__ import annotations

from typing import Any

from libs.sbar.source_resolver import (
    _chunk_business_id,
    _resolve_document_reference,
)


class _FakeNode:
    """Mimic neo4j.graph.Node: .id is legacy int, ['id'] is property."""

    def __init__(self, business_id: str, legacy_id: int) -> None:
        self.id = legacy_id
        self._props = {"id": business_id}

    def __getitem__(self, key: str) -> Any:
        return self._props[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._props.get(key, default)


class _Session:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks
        self.chunk_lookups: list[str] = []

    def run(self, query: str, **params: Any):
        if "DocumentReference" in query and "HAS_CHUNK" in query:
            return _Result(
                {
                    "id": params["source_id"],
                    "chunks": self._chunks,
                    "fallback_text": "",
                }
            )
        if "Chunk" in query:
            self.chunk_lookups.append(str(params["source_id"]))
            return _Result(
                {
                    "text": f"text-for-{params['source_id']}",
                    "ordinal": 1,
                    "codes": [],
                }
            )
        return _Result(None)


class _Result:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def single(self):
        return self._row


def test_chunk_business_id_prefers_property_over_legacy_identity() -> None:
    node = _FakeNode("38f3817854e23f94c99507a58aadc61d", legacy_id=8633)
    assert _chunk_business_id(node) == "38f3817854e23f94c99507a58aadc61d"
    assert _chunk_business_id({"id": "abc"}) == "abc"
    assert _chunk_business_id({"id": 8633}) is None


def test_resolve_document_reference_uses_business_chunk_ids() -> None:
    nodes = [
        _FakeNode("chunk-hash-aaa", legacy_id=8633),
        _FakeNode("chunk-hash-bbb", legacy_id=8634),
    ]
    session = _Session(nodes)
    resolved = _resolve_document_reference(session, "dr-1")

    assert [r.source_id for r in resolved] == [
        "chunk-hash-aaa",
        "chunk-hash-bbb",
    ]
    assert session.chunk_lookups == ["chunk-hash-aaa", "chunk-hash-bbb"]
    assert all(r.text and not (r.metadata or {}).get("error") for r in resolved)


def test_resolve_document_reference_accepts_map_rows_from_cypher() -> None:
    session = _Session(
        [
            {"id": "chunk-hash-ccc", "ordinal": 1},
            {"id": "chunk-hash-ddd", "ordinal": 2},
        ]
    )
    resolved = _resolve_document_reference(session, "dr-2")
    assert [r.source_id for r in resolved] == [
        "chunk-hash-ccc",
        "chunk-hash-ddd",
    ]
