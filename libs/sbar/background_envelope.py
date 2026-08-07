"""Codes-first Background user-message envelope (A3.5).

Atlas trace:
  DO: DO-FA365C59
  DI: DI-3AAB5328
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-FA365C59")

Sends codes, assertions, evidence spans and approved salvage sentences only.
Does not dump full chunk prose when codes exist for that chunk.
"""

from __future__ import annotations

import json
from typing import Any

from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.sbar.source_resolver import ResolvedCode, ResolvedSource
from libs.sbar.uncoded_coverage import CoverageReport, SalvageSentence


def serialise_code(code: ResolvedCode) -> dict[str, Any]:
    patient_wording = sanitise_for_prompt(
        code.evidence_sentence or code.evidence or ""
    )
    return {
        "concept_id": code.concept_id,
        "term": code.term,
        "patient_wording": patient_wording,
        "semantic_tag": code.semantic_tag,
        "assertion": code.assertion,
        "evidence": sanitise_for_prompt(code.evidence or ""),
        "evidence_sentence": sanitise_for_prompt(code.evidence_sentence or ""),
        "evidence_start": code.evidence_start,
        "evidence_end": code.evidence_end,
        "sentence_index": code.sentence_index,
        "chunk_id": code.chunk_id,
        "run_id": code.run_id,
        "confidence": code.confidence,
        "source": {"type": code.source_label, "id": code.source_id},
    }


def _serialise_salvage(item: SalvageSentence) -> dict[str, Any]:
    return {
        "chunk_id": item.chunk_id,
        "sentence_index": item.sentence_index,
        "text": sanitise_for_prompt(item.text),
        "reason": item.reason,
    }


def serialise_completeness_for_context(
    completeness_result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Slim completeness payload for the Background LLM CONTEXT."""
    if not isinstance(completeness_result, dict):
        return None
    if not completeness_result.get("configured"):
        return None

    def _groups(key: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for group in completeness_result.get(key) or []:
            if not isinstance(group, dict):
                continue
            name = str(group.get("name") or "").strip()
            if not name:
                continue
            out.append({"name": name, "required": bool(group.get("required"))})
        return out

    missing_groups = _groups("missing_groups")
    if not missing_groups:
        return None
    return {
        "configured": True,
        "complete": bool(completeness_result.get("complete")),
        "domain": str(completeness_result.get("domain") or ""),
        "subdomain": str(completeness_result.get("subdomain") or ""),
        "missing_groups": missing_groups,
        "matched_groups": _groups("matched_groups"),
    }


def build_codes_first_envelope(
    sources: list[ResolvedSource],
    codes: list[ResolvedCode],
    coverage: CoverageReport | None = None,
    *,
    referring_specialty: str | None = None,
    completeness_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the CONTEXT body for Background without full-chunk prose dumps."""
    coded_chunk_ids = {str(c.chunk_id or c.source_id or "") for c in codes if c}
    coded_chunk_ids.discard("")

    source_entries: list[dict[str, Any]] = []
    for src in sources:
        chunk_id = str(src.source_id or "")
        has_codes = bool(src.codes) or chunk_id in coded_chunk_ids
        entry: dict[str, Any] = {
            "type": src.source_label,
            "id": chunk_id,
            "metadata": dict(src.metadata or {}),
            "has_codes": has_codes,
        }
        if not has_codes:
            entry["text"] = sanitise_for_prompt(src.text or "", max_chars=500)
        source_entries.append(entry)

    body: dict[str, Any] = {
        "referring_specialty": referring_specialty,
        "codes": [serialise_code(c) for c in codes],
        "sources": source_entries,
        "source_accounting": _source_accounting(coverage),
    }
    if coverage and coverage.salvage_sentences:
        body["salvage_sentences"] = [
            _serialise_salvage(s) for s in coverage.salvage_sentences
        ]
    completeness = serialise_completeness_for_context(completeness_result)
    if completeness:
        body["completeness"] = completeness
    return body


def build_codes_first_user_message(
    sources: list[ResolvedSource],
    codes: list[ResolvedCode],
    coverage: CoverageReport | None = None,
    *,
    referring_specialty: str | None = None,
    completeness_result: dict[str, Any] | None = None,
) -> str:
    body = build_codes_first_envelope(
        sources,
        codes,
        coverage,
        referring_specialty=referring_specialty,
        completeness_result=completeness_result,
    )
    return "CONTEXT:\n```json\n" + json.dumps(body, default=str) + "\n```"


def _source_accounting(coverage: CoverageReport | None) -> dict[str, int]:
    if coverage is None:
        return {}
    return {
        "total_sentences": coverage.total_sentences,
        "covered_sentences": coverage.covered_sentences,
        "uncovered_sentences": coverage.uncovered_sentences,
        "salvage_sentences": len(coverage.salvage_sentences),
        "omitted_filler": coverage.omitted_filler,
        "omitted_uncoded": coverage.omitted_uncoded,
    }
