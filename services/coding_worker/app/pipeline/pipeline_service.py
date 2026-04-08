from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from libs.coding_engine.tier_classifier import classify_tier
from libs.ner.extractor_contract import CONTRACT_VERSION, ExtractionItem
from libs.nlp.sentence_splitter import (
    SentenceChunk,
    SentenceSplitter,
    filter_header_sentences,
)
from services.coding_worker.app.pipeline.extractor_registry import build_extractor
from services.coding_worker.app.pipeline.llm_extractor import (
    ExtractedTerm,
    LLMExtractor,
    maybe_create_surface_form_tasks,
)


def _items_to_dicts(items: list[ExtractionItem]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        row = {
            "sentence_id": item.sentence_id,
            "text": item.text,
            "label": item.semantic_tag,
            "semantic_tag": item.semantic_tag,
            "assertion": item.assertion,
            "lookup_term": item.normalized,
            "normalized": item.normalized,
            "confidence": item.confidence,
            "numeric_value": item.numeric_value,
            "value": item.numeric_value,
            "unit": item.unit,
            "reference_range": item.reference_range,
            "source": item.source,
            "model_name": item.model_name,
            "model_version": item.model_version,
            "contract_version": item.contract_version,
        }
        rows.append(row)
    return rows


def _dict_to_item(ent: dict[str, Any]) -> ExtractionItem:
    text = str(ent.get("text") or ent.get("normalized") or "")
    normalized = str(ent.get("normalized") or ent.get("lookup_term") or text)
    return ExtractionItem(
        sentence_id=str(ent.get("sentence_id") or "s0"),
        text=text,
        span_start=int(ent.get("span_start") or 0),
        span_end=int(ent.get("span_end") or len(text)),
        semantic_tag=str(ent.get("semantic_tag") or ent.get("label") or "finding"),
        assertion=str(ent.get("assertion") or "present"),
        confidence=float(ent.get("confidence") or 1.0),
        normalized=normalized,
        numeric_value=str(ent.get("numeric_value") or ent.get("value") or ""),
        unit=str(ent.get("unit") or ""),
        reference_range=str(ent.get("reference_range") or ""),
        source=str(ent.get("source") or "unknown"),
        model_name=str(ent.get("model_name") or ""),
        model_version=str(ent.get("model_version") or ""),
        contract_version=str(ent.get("contract_version") or CONTRACT_VERSION),
    )


@dataclass
class PipelineStats:
    processed_encounters: int = 0
    queued_for_review: int = 0
    rejected_hard_fail: int = 0
    warnings_only: int = 0
    llm_usage: dict[str, Any] | None = None

    def record(self, hard_fails: bool, warnings: bool) -> None:
        self.processed_encounters += 1
        if hard_fails:
            self.rejected_hard_fail += 1
        if warnings:
            self.warnings_only += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "processed_encounters": self.processed_encounters,
            "queued_for_review": self.queued_for_review,
            "rejected_hard_fail": self.rejected_hard_fail,
            "warnings_only": self.warnings_only,
            "llm_usage": self.llm_usage or {},
        }


