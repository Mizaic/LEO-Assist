"""V3 clinical coding pipeline service."""

from __future__ import annotations

import logging
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.config import get_settings
from app.db.neo4j_client import run_with_retry
from app.services.neo4j_store import create_review_task, upsert_candidate
from app.services.v3.coding_resolver import CodingResolver
from app.services.v3.disambiguator import CodingDisambiguator
from app.services.v3.llm_extractor import ExtractionError, ExtractedTerm, LLMExtractor
from app.services.v3.llm_usage import LLMCostConfig, LLMUsage
from app.services.v3.patient_graph_writer import SemanticLinkPayload
from app.services.v3.post_processing_rules import apply_rules as apply_post_rules
from app.services.v3.sentence_splitter import SentenceChunk, SentenceSplitter, deduplicate_lines

logger = logging.getLogger(__name__)


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
    llm_usage: LLMUsage = field(default_factory=LLMUsage.zero)
    _cost_config: LLMCostConfig | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, hard_fails: bool, warnings: bool) -> None:
        with self._lock:
            self.processed_encounters += 1
            self.queued_for_review += 1
            if hard_fails:
                self.rejected_hard_fail += 1
            elif warnings:
                self.warnings_only += 1

    def add_usage(self, usage: LLMUsage) -> None:
        with self._lock:
            self.llm_usage += usage

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "processed_encounters": self.processed_encounters,
                "queued_for_review": self.queued_for_review,
                "rejected_hard_fail": self.rejected_hard_fail,
                "warnings_only": self.warnings_only,
                "llm_usage": self.llm_usage.to_dict(self._cost_config),
            }


