"""Gate 3 orchestrator prep: coverage, recall, structured Situation (D3/E3/A3).

Atlas trace:
  DO: DO-8CD63B3B
  DI: DI-CC00ABBD
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8CD63B3B")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from libs.sbar.events import SituationArtifactType
from libs.sbar.recall_preflight import (
    RecallExhaustionResult,
    check_recall_budget,
    preflight_recall,
    recall_policy_from_manifest,
)
from libs.sbar.recall_tools import RecallScope, RecallToolRegistry
from libs.sbar.prompt_calls import call_recall
from libs.sbar.situation_headline import (
    absent_finding_terms,
    present_finding_terms,
)
from libs.sbar.situation_source import (
    ReferralReasonEvidence,
    SituationSourceResult,
    build_structured_situation,
    reason_evidence_to_dict,
)
from libs.sbar.source_resolver import ResolvedCode, ResolvedSource
from libs.sbar.uncoded_coverage import (
    ChunkText,
    CodeEvidenceSpan,
    CoverageReport,
    analyse_uncoded_coverage,
)


@dataclass
class Gate3Context:
    structured: SituationSourceResult
    coverage: CoverageReport | None = None
    recall_exhaustion: RecallExhaustionResult | None = None
    source_accounting: dict[str, Any] = field(default_factory=dict)
    present_findings: list[str] = field(default_factory=list)
    absent_findings: list[str] = field(default_factory=list)


def manifest_from_runtime(policy_runtime: Any | None) -> dict[str, Any]:
    if policy_runtime is None:
        return {}
    return dict(getattr(policy_runtime, "execution_manifest", None) or {})


async def prepare_gate3_context(
    *,
    payload: Any,
    resolved_situation: Any,
    resolved_sources: list[ResolvedSource],
    aggregated: list[ResolvedCode],
    policy_runtime: Any | None,
    recall_reason_raw: str | None = None,
    allowed_chunk_ids: list[str] | None = None,
) -> Gate3Context:
    """Run uncoded coverage, bounded recall, and structured-first Situation."""
    manifest = manifest_from_runtime(policy_runtime)
    referral_request = _referral_request_artifact(resolved_situation)
    recall_evidence = _coerce_recall_evidence(
        recall_reason_raw,
        allowed_chunk_ids=allowed_chunk_ids or [],
        run_id=str(getattr(payload, "run_id", "") or ""),
    )
    extra = dict(getattr(payload, "extra", None) or {})
    entities = list(extra.get("entities") or [])
    structured = _structured_from_payload(
        payload,
        referral_request,
        recall_evidence,
        resolved_sources,
        extra,
        entities,
    )
    _align_referral_reason_artifact(resolved_situation, structured)

    coverage = _analyse_coverage(resolved_sources, aggregated, manifest)
    missing_slots = _missing_recall_slots(structured, referral_request)
    preflight = preflight_recall(
        missing_slots=missing_slots,
        coverage_gaps=int(coverage.uncovered_sentences if coverage else 0),
    )

    recall_exhaustion: RecallExhaustionResult | None = None
    if preflight.should_recall and manifest:
        recall_evidence, recall_exhaustion = await _run_bounded_recall(
            payload=payload,
            manifest=manifest,
            allowed_chunk_ids=allowed_chunk_ids or [],
            existing=recall_evidence,
            preflight_reasons=list(preflight.reasons),
            resolved_sources=resolved_sources,
            aggregated=aggregated,
            policy_runtime=policy_runtime,
        )
        if recall_evidence and not structured.referral_reason:
            structured = _structured_from_payload(
                payload,
                referral_request,
                recall_evidence,
                resolved_sources,
                extra,
                entities,
            )
            _align_referral_reason_artifact(resolved_situation, structured)

    accounting = _build_source_accounting(
        resolved_sources,
        aggregated,
        coverage,
        recall_exhaustion,
    )
    return Gate3Context(
        structured=structured,
        coverage=coverage,
        recall_exhaustion=recall_exhaustion,
        source_accounting=accounting,
        present_findings=present_finding_terms(entities),
        absent_findings=absent_finding_terms(entities),
    )


def persist_gate3_assessment_fields(
    client: Any,
    *,
    assessment_id: str,
    gate3: Gate3Context,
    run_cypher: Any,
) -> None:
    """Persist ReferralReasonEvidence and recall exhaustion on :Assessment."""
    from libs.cypher.sbar_assessment_queries import SET_ASSESSMENT_GATE3

    evidence_json = None
    if gate3.structured.referral_reason is not None:
        evidence_json = json.dumps(
            reason_evidence_to_dict(gate3.structured.referral_reason),
            default=str,
            sort_keys=True,
        )
    exhaustion_json = None
    needs_review = False
    if gate3.recall_exhaustion is not None:
        exhaustion_json = json.dumps(
            {
                "exhausted": gate3.recall_exhaustion.exhausted,
                "missing_flags": list(gate3.recall_exhaustion.missing_flags),
                "needs_review": gate3.recall_exhaustion.needs_review,
                "source_accounting": dict(gate3.recall_exhaustion.source_accounting),
            },
            default=str,
            sort_keys=True,
        )
        needs_review = bool(gate3.recall_exhaustion.needs_review)
    run_cypher(
        client,
        SET_ASSESSMENT_GATE3,
        assessment_id=assessment_id,
        referral_reason_evidence_json=evidence_json,
        recall_exhaustion_json=exhaustion_json,
        recall_needs_review=needs_review,
    )


def situation_extra_context(
    gate3: Gate3Context,
    *,
    guideline_ids: list[str],
    concern: str | None,
) -> dict[str, Any]:
    """Extra Situation LLM context from structured-first precedence."""
    return {
        "guideline_ids": guideline_ids,
        "concern": concern,
        "structured_headline": gate3.structured.headline,
        "source_precedence": list(gate3.structured.source_precedence),
        "structured_priority": gate3.structured.structured_priority,
        "present_findings": list(gate3.present_findings),
        "absent_findings": list(gate3.absent_findings),
    }


def _align_referral_reason_artifact(
    resolved_situation: Any, structured: SituationSourceResult
) -> None:
    """Stop a specialty-mismatched stored reason leading the Situation LLM."""
    if structured.source_precedence[:1] not in (
        ["form_clinical_section"],
        ["coded_facts"],
    ):
        return
    for art in getattr(resolved_situation, "artifacts", None) or []:
        if art.get("type") != SituationArtifactType.referral_request.value:
            continue
        art["reason"] = structured.headline
        art["reason_source"] = structured.source_precedence[0]


def _structured_from_payload(
    payload: Any,
    referral_request: dict[str, Any] | None,
    recall_evidence: ReferralReasonEvidence | None,
    resolved_sources: list[ResolvedSource],
    extra: dict[str, Any],
    entities: list[dict[str, Any]],
) -> SituationSourceResult:
    return build_structured_situation(
        referral_request=referral_request,
        referral_reason=recall_evidence,
        trigger_scoped_letter=_trigger_scoped_letter(resolved_sources),
        form_clinical_section=extra.get("form_clinical_section"),
        form_sections=extra.get("form_sections"),
        coded_facts=entities,
        run_id=str(getattr(payload, "run_id", "") or ""),
    )


def _referral_request_artifact(resolved_situation: Any) -> dict[str, Any] | None:
    for art in getattr(resolved_situation, "artifacts", None) or []:
        if art.get("type") == SituationArtifactType.referral_request.value:
            return dict(art)
    return None


def _trigger_scoped_letter(sources: list[ResolvedSource]) -> str | None:
    parts: list[str] = []
    for src in sources:
        label = str(src.source_label or "").lower()
        if label in {"chunk", "documentreference", "document"}:
            text = str(src.text or "").strip()
            if text:
                parts.append(text)
    joined = "\n".join(parts).strip()
    return joined or None


def _coerce_recall_evidence(
    raw: str | None,
    *,
    allowed_chunk_ids: list[str],
    run_id: str,
) -> ReferralReasonEvidence | None:
    text = str(raw or "").strip()
    if not text:
        return None
    chunk_id = allowed_chunk_ids[0] if allowed_chunk_ids else None
    return ReferralReasonEvidence(
        reason_text=text,
        source_type="ReferralReasonSubgraph",
        source_id=chunk_id or "",
        chunk_id=chunk_id,
        evidence_text=text,
        run_id=run_id or None,
    )


def _analyse_coverage(
    sources: list[ResolvedSource],
    codes: list[ResolvedCode],
    manifest: dict[str, Any],
) -> CoverageReport | None:
    if not manifest:
        return None
    chunks = [
        ChunkText(chunk_id=str(src.source_id or ""), text=str(src.text or ""))
        for src in sources
        if str(src.text or "").strip()
    ]
    if not chunks:
        return None
    spans = [
        CodeEvidenceSpan(
            chunk_id=str(code.chunk_id or code.source_id or ""),
            sentence_index=code.sentence_index,
            evidence_start=code.evidence_start,
            evidence_end=code.evidence_end,
        )
        for code in codes
    ]
    salvage_policy = dict(manifest.get("salvage") or {})
    return analyse_uncoded_coverage(chunks, spans, salvage_policy=salvage_policy)


def _missing_recall_slots(
    structured: SituationSourceResult,
    referral_request: dict[str, Any] | None,
) -> list[str]:
    missing: list[str] = []
    rr = referral_request or {}
    if not str(rr.get("reason") or "").strip() and structured.source_precedence != [
        "referral_request.reason"
    ]:
        if "referral_request.reason" not in structured.source_precedence:
            missing.append("missing_referral_reason")
    if not str(rr.get("priority") or "").strip():
        missing.append("missing_priority")
    return missing


async def _run_bounded_recall(
    *,
    payload: Any,
    manifest: dict[str, Any],
    allowed_chunk_ids: list[str],
    existing: ReferralReasonEvidence | None,
    preflight_reasons: list[str],
    resolved_sources: list[ResolvedSource],
    aggregated: list[ResolvedCode],
    policy_runtime: Any | None = None,
) -> tuple[ReferralReasonEvidence | None, RecallExhaustionResult | None]:
    budget = recall_policy_from_manifest(manifest)
    scope = RecallScope(
        tenant_id=str(getattr(payload, "tenant_id", "") or ""),
        patient_id=str(getattr(payload, "situation", None).patient_id or ""),
        referral_id=_referral_id_from_payload(payload),
        run_id=str(getattr(payload, "run_id", "") or ""),
        allowed_chunk_ids=frozenset(str(c) for c in allowed_chunk_ids if c),
    )
    chunk_store = _chunk_store(resolved_sources, allowed_chunk_ids)
    stored_reason = str(
        (getattr(payload, "extra", None) or {}).get("referral_reason") or ""
    ).strip()

    def _find_reason() -> dict[str, Any] | None:
        if not stored_reason:
            return None
        chunk_id = allowed_chunk_ids[:1]
        return {
            "reason_text": stored_reason,
            "chunk_id": chunk_id[0] if chunk_id else "",
        }

    registry = RecallToolRegistry(
        scope=scope,
        list_coded_facts=lambda: _coded_facts(aggregated),
        fetch_chunk=lambda cid: chunk_store.get(str(cid)),
        find_referral_reason=_find_reason,
    )
    if existing is not None and str(existing.reason_text or "").strip():
        return existing, check_recall_budget(
            chunk_fetches=registry.fetch_count,
            llm_calls=0,
            tokens_used=0,
            budget=budget,
        )

    recall_result = await call_recall(
        registry=registry,
        budget=budget,
        preflight_reasons=preflight_reasons,
        allowed_chunk_ids=list(allowed_chunk_ids or []),
        run_id=str(getattr(payload, "run_id", "") or ""),
        patient_id=str(getattr(payload, "situation", None).patient_id or ""),
        policy_runtime=policy_runtime,
    )
    found = recall_result.get("evidence")
    exhaustion = recall_result.get("exhaustion")
    if isinstance(found, ReferralReasonEvidence):
        return found, exhaustion
    if found is not None and hasattr(found, "reason_text"):
        return found, exhaustion
    return None, exhaustion


def _chunk_store(
    sources: list[ResolvedSource],
    allowed_chunk_ids: list[str],
) -> dict[str, dict[str, Any]]:
    allowed = {str(cid) for cid in allowed_chunk_ids if cid}
    store: dict[str, dict[str, Any]] = {}
    for src in sources or []:
        cid = str(src.source_id or "").strip()
        if not cid or (allowed and cid not in allowed):
            continue
        text = str(src.text or "").strip()
        if not text:
            continue
        store[cid] = {
            "id": cid,
            "text": text,
            "label": str(src.source_label or ""),
        }
    return store


def _coded_facts(codes: list[ResolvedCode]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for code in codes or []:
        facts.append(
            {
                "concept_id": str(code.concept_id or ""),
                "term": str(code.term or ""),
                "text": str(code.evidence or code.evidence_sentence or ""),
                "label": str(code.semantic_tag or ""),
                "assertion": str(code.assertion or "present"),
                "chunk_id": str(code.chunk_id or code.source_id or ""),
            }
        )
    return facts


def _referral_id_from_payload(payload: Any) -> str:
    for art in getattr(getattr(payload, "situation", None), "artifacts", None) or []:
        if art.type is SituationArtifactType.referral_request and art.id:
            return str(art.id)
    extra = getattr(payload, "extra", None) or {}
    return str(extra.get("referral_id") or "")


def _build_source_accounting(
    sources: list[ResolvedSource],
    codes: list[ResolvedCode],
    coverage: CoverageReport | None,
    recall_exhaustion: RecallExhaustionResult | None,
) -> dict[str, Any]:
    base = {
        "source_count": len(sources or []),
        "code_count": len(codes or []),
    }
    if coverage is not None:
        base.update(
            {
                "total_sentences": coverage.total_sentences,
                "covered_sentences": coverage.covered_sentences,
                "uncovered_sentences": coverage.uncovered_sentences,
                "salvage_sentences": len(coverage.salvage_sentences),
                "omitted_filler": coverage.omitted_filler,
                "omitted_uncoded": coverage.omitted_uncoded,
            }
        )
    else:
        source_count = len(sources or [])
        code_count = len(codes or [])
        base.update(
            {
                "total_sentences": max(code_count, source_count),
                "covered_sentences": code_count,
                "uncovered_sentences": max(source_count - code_count, 0),
            }
        )
    if recall_exhaustion is not None:
        base["recall_exhausted"] = recall_exhaustion.exhausted
        base["recall_needs_review"] = recall_exhaustion.needs_review
        base.update(dict(recall_exhaustion.source_accounting or {}))
    return base
