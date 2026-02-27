"""Two-phase coding pipeline adapted from PCA V3PipelineService.

Phase 1: LLM-based term extraction from de-identified encounter text.
Phase 2: Terminology resolution via the Terminology API (hybrid search).

Key differences from the original:
- Calls Terminology API HTTP endpoint for resolution instead of direct Neo4j
- Uses libs/llm-client for LLM invocation with cache + fallback
- Publishes progress via a callback hook (Redis pub/sub in production)
- Async-first design for Service Bus consumer context
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

from libs.cypher.candidate_queries import (
    UPSERT_CANDIDATE,
    CREATE_REVIEW_TASK,
)
from libs.cypher.documents_queries import write_documents_from_sentences_payload
from services.coding_worker.app.pipeline.llm_extractor import (
    ExtractionError,
    ExtractedTerm,
    LLMExtractor,
)
from services.coding_worker.app.pipeline.sentence_splitter import (
    SentenceChunk,
    SentenceSplitter,
    deduplicate_lines,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 5
_READ_CODE_RE = re.compile(r"\(([A-Za-z0-9.]{3,8})\)")
TERMINOLOGY_API_URL = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001")


@dataclass
class PipelineStats:
    processed_encounters: int = 0
    queued_for_review: int = 0
    rejected_hard_fail: int = 0
    warnings_only: int = 0

    def record(self, hard_fails: bool, warnings: bool) -> None:
        self.processed_encounters += 1
        self.queued_for_review += 1
        if hard_fails:
            self.rejected_hard_fail += 1
        elif warnings:
            self.warnings_only += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "processed_encounters": self.processed_encounters,
            "queued_for_review": self.queued_for_review,
            "rejected_hard_fail": self.rejected_hard_fail,
            "warnings_only": self.warnings_only,
        }


class CodingPipeline:
    """Async coding pipeline for the Coding Worker."""

    def __init__(self, patient_client, knowledge_client) -> None:
        self.patient_client = patient_client
        self.knowledge_client = knowledge_client
        model_id = os.getenv("AWS_BEDROCK_MODEL", "")
        region = os.getenv("AWS_DEFAULT_REGION", "eu-west-2")
        self.splitter = SentenceSplitter()
        self.extractor = LLMExtractor(model_id=model_id, region=region)

    async def run(
        self,
        patient_ids: list[str],
        dry_run: bool = False,
        progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> PipelineStats:
        stats = PipelineStats()
        for patient_id in patient_ids:
            encounters = self._fetch_encounters(patient_id)
            self._emit(progress_hook, {
                "type": "patient_started",
                "patient_id": patient_id,
                "encounter_count": len(encounters),
            })
            for enc in encounters:
                await self._process_encounter(patient_id, enc, dry_run, stats, progress_hook)
        self._emit(progress_hook, {"type": "run_completed", **stats.snapshot()})
        return stats

    async def run_unprocessed(
        self,
        patient_ids: list[str],
        dry_run: bool = False,
        progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> PipelineStats:
        stats = PipelineStats()
        for patient_id in patient_ids:
            encounters = self._fetch_unprocessed_encounters(patient_id)
            self._emit(progress_hook, {
                "type": "patient_started",
                "patient_id": patient_id,
                "encounter_count": len(encounters),
            })
            for enc in encounters:
                await self._process_encounter(patient_id, enc, dry_run, stats, progress_hook)
        self._emit(progress_hook, {"type": "run_completed", **stats.snapshot()})
        return stats

    async def run_single_encounter(
        self,
        patient_id: str,
        encounter_id: str,
        dry_run: bool = False,
        progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> PipelineStats:
        stats = PipelineStats()
        rows = self.patient_client.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid AND toString(e.id) = $eid "
            "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text",
            pid=patient_id,
            eid=encounter_id,
        )
        if rows:
            await self._process_encounter(patient_id, rows[0], dry_run, stats, progress_hook)
        self._emit(progress_hook, {"type": "run_completed", **stats.snapshot()})
        return stats

    async def _process_encounter(
        self,
        patient_id: str,
        encounter: dict[str, Any],
        dry_run: bool,
        stats: PipelineStats,
        progress_hook: Optional[Callable[[dict[str, Any]], None]],
    ) -> None:
        encounter_id = str(encounter.get("encounter_id", ""))
        encounter_text = str(encounter.get("text") or "")

        self._emit(progress_hook, {
            "type": "encounter_started",
            "patient_id": patient_id,
            "encounter_id": encounter_id,
        })

        deidentified = deduplicate_lines(encounter_text)
        sentences = self.splitter.split(deidentified)
        self._emit(progress_hook, {
            "type": "sentence_split_completed",
            "sentence_count": len(sentences),
        })

        try:
            extracted = self._extract_terms(deidentified, sentences)
        except ExtractionError as exc:
            logger.error("Extraction failed for %s: %s", encounter_id, exc)
            stats.record(True, False)
            self._emit(progress_hook, {"type": "encounter_processed", **stats.snapshot()})
            return

        all_terms = [t for terms in extracted.values() for t in terms]
        self._emit(progress_hook, {
            "type": "term_extraction_completed",
            "term_count": len(all_terms),
        })

        resolved = await self._resolve_via_api([t.lookup_term for t in all_terms])
        self._emit(progress_hook, {"type": "coding_resolve_completed"})

        sentences_payload = self._build_sentences_payload(sentences, extracted, resolved)

        if not dry_run:
            candidate_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"candidate:{patient_id}:{encounter_id}"))
            self._persist_candidate(patient_id, encounter_id, encounter, deidentified, candidate_id, sentences_payload)

        stats.record(False, False)
        self._emit(progress_hook, {"type": "encounter_processed", **stats.snapshot()})

    def _extract_terms(
        self, deidentified: str, sentences: list[SentenceChunk]
    ) -> dict[str, list[ExtractedTerm]]:
        by_sentence: dict[str, list[ExtractedTerm]] = {s.sentence_id: [] for s in sentences}
        for idx in range(0, len(sentences), _BATCH_SIZE):
            batch = sentences[idx : idx + _BATCH_SIZE]
            extracted = self.extractor.extract_batch(deidentified, batch)
            for term in extracted:
                by_sentence.setdefault(term.sentence_id, []).append(term)
        return by_sentence

    async def _resolve_via_api(self, terms: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Call the Terminology API /resolve endpoint."""
        if not terms:
            return {}
        unique = list(dict.fromkeys(terms))
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{TERMINOLOGY_API_URL}/terminology/resolve",
                    json={"terms": unique},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("results", {})
        except Exception:
            logger.warning("Terminology API call failed — returning empty results", exc_info=True)
            return {}

    def _build_sentences_payload(
        self,
        sentences: list[SentenceChunk],
        extracted: dict[str, list[ExtractedTerm]],
        resolved: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        term_counter = 0
        for sentence in sentences:
            terms_data: list[dict[str, Any]] = []
            for term in extracted.get(sentence.sentence_id, []):
                candidates = resolved.get(term.lookup_term, [])
                best = candidates[0] if candidates else {}
                terms_data.append({
                    "term_id": f"{sentence.sentence_id}_t{term_counter}",
                    "text": term.text,
                    "span_start": sentence.start,
                    "span_end": sentence.end,
                    "coding": {
                        "snomed_concept_id": best.get("snomed_concept_id"),
                        "read_code": best.get("read_code"),
                        "snomed_term": best.get("snomed_term"),
                        "score": best.get("score", 0.0),
                        "source": best.get("source", "terminology_api"),
                    },
                    "semantic_tag": term.semantic_tag,
                    "modifiers": term.modifiers,
                })
                term_counter += 1
            payload.append({
                "sentence_id": sentence.sentence_id,
                "start": sentence.start,
                "end": sentence.end,
                "text": sentence.text,
                "terms": terms_data,
            })
        return payload

    @staticmethod
    def _stable_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _persist_candidate(
        self,
        patient_id: str,
        encounter_id: str,
        encounter: dict[str, Any],
        deidentified: str,
        candidate_id: str,
        sentences_payload: list[dict[str, Any]],
    ) -> None:
        source_hash = self._stable_hash(str(encounter.get("text") or ""))
        deidentified_hash = self._stable_hash(deidentified)
        sentences_json = json.dumps(sentences_payload, ensure_ascii=False)
        task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"review-task:{candidate_id}"))

        with self.patient_client.session() as session:
            # Write the full candidate (all fields required by the review queue)
            session.run(
                UPSERT_CANDIDATE,
                candidate_id=candidate_id,
                patient_id=patient_id,
                encounter_id=encounter_id,
                date=str(encounter.get("date", "")),
                source_hash=source_hash,
                deidentified_hash=deidentified_hash,
                deidentified_text=deidentified,
                approval_status="pending",
                hard_fail_reasons=[],
                warning_reasons=[],
                sentences_json=sentences_json,
                llm_usage_json=None,
            )
            # Create the ReviewTask so this candidate appears in the review queue
            # and _fetch_unprocessed_encounters treats the encounter as processed.
            session.run(
                CREATE_REVIEW_TASK,
                candidate_id=candidate_id,
                task_id=task_id,
                priority=50,
                status="pending",
                assigned_reviewer=None,
                warning_count=0,
            )

            # Write provisional DOCUMENTS + HAS_<tag> links immediately so
            # downstream workers (episode builder, analytics) can query them
            # before a human reviewer has approved the candidate.
            written = write_documents_from_sentences_payload(
                encounter_id,
                sentences_payload,
                session,
                source="provisional",
            )
            logger.debug(
                "_persist_candidate: wrote %d provisional DOCUMENTS links for encounter %s",
                written,
                encounter_id,
            )

    def _fetch_encounters(self, patient_id: str) -> list[dict[str, Any]]:
        return self.patient_client.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text "
            "ORDER BY e.date",
            pid=patient_id,
        )

    def _fetch_unprocessed_encounters(self, patient_id: str) -> list[dict[str, Any]]:
        return self.patient_client.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "AND NOT EXISTS { "
            "  MATCH (c:EncounterCandidate)-[:HAS_TASK]->(:ReviewTask) "
            "  WHERE c.patient_id = $pid AND c.encounter_id = toString(e.id) "
            "} "
            "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text "
            "ORDER BY e.date",
            pid=patient_id,
        )

    @staticmethod
    def _emit(hook: Optional[Callable[[dict[str, Any]], None]], payload: dict[str, Any]) -> None:
        if hook:
            hook(payload)
