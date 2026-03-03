"""Two-phase coding pipeline adapted from PCA V3PipelineService.

Phase 1: Clinical term extraction via the configured ExtractorProvider
         (LLM-backed or model-backed, selected by CODING_EXTRACTOR_BACKEND).
Phase 2: Terminology resolution via the Terminology API (hybrid search).

Key design properties:
- ExtractorProvider abstraction: no inline backend branching here.
- Queue payload contract preserved: patient_id/encounter_id/mode/run_id only.
- Encounter text is always fetched from Neo4j at runtime.
- Idempotent writes: MERGE semantics on DOCUMENTS relationships.
- Provenance stamped on every persisted output:
    source / model_name / model_version / contract_version / run_id.
- Structured progress events emitted per encounter for Redis pub/sub.
- EncounterCandidate/ReviewTask nodes are NOT written by the routine pipeline.
  They are created on-demand via the review/correction flow (Classification
  Review, Peer Review, manual coding corrections) and feed the training corpus.
"""

from __future__ import annotations
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

from libs.coding_engine.tier_classifier import TierDecision, classify_tier
from libs.cypher.coding_decision_queries import UPSERT_CODING_DECISION
from libs.cypher.coding_review_queries import UPSERT_CODING_SUGGESTION
from libs.cypher.post_processor_rule_queries import GET_ACTIVE_POST_PROCESSOR_RULES
from libs.cypher.documents_queries import write_documents_from_sentences_payload
from libs.llm_client.escalation import escalate_coding
from libs.ner.context_detector import normalize_situation_lookup
from libs.ner.context_engine import detect_assertions_for_encounter
from libs.ner.lab_value_guard import should_suppress_disorder
from libs.ner.observable_post_processor import normalize_observable_entities
from libs.ner.scope_guard import reclassify_assertion
from libs.ner.post_processor_rules import apply_rules_to_entities, parse_rules, PostProcessorRule
from libs.ner.schema_mapper import LABEL_TO_SNOMED_TAG
from services.coding_worker.app.pipeline.extractor_contract import (
    CONTRACT_VERSION,
    ExtractionItem,
    ExtractorProvider,
)
from services.coding_worker.app.pipeline.extractor_registry import build_extractor
from services.coding_worker.app.pipeline.sentence_splitter import (
    SentenceChunk,
    SentenceSplitter,
    deduplicate_lines,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 5
_READ_CODE_RE = re.compile(r"\(([A-Za-z0-9.]{3,8})\)")
TERMINOLOGY_API_URL = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001")


_SURFACE_FORM_SCORE_THRESHOLD = float(
    os.getenv("PIPELINE_SURFACE_FORM_SCORE_THRESHOLD", "0.50")
)
_SURFACE_FORM_AUTO_THRESHOLD = float(
    os.getenv("PIPELINE_SURFACE_FORM_AUTO_CONFIDENCE", "0.90")
)
_SURFACE_FORM_SUGGEST_ENABLED = (
    os.getenv("PIPELINE_SURFACE_FORM_SUGGEST", "true").lower() == "true"
)
_CODEABLE_LABELS = frozenset({
    "disorder", "finding", "procedure", "observable_entity", "substance",
    "medicinal_product", "clinical_drug", "situation", "body_structure",
    "morphologic_abnormality", "regime_therapy", "assessment_scale",
    "tumor_staging", "organism", "occupation", "physical_object",
})


def _build_expected_tags(
    items: list[ExtractionItem],
) -> dict[str, str]:
    """Map each unique normalised term to its SNOMED semantic tag.

    When the same term appears with different NER labels, the first occurrence
    wins.  Modifier labels (X_TEMPORAL, X_DOSAGE, etc.) are skipped because
    they have no corresponding SNOMED semantic tag.
    """
    tags: dict[str, str] = {}
    for item in items:
        key = item.normalized
        if key in tags:
            continue
        snomed_tag = LABEL_TO_SNOMED_TAG.get(item.semantic_tag)
        if snomed_tag:
            tags[key] = snomed_tag
    return tags


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
    """Async coding pipeline for the Coding Worker.

    The active extraction backend is selected at construction time via
    ``build_extractor()``.  No inline backend branching occurs inside the
    pipeline logic itself.
    """

    def __init__(
        self,
        patient_client,
        knowledge_client,
        coding_mode: str = "hitl",
    ) -> None:
        self.patient_client = patient_client
        self.knowledge_client = knowledge_client
        self.coding_mode = coding_mode
        self.splitter = SentenceSplitter()
        # Provider is lazily initialised on first run so the progress_hook
        # can be forwarded for fallback events.
        self._extractor: Optional[ExtractorProvider] = None
        self._post_rules: list[PostProcessorRule] | None = None

    def _get_extractor(
        self,
        progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> ExtractorProvider:
        if self._extractor is None:
            self._extractor = build_extractor(progress_hook=progress_hook)
            logger.info(
                "CodingPipeline: extractor=%s model=%s v%s contract=%s",
                self._extractor.source,
                self._extractor.model_name,
                self._extractor.model_version,
                CONTRACT_VERSION,
            )
        return self._extractor

    async def run(
        self,
        patient_ids: list[str],
        dry_run: bool = False,
        progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
        run_id: Optional[str] = None,
    ) -> PipelineStats:
        run_id = run_id or str(uuid.uuid4())
        stats = PipelineStats()
        extractor = self._get_extractor(progress_hook)
        for patient_id in patient_ids:
            encounters = self._fetch_encounters(
                patient_id=patient_id,
                run_id=run_id,
                progress_hook=progress_hook,
            )
            self._emit(progress_hook, {
                "type": "patient_started",
                "patient_id": patient_id,
                "encounter_count": len(encounters),
            })
            for enc in encounters:
                await self._process_encounter(
                    patient_id, enc, dry_run, stats, progress_hook, run_id, extractor
                )
        self._emit(progress_hook, {"type": "run_completed", "run_id": run_id, **stats.snapshot()})
        return stats

    async def run_unprocessed(
        self,
        patient_ids: list[str],
        dry_run: bool = False,
        progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
        run_id: Optional[str] = None,
    ) -> PipelineStats:
        run_id = run_id or str(uuid.uuid4())
        stats = PipelineStats()
        extractor = self._get_extractor(progress_hook)
        for patient_id in patient_ids:
            encounters = self._fetch_unprocessed_encounters(
                patient_id=patient_id,
                run_id=run_id,
                progress_hook=progress_hook,
            )
            self._emit(progress_hook, {
                "type": "patient_started",
                "patient_id": patient_id,
                "encounter_count": len(encounters),
            })
            for enc in encounters:
                await self._process_encounter(
                    patient_id, enc, dry_run, stats, progress_hook, run_id, extractor
                )
        self._emit(progress_hook, {"type": "run_completed", "run_id": run_id, **stats.snapshot()})
        return stats

    async def run_single_encounter(
        self,
        patient_id: str,
        encounter_id: str,
        dry_run: bool = False,
        progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
        run_id: Optional[str] = None,
    ) -> PipelineStats:
        run_id = run_id or str(uuid.uuid4())
        stats = PipelineStats()
        extractor = self._get_extractor(progress_hook)
        rows = self.patient_client.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid AND toString(e.id) = $eid "
            "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text",
            pid=patient_id,
            eid=encounter_id,
        )
        if rows:
            await self._process_encounter(
                patient_id, rows[0], dry_run, stats, progress_hook, run_id, extractor
            )
        self._emit(progress_hook, {"type": "run_completed", "run_id": run_id, **stats.snapshot()})
        return stats

    # ------------------------------------------------------------------
    # Core encounter processing
    # ------------------------------------------------------------------

    async def _process_encounter(
        self,
        patient_id: str,
        encounter: dict[str, Any],
        dry_run: bool,
        stats: PipelineStats,
        progress_hook: Optional[Callable[[dict[str, Any]], None]],
        run_id: str,
        extractor: ExtractorProvider,
    ) -> None:
        encounter_id = str(encounter.get("encounter_id", ""))
        encounter_text = str(encounter.get("text") or "")

        self._emit(progress_hook, {
            "type": "encounter_started",
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "run_id": run_id,
        })

        t_fetch = time.monotonic()
        deidentified = deduplicate_lines(encounter_text)
        sentences = self.splitter.split(deidentified)

        self._emit(progress_hook, {
            "type": "fetched",
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "run_id": run_id,
            "sentence_count": len(sentences),
            "fetch_latency_ms": round((time.monotonic() - t_fetch) * 1000),
        })

        # Phase 1: extraction
        t_extract = time.monotonic()
        try:
            extracted = self._extract_terms(deidentified, sentences, extractor)
        except Exception as exc:
            logger.error(
                "Extraction failed for encounter %s (%s backend): %s",
                encounter_id, extractor.source, exc,
            )
            stats.record(True, False)
            self._emit(progress_hook, {
                "type": "failed",
                "stage": "extraction",
                "encounter_id": encounter_id,
                "run_id": run_id,
                "backend": extractor.source,
                "failure_taxonomy": "backend_unavailable" if "unavailable" in str(exc).lower()
                                    else "timeout" if "timed out" in str(exc).lower()
                                    else "extraction_error",
                **stats.snapshot(),
            })
            return

        extracted = self._suppress_inferred_diagnoses(sentences, extracted)
        extracted = self._apply_scope_guard(sentences, extracted)
        extracted = self._apply_post_processor_rules(deidentified, extracted)
        extracted = self._apply_observable_post_processing(deidentified, extracted)
        extracted, context_detection_failed = self._apply_context_detection(deidentified, extracted)

        all_items = [item for items in extracted.values() for item in items]
        extract_latency_ms = round((time.monotonic() - t_extract) * 1000)

        self._emit(progress_hook, {
            "type": "extracted",
            "encounter_id": encounter_id,
            "run_id": run_id,
            "backend_used": extractor.source,
            "model_name": extractor.model_name,
            "model_version": extractor.model_version,
            "entity_count": len(all_items),
            "extract_latency_ms": extract_latency_ms,
            "context_detection_failed": context_detection_failed,
        })

        # Phase 2: terminology resolution
        t_resolve = time.monotonic()
        tag_map = _build_expected_tags(all_items)
        resolved = await self._resolve_via_api(
            [item.normalized for item in all_items],
            expected_tags=tag_map,
        )
        resolve_latency_ms = round((time.monotonic() - t_resolve) * 1000)

        coded_count = sum(1 for k in resolved if resolved[k])
        reject_count = len(all_items) - coded_count

        self._emit(progress_hook, {
            "type": "resolved",
            "encounter_id": encounter_id,
            "run_id": run_id,
            "coded_count": coded_count,
            "reject_count": reject_count,
            "resolve_latency_ms": resolve_latency_ms,
        })

        is_autonomous = self.coding_mode == "autonomous"

        if not is_autonomous:
            self._suggest_surface_forms(all_items, resolved, dry_run)

        sentences_payload = self._build_sentences_payload(
            sentences, extracted, resolved, extractor
        )

        # Autonomous mode: filter out Tier 3 items and log CodingDecision nodes
        if is_autonomous and not dry_run:
            self._write_coding_decisions(
                encounter_id, patient_id, sentences_payload,
            )
            for sentence in sentences_payload:
                sentence["terms"] = [
                    t for t in sentence.get("terms", [])
                    if t.get("tier_decision") != "not_coded"
                ]

        # Persistence
        t_persist = time.monotonic()
        if not dry_run:
            self._persist_documents(
                encounter_id,
                sentences_payload,
                extractor=extractor,
                run_id=run_id,
            )

        persist_latency_ms = round((time.monotonic() - t_persist) * 1000)

        stats.record(False, False)
        self._emit(progress_hook, {
            "type": "persisted",
            "encounter_id": encounter_id,
            "run_id": run_id,
            "dry_run": dry_run,
            "persist_latency_ms": persist_latency_ms,
            **stats.snapshot(),
        })

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def _extract_terms(
        self,
        deidentified: str,
        sentences: list[SentenceChunk],
        extractor: ExtractorProvider,
    ) -> dict[str, list[ExtractionItem]]:
        by_sentence: dict[str, list[ExtractionItem]] = {
            s.sentence_id: [] for s in sentences
        }
        for idx in range(0, len(sentences), _BATCH_SIZE):
            batch = sentences[idx : idx + _BATCH_SIZE]
            items = extractor.extract_batch(deidentified, batch)
            for item in items:
                by_sentence.setdefault(item.sentence_id, []).append(item)
        return by_sentence

    def _suppress_inferred_diagnoses(
        self,
        sentences: list[SentenceChunk],
        extracted: dict[str, list[ExtractionItem]],
    ) -> dict[str, list[ExtractionItem]]:
        """Remove disorder entities whose evidence is a lab result, not a diagnosis.

        Clinical safety guard: lab values (eGFR, creatinine, HbA1c, etc.)
        must be coded as observable entities only.  If the LLM infers a
        disorder from a numeric measurement (e.g. CKD stage 1 from eGFR 69),
        this guard suppresses it before terminology resolution.
        """
        sentence_map = {s.sentence_id: s.text for s in sentences}
        output: dict[str, list[ExtractionItem]] = {}
        suppressed = 0
        for sentence_id, items in extracted.items():
            sentence_text = sentence_map.get(sentence_id, "")
            kept: list[ExtractionItem] = []
            for item in items:
                if should_suppress_disorder(
                    entity_text=item.text,
                    entity_semantic_tag=item.semantic_tag,
                    entity_normalized=item.normalized,
                    sentence_text=sentence_text,
                    entity_numeric_value=item.numeric_value,
                    entity_unit=item.unit,
                ):
                    suppressed += 1
                else:
                    kept.append(item)
            output[sentence_id] = kept
        if suppressed:
            logger.info(
                "Lab-value guard: suppressed %d disorder(s) inferred from lab results",
                suppressed,
            )
        return output

    def _apply_scope_guard(
        self,
        sentences: list[SentenceChunk],
        extracted: dict[str, list[ExtractionItem]],
    ) -> dict[str, list[ExtractionItem]]:
        """Enforce intended-use boundaries on extracted entities.

        Reclassifies assertions for entities in safety-netting text,
        treatment recommendation context, or hedged diagnostic language.
        Runs before ConText so that MedSpaCy can further tighten assertions.
        """
        sentence_map = {s.sentence_id: s.text for s in sentences}
        output: dict[str, list[ExtractionItem]] = {}
        reclassified = 0
        for sentence_id, items in extracted.items():
            sentence_text = sentence_map.get(sentence_id, "")
            updated: list[ExtractionItem] = []
            for item in items:
                new_assertion = reclassify_assertion(
                    entity_semantic_tag=item.semantic_tag,
                    entity_assertion=item.assertion,
                    sentence_text=sentence_text,
                )
                if new_assertion is not None:
                    item = ExtractionItem(
                        sentence_id=item.sentence_id,
                        text=item.text,
                        span_start=item.span_start,
                        span_end=item.span_end,
                        semantic_tag=item.semantic_tag,
                        assertion=new_assertion,
                        confidence=item.confidence,
                        normalized=item.normalized,
                        source_meta=item.source_meta,
                        relations=item.relations,
                        numeric_value=item.numeric_value,
                        unit=item.unit,
                        reference_range=item.reference_range,
                        source=item.source,
                        model_name=item.model_name,
                        model_version=item.model_version,
                        contract_version=item.contract_version,
                    )
                    reclassified += 1
                updated.append(item)
            output[sentence_id] = updated
        if reclassified:
            logger.info(
                "Scope guard: reclassified %d entit(ies) "
                "(safety-netting / recommendation / hedged diagnosis)",
                reclassified,
            )
        return output

    def _load_post_processor_rules(self) -> list[PostProcessorRule]:
        if self._post_rules is not None:
            return self._post_rules
        rows = self.patient_client.run(GET_ACTIVE_POST_PROCESSOR_RULES)
        self._post_rules = parse_rules(rows)
        if self._post_rules:
            logger.info("Loaded %d active post-processor rules", len(self._post_rules))
        return self._post_rules

    def _apply_post_processor_rules(
        self,
        encounter_text: str,
        extracted: dict[str, list[ExtractionItem]],
    ) -> dict[str, list[ExtractionItem]]:
        rules = self._load_post_processor_rules()
        if not rules:
            return extracted

        output: dict[str, list[ExtractionItem]] = {}
        for sentence_id, items in extracted.items():
            transformed: list[ExtractionItem] = []
            for item in items:
                entity = {
                    "text": item.text,
                    "label": item.semantic_tag,
                    "start": item.span_start,
                    "end": item.span_end,
                }
                updated = apply_rules_to_entities(encounter_text, [entity], rules)
                if not updated:
                    continue
                ent = updated[0]
                transformed.append(
                    ExtractionItem(
                        sentence_id=item.sentence_id,
                        text=str(ent.get("text", item.text)),
                        span_start=int(ent.get("start", item.span_start)),
                        span_end=int(ent.get("end", item.span_end)),
                        semantic_tag=str(ent.get("label", item.semantic_tag)),
                        assertion=item.assertion,
                        confidence=item.confidence,
                        normalized=str(ent.get("text", item.normalized)),
                        source_meta=item.source_meta,
                        relations=item.relations,
                        source=item.source,
                        model_name=item.model_name,
                        model_version=item.model_version,
                        contract_version=item.contract_version,
                    )
                )
            output[sentence_id] = transformed
        return output

    def _apply_observable_post_processing(
        self,
        encounter_text: str,
        extracted: dict[str, list[ExtractionItem]],
    ) -> dict[str, list[ExtractionItem]]:
        """Normalize observable spans and attach value/unit/reference_range."""
        output: dict[str, list[ExtractionItem]] = {}
        for sentence_id, items in extracted.items():
            if not items:
                output[sentence_id] = items
                continue

            as_entities = [
                {
                    "__idx": i,
                    "text": item.text,
                    "label": item.semantic_tag,
                    "start": item.span_start,
                    "end": item.span_end,
                    "value": item.numeric_value or None,
                    "unit": item.unit or None,
                    "reference_range": item.reference_range or None,
                }
                for i, item in enumerate(items)
            ]
            normalized_entities = normalize_observable_entities(
                encounter_text,
                as_entities,
                add_qualifier_value=False,
            )
            by_idx = {
                int(ent.get("__idx")): ent
                for ent in normalized_entities
                if isinstance(ent.get("__idx"), int)
            }

            transformed: list[ExtractionItem] = []
            for i, item in enumerate(items):
                ent = by_idx.get(i, as_entities[i])
                normalized_lookup = (
                    item.normalized
                    if str(item.normalized or "").strip() and item.normalized != item.text
                    else str(ent.get("text", item.normalized))
                )
                transformed.append(
                    ExtractionItem(
                        sentence_id=item.sentence_id,
                        text=str(ent.get("text", item.text)),
                        span_start=int(ent.get("start", item.span_start)),
                        span_end=int(ent.get("end", item.span_end)),
                        semantic_tag=str(ent.get("label", item.semantic_tag)),
                        assertion=item.assertion,
                        confidence=item.confidence,
                        normalized=normalized_lookup,
                        source_meta=item.source_meta,
                        relations=item.relations,
                        numeric_value=str(ent.get("value", item.numeric_value) or "").strip(),
                        unit=str(ent.get("unit", item.unit) or "").strip(),
                        reference_range=str(ent.get("reference_range", item.reference_range) or "").strip(),
                        source=item.source,
                        model_name=item.model_name,
                        model_version=item.model_version,
                        contract_version=item.contract_version,
                    )
                )
            output[sentence_id] = transformed
        return output

    def _apply_context_detection(
        self,
        encounter_text: str,
        extracted: dict[str, list[ExtractionItem]],
    ) -> tuple[dict[str, list[ExtractionItem]], bool]:
        """Detect context assertions via MedSpaCy ConText and set assertion.

        Also normalizes lookup terms for situation entities whose freeform
        text won't resolve via the terminology API directly.

        Returns:
            Tuple of (updated extracted dict, context_detection_failed flag).
        """
        all_items = [item for items in extracted.values() for item in items]
        assertions, failed = detect_assertions_for_encounter(encounter_text, all_items)
        assertion_map = {
            id(item): assertions[i] for i, item in enumerate(all_items)
        }

        output: dict[str, list[ExtractionItem]] = {}
        for sentence_id, items in extracted.items():
            output[sentence_id] = [
                self._update_item_context(item, assertion_map[id(item)])
                for item in items
            ]
        return output, failed

    def _update_item_context(
        self, item: ExtractionItem, new_assertion: str
    ) -> ExtractionItem:
        """Return item updated with assertion and situation normalisation."""
        new_normalized = item.normalized
        if item.semantic_tag == "situation":
            canonical = normalize_situation_lookup(item.text)
            if canonical:
                new_normalized = canonical

        if new_assertion == (item.assertion or "present") and new_normalized == item.normalized:
            return item

        return ExtractionItem(
            sentence_id=item.sentence_id,
            text=item.text,
            span_start=item.span_start,
            span_end=item.span_end,
            semantic_tag=item.semantic_tag,
            assertion=new_assertion,
            confidence=item.confidence,
            normalized=new_normalized,
            source_meta=item.source_meta,
            relations=item.relations,
            numeric_value=item.numeric_value,
            unit=item.unit,
            reference_range=item.reference_range,
            source=item.source,
            model_name=item.model_name,
            model_version=item.model_version,
            contract_version=item.contract_version,
        )

    # ------------------------------------------------------------------
    # Terminology resolution
    # ------------------------------------------------------------------

    async def _resolve_via_api(
        self,
        terms: list[str],
        expected_tags: dict[str, str] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        if not terms:
            return {}
        unique = list(dict.fromkeys(terms))
        body: dict[str, Any] = {"terms": unique}
        if expected_tags:
            body["expected_tags"] = expected_tags
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{TERMINOLOGY_API_URL}/terminology/resolve",
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("results", {})
        except Exception:
            logger.warning(
                "Terminology API call failed -- returning empty results",
                exc_info=True,
            )
            return {}

    def _suggest_surface_forms(
        self,
        all_items: list[ExtractionItem],
        resolved: dict[str, list[dict[str, Any]]],
        dry_run: bool,
    ) -> int:
        """Suggest surface forms for entities with no or low-confidence coding.

        High-confidence suggestions (>= _SURFACE_FORM_AUTO_THRESHOLD) are
        stored as ``pending_review`` CodingSuggestion nodes.  All suggestions
        are batched by unique term so repeated occurrences increment a counter
        rather than creating duplicates.

        Returns the number of suggestions created.
        """
        if not _SURFACE_FORM_SUGGEST_ENABLED or dry_run:
            return 0

        seen: set[str] = set()
        suggestions = 0

        for item in all_items:
            if item.semantic_tag not in _CODEABLE_LABELS:
                continue
            if item.assertion in {
                "absent", "declined", "cancelled",
                "hypothetical", "possible", "family", "historical",
            }:
                continue
            key = item.normalized
            if key in seen:
                continue
            seen.add(key)

            candidates = resolved.get(key, [])
            top = candidates[0] if candidates else {}
            score = float(top.get("score", 0.0)) if top else 0.0

            if score >= _SURFACE_FORM_SCORE_THRESHOLD:
                continue

            esc = escalate_coding(
                entity_text=item.text,
                entity_label=item.semantic_tag,
                encounter_text="",
                confidence_threshold=_SURFACE_FORM_AUTO_THRESHOLD,
                start_tier="small",
            )
            if not esc.concept_term:
                continue

            status = (
                "pending_review"
                if esc.confidence >= _SURFACE_FORM_AUTO_THRESHOLD
                else "low_confidence"
            )
            try:
                with self.patient_client.session() as session:
                    session.run(
                        UPSERT_CODING_SUGGESTION,
                        entity_text=item.text,
                        entity_label=item.semantic_tag,
                        suggested_term=esc.concept_term,
                        confidence=esc.confidence,
                        model_tier=esc.model_tier,
                        model_id=esc.model_id,
                        status=status,
                    )
                suggestions += 1
            except Exception:
                logger.debug(
                    "Failed to write CodingSuggestion for %r", item.text,
                    exc_info=True,
                )

        if suggestions:
            logger.info(
                "Pipeline surface form suggestions: %d new suggestions created",
                suggestions,
            )
        return suggestions

    # ------------------------------------------------------------------
    # Payload building
    # ------------------------------------------------------------------

    def _build_sentences_payload(
        self,
        sentences: list[SentenceChunk],
        extracted: dict[str, list[ExtractionItem]],
        resolved: dict[str, list[dict[str, Any]]],
        extractor: ExtractorProvider,
    ) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        term_counter = 0
        for sentence in sentences:
            terms_data: list[dict[str, Any]] = []
            for item in extracted.get(sentence.sentence_id, []):
                candidates = resolved.get(item.normalized, [])
                best = candidates[0] if candidates else {}
                # Extract modifiers from source_meta (populated by LLM provider)
                source_meta = item.source_meta or {}
                modifiers = source_meta.get("modifiers", {})
                score = float(best.get("score", 0.0) or 0.0)
                sf_status = str(best.get("surface_form_status", "") or "")
                tier_decision = classify_tier(
                    assertion=item.assertion or "present",
                    context_failed=False,
                    terminology_score=score,
                    surface_form_status=sf_status,
                    coding_mode=self.coding_mode,
                )
                terms_data.append({
                    "term_id": f"{sentence.sentence_id}_t{term_counter}",
                    "text": item.text,
                    "span_start": item.span_start,
                    "span_end": item.span_end,
                    "coding": {
                        "snomed_concept_id": best.get("snomed_concept_id"),
                        "read_code": best.get("read_code"),
                        "snomed_term": best.get("snomed_term"),
                        "score": score,
                        "source": "terminology_api",
                    },
                    "semantic_tag": item.semantic_tag,
                    "assertion": item.assertion,
                    "confidence": item.confidence,
                    "modifiers": modifiers,
                    "numeric_value": item.numeric_value,
                    "unit": item.unit,
                    "reference_range": item.reference_range,
                    "extraction_source": item.source,
                    "extraction_model_name": item.model_name,
                    "extraction_model_version": item.model_version,
                    "contract_version": item.contract_version,
                    "decision_tier": tier_decision.tier,
                    "audit_flag": tier_decision.decision == "coded_with_flag",
                    "tier_reason": tier_decision.reason,
                    "tier_decision": tier_decision.decision,
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

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_documents(
        self,
        encounter_id: str,
        sentences_payload: list[dict[str, Any]],
        extractor: ExtractorProvider,
        run_id: str,
    ) -> None:
        """Write :DOCUMENTS relationships directly to the patient graph.

        EncounterCandidate/ReviewTask nodes are not created here.  They are
        created on-demand via the review/correction flow so that only
        human-reviewed outputs enter the training corpus.
        """
        with self.patient_client.session() as session:
            written = write_documents_from_sentences_payload(
                encounter_id,
                sentences_payload,
                session,
                source="model_coded",
                model_name=extractor.model_name,
                model_version=extractor.model_version,
                contract_version=CONTRACT_VERSION,
                run_id=run_id,
            )
            logger.debug(
                "_persist_documents: wrote %d DOCUMENTS links for encounter %s "
                "(backend=%s model=%s v%s)",
                written,
                encounter_id,
                extractor.source,
                extractor.model_name,
                extractor.model_version,
            )

    def _write_coding_decisions(
        self,
        encounter_id: str,
        patient_id: str,
        sentences_payload: list[dict[str, Any]],
    ) -> None:
        """Write CodingDecision audit nodes for all terms in autonomous mode."""
        import hashlib
        pid_hash = hashlib.sha256(patient_id.encode()).hexdigest()
        with self.patient_client.session() as session:
            idx = 0
            for sentence in sentences_payload:
                for term in sentence.get("terms", []):
                    decision_id = f"dec:{encounter_id}:{idx}"
                    try:
                        session.run(
                            UPSERT_CODING_DECISION,
                            decision_id=decision_id,
                            encounter_id=encounter_id,
                            patient_id_hash=pid_hash,
                            entity_text=term.get("text", ""),
                            entity_label=term.get("semantic_tag", ""),
                            assertion=term.get("assertion", "present"),
                            tier=term.get("decision_tier"),
                            decision=term.get("tier_decision", ""),
                            reason=term.get("tier_reason", ""),
                            terminology_score=float(
                                (term.get("coding") or {}).get("score", 0.0) or 0.0
                            ),
                            consensus_verdict="",
                            model_ids="",
                        )
                    except Exception:
                        logger.warning(
                            "Failed to write CodingDecision for %s idx=%d",
                            encounter_id, idx, exc_info=True,
                        )
                    idx += 1

    # ------------------------------------------------------------------
    # Neo4j fetches
    # ------------------------------------------------------------------

    def _fetch_encounters(
        self,
        patient_id: str,
        run_id: str,
        progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> list[dict[str, Any]]:
        encounters = self.patient_client.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text, "
            "e.classification_content_type AS classification_content_type "
            "ORDER BY e.date",
            pid=patient_id,
        )
        return self._classify_and_filter_clinical(
            patient_id=patient_id,
            run_id=run_id,
            encounters=encounters,
            progress_hook=progress_hook,
        )

    def _fetch_unprocessed_encounters(
        self,
        patient_id: str,
        run_id: str,
        progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> list[dict[str, Any]]:
        encounters = self.patient_client.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "AND NOT EXISTS { MATCH (e)-[:DOCUMENTS]->() } "
            "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text, "
            "e.classification_content_type AS classification_content_type "
            "ORDER BY e.date",
            pid=patient_id,
        )
        return self._classify_and_filter_clinical(
            patient_id=patient_id,
            run_id=run_id,
            encounters=encounters,
            progress_hook=progress_hook,
        )

    def _classify_and_filter_clinical(
        self,
        patient_id: str,
        run_id: str,
        encounters: list[dict[str, Any]],
        progress_hook: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> list[dict[str, Any]]:
        """Ensure encounter classifications exist and return only clinical rows."""
        if not encounters:
            return []

        if self._classification_complete(encounters):
            clinical = [
                enc for enc in encounters
                if str(enc.get("classification_content_type") or "") == "clinical"
            ]
            self._emit(progress_hook, {
                "type": "classification_completed",
                "patient_id": patient_id,
                "run_id": run_id,
                "source": "existing",
                "total_count": len(encounters),
                "clinical_count": len(clinical),
                "admin_count": sum(
                    1 for enc in encounters
                    if str(enc.get("classification_content_type") or "") == "admin_only"
                ),
                "document_transfer_count": sum(
                    1 for enc in encounters
                    if str(enc.get("classification_content_type") or "") == "document_transfer"
                ),
            })
            return clinical

        self._emit(progress_hook, {
            "type": "classification_started",
            "patient_id": patient_id,
            "run_id": run_id,
            "encounter_count": len(encounters),
        })
        t0 = time.monotonic()
        try:
            from libs.classifiers.encounter_classifier import (
                build_patient_encounter_index,
                persist_patient_encounter_classification,
            )
            index = build_patient_encounter_index(
                patient_id=patient_id,
                encounters=encounters,
                run_id=run_id,
            )
            persist_patient_encounter_classification(
                patient_client=self.patient_client,
                patient_id=patient_id,
                run_id=run_id,
                index=index,
            )
            cls_by_encounter = {
                str(enc_id): result.content_type
                for enc_id, result in index.classifications.items()
            }
            for enc in encounters:
                enc["classification_content_type"] = cls_by_encounter.get(
                    str(enc.get("encounter_id", "")),
                    str(enc.get("classification_content_type") or ""),
                )
            clinical = [
                enc for enc in encounters
                if str(enc.get("classification_content_type") or "") == "clinical"
            ]
            self._emit(progress_hook, {
                "type": "classification_completed",
                "patient_id": patient_id,
                "run_id": run_id,
                "source": "new",
                "total_count": len(encounters),
                "clinical_count": index.clinical_count,
                "admin_count": index.admin_count,
                "document_transfer_count": index.document_transfer_count,
                "classification_latency_ms": round((time.monotonic() - t0) * 1000),
            })
            return clinical
        except Exception as exc:
            logger.warning(
                "Classification failed for patient %s. Falling back to all encounters. err=%s",
                patient_id,
                exc,
                exc_info=True,
            )
            self._emit(progress_hook, {
                "type": "classification_failed",
                "patient_id": patient_id,
                "run_id": run_id,
                "error": str(exc),
            })
            return encounters

    @staticmethod
    def _classification_complete(encounters: list[dict[str, Any]]) -> bool:
        return all(
            str(enc.get("classification_content_type") or "")
            in {"clinical", "admin_only", "document_transfer"}
            for enc in encounters
        )

    @staticmethod
    def _emit(
        hook: Optional[Callable[[dict[str, Any]], None]],
        payload: dict[str, Any],
    ) -> None:
        if hook:
            hook(payload)