class V3PipelineService:
    def __init__(self, patient_client, coding_client) -> None:
        self.patient_graph = patient_client
        self.coding_graph = coding_client
        self.settings = get_settings()
        self.cost_config = self._load_cost_config()
        (
            self.build_audit_event,
            self.deidentify_text,
            self.stable_hash,
            self.validate_encounter_payload,
        ) = _load_v2_utils()
        self.version_bundle = {
            "pipeline_version": f"{self.settings.pipeline_version}-v3",
            "extractor_version": "v3.llm_batch5_prompt_v2",
            "validator_version": self.settings.validator_version,
            "model_id": self.settings.model_id,
            "prompt_version": "v2",
            "terminology_version": self.settings.terminology_version,
        }
        region = self._resolve_aws_region()
        self.splitter = SentenceSplitter()
        self.extractor = LLMExtractor(model_id=self.settings.model_id, region=region)
        self.resolver = CodingResolver(embedder=self._try_load_embedder())
        self.disambiguator = CodingDisambiguator(model_id=self.settings.model_id, region=region)

    @staticmethod
    def _load_cost_config() -> LLMCostConfig:
        cfg = LLMCostConfig.from_env()
        logger.info(
            "LLM cost config: $%.2f/1M input, $%.4f/1M cached, $%.2f/1M output",
            cfg.cost_per_1m_input, cfg.cost_per_1m_cached_input, cfg.cost_per_1m_output,
        )
        return cfg

    _embedder_cache: Any = None

    @classmethod
    def _try_load_embedder(cls):
        if cls._embedder_cache is not None:
            return cls._embedder_cache
        try:
            from scripts.embedding_utils import TextEmbedder, load_vector_settings
            settings = load_vector_settings()
            embedder = TextEmbedder(settings)
            # Eager load so model is ready before any request handling
            embedder.encode(["x"])
            logger.info("Vector embedder loaded: model=%s", settings.model_name)
            cls._embedder_cache = embedder
            return embedder
        except Exception:
            logger.info("Vector embedder unavailable — hybrid resolution will use exact+fulltext only")
            return None

    @classmethod
    def preload_embedder(cls) -> None:
        """Load embedder at app startup (main thread). Call from lifespan."""
        cls._try_load_embedder()

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
        stats = PipelineStats(_cost_config=self.cost_config)
        workers = max(1, min(workers, _MAX_WORKERS))

        logger.info(
            "Starting pipeline run %s — %d patients, dry_run=%s, workers=%d",
            run_id, len(patient_ids), dry_run, workers,
        )

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

        snap = stats.snapshot()
        usage = snap.get("llm_usage", {})
        logger.info(
            "Pipeline run %s finished - %d processed, %d queued, %d hard-fail | "
            "LLM: %d calls, %d in + %d out = %d tokens, $%.4f",
            run_id,
            snap.get("processed_encounters", 0),
            snap.get("queued_for_review", 0),
            snap.get("rejected_hard_fail", 0),
            usage.get("llm_calls", 0),
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
            usage.get("total_tokens", 0),
            usage.get("cost_usd", 0.0),
        )
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
        slot_counter = 0
        slot_lock = threading.Lock()
        thread_slots: dict[int, int] = {}

        def _thread_slot() -> int:
            nonlocal slot_counter
            tid = threading.get_ident()
            with slot_lock:
                if tid not in thread_slots:
                    slot_counter += 1
                    thread_slots[tid] = slot_counter
                return thread_slots[tid]

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for patient_id, encounter in work:
                fut = pool.submit(
                    self._process_encounter,
                    patient_id,
                    encounter,
                    run_id,
                    dry_run,
                    stats,
                    progress_hook=progress_hook,
                    worker_id_fn=_thread_slot,
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
        worker_id_fn: Callable[[], int] | None = None,
    ) -> None:
        resolved_wid = worker_id_fn() if worker_id_fn else worker_id
        encounter_id = str(encounter.get("encounter_id"))
        base = {
            "type": "encounter_started",
            "run_id": run_id,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            **stats.snapshot(),
        }
        if resolved_wid is not None:
            base["worker_id"] = resolved_wid

        logger.info("Fetching encounter %s for patient %s", encounter_id, patient_id)
        self._emit(progress_hook, base)

        encounter_text = str(encounter.get("text") or "")
        self._emit(progress_hook, {**base, "type": "deidentify_started"})
        logger.info("De-identifying encounter %s (%d chars)", encounter_id, len(encounter_text))
        deidentified = self.deidentify_text(encounter_text)
        deidentified = deduplicate_lines(deidentified)
        self._emit(
            progress_hook,
            {
                **base,
                "type": "deidentify_completed",
                "input_chars": len(encounter_text),
                "output_chars": len(deidentified),
            },
        )

        self._emit(progress_hook, {**base, "type": "sentence_split_started"})
        sentence_chunks = self.splitter.split(deidentified)
        logger.info("Split into %d sentences", len(sentence_chunks))
        self._emit(
            progress_hook,
            {
                **base,
                "type": "sentence_split_completed",
                "sentence_count": len(sentence_chunks),
            },
        )

        self._emit(progress_hook, {**base, "type": "term_extraction_started"})
        logger.info("Sending encounter %s to LLM for extraction", encounter_id)
        try:
            extracted, extraction_usage = self._extract_terms_for_encounter(
                deidentified, sentence_chunks,
            )
        except ExtractionError as exc:
            logger.error(
                "Extraction hard-fail for encounter %s: %s", encounter_id, exc,
            )
            self._emit(
                progress_hook,
                {
                    **base,
                    "type": "term_extraction_failed",
                    "error": str(exc),
                },
            )
            candidate = self._build_candidate(
                patient_id=patient_id,
                encounter_id=encounter_id,
                date=str(encounter.get("date", "")),
                source_text=encounter_text,
                deidentified_text=deidentified,
                sentences_payload=[],
            )
            candidate["hard_fail_reasons"] = [f"extraction_error: {exc}"]
            candidate["warning_reasons"] = []
            stats.record(True, False)
            self._persist(candidate, [], dry_run, True, base, progress_hook)
            self._emit(progress_hook, {**base, **stats.snapshot(), "type": "encounter_processed"})
            return

        stats.add_usage(extraction_usage)
        term_count = sum(len(v) for v in extracted.values())
        logger.info(
            "LLM extracted %d terms from encounter %s (%d tokens)",
            term_count, encounter_id, extraction_usage.total_tokens,
        )
        self._emit(
            progress_hook,
            {
                **base,
                "type": "term_extraction_completed",
                "term_count": term_count,
                "llm_usage": extraction_usage.to_dict(self.cost_config),
            },
        )

        self._emit(progress_hook, {**base, "type": "coding_resolve_started"})
        logger.info("Sending %d terms for SNOMED coding resolution", term_count)
        sentences_payload, semantic_links, disambig_usage = self._resolve_and_build_payload(
            deidentified,
            sentence_chunks,
            extracted,
        )
        stats.add_usage(disambig_usage)
        resolution_count = sum(len(s.get("terms", [])) for s in sentences_payload)
        logger.info("Coding resolved — %d terms matched", resolution_count)
        self._emit(
            progress_hook,
            {
                **base,
                "type": "coding_resolve_completed",
                "resolution_count": resolution_count,
            },
        )

        encounter_llm_usage = extraction_usage + disambig_usage
        candidate = self._build_candidate(
            patient_id=patient_id,
            encounter_id=encounter_id,
            date=str(encounter.get("date", "")),
            source_text=encounter_text,
            deidentified_text=deidentified,
            sentences_payload=sentences_payload,
            llm_usage=encounter_llm_usage.to_dict(self.cost_config),
        )

        pp_result = apply_post_rules(candidate)
        if pp_result.actions:
            action_summary = "; ".join(a.detail for a in pp_result.actions)
            logger.info("Post-processing: %s", action_summary)
            self._emit(progress_hook, {
                **base,
                "type": "post_processing_applied",
                "actions": [{"rule_id": a.rule_id, "action": a.action, "detail": a.detail} for a in pp_result.actions],
                "terms_removed": pp_result.terms_removed,
                "terms_added": pp_result.terms_added,
                "auto_approve": pp_result.auto_approve,
            })

        self._emit(progress_hook, {**base, "type": "validation_started"})
        gate = self.validate_encounter_payload(candidate)
        candidate["hard_fail_reasons"] = gate.hard_fails
        candidate["warning_reasons"] = gate.warnings
        logger.info(
            "Validation complete — %d hard fails, %d warnings",
            len(gate.hard_fails), len(gate.warnings),
        )
        self._emit(
            progress_hook,
            {
                **base,
                "type": "validation_completed",
                "hard_fail_count": len(gate.hard_fails),
                "warning_count": len(gate.warnings),
            },
        )

        stats.record(bool(gate.hard_fails), bool(gate.warnings))
        self._persist(candidate, semantic_links, dry_run, bool(gate.hard_fails), base, progress_hook)
        self._emit(progress_hook, {**base, **stats.snapshot(), "type": "encounter_processed"})

    def _extract_terms_for_encounter(
        self,
        deidentified_text: str,
        sentence_chunks: list[SentenceChunk],
    ) -> tuple[dict[str, list[ExtractedTerm]], LLMUsage]:
        by_sentence: dict[str, list[ExtractedTerm]] = {s.sentence_id: [] for s in sentence_chunks}
        encounter_usage = LLMUsage.zero()
        for idx in range(0, len(sentence_chunks), _BATCH_SIZE):
            batch = sentence_chunks[idx : idx + _BATCH_SIZE]
            extracted, batch_usage = self.extractor.extract_batch(deidentified_text, batch)
            encounter_usage += batch_usage
            for term in extracted:
                by_sentence.setdefault(term.sentence_id, []).append(term)
        return by_sentence, encounter_usage

    def _resolve_and_build_payload(
        self,
        deidentified_text: str,
        sentence_chunks: list[SentenceChunk],
        extracted: dict[str, list[ExtractedTerm]],
    ) -> tuple[list[dict[str, Any]], list[SemanticLinkPayload], LLMUsage]:
        all_terms = [term for terms in extracted.values() for term in terms]
        all_texts = [t.lookup_term for t in all_terms]
        expected_tags = {t.lookup_term: t.semantic_tag for t in all_terms}
        sentences_payload: list[dict[str, Any]] = []
        links: list[SemanticLinkPayload] = []
        disambig_usage = LLMUsage.zero()
        term_counter = 0

        with self.coding_graph.session() as coding_session:
            candidates_by_text = self.resolver.resolve_candidates(
                all_texts, neo4j_session=coding_session,
                expected_tags=expected_tags,
            )

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
                    candidates = candidates_by_text.get(term.lookup_term, [])
                    best, call_usage = self.disambiguator.choose_best(
                        encounter_text=deidentified_text,
                        term_text=term.text,
                        candidates=candidates,
                    )
                    disambig_usage += call_usage
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
                self._append_inline_read_codes(payload, sentence, coding_session)
                sentences_payload.append(payload)
        return sentences_payload, links, disambig_usage

    def _append_inline_read_codes(
        self,
        sentence_payload: dict[str, Any],
        sentence: SentenceChunk,
        coding_session,
    ) -> None:
        """Attach inline read codes (e.g. (XaMeF)) to the preceding clinical span.

        Inline read codes in parentheses typically code the preceding phrase.
        Instead of creating a separate entity, we merge the read_code into the
        nearest preceding term's coding.
        """
        terms = sentence_payload["terms"]
        for match in READ_CODE_RE.finditer(sentence.text):
            read_code = match.group(1)
            read_code_abs_start = sentence.start + match.start()

            # Find the preceding term whose span ends before (or near) this read code.
            # Allow up to 10 chars gap for " (" between phrase and parenthetical code.
            max_gap = 10
            preceding: dict[str, Any] | None = None
            best_span_end = -1
            for t in terms:
                span_end = int(t.get("span_end", 0))
                if span_end <= read_code_abs_start + max_gap and span_end > best_span_end:
                    best_span_end = span_end
                    preceding = t

            if preceding is not None:
                # Attach read_code to the preceding span's coding
                coding = preceding.setdefault("coding", {})
                coding["read_code"] = read_code
                if coding.get("source") != "inline_read_code":
                    coding["source"] = (
                        "inline_read_code" if not coding.get("snomed_concept_id") else "neo4j_hybrid+inline_read_code"
                    )
                # Resolve read code to SNOMED if term has no concept yet
                if not coding.get("snomed_concept_id"):
                    resolved = self.resolver.resolve_read_code(
                        read_code, neo4j_session=coding_session,
                    )
                    if resolved:
                        coding["snomed_concept_id"] = resolved.snomed_concept_id
                        coding["snomed_term"] = resolved.snomed_term
                        coding["score"] = max(float(coding.get("score", 0)), resolved.score)
                continue

            # No preceding term: create a standalone term only if truly orphaned
            # (e.g. sentence starts with (XaMeF)). Avoid creating duplicates.
            seen = {str(t.get("text", "")).lower() for t in terms}
            key = f"read:{read_code.lower()}"
            if key in seen:
                continue
            next_idx = len(terms)
            terms.append(
                {
                    "term_id": f"{sentence.sentence_id}_t{next_idx}",
                    "text": read_code,
                    "span_start": read_code_abs_start,
                    "span_end": read_code_abs_end,
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
        llm_usage: dict[str, Any] | None = None,
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
            "llm_usage": llm_usage,
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
            self._emit(progress_hook, {**base, "type": "persist_skipped"})
            return
        self._emit(progress_hook, {**base, "type": "persist_started"})
        with self.patient_graph.session() as patient_session:
            upsert_candidate(candidate, patient_session)
            if hard_fail:
                priority = 150
            elif candidate.get("warning_reasons"):
                priority = 100
            else:
                priority = 50
            create_review_task(
                candidate_id=candidate["candidate_id"],
                session=patient_session,
                priority=priority,
                warning_count=len(candidate.get("warning_reasons", [])),
            )

        self._emit(progress_hook, {**base, "type": "persist_completed", "queued": True})

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

    def _fetch_unprocessed_encounters(self, patient_id: str) -> list[dict[str, Any]]:
        """Return encounters that have no EncounterCandidate with a ReviewTask."""
        with self.patient_graph.session() as session:
            result = session.run(
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
            return [dict(row) for row in result]

    def run_unprocessed(
        self,
        patient_ids: list[str],
        dry_run: bool = False,
        workers: int = _DEFAULT_WORKERS,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, PipelineStats]:
        """Run pipeline only for encounters that don't yet have a ReviewTask."""
        run_id = str(uuid.uuid4())
        stats = PipelineStats(_cost_config=self.cost_config)
        workers = max(1, min(workers, _MAX_WORKERS))

        work: list[tuple[str, dict[str, Any]]] = []
        for patient_id in patient_ids:
            encounters = self._fetch_unprocessed_encounters(patient_id)
            logger.info(
                "Patient %s: %d unprocessed encounters to run",
                patient_id, len(encounters),
            )
            self._emit(
                progress_hook,
                {
                    "type": "run_started",
                    "run_id": run_id,
                    "patient_count": len(patient_ids),
                    "encounter_count": len(encounters),
                    "dry_run": dry_run,
                    "workers": workers,
                    "pipeline_version": "v3",
                    "mode": "unprocessed_only",
                },
            )
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

        if not work:
            self._emit(progress_hook, {
                "type": "run_completed", "run_id": run_id,
                **stats.snapshot(), "message": "No unprocessed encounters found",
            })
            return run_id, stats

        if workers <= 1 or len(work) <= 1:
            for patient_id, encounter in work:
                self._process_encounter(
                    patient_id, encounter, run_id, dry_run, stats,
                    progress_hook=progress_hook,
                )
        else:
            self._process_parallel(work, run_id, dry_run, stats, workers, progress_hook)

        self._emit(progress_hook, {
            "type": "run_completed", "run_id": run_id, **stats.snapshot(),
        })
        return run_id, stats

    def run_single_encounter(
        self,
        patient_id: str,
        encounter_id: str,
        dry_run: bool = False,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, PipelineStats]:
        """Run the pipeline for exactly one encounter."""
        run_id = str(uuid.uuid4())
        stats = PipelineStats(_cost_config=self.cost_config)

        rows = run_with_retry(
            self.patient_graph,
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid AND toString(e.id) = $eid "
            "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text",
            pid=patient_id,
            eid=encounter_id,
        )

        if not rows:
            self._emit(progress_hook, {
                "type": "run_completed", "run_id": run_id,
                **stats.snapshot(), "message": "Encounter not found",
            })
            return run_id, stats

        encounter = rows[0]

        self._emit(progress_hook, {
            "type": "run_started",
            "run_id": run_id,
            "patient_count": 1,
            "encounter_count": 1,
            "dry_run": dry_run,
            "workers": 1,
            "pipeline_version": "v3",
            "mode": "single_encounter",
        })
        self._emit(progress_hook, {
            "type": "patient_started",
            "run_id": run_id,
            "patient_id": patient_id,
            "encounter_count": 1,
        })

        self._process_encounter(
            patient_id, encounter, run_id, dry_run, stats,
            progress_hook=progress_hook,
        )

        self._emit(progress_hook, {
            "type": "run_completed", "run_id": run_id, **stats.snapshot(),
        })
        return run_id, stats

    @staticmethod
    def _emit(hook: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]) -> None:
        if hook:
            hook(payload)

