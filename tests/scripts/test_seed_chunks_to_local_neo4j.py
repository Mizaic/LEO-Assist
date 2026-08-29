"""Tests for seeding pulled chunks into a local Neo4j graph.

Atlas trace:
  VT: VT-3FE08AC5
  DI: DI-ACA9659D
  Look up via: get_design_control(dc_type="verification-test", dc_id="VT-3FE08AC5")
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from libs.chunking.validation_bundle import write_bundle
from scripts.seed_chunks_to_local_neo4j import (
    RemoteGraphRefused,
    assert_local_graph,
    seed_bundle,
)


def test_assert_local_graph_allows_localhost() -> None:
    assert_local_graph("bolt://localhost:7687", allow_remote=False)
    assert_local_graph("neo4j://127.0.0.1:7687", allow_remote=False)


def test_assert_local_graph_refuses_remote_by_default() -> None:
    with pytest.raises(RemoteGraphRefused):
        assert_local_graph(
            "neo4j+s://prod.databases.neo4j.io",
            allow_remote=False,
        )


def test_assert_local_graph_allows_remote_when_flagged() -> None:
    assert_local_graph(
        "neo4j+s://prod.databases.neo4j.io",
        allow_remote=True,
    )


def test_seed_bundle_creates_stubs_and_upserts_chunks(tmp_path: Path) -> None:
    chunks = [
        {
            "chunk_id": "c1",
            "document_reference_id": "dr-1",
            "ordinal": 1,
            "sha256": "abc",
            "text": "Hb 120",
            "char_start": 0,
            "char_end": 6,
        }
    ]
    dest = write_bundle(
        tmp_path,
        referral_id="r1",
        manifest={"patient_id": "p1", "referral_id": "r1", "chunk_count": 1},
        chunks=chunks,
    )
    from libs.chunking.validation_bundle import load_bundle

    bundle = load_bundle(dest)
    client = MagicMock()
    client.run.return_value = [{"chunk_id": "c1"}]
    summary = seed_bundle(client, bundle, tenant_id="validation")
    assert summary["chunk_count"] == 1
    assert client.run.call_count >= 2
    cypher_calls = [call.args[0] for call in client.run.call_args_list]
    assert any("ReferralRequest" in q for q in cypher_calls)
    assert any("DocumentReference" in q for q in cypher_calls)
    assert any("HAS_CHUNK" in q for q in cypher_calls)
