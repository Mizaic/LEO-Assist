"""V3 clinical coding pipeline service."""

from __future__ import annotations

import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.config import get_settings
from app.services.neo4j_store import create_review_task, upsert_candidate
from app.services.v3.coding_resolver import CodingResolver
from app.services.v3.disambiguator import CodingDisambiguator
from app.services.v3.llm_extractor import ExtractedTerm, LLMExtractor
from app.services.v3.patient_graph_writer import PatientGraphWriter, SemanticLinkPayload
from app.services.v3.sentence_splitter import SentenceChunk, SentenceSplitter


ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_WORKERS = 4
_MAX_WORKERS = 8
_BATCH_SIZE = 5
READ_CODE_RE = re.compile(r"\(([A-Za-z0-9.]{3,8})\)")


def _load_v2_utils():
    import sys

    if str(ROOT) not in sys.path:
        sys.path.append(str(ROOT))
    from scripts.training_v2_utils import (  # pylint: disable=import-outside-toplevel
        build_audit_event,
        deidentify_text,
        stable_hash,
        validate_encounter_payload,
    )

    return build_audit_event, deidentify_text, stable_hash, validate_encounter_payload


@dataclass
class PipelineStats:
    processed_encounters: int = 0
    queued_for_review: int = 0
    rejected_hard_fail: int = 0
    warnings_only: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, hard_fails: bool, warnings: bool) -> None:
        with self._lock:
            self.processed_encounters += 1
            if hard_fails:
                self.rejected_hard_fail += 1
            else:
                if warnings:
                    self.warnings_only += 1
                self.queued_for_review += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "processed_encounters": self.processed_encounters,
                "queued_for_review": self.queued_for_review,
                "rejected_hard_fail": self.rejected_hard_fail,
                "warnings_only": self.warnings_only,
            }