class CodingPipeline:
    def __init__(self, patient_client, knowledge_client, coding_mode: str = "hitl") -> None:
        self.patient_client = patient_client
        self.knowledge_client = knowledge_client
        self.coding_mode = coding_mode
        self.sentence_splitter = SentenceSplitter()
        self.llm_extractor = LLMExtractor()

    @staticmethod
    def _emit(progress_hook, event: dict[str, Any]) -> None:
        if progress_hook:
            progress_hook(event)

    def _terminology_resolve_url(self) -> str:
        base = (os.getenv("TERMINOLOGY_API_URL") or "").strip()
        if not base:
            urls = (os.getenv("TERMINOLOGY_API_URLS") or "").strip()
            if urls:
                base = urls.split(",")[0].strip()
        if not base:
            base = "http://localhost:8001"
        return base.rstrip("/") + "/terminology/resolve"

    async def _resolve_via_api(self, terms: list[str], **_kwargs) -> dict[str, Any]:
        unique_terms = list(dict.fromkeys(t for t in terms if t))
        if not unique_terms:
            return {}
        url = self._terminology_resolve_url()
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json={"terms": unique_terms})
            response.raise_for_status()
            return (response.json() or {}).get("results", {})

    def _build_sentences_payload(
        self,
        sentences: list[SentenceChunk],
        extracted: dict[str, list[ExtractionItem | ExtractedTerm]],
        resolved: dict[str, Any],
        extractor=None,
    ) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        extractor = extractor or self.llm_extractor
        for sentence in sentences:
            sent_terms: list[dict[str, Any]] = []
            for item in extracted.get(sentence.sentence_id, []):
                if isinstance(item, ExtractedTerm):
                    text = item.text
                    lookup_term = item.lookup_term
                    semantic_tag = item.semantic_tag
                    assertion = item.assertion
                    numeric_value = ""
                    unit = ""
                    reference_range = ""
                    contract_version = CONTRACT_VERSION
                else:
                    text = item.text
                    lookup_term = item.normalized or item.text
                    semantic_tag = item.semantic_tag
                    assertion = item.assertion
                    numeric_value = item.numeric_value
                    unit = item.unit
                    reference_range = item.reference_range
                    contract_version = item.contract_version
                candidates = resolved.get(lookup_term) or resolved.get(text) or []
                best = candidates[0] if candidates else {}
                decision = classify_tier(
                    assertion=assertion,
                    context_failed=False,
                    terminology_score=float(best.get("score") or 0.0),
                    surface_form_status=str(best.get("surface_form_status") or ""),
                    coding_mode=self.coding_mode,
                )
                sent_terms.append(
                    {
                        "text": text,
                        "lookup_term": lookup_term,
                        "semantic_tag": semantic_tag,
                        "assertion": assertion,
                        "numeric_value": numeric_value,
                        "unit": unit,
                        "reference_range": reference_range,
                        "decision_tier": decision.tier,
                        "tier_decision": decision.decision,
                        "tier_reason": decision.reason,
                        "audit_flag": decision.tier == 2,
                        "coding": {
                            "snomed_concept_id": best.get("snomed_concept_id"),
                            "snomed_term": best.get("snomed_term"),
                            "read_code": best.get("read_code"),
                            "score": float(best.get("score") or 0.0),
                        },
                        "extraction_source": getattr(extractor, "source", ""),
                        "extraction_model_name": getattr(extractor, "model_name", ""),
                        "extraction_model_version": getattr(extractor, "model_version", ""),
                        "contract_version": contract_version,
                    }
                )
            payload.append({"sentence_id": sentence.sentence_id, "text": sentence.text, "terms": sent_terms})
        return payload

    def _persist_documents(self, encounter_id: str, sentences_payload: list[dict[str, Any]], extractor=None, run_id: str = "") -> None:
        _ = (extractor, run_id)
        if not self.patient_client:
            return
        with self.patient_client.session() as session:
            session.run(
                "MERGE (e:Encounter {id: $encounter_id}) SET e.sentences_payload = $payload",
                encounter_id=encounter_id,
                payload=json.dumps(sentences_payload),
            )

    def _write_coding_decisions(self, encounter_id: str, patient_id: str, sentences_payload: list[dict[str, Any]]) -> None:
        pid_hash = hashlib.sha256(patient_id.encode()).hexdigest()
        if not self.patient_client:
            return
        try:
            with self.patient_client.session() as session:
                idx = 0
                for sentence in sentences_payload:
                    for term in sentence.get("terms", []):
                        decision_id = f"dec:{encounter_id}:{idx}"
                        idx += 1
                        session.run(
                            "MERGE (d:CodingDecision {decision_id: $decision_id}) "
                            "SET d.patient_id_hash = $patient_id_hash",
                            decision_id=decision_id,
                            patient_id_hash=pid_hash,
                        )
        except Exception:
            return

    async def run_single_encounter(
        self,
        patient_id: str,
        encounter_id: str,
        *,
        dry_run: bool = False,
        progress_hook=None,
        run_id: str = "",
    ) -> None:
        run_id = run_id or str(uuid.uuid4())
        self._emit(progress_hook, {"type": "encounter_started", "patient_id": patient_id, "encounter_id": encounter_id, "run_id": run_id})
        rows = self.patient_client.run("MATCH (e:Encounter {id: $encounter_id}) RETURN e", encounter_id=encounter_id) if self.patient_client else []
        encounter = (rows or [{}])[0]
        encounter_text = str(encounter.get("text") or "")
        self._emit(progress_hook, {"type": "fetched", "patient_id": patient_id, "encounter_id": encounter_id, "run_id": run_id})
        sentences = filter_header_sentences(
            self.sentence_splitter.split(encounter_text)
        )
        extractor = build_extractor(progress_hook=progress_hook)
        try:
            items = extractor.extract_batch(encounter_text, sentences)
        except Exception as exc:
            self._emit(progress_hook, {"type": "failed", "stage": "extraction", "message": str(exc), "encounter_id": encounter_id, "run_id": run_id})
            return
        self._emit(progress_hook, {"type": "extracted", "count": len(items), "encounter_id": encounter_id, "run_id": run_id})
        extracted_by_sentence: dict[str, list[ExtractionItem]] = {}
        for item in items:
            extracted_by_sentence.setdefault(item.sentence_id, []).append(item)
        resolved = await self._resolve_via_api([item.normalized or item.text for item in items])
        self._emit(progress_hook, {"type": "resolved", "encounter_id": encounter_id, "run_id": run_id})
        maybe_create_surface_form_tasks(items, resolved)
        payload = self._build_sentences_payload(sentences, extracted_by_sentence, resolved, extractor)
        if not dry_run:
            self._persist_documents(encounter_id, payload, extractor, run_id=run_id)
            if self.coding_mode == "autonomous":
                self._write_coding_decisions(encounter_id, patient_id, payload)
        self._emit(progress_hook, {"type": "persisted", "encounter_id": encounter_id, "run_id": run_id})
        self._emit(progress_hook, {"type": "run_completed", "patient_id": patient_id, "encounter_id": encounter_id, "run_id": run_id})
