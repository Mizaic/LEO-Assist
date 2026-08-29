"""Dry-run in-process referral: set dry_run and skip Neo4j writes.

Atlas: Class A tooling. Look up after create via search_design_controls
for 'in-process referral dry-run'.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from libs.referral_quality.inprocess_dry_run import (
    build_dry_run_state,
    dump_quality_report,
    is_write_cypher,
    resolve_existing_chunks,
)
from scripts.run_referral_inprocess import build_parser


def test_refuses_reset_with_dry_run() -> None:
    args = build_parser().parse_args(
        ["--referral-id", "000481914514", "--dry-run", "--reset"]
    )
    assert args.dry_run is True
    assert args.reset is True
    with pytest.raises(SystemExit, match="Refusing --reset with --dry-run"):
        from scripts import run_referral_inprocess as script

        with patch.object(
            script.sys,
            "argv",
            [
                "run_referral_inprocess.py",
                "--referral-id",
                "000481914514",
                "--dry-run",
                "--reset",
            ],
        ):
            script.main()


def test_dry_run_flag_sets_pipeline_dry_run() -> None:
    args = build_parser().parse_args(["--referral-id", "000481914514", "--dry-run"])
    assert args.dry_run is True
    state = build_dry_run_state(
        referral_id=args.referral_id,
        patient_id="p-1",
        encounter_id="000481914514:referral-assessment",
        document_reference_id="doc-1",
        chunk_ids=["c-1"],
        run_id="run-1",
    )
    assert state["dry_run"] is True
    assert state["referral_id"] == "000481914514"
    assert state["chunk_ids"] == ["c-1"]


def test_dry_run_resolves_existing_chunks_without_backfill() -> None:
    client = MagicMock()
    target = MagicMock()
    target.document_reference_id = "doc-1"
    resolved = MagicMock()
    resolved.chunks = [{"id": "chunk-a"}]
    with (
        patch(
            "scripts.replay_referral._resolve_referral_target",
            return_value=target,
        ),
        patch(
            "libs.patient_document_runs.chunk_resolver.resolve_pipeline_chunks",
            return_value=resolved,
        ) as resolve,
    ):
        out = resolve_existing_chunks(client, "000481914514")
    assert out["chunk_ids"] == ["chunk-a"]
    assert resolve.call_args.kwargs["backfill_legacy_ids"] is False


def test_persist_dry_run_does_not_open_neo4j() -> None:
    from libs.pipeline_graph.subgraphs.persist import write_patient_graph

    with patch(
        "libs.pipeline_graph.subgraphs.persist._get_patient_graph_client"
    ) as get_client:
        out = write_patient_graph(
            {
                "dry_run": True,
                "entities": [{"text": "lump", "concept_id": "1", "label": "finding"}],
                "encounter_id": "e-1",
                "patient_id": "p-1",
                "run_id": "r-1",
            }
        )
    get_client.assert_not_called()
    assert out["documents_written"] == 0


def test_referral_reason_dry_run_does_not_write() -> None:
    from libs.pipeline_graph.subgraphs.referral_reason import _async_extract_reason

    rows = [{"text": "Reason for referral: breast lump"}]
    write_client = MagicMock()
    read_client = MagicMock()
    read_client.run.return_value = rows

    async def _fake_llm(*_args, **_kwargs):
        return {"reason": "Breast lump for two weeks."}

    with (
        patch(
            "libs.neo4j_client.client.PatientGraphClient",
            side_effect=[read_client, write_client],
        ) as client_cls,
        patch(
            "libs.llm_client.json_helper.invoke_llm_json",
            _fake_llm,
        ),
    ):
        result = pytest.importorskip("asyncio").run(
            _async_extract_reason(
                "000481914514",
                ["c-1"],
                "p-1",
                "r-1",
                dry_run=True,
            )
        )
    write_client.run.assert_not_called()
    assert client_cls.call_count == 1
    assert result["referral_reason"] == "Breast lump for two weeks."


def test_sbar_write_cypher_is_detected() -> None:
    assert is_write_cypher("MERGE (a:Assessment {id: $id}) SET a.status = $s")
    assert is_write_cypher("CREATE (n:Assessment)")
    assert not is_write_cypher("MATCH (c:Chunk {id: $id}) RETURN c.text AS text")


def test_sbar_orchestrator_dry_run_skips_write_queries() -> None:
    from services.pipeline_worker.app.services.sbar_orchestrator import (
        SBAROrchestrator,
    )

    client = MagicMock()
    orch = SBAROrchestrator(patient_graph_client=client, dry_run=True)
    orch._run_cypher(client, "MERGE (a:Assessment {id: $id})", id="a-1")
    client.run.assert_not_called()


def test_sbar_completeness_persist_dry_run_skips_write() -> None:
    from libs.pipeline_graph.subgraphs.sbar import _persist_completeness

    with patch("libs.neo4j_client.client.PatientGraphClient") as cls:
        _persist_completeness("a-1", {"missing_groups": []}, dry_run=True)
    cls.assert_not_called()


def test_hitl_and_staging_dry_run_skip_writes() -> None:
    from libs.pipeline_graph.subgraphs.hitl_coding_queue import queue_hitl_coding
    from libs.pipeline_graph.subgraphs.hitl_ner_queue import queue_hitl_ner
    from libs.pipeline_graph.subgraphs.staging_enrichment import enrich_staging

    with patch("libs.neo4j_client.client.KnowledgeGraphClient") as kg:
        ner = queue_hitl_ner(
            {
                "dry_run": True,
                "llm_check_changes": [{"type": "drop"}],
                "entities": [{"text": "x"}],
                "encounter_text": "x",
            }
        )
        coding = queue_hitl_coding(
            {
                "dry_run": True,
                "llm_check_changes": [{"type": "force_review"}],
                "entities": [{"text": "x"}],
                "encounter_text": "x",
            }
        )
    kg.assert_not_called()
    assert ner["training_labels_written"] == 0
    assert coding["training_labels_written"] == 0

    with patch("libs.neo4j_client.client.PatientGraphClient") as pg:
        out = enrich_staging({"dry_run": True, "episode_ids": ["ep-1"]})
    pg.assert_not_called()
    assert out["errors"] == []


def test_write_guard_blocks_mutating_cypher() -> None:
    from libs.referral_quality import inprocess_dry_run as dry

    dry._GUARD_INSTALLED = False
    calls: list[str] = []

    def fake_run(_client: object, query: str, **_params: object) -> list[dict]:
        calls.append(query)
        return []

    with patch("libs.neo4j_client.client.run_with_retry", fake_run):
        dry._GUARD_INSTALLED = False
        dry.install_dry_run_write_guard()
        from libs.neo4j_client import client as neo4j_client

        with pytest.raises(RuntimeError, match="dry-run blocked"):
            neo4j_client.run_with_retry(MagicMock(), "MERGE (n:X {id: 1})")
        neo4j_client.run_with_retry(MagicMock(), "MATCH (c:Chunk) RETURN c.id")
    assert any("MATCH" in q for q in calls)


def test_quality_report_omits_patient_id(tmp_path: Path) -> None:
    path = dump_quality_report(
        tmp_path,
        "000481914514",
        {
            "patient_id": "should-not-appear",
            "dry_run": True,
            "entities": [{"text": "lump", "assertion": "present", "label": "finding"}],
            "completeness_result": {"complete": False},
            "compliance_result": {"fired": ["g1"]},
            "sbar_sections": {"situation": "s"},
            "status": "completed",
            "warnings": [],
            "errors": [],
        },
    )
    payload = json.loads(path.read_text())
    assert payload["referral_id"] == "000481914514"
    assert "patient_id" not in payload
    assert "scope" in payload
    assert payload["facts"][0]["text"] == "lump"
    assert payload["completeness"]["complete"] is False
    assert payload["fired_guidelines"] == ["g1"]
    assert payload["sbar_sections"]["situation"] == "s"