class V3PipelineService:
    def __init__(self, patient_client, coding_client) -> None:
        self.patient_graph = patient_client
        self.coding_graph = coding_client
        self.settings = get_settings()
        (
            self.build_audit_event,
            self.deidentify_text,
            self.stable_hash,
            self.validate_encounter_payload,
        ) = _load_v2_utils()
        self.version_bundle = {
            "pipeline_version": f"{self.settings.pipeline_version}-v3",
            "extractor_version": "v3.llm_batch5",
            "validator_version": self.settings.validator_version,
            "model_id": self.settings.model_id,
            "prompt_version": self.settings.prompt_version,
            "terminology_version": self.settings.terminology_version,
        }
        region = self._resolve_aws_region()
        self.splitter = SentenceSplitter()
        self.extractor = LLMExtractor(model_id=self.settings.model_id, region=region)
        self.resolver = CodingResolver()
        self.disambiguator = CodingDisambiguator(model_id=self.settings.model_id, region=region)
        self.graph_writer = PatientGraphWriter()

    def _resolve_aws_region(self) -> str | None:
        import os

        return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "eu-west-2"

    def run(
        self,
        patient_ids: list[str],
        max_encounters_per_patient: int | None = None,
        dry_run: bool = False,
        workers: int = _DEFAULT_WORKERS,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, PipelineStats]:
        run_id = str(uuid.uuid4())
        stats = PipelineStats()
        workers = max(1, min(workers, _MAX_WORKERS))

        self._emit(
            progress_hook,
            {
                "type": "run_started",
                "run_id": run_id,
                "patient_count": len(patient_ids),
                "dry_run": dry_run,
                "workers": workers,
                "pipeline_version": "v3",
                "sentence_mode": self.splitter.mode,
                "llm_enabled": self.extractor.enabled,
            },
        )

        work: list[tuple[str, dict[str, Any]]] = []
        for patient_id in patient_ids:
            encounters = self._fetch_encounters(patient_id, max_encounters_per_patient)
            self._emit(
                progress_hook,
                {
                    "type": "patient_started",
                    "run_id": run_id,
                    "patient_id": patient_id,
                    "encounter_count": len(encounters),
                },
            )
            for enc in encounters:
                work.append((patient_id, enc))

        if workers <= 1 or len(work) <= 1:
            for patient_id, encounter in work:
                self._process_encounter(
                    patient_id,
                    encounter,
                    run_id,
                    dry_run,
                    stats,
                    progress_hook=progress_hook,
                )
        else:
            self._process_parallel(work, run_id, dry_run, stats, workers, progress_hook)

        self._emit(
            progress_hook,
            {
                "type": "run_completed",
                "run_id": run_id,
                **stats.snapshot(),
            },
        )
        return run_id, stats

    def _process_parallel(
        self,
        work: list[tuple[str, dict[str, Any]]],
        run_id: str,
        dry_run: bool,
        stats: PipelineStats,
        workers: int,
        progress_hook: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        worker_counter = 0
        lock = threading.Lock()

        def _next_worker_id() -> int:
            nonlocal worker_counter
            with lock:
                worker_counter += 1
                return worker_counter

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for patient_id, encounter in work:
                wid = _next_worker_id()
                fut = pool.submit(
                    self._process_encounter,
                    patient_id,
                    encounter,
                    run_id,
                    dry_run,
                    stats,
                    progress_hook=progress_hook,
                    worker_id=wid,
                )
                futures[fut] = (patient_id, encounter)
            for fut in as_completed(futures):
                exc = fut.exception()
                if not exc:
                    continue
                patient_id, encounter = futures[fut]
                self._emit(
                    progress_hook,
                    {
                        "type": "encounter_error",
                        "run_id": run_id,
                        "patient_id": patient_id,
                        "encounter_id": str(encounter.get("encounter_id")),
                        "error": str(exc),
                    },
                )

    def _process_encounter(
        self,
        patient_id: str,
        encounter: dict[str, Any],
        run_id: str,
        dry_run: bool,
        stats: PipelineStats,
        *,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
        worker_id: int | None = None,
    ) -> None:
        encounter_id = str(encounter.get("encounter_id"))
        base = {
            "type": "encounter_started",
            "run_id": run_id,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            **stats.snapshot(),
        }
        if worker_id is not None:
            base["worker_id"] = worker_id
        self._emit(progress_hook, base)

        encounter_text = str(encounter.get("text") or "")
        self._emit(progress_hook, {"type": "deidentify_started", **base})
        deidentified = self.deidentify_text(encounter_text)
        self._emit(
            progress_hook,
            {
                "type": "deidentify_completed",
                **base,
                "input_chars": len(encounter_text),
                "output_chars": len(deidentified),
            },
        )

        self._emit(progress_hook, {"type": "sentence_split_started", **base})
        sentence_chunks = self.splitter.split(deidentified)
        self._emit(
            progress_hook,
            {
                "type": "sentence_split_completed",
                **base,
                "sentence_count": len(sentence_chunks),
            },
        )

        self._emit(progress_hook, {"type": "term_extraction_started", **base})
        extracted = self._extract_terms_for_encounter(deidentified, sentence_chunks)
        self._emit(
            progress_hook,
            {
                "type": "term_extraction_completed",
                **base,
                "term_count": sum(len(v) for v in extracted.values()),
            },
        )

        self._emit(progress_hook, {"type": "coding_resolve_started", **base})
        sentences_payload, semantic_links = self._resolve_and_build_payload(
            deidentified,
            sentence_chunks,
            extracted,
        )
        self._emit(
            progress_hook,
            {
                "type": "coding_resolve_completed",
                **base,
                "resolution_count": sum(len(s.get("terms", [])) for s in sentences_payload),
            },
        )

        candidate = self._build_candidate(
            patient_id=patient_id,
            encounter_id=encounter_id,
            date=str(encounter.get("date", "")),
            source_text=encounter_text,
            deidentified_text=deidentified,
            sentences_payload=sentences_payload,
        )
        self._emit(progress_hook, {"type": "validation_started", **base})
        gate = self.validate_encounter_payload(candidate)
        candidate["hard_fail_reasons"] = gate.hard_fails
        candidate["warning_reasons"] = gate.warnings
        self._emit(
            progress_hook,
            {
                "type": "validation_completed",
                **base,
                "hard_fail_count": len(gate.hard_fails),
                "warning_count": len(gate.warnings),
            },
        )

        stats.record(bool(gate.hard_fails), bool(gate.warnings))
        self._persist(candidate, semantic_links, dry_run, bool(gate.hard_fails), base, progress_hook)
        self._emit(progress_hook, {"type": "encounter_processed", **base, **stats.snapshot()})

    def _extract_terms_for_encounter(
        self,
        deidentified_text: str,
        sentence_chunks: list[SentenceChunk],
    ) -> dict[str, list[ExtractedTerm]]:
        by_sentence: dict[str, list[ExtractedTerm]] = {s.sentence_id: [] for s in sentence_chunks}
        for idx in range(0, len(sentence_chunks), _BATCH_SIZE):
            batch = sentence_chunks[idx : idx + _BATCH_SIZE]
            extracted = self.extractor.extract_batch(deidentified_text, batch)
            for term in extracted:
                by_sentence.setdefault(term.sentence_id, []).append(term)
        return by_sentence

    def _resolve_and_build_payload(
        self,
        deidentified_text: str,
        sentence_chunks: list[SentenceChunk],
        extracted: dict[str, list[ExtractedTerm]],
    ) -> tuple[list[dict[str, Any]], list[SemanticLinkPayload]]:
        all_texts = [term.text for terms in extracted.values() for term in terms]
        with self.coding_graph.session() as coding_session:
            candidates_by_text = self.resolver.resolve_candidates(all_texts, neo4j_session=coding_session)

        sentences_payload: list[dict[str, Any]] = []
        links: list[SemanticLinkPayload] = []
        term_counter = 0

        for sentence in sentence_chunks:
            sentence_terms = extracted.get(sentence.sentence_id, [])
            payload_terms: list[dict[str, Any]] = []
            sentence_cursor = 0
            for term in sentence_terms:
                start_in_sentence = sentence.text.lower().find(term.text.lower(), sentence_cursor)
                if start_in_sentence < 0:
                    continue
                end_in_sentence = start_in_sentence + len(term.text)
                sentence_cursor = end_in_sentence

                absolute_start = sentence.start + start_in_sentence
                absolute_end = sentence.start + end_in_sentence
                candidates = candidates_by_text.get(term.text, [])
                best = self.disambiguator.choose_best(
                    encounter_text=deidentified_text,
                    term_text=term.text,
                    candidates=candidates,
                )
                coding = {
                    "snomed_concept_id": best.snomed_concept_id if best else None,
                    "read_code": best.read_code if best else None,
                    "snomed_term": best.snomed_term if best else None,
                    "score": best.score if best else 0.0,
                    "source": best.source if best else "neo4j_hybrid",
                }
                payload_terms.append(
                    {
                        "term_id": f"{sentence.sentence_id}_t{term_counter}",
                        "text": term.text,
                        "span_start": absolute_start,
                        "span_end": absolute_end,
                        "context": term.context,
                        "coding": coding,
                        "evidence_text": sentence.text,
                        "extraction_method": "v3_llm_batch",
                        "extraction_confidence": coding["score"],
                        "semantic_tag": term.semantic_tag,
                        "modifiers": term.modifiers,
                    }
                )
                term_counter += 1

                if best and best.snomed_concept_id:
                    links.append(
                        SemanticLinkPayload(
                            encounter_id=str(sentence.sentence_id),  # replaced in persist
                            semantic_tag=term.semantic_tag,
                            concept_id=best.snomed_concept_id,
                            term=best.snomed_term,
                            read_code=best.read_code,
                            evidence=term.text,
                            confidence=float(best.score),
                            domain="clinical",
                            context=term.context,
                            modifiers=term.modifiers,
                            source=best.source,
                        )
                    )
            payload = {
                "sentence_id": sentence.sentence_id,
                "start": sentence.start,
                "end": sentence.end,
                "text": sentence.text,
                "section": None,
                "terms": payload_terms,
            }
            self._append_inline_read_codes(payload, sentence)
            sentences_payload.append(payload)
        return sentences_payload, links

    def _append_inline_read_codes(self, sentence_payload: dict[str, Any], sentence: SentenceChunk) -> None:
        seen = {str(t.get("text", "")).lower() for t in sentence_payload["terms"]}
        next_idx = len(sentence_payload["terms"])
        for idx, match in enumerate(READ_CODE_RE.finditer(sentence.text), start=next_idx):
            read_code = match.group(1)
            key = f"read:{read_code.lower()}"
            if key in seen:
                continue
            seen.add(key)
            sentence_payload["terms"].append(
                {
                    "term_id": f"{sentence.sentence_id}_t{idx}",
                    "text": read_code,
                    "span_start": sentence.start + match.start(1),
                    "span_end": sentence.start + match.end(1),
                    "context": {
                        "negated": False,
                        "uncertain": False,
                        "historical": False,
                        "subject": "patient",
                        "temporality": "unknown",
                    },
                    "coding": {
                        "snomed_concept_id": None,
                        "read_code": read_code,
                        "snomed_term": None,
                        "score": 0.6,
                        "source": "inline_read_code",
                    },
                    "evidence_text": sentence.text,
                    "extraction_method": "inline_read_code",
                    "extraction_confidence": 0.6,
                    "semantic_tag": "Other",
                    "modifiers": {},
                }
            )

    def _build_candidate(
        self,
        *,
        patient_id: str,
        encounter_id: str,
        date: str,
        source_text: str,
        deidentified_text: str,
        sentences_payload: list[dict[str, Any]],
    ) -> dict[str, Any]:
        candidate_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"candidate:{patient_id}:{encounter_id}"))
        source_hash = self.stable_hash({"text": source_text})
        deid_hash = self.stable_hash({"text": deidentified_text})
        event = self.build_audit_event(
            event_type="candidate_generated_v3",
            actor="pipeline_v3",
            reason="llm batch extraction + neo4j resolve",
            before_payload={"patient_id": patient_id, "encounter_id": encounter_id, "source_hash": source_hash},
            after_payload={"candidate_id": candidate_id, "deidentified_hash": deid_hash, "sentences": sentences_payload},
            version_bundle=self.version_bundle,
        )
        return {
            "candidate_id": candidate_id,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "date": date,
            "source_hash": source_hash,
            "deidentified_hash": deid_hash,
            "deidentified_text": deidentified_text,
            "approval_status": "pending",
            "hard_fail_reasons": [],
            "warning_reasons": [],
            "sentences": sentences_payload,
            "audit_events": [event],
        }

    def _persist(
        self,
        candidate: dict[str, Any],
        semantic_links: list[SemanticLinkPayload],
        dry_run: bool,
        hard_fail: bool,
        base: dict[str, Any],
        progress_hook: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        if dry_run:
            self._emit(progress_hook, {"type": "persist_skipped", **base})
            return
        self._emit(progress_hook, {"type": "persist_started", **base})
        with self.coding_graph.session() as coding_session:
            upsert_candidate(candidate, coding_session)
            if not hard_fail:
                priority = 100 if candidate.get("warning_reasons") else 50
                create_review_task(
                    candidate_id=candidate["candidate_id"],
                    session=coding_session,
                    priority=priority,
                    warning_count=len(candidate.get("warning_reasons", [])),
                )

        # Write semantic links to patient graph for discoverability/correction UX.
        with self.patient_graph.session() as patient_session:
            encounter_id = str(candidate["encounter_id"])
            for link in semantic_links:
                if not link.concept_id:
                    continue
                payload = SemanticLinkPayload(
                    encounter_id=encounter_id,
                    semantic_tag=link.semantic_tag,
                    concept_id=link.concept_id,
                    term=link.term,
                    read_code=link.read_code,
                    evidence=link.evidence,
                    confidence=link.confidence,
                    domain=link.domain,
                    context=link.context,
                    modifiers=link.modifiers,
                    source=link.source,
                )
                self.graph_writer.upsert_documents_link(payload, session=patient_session)

        self._emit(progress_hook, {"type": "persist_completed", **base, "queued": not hard_fail})

    def _fetch_encounters(self, patient_id: str, max_enc: int | None) -> list[dict[str, Any]]:
        with self.patient_graph.session() as session:
            limit = max_enc or 10000
            result = session.run(
                "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
                "WHERE toString(p.id) = $pid "
                "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text "
                "ORDER BY e.date LIMIT $limit",
                pid=patient_id,
                limit=limit,
            )
            return [dict(row) for row in result]

    @staticmethod
    def _emit(hook: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]) -> None:
        if hook:
            hook(payload)

