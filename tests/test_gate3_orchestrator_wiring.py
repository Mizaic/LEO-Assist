"""Gate 3 live orchestrator wiring -- coverage, recall, structured Situation."""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from libs.cypher.sbar_assessment_queries import SET_ASSESSMENT_GATE3
from libs.sbar.context_integrity import ContextIntegrityResult
from libs.sbar.events import (
    BackgroundSourceType,
    SBARArtifactRef,
    SBARBackgroundSourceRef,
    SBARRequestPayload,
    SBARSituationInput,
    SituationArtifactType,
)
from libs.sbar.policy_runtime import build_runtime
from libs.sbar.source_resolver import ResolvedCode, ResolvedSource
from libs.workflow.execution_manifest import build_execution_manifest
from libs.workflow.plan_manifest import PlanManifest
from libs.workflow.referral_policy import DEFAULT_REFERRAL_POLICY
from services.pipeline_worker.app.services.sbar_orchestrator import SBAROrchestrator


@dataclass
class _FakeSession:
    runs: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def run(self, query: str, **kwargs):
        self.runs.append((query, kwargs))
        return _FakeResult(None)


@dataclass
class _FakeResult:
    record: Any | None = None

    def single(self):
        return self.record


class _FakeClient:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    @contextmanager
    def session(self):
        yield self._session

    def run(self, query: str, **kwargs):
        self._session.run(query, **kwargs)
        return []


def _policy_runtime():
    plan = PlanManifest(
        plan_id="pd-referral-assessment",
        version_id=1,
        version_node_id="ver-test-1",
        policy_version="v1",
        workflow_mode="durable_pubsub",
        actions=(),
        referral_policy=dict(DEFAULT_REFERRAL_POLICY),
    )
    manifest = build_execution_manifest(
        plan,
        prompt_hashes={
            "situation": "h1",
            "background": "h2",
            "recommendation": "h3",
            "recall": "h4",
        },
        model_config={
            "key": "aws:big",
            "provider": "aws",
            "tier": "big",
            "modelId": "sonnet-test",
        },
    )
    return build_runtime(manifest)


def _patch_recall_noop(monkeypatch) -> None:
    async def _fake_call_recall(**kwargs):
        from libs.sbar.recall_preflight import RecallBudget, check_recall_budget

        budget = kwargs.get("budget") or RecallBudget()
        exhaustion = check_recall_budget(
            chunk_fetches=0,
            llm_calls=0,
            tokens_used=0,
            budget=budget,
        )
        return {
            "evidence": None,
            "exhaustion": exhaustion,
            "missing": [],
            "llm_calls": 0,
            "audit_log": [],
            "raw": {},
            "error": None,
            "error_code": None,
        }

    monkeypatch.setattr(
        "libs.sbar.orchestrator_gate3.call_recall",
        _fake_call_recall,
    )


def _patch_integrity_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator.validate_sbar_context",
        lambda _session, _payload: ContextIntegrityResult(ok=True),
    )


def _make_payload(**extra: Any) -> SBARRequestPayload:
    return SBARRequestPayload(
        run_id="run-gate3",
        upstream_correlation_id="parent-run-gate3",
        situation=SBARSituationInput(
            patient_id="pat-1",
            artifacts=[
                SBARArtifactRef(type=SituationArtifactType.referral_request, id="rr-1")
            ],
        ),
        background=[
            SBARBackgroundSourceRef(type=BackgroundSourceType.encounter, id="enc-1")
        ],
        extra=extra,
    )


