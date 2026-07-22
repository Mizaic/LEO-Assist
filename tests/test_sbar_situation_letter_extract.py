"""VT-D2749EC9: referral-assessment Situation letter extract.

Atlas:
  DI: DI-43233166
  DO: DO-FE95EA83
  VT: VT-D2749EC9
"""

from __future__ import annotations

import asyncio
import re
from typing import Any
from unittest.mock import MagicMock, patch

from libs.prompts.sbar_situation_v1 import SBAR_SITUATION_SYSTEM_V1
from libs.sbar.context_integrity import validate_sbar_context
from libs.sbar.events import (
    BackgroundSourceType,
    SBARArtifactRef,
    SBARBackgroundSourceRef,
    SBARRequestPayload,
    SBARSituationInput,
    SUMMARISATION_CONTEXT_PROMPTS,
    SituationArtifactType,
    SummarisationContext,
)
from libs.sbar.prompt_calls import call_situation
from libs.sbar.source_resolver import (
    ResolvedSituation,
    ResolvedSource,
    _SITUATION_LETTER_MAX_CHARS,
    _resolve_situation_document_reference,
    resolve_situation,
)

_GALLBLADDER_LETTER = (
    "Dear Colleague,\n\n"
    "I am writing to refer Robert for urgent direct access ultrasound "
    "of the abdomen. He has presented with a 2-month history of "
    "dyspeptic symptoms that have not responded to standard proton "
    "pump inhibitor therapy. He reports early satiety and a sensation "
    "of upper abdominal fullness.\n\n"
    "On examination, I have identified a firm, palpable mass in the "
    "epigastric region, which is consistent with an enlarged gall "
    "bladder. Given the clinical findings and the treatment-resistant "
    "nature of his symptoms, I am concerned about underlying gall "
    "bladder pathology and would like urgent imaging to exclude "
    "malignancy.\n\n"
    "Robert has a background of GORD and obesity. He is otherwise well."
)


def _flatten(txt: str) -> str:
    return re.sub(r"\s+", " ", txt)


def test_referral_assessment_context_framing_is_narrow() -> None:
    snippet = SUMMARISATION_CONTEXT_PROMPTS[SummarisationContext.referral_assessment]
    flat = _flatten(snippet).lower()
    assert "never assume two-week-wait" in flat
    assert "missing-from-system-data" in flat or "missing-from-system" in flat
    assert "headline trigger" in flat
    assert "do not retell" in flat
    assert "background owns" in flat


def test_situation_prompt_forbids_assumed_2ww_and_apology_with_letter() -> None:
    flat = _flatten(SBAR_SITUATION_SYSTEM_V1).lower()
    assert "never assume two-week-wait" in flat
    assert "missing-from-system-data apology" in flat
    assert "documentreference" in flat
    assert "situation vs background" in flat
    assert "do not retell letter history" in flat
    assert "one headline trigger" in flat


def test_resolve_situation_document_reference_truncates() -> None:
    long_text = "A" * (_SITUATION_LETTER_MAX_CHARS + 200)
    sources = [
        ResolvedSource(
            source_label="Chunk",
            source_id="c1",
            text=long_text,
            metadata={"ordinal": 1},
        )
    ]
    session = MagicMock()
    with patch(
        "libs.sbar.source_resolver._resolve_document_reference",
        return_value=sources,
    ):
        out = _resolve_situation_document_reference(session, "dr-1")
    assert out["type"] == SituationArtifactType.document_reference.value
    assert out["id"] == "dr-1"
    assert out["truncated"] is True
    assert len(out["text"]) <= _SITUATION_LETTER_MAX_CHARS


def test_resolve_situation_includes_document_letter(monkeypatch) -> None:
    from libs.sbar import source_resolver as sr

    monkeypatch.setattr(
        sr,
        "get_patient_context",
        lambda _s, _pid: {"id": _pid, "gender": "male", "birth_date": "1968-07-20"},
    )
    monkeypatch.setattr(
        sr,
        "_resolve_situation_document_reference",
        lambda _s, dr_id: {
            "type": SituationArtifactType.document_reference.value,
            "id": dr_id,
            "text": _GALLBLADDER_LETTER,
            "truncated": False,
        },
    )
    resolved = resolve_situation(
        MagicMock(),
        SBARSituationInput(
            patient_id="pat-1",
            artifacts=[
                SBARArtifactRef(
                    type=SituationArtifactType.document_reference,
                    id="dr-gb-1",
                )
            ],
        ),
    )
    assert len(resolved.artifacts) == 1
    assert "ultrasound" in resolved.artifacts[0]["text"].lower()
    assert "gall bladder" in resolved.artifacts[0]["text"].lower()


