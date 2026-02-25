"""Training data creator pipeline service for HITL MVP."""

from __future__ import annotations

import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.config import get_settings
from app.services.context_reconciler import reconcile_context
from app.services.neo4j_store import create_review_task, upsert_candidate
from app.services.term_patcher import batch_patch_surface_terms


ROOT = Path(__file__).resolve().parents[4]
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
TERM_RE = re.compile(
    r"\b([A-Za-z][A-Za-z\-]{2,}(?:\s+[A-Za-z][A-Za-z\-]{2,}){0,3})\b"
)
READ_CODE_RE = re.compile(r"\(([A-Za-z0-9.]{3,8})\)")

_DEFAULT_WORKERS = 4
_MAX_WORKERS = 8


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


class TrainingCreatorService:
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
            "pipeline_version": self.settings.pipeline_version,
            "extractor_version": self.settings.extractor_version,
            "validator_version": self.settings.validator_version,
            "model_id": self.settings.model_id,
            "prompt_version": self.settings.prompt_version,
            "terminology_version": self.settings.terminology_version,
        }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

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

        self._emit(progress_hook, {
            "type": "run_started",
            "run_id": run_id,
            "patient_count": len(patient_ids),
            "dry_run": dry_run,
            "workers": workers,
        })

        all_work: list[tuple[str, dict]] = []
        for patient_id in patient_ids:
            encounters = self._fetch_encounters(
                patient_id, max_encounters_per_patient
            )
            self._emit(progress_hook, {
                "type": "patient_started",
                "run_id": run_id,
                "patient_id": patient_id,
                "encounter_count": len(encounters),
            })
            for enc in encounters:
                all_work.append((patient_id, enc))

        if workers <= 1 or len(all_work) <= 1:
            for patient_id, enc in all_work:
                self._process_encounter(
                    patient_id, enc, run_id, dry_run, stats,
                    progress_hook=progress_hook,
                )
        else:
            self._process_parallel(
                all_work, run_id, dry_run, stats, workers, progress_hook
            )

        self._emit(progress_hook, {
            "type": "run_completed",
            "run_id": run_id,
            **stats.snapshot(),
        })
        return run_id, stats

    # ------------------------------------------------------------------
    # Parallel dispatch
    # ------------------------------------------------------------------

    def _process_parallel(
        self,
        work: list[tuple[str, dict]],
        run_id: str,
        dry_run: bool,
        stats: PipelineStats,
        workers: int,
        progress_hook: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        worker_counter = 0
        counter_lock = threading.Lock()

        def _next_worker_id() -> int:
            nonlocal worker_counter
            with counter_lock:
                worker_counter += 1
                return worker_counter

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for patient_id, enc in work:
                wid = _next_worker_id()
                fut = pool.submit(
                    self._process_encounter,
                    patient_id, enc, run_id, dry_run, stats,
                    progress_hook=progress_hook,
                    worker_id=wid,
                )
                futures[fut] = (patient_id, enc)

            for fut in as_completed(futures):
                exc = fut.exception()
                if exc:
                    pid, e = futures[fut]
                    self._emit(progress_hook, {
                        "type": "encounter_error",
                        "run_id": run_id,
                        "patient_id": pid,
                        "encounter_id": str(e.get("encounter_id")),
                        "error": str(exc),
                    })

    # ------------------------------------------------------------------
    # Single-encounter pipeline
    # ------------------------------------------------------------------

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
            "run_id": run_id,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
        }
        if worker_id is not None:
            base["worker_id"] = worker_id

        self._emit(progress_hook, {
            "type": "encounter_started", **base, **stats.snapshot(),
        })
        self._emit(progress_hook, {"type": "encounter_loaded", **base})

        candidate = self._build_candidate(
            patient_id, encounter, run_id=run_id,
            progress_hook=progress_hook, extra=base,
        )

        self._emit(progress_hook, {"type": "validation_started", **base})
        result = self.validate_encounter_payload(candidate)
        candidate["hard_fail_reasons"] = result.hard_fails
        candidate["warning_reasons"] = result.warnings
        self._emit(progress_hook, {
            "type": "validation_completed", **base,
            "hard_fail_count": len(result.hard_fails),
            "warning_count": len(result.warnings),
        })

        stats.record(bool(result.hard_fails), bool(result.warnings))

        self._persist_candidate(
            candidate, result, dry_run, base, stats, progress_hook
        )

        self._emit(progress_hook, {
            "type": "encounter_processed", **base, **stats.snapshot(),
        })

    # ------------------------------------------------------------------
    # Build candidate
    # ------------------------------------------------------------------

    def _build_candidate(
        self,
        patient_id: str,
        encounter: dict[str, Any],
        *,
        run_id: str,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encounter_id = str(encounter.get("encounter_id"))
        encounter_text = str(encounter.get("text") or "")
        ctx = extra or {}

        self._emit(progress_hook, {"type": "deidentify_started", **ctx})
        deidentified = self.deidentify_text(encounter_text)
        self._emit(progress_hook, {
            "type": "deidentify_completed", **ctx,
            "input_chars": len(encounter_text),
            "output_chars": len(deidentified),
        })

        # Keep one mutable candidate record per patient+encounter.
        candidate_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"candidate:{patient_id}:{encounter_id}",
            )
        )
        source_hash = self.stable_hash({"text": encounter_text})
        deidentified_hash = self.stable_hash({"text": deidentified})

        sentences = self._build_sentences(
            deidentified, progress_hook=progress_hook, extra=ctx,
        )

        event = self.build_audit_event(
            event_type="candidate_generated",
            actor="pipeline",
            reason="deterministic preprocessing and surface patch",
            before_payload={
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "source_hash": source_hash,
            },
            after_payload={
                "candidate_id": candidate_id,
                "deidentified_hash": deidentified_hash,
                "sentences": sentences,
            },
            version_bundle=self.version_bundle,
        )

        return {
            "candidate_id": candidate_id,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "date": str(encounter.get("date", "")),
            "source_hash": source_hash,
            "deidentified_hash": deidentified_hash,
            "deidentified_text": deidentified,
            "approval_status": "pending",
            "hard_fail_reasons": [],
            "warning_reasons": [],
            "sentences": sentences,
            "audit_events": [event],
        }

    # ------------------------------------------------------------------
    # Sentence splitting
    # ------------------------------------------------------------------

    def _build_sentences(
        self,
        deidentified_text: str,
        *,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ctx = extra or {}
        self._emit(progress_hook, {"type": "sentence_split_started", **ctx})

        sentences: list[dict[str, Any]] = []
        cursor = 0
        sentence_idx = 0
        for chunk in SENT_SPLIT_RE.split(deidentified_text):
            text = chunk.strip()
            if not text:
                continue
            start = deidentified_text.find(text, cursor)
            if start < 0:
                start = cursor
            end = start + len(text)
            cursor = end

            terms = self._extract_terms(
                text,
                sentence_id=f"s{sentence_idx}",
                sentence_start=start,
                progress_hook=progress_hook,
                extra=ctx,
            )
            sentences.append({
                "sentence_id": f"s{sentence_idx}",
                "start": start,
                "end": end,
                "text": text,
                "section": None,
                "terms": terms,
            })
            sentence_idx += 1

        self._emit(progress_hook, {
            "type": "sentence_split_completed", **ctx,
            "sentence_count": len(sentences),
        })
        return sentences

    # ------------------------------------------------------------------
    # Term extraction (batch Neo4j lookups)
    # ------------------------------------------------------------------

    def _extract_terms(
        self,
        sentence_text: str,
        *,
        sentence_id: str,
        sentence_start: int,
        progress_hook: Callable[[dict[str, Any]], None] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ctx = {**(extra or {}), "sentence_id": sentence_id}
        self._emit(progress_hook, {"type": "term_extraction_started", **ctx})

        matches = self._collect_surface_matches(sentence_text)
        surface_texts = [m["text"] for m in matches]

        with self.coding_graph.session() as session:
            patched_map = batch_patch_surface_terms(surface_texts, session)

        terms = self._assemble_terms(
            matches, patched_map, sentence_text,
            sentence_id, sentence_start,
        )
        read_terms = self._extract_read_codes(
            sentence_text, sentence_id, sentence_start,
            start_idx=len(terms),
            seen={m["lowered"] for m in matches},
        )
        terms.extend(read_terms)

        self._emit(progress_hook, {
            "type": "coding_resolve_completed", **ctx,
            "resolution_count": len(surface_texts),
        })
        self._emit(progress_hook, {
            "type": "term_extraction_completed", **ctx,
            "term_count": len(terms),
        })
        return terms

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_surface_matches(sentence_text: str) -> list[dict[str, Any]]:
        seen: set[str] = set()
        matches: list[dict[str, Any]] = []
        for idx, m in enumerate(TERM_RE.finditer(sentence_text)):
            text = m.group(1).strip()
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            matches.append({
                "idx": idx,
                "text": text,
                "lowered": lowered,
                "match": m,
            })
        return matches

    @staticmethod
    def _assemble_terms(
        matches: list[dict],
        patched_map: dict[str, dict],
        sentence_text: str,
        sentence_id: str,
        sentence_start: int,
    ) -> list[dict[str, Any]]:
        terms: list[dict[str, Any]] = []
        context = reconcile_context(sentence_text)
        ctx_dict = {
            "negated": context.negated,
            "uncertain": context.uncertain,
            "historical": context.historical,
            "subject": context.subject,
            "temporality": context.temporality,
        }
        for entry in matches:
            m = entry["match"]
            patched = patched_map.get(entry["text"], {})
            coding = patched.get("coding", {
                "snomed_concept_id": None,
                "read_code": None,
                "snomed_term": None,
                "score": 0.0,
                "source": "neo4j_hybrid",
            })
            terms.append({
                "term_id": f"{sentence_id}_t{entry['idx']}",
                "text": entry["text"],
                "span_start": sentence_start + m.start(1),
                "span_end": sentence_start + m.end(1),
                "context": ctx_dict,
                "coding": coding,
                "evidence_text": sentence_text,
                "extraction_method": "surface_patch_v2",
                "extraction_confidence": coding.get("score", 0.0),
            })
        return terms

    @staticmethod
    def _extract_read_codes(
        sentence_text: str,
        sentence_id: str,
        sentence_start: int,
        *,
        start_idx: int = 0,
        seen: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        seen = seen or set()
        context = reconcile_context(sentence_text)
        ctx_dict = {
            "negated": context.negated,
            "uncertain": context.uncertain,
            "historical": context.historical,
            "subject": context.subject,
            "temporality": context.temporality,
        }
        terms: list[dict[str, Any]] = []
        for idx, m in enumerate(READ_CODE_RE.finditer(sentence_text), start=start_idx):
            read_code = m.group(1)
            key = f"read:{read_code.lower()}"
            if key in seen:
                continue
            seen.add(key)
            terms.append({
                "term_id": f"{sentence_id}_t{idx}",
                "text": read_code,
                "span_start": sentence_start + m.start(1),
                "span_end": sentence_start + m.end(1),
                "context": ctx_dict,
                "coding": {
                    "snomed_concept_id": None,
                    "read_code": read_code,
                    "snomed_term": None,
                    "score": 0.6,
                    "source": "inline_read_code",
                },
                "evidence_text": sentence_text,
                "extraction_method": "inline_read_code",
                "extraction_confidence": 0.6,
            })
        return terms

    def _fetch_encounters(
        self, patient_id: str, max_enc: int | None
    ) -> list[dict[str, Any]]:
        with self.patient_graph.session() as session:
            limit = max_enc or 10000
            result = session.run(
                "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
                "WHERE toString(p.id) = $pid "
                "RETURN e.id AS encounter_id, toString(e.date) AS date, "
                "e.text AS text ORDER BY e.date LIMIT $limit",
                pid=patient_id,
                limit=limit,
            )
            return [dict(r) for r in result]

    def _persist_candidate(
        self,
        candidate: dict,
        result: Any,
        dry_run: bool,
        base: dict,
        stats: PipelineStats,
        progress_hook: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        if dry_run:
            self._emit(progress_hook, {"type": "persist_skipped", **base})
            return

        self._emit(progress_hook, {"type": "persist_started", **base})
        with self.patient_graph.session() as session:
            upsert_candidate(candidate, session)
            if not result.hard_fails:
                priority = 100 if result.warnings else 50
                create_review_task(
                    candidate_id=candidate["candidate_id"],
                    session=session,
                    priority=priority,
                    warning_count=len(result.warnings),
                )
        self._emit(progress_hook, {
            "type": "persist_completed", **base,
            "queued": not bool(result.hard_fails),
        })

    @staticmethod
    def _emit(
        hook: Callable[[dict[str, Any]], None] | None,
        payload: dict[str, Any],
    ) -> None:
        if hook:
            hook(payload)