def test_orchestrator_persists_referral_reason_evidence(monkeypatch) -> None:
    session = _FakeSession()
    client = _FakeClient(session)
    captured_bg: dict[str, Any] = {}
    captured_sit: dict[str, Any] = {}

    async def _fake_situation(_resolved, **kwargs):
        captured_sit.update(kwargs.get("extra_context") or {})
        return {"markdown": "Situation.", "raw": {}, "error": None}

    async def _fake_background(_sources, _codes, **kwargs):
        captured_bg.update(kwargs)
        return {"markdown": "Background.", "raw": {}, "error": None}

    async def _fake_recommendation(**_kwargs):
        return {"markdown": "Recommend.", "actions": [], "raw": {}, "error": None}

    def _fake_resolve_situation(_session, _input):
        from libs.sbar.source_resolver import ResolvedSituation

        return ResolvedSituation(
            patient_id="pat-1",
            patient_summary={},
            artifacts=[
                {
                    "type": SituationArtifactType.referral_request.value,
                    "id": "rr-1",
                    "reason": "Suspected lung cancer.",
                    "priority": "2ww",
                }
            ],
        )

    def _fake_resolve_background(_session, _refs):
        return [
            ResolvedSource(
                source_label="Chunk",
                source_id="chunk-a",
                text="Progressive dysphagia for 6 weeks without weight loss.",
                codes=[
                    ResolvedCode(
                        concept_id="123",
                        term="Dysphagia",
                        chunk_id="chunk-a",
                        source_label="Chunk",
                        source_id="chunk-a",
                    )
                ],
            )
        ]

    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator.resolve_situation",
        _fake_resolve_situation,
    )
    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator."
        "resolve_background_sources",
        _fake_resolve_background,
    )
    _patch_integrity_ok(monkeypatch)

    orch = SBAROrchestrator(
        patient_graph_client=client,
        publish_progress=MagicMock(),
        situation_caller=_fake_situation,
        background_caller=_fake_background,
        recommendation_caller=_fake_recommendation,
        evaluator=AsyncMock(return_value={"matched_rules": []}),
        policy_runtime=_policy_runtime(),
    )
    payload = _make_payload(
        chunk_ids=["chunk-a"],
        referral_reason="Progressive dysphagia.",
    )
    result = asyncio.run(orch.run(payload))
    assert result.status == "completed"

    gate3_writes = [
        kwargs
        for query, kwargs in session.runs
        if query.strip() == SET_ASSESSMENT_GATE3.strip()
    ]
    assert gate3_writes, "expected SET_ASSESSMENT_GATE3 persistence"
    evidence_raw = gate3_writes[0].get("referral_reason_evidence_json")
    assert evidence_raw
    evidence = json.loads(evidence_raw)
    assert "lung cancer" in evidence["reason_text"].lower()
    assert evidence["source_type"] == "ReferralRequest"

    assert captured_sit.get("structured_headline")
    assert captured_bg.get("coverage") is not None
    assert captured_bg["coverage"].total_sentences >= 1


def test_orchestrator_passes_salvage_coverage_to_background(monkeypatch) -> None:
    session = _FakeSession()
    client = _FakeClient(session)
    captured: dict[str, Any] = {}

    async def _fake_situation(*_a, **_kw):
        return {"markdown": "Sit.", "raw": {}, "error": None}

    async def _fake_background(_sources, _codes, **kwargs):
        captured.update(kwargs)
        return {"markdown": "Bg.", "raw": {}, "error": None}

    async def _fake_recommendation(**_kw):
        return {"markdown": "Rec.", "actions": [], "raw": {}, "error": None}

    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator.resolve_situation",
        lambda _s, _i: __import__(
            "libs.sbar.source_resolver", fromlist=["ResolvedSituation"]
        ).ResolvedSituation(patient_id="pat-1", patient_summary={}, artifacts=[]),
    )
    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator."
        "resolve_background_sources",
        lambda _s, _r: [
            ResolvedSource(
                source_label="Chunk",
                source_id="chunk-a",
                text="Progressive dysphagia for 6 weeks.",
                codes=[],
            )
        ],
    )
    _patch_integrity_ok(monkeypatch)
    _patch_recall_noop(monkeypatch)

    orch = SBAROrchestrator(
        patient_graph_client=client,
        publish_progress=MagicMock(),
        situation_caller=_fake_situation,
        background_caller=_fake_background,
        recommendation_caller=_fake_recommendation,
        evaluator=AsyncMock(return_value={"matched_rules": []}),
        policy_runtime=_policy_runtime(),
    )
    asyncio.run(orch.run(_make_payload(chunk_ids=["chunk-a"])))
    coverage = captured.get("coverage")
    assert coverage is not None
    assert coverage.uncovered_sentences >= 1
    assert len(coverage.salvage_sentences) >= 1


def test_extraction_subgraph_uses_manifest_windows(monkeypatch) -> None:
    from dataclasses import asdict

    from libs.nlp.sentence_splitter import SentenceChunk
    from libs.pipeline_graph.subgraphs import extraction as extraction_mod

    calls: list[int] = []

    def _fake_llm(encounter_text, chunks, state):
        calls.append(len(chunks))
        return {
            "entities": [
                {
                    "text": "finding",
                    "label": "finding",
                    "chunk_id": chunks[0].sentence_id,
                    "sentence_id": chunks[0].sentence_id,
                    "assertion": "present",
                }
            ],
            "llm_tokens": {"input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0},
            "extraction_route": "llm",
        }

    monkeypatch.setattr(extraction_mod, "_run_llm_extraction", _fake_llm)
    sentences = [
        asdict(
            SentenceChunk(
                sentence_id=f"c{i}",
                text=f"Sentence {i}.",
                start=i * 10,
                end=i * 10 + 9,
            )
        )
        for i in range(12)
    ]
    state = {
        "encounter_text": " ".join(s["text"] for s in sentences),
        "sentences": sentences,
        "text_segmentation_mode": "document_chunks",
        "execution_manifest": {
            "extraction": {"windowSize": 10, "windowOverlap": 1},
        },
        "model_mode": "llm",
    }
    result = extraction_mod.extract_entities(state)
    assert result.get("extraction_route") == "llm-windowed"
    assert len(calls) == 2
    assert calls[0] == 10
    assert calls[1] == 3
    assert len(result.get("entities") or []) >= 1
    assert "window_usage" in (result.get("llm_tokens") or {})