def test_context_integrity_accepts_situation_document() -> None:
    class _Session:
        def run(self, query: str, **kwargs: Any):
            class _R:
                def single(self_inner):
                    return {"id": kwargs.get("record_id") or kwargs.get("patient_id")}

            return _R()

    payload = SBARRequestPayload(
        run_id="run-1",
        situation=SBARSituationInput(
            patient_id="pat-1",
            artifacts=[
                SBARArtifactRef(
                    type=SituationArtifactType.document_reference,
                    id="dr-1",
                )
            ],
        ),
        background=[
            SBARBackgroundSourceRef(
                type=BackgroundSourceType.document_reference,
                id="dr-1",
            )
        ],
    )
    result = validate_sbar_context(_Session(), payload)
    assert result.ok is True


def test_sbar_subgraph_payload_uses_referral_assessment_and_letter() -> None:
    captured: dict[str, Any] = {}

    class _FakeOrch:
        async def run(self, payload: SBARRequestPayload):
            captured["payload"] = payload
            return MagicMock(
                assessment_id="a1",
                status="completed",
                situation="ok",
                background="ok",
                assessment="ok",
                recommendation="ok",
                errors=[],
            )

    with patch(
        "services.pipeline_worker.app.services.sbar_orchestrator.SBAROrchestrator",
        _FakeOrch,
    ):
        from libs.pipeline_graph.subgraphs.sbar import _async_run_sbar

        asyncio.run(
            _async_run_sbar(
                {
                    "patient_id": "pat-1",
                    "encounter_id": "enc-1",
                    "run_id": "run-1",
                    "referral_id": "rr-1",
                    "document_reference_id": "dr-1",
                    "guideline_ids": [],
                }
            )
        )

    payload = captured["payload"]
    sit_types = [a.type for a in payload.situation.artifacts]
    assert SituationArtifactType.summarisation_context in sit_types
    assert SituationArtifactType.document_reference in sit_types
    assert SituationArtifactType.referral_request in sit_types
    ctx = next(
        a
        for a in payload.situation.artifacts
        if a.type is SituationArtifactType.summarisation_context
    )
    assert ctx.context_value is SummarisationContext.referral_assessment
    assert all(
        a.context_value is not SummarisationContext.two_week_wait
        for a in payload.situation.artifacts
        if a.type is SituationArtifactType.summarisation_context
    )
    bg_docs = [
        s
        for s in payload.background
        if s.type is BackgroundSourceType.document_reference
    ]
    assert len(bg_docs) == 1
    assert bg_docs[0].id == "dr-1"


def test_mocked_situation_gallbladder_letter_cues() -> None:
    """AC3: letter trigger present; 2WW / missing-data apology forbidden."""

    async def _fake_invoker(*_a: Any, **_k: Any) -> dict[str, Any]:
        # Narrow Situation shape: who + request + one headline trigger.
        # Symptom timeline / PPI failure stay in Background.
        return {
            "situation_markdown": (
                "This is a 56-year-old man referred for urgent direct "
                "access abdominal ultrasound to exclude gall bladder "
                "malignancy after a palpable epigastric mass."
            )
        }

    resolved = ResolvedSituation(
        patient_id="pat-1",
        patient_summary={"gender": "male", "birth_date": "1968-07-20"},
        artifacts=[
            {
                "type": SituationArtifactType.summarisation_context.value,
                "value": SummarisationContext.referral_assessment.value,
                "prompt_snippet": SUMMARISATION_CONTEXT_PROMPTS[
                    SummarisationContext.referral_assessment
                ],
            },
            {
                "type": SituationArtifactType.document_reference.value,
                "id": "dr-1",
                "text": _GALLBLADDER_LETTER,
            },
        ],
    )
    result = asyncio.run(
        call_situation(
            resolved,
            prompt_fetcher=lambda _n: SBAR_SITUATION_SYSTEM_V1,
            invoker=_fake_invoker,
        )
    )
    md = (result["markdown"] or "").lower()
    assert "ultrasound" in md
    assert "gall bladder" in md or "epigastric" in md
    assert "2-week" not in md and "two-week" not in md
    assert "have not been recorded" not in md
    assert "not recorded in the available" not in md
    # Must not retell Background-owned chronology.
    assert "2-month" not in md and "two-month" not in md
    assert "proton pump" not in md and " ppi " not in f" {md} "
    assert "early satiety" not in md
    assert "obesity" not in md


def test_sbar_subgraph_source_has_no_hardcoded_two_week_wait() -> None:
    from pathlib import Path

    src = Path("libs/pipeline_graph/subgraphs/sbar.py").read_text(encoding="utf-8")
    assert "SummarisationContext.two_week_wait" not in src
    assert "SummarisationContext.referral_assessment" in src
    assert "SituationArtifactType.document_reference" in src
