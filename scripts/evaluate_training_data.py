"""Evaluate and refresh TrainingLabel entities using the full coding pipeline.

Runs the complete NER + post-processing + terminology resolution + tier
classification pipeline against every included TrainingLabel record in Neo4j.
Writes the resulting entities back to ``entities_json`` on each node,
replacing any legacy (untrusted) labels.  Produces a Markdown quality report.

Usage
-----
    # Full run (writes back + generates report):
    python -m scripts.evaluate_training_data

    # Cap to N records during development:
    EVAL_LIMIT=50 python -m scripts.evaluate_training_data

Environment variables
---------------------
    EVAL_LIMIT            Cap the number of records processed (default: all).
    TERMINOLOGY_API_URL   Override API base (default: http://localhost:8001).
    NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD   Patient Graph credentials.
    CODING_EXTRACTOR_BACKEND  llm | model | auto (default: llm).
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

# ── repo root on sys.path ─────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# Load environment from secrets/ — mirrors how every service bootstraps itself.
# .env.config first (non-secret defaults, override=True) then .env (secrets).
_SECRETS = _REPO_ROOT / "secrets"
load_dotenv(_SECRETS / ".env.config", override=True)
load_dotenv(_SECRETS / ".env", override=False)

from libs.coding_engine.tier_classifier import classify_tier
from libs.cypher.post_processor_rule_queries import GET_ACTIVE_POST_PROCESSOR_RULES
from libs.neo4j_client.client import PatientGraphClient
from libs.ner.post_processor_rules import parse_rules, PostProcessorRule
from libs.ner.schema_mapper import LABEL_TO_SNOMED_TAG
from libs.pipeline.post_processing import run_post_processing
from services.coding_worker.app.pipeline.extractor_contract import (
    CONTRACT_VERSION,
    ExtractionItem,
)
from services.coding_worker.app.pipeline.extractor_registry import build_extractor
from services.coding_worker.app.pipeline.sentence_splitter import SentenceSplitter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("PyRuSH").setLevel(logging.WARNING)  # standard logging guard
try:
    from loguru import logger as _loguru  # PyRuSH uses loguru, not stdlib logging

    _loguru.disable("PyRuSH")
except ImportError:
    pass
logger = logging.getLogger("evaluate_training_data")


# ── Patch ConText if medspacy/PyRuSH not available ───────────────────────────
# context_engine.apply_context_detection_to_dicts intentionally re-raises
# when medspacy fails to load. We patch the reference inside post_processing
# at the module level so layers 1-6 and 8 still run correctly.
def _patch_context_if_needed() -> bool:
    """Replace apply_context_detection_to_dicts with a safe no-op if PyRuSH missing.

    post_processing.py binds the function by name at import time, so patching
    the module attribute redirects all subsequent calls inside run_post_processing.
    Returns True if the patch was applied.
    """
    try:
        from PyRuSH import PyRuSHSentencizer  # noqa: F401

        return False  # available — no patch needed
    except ModuleNotFoundError:
        pass

    def _context_noop(encounter_text: str, entities: list, **kwargs) -> None:  # type: ignore[misc]
        for ent in entities:
            ent["context_detection_failed"] = True

    import libs.pipeline.post_processing as _pp_mod

    _pp_mod.apply_context_detection_to_dicts = _context_noop  # type: ignore[attr-defined]
    logger.warning(
        "PyRuSH / medspacy ConText not installed — assertion detection disabled. "
        "All entities will have context_detection_failed=True and route to Tier 3. "
        "Install PyRuSH to enable full ConText assertion detection."
    )
    return True


# ── config ────────────────────────────────────────────────────────────────────
TERMINOLOGY_API_URL = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001")

# Support multiple terminology API instances for parallel resolution.
# Set TERMINOLOGY_API_URLS=http://localhost:8001,http://localhost:8011,http://localhost:8012
# to round-robin across all of them.  Falls back to TERMINOLOGY_API_URL if not set.
_raw_urls = os.getenv("TERMINOLOGY_API_URLS", "")
_API_URLS: list[str] = (
    [u.strip() for u in _raw_urls.split(",") if u.strip()]
    if _raw_urls
    else [TERMINOLOGY_API_URL]
)
_url_cycle = itertools.cycle(_API_URLS)

# Cap concurrent terminology requests: each uvicorn instance has one worker,
# so more than ~3 simultaneous requests per instance just queues at the OS
# TCP layer and causes connection errors.  3 instances × 3 slots = 9 total.
_TERM_CONCURRENCY = int(os.getenv("TERM_CONCURRENCY", str(len(_API_URLS) * 3)))
_term_semaphore: asyncio.Semaphore | None = None  # initialised in main()


def _get_term_semaphore() -> asyncio.Semaphore:
    global _term_semaphore
    if _term_semaphore is None:
        _term_semaphore = asyncio.Semaphore(_TERM_CONCURRENCY)
    return _term_semaphore


OUTPUT_PATH = Path(__file__).parent / "training_evaluation_report.md"
MIN_SCORE_CODED = 0.50  # below this = surface form gap
CONFIDENCE_FLAG_THRESHOLD = 0.60
BATCH_SIZE = 5  # matches pipeline _BATCH_SIZE
MAX_DETAIL_RECORDS = 30  # records shown in per-record section
EVAL_LIMIT = int(os.getenv("EVAL_LIMIT", "0")) or None  # 0 = no limit
CONCURRENCY = int(os.getenv("EVAL_CONCURRENCY", "8"))  # parallel records

_CODEABLE_LABELS = frozenset(
    {
        "disorder",
        "finding",
        "procedure",
        "observable_entity",
        "substance",
        "medicinal_product",
        "clinical_drug",
        "situation",
        "body_structure",
        "morphologic_abnormality",
        "regime_therapy",
        "assessment_scale",
        "tumor_staging",
        "organism",
        "occupation",
        "physical_object",
    }
)

# ── Cypher ────────────────────────────────────────────────────────────────────
FETCH_LABELS_QUERY = """
MATCH (t:TrainingLabel)
WHERE t.include = true AND t.text IS NOT NULL
RETURN
    t.label_id      AS label_id,
    t.encounter_id  AS encounter_id,
    t.text          AS text,
    t.source        AS source,
    coalesce(t.quality_score, 0.0) AS quality_score
ORDER BY t.created_at ASC
"""

WRITE_BACK_QUERY = """
MATCH (t:TrainingLabel {label_id: $label_id})
SET t.entities_json = $entities_json,
    t.updated_at    = datetime()
RETURN t.label_id AS label_id
"""


# ── data structures ───────────────────────────────────────────────────────────
@dataclass
class RecordResult:
    label_id: str
    encounter_id: str
    source: str
    quality_score: float
    entity_count: int
    coded_count: int  # entities with score >= MIN_SCORE_CODED
    tier1_count: int
    tier2_count: int
    tier3_count: int
    surface_gaps: list[dict]  # entities that failed to code
    low_conf: list[dict]  # entities below confidence threshold
    assertion_counts: dict[str, int]
    written: bool = False
    error: str = ""


# ── pipeline helpers (mirrored from pipeline_service.py) ──────────────────────
def _items_to_dicts(items: list[ExtractionItem]) -> list[dict[str, Any]]:
    return [
        {
            "text": item.text,
            "label": item.semantic_tag,
            "start": item.span_start,
            "end": item.span_end,
            "assertion": item.assertion or "present",
            "confidence": item.confidence,
            "normalized": (
                item.normalized
                if item.normalized and item.normalized != item.text
                else None
            ),
            "value": item.numeric_value or None,
            "unit": item.unit or None,
            "reference_range": item.reference_range or None,
            "__sentence_id": item.sentence_id,
            "__source": item.source,
            "__model_name": item.model_name,
            "__model_version": item.model_version,
            "__contract_version": item.contract_version,
            "__source_meta": item.source_meta,
            "__relations": item.relations,
        }
        for item in items
    ]


def _dict_to_item(ent: dict[str, Any]) -> ExtractionItem:
    normalized = str(
        ent.get("normalized") or ent.get("normalized_lookup") or ent.get("text", "")
    )
    return ExtractionItem(
        sentence_id=str(ent.get("__sentence_id", "")),
        text=str(ent.get("text", "")),
        span_start=int(ent.get("start", 0) or 0),
        span_end=int(ent.get("end", 0) or 0),
        semantic_tag=str(ent.get("label", "")),
        assertion=str(ent.get("assertion") or "present"),
        confidence=float(ent.get("confidence", 0.0) or 0.0),
        normalized=normalized,
        source_meta=ent.get("__source_meta") or {},
        relations=ent.get("__relations") or [],
        numeric_value=str(ent.get("value", "") or "").strip(),
        unit=str(ent.get("unit", "") or "").strip(),
        reference_range=str(ent.get("reference_range", "") or "").strip(),
        source=str(ent.get("__source", "unknown")),
        model_name=str(ent.get("__model_name", "")),
        model_version=str(ent.get("__model_version", "")),
        contract_version=str(ent.get("__contract_version", CONTRACT_VERSION)),
    )


def _build_expected_tags(items: list[ExtractionItem]) -> dict[str, str]:
    tags: dict[str, str] = {}
    for item in items:
        key = item.normalized
        if key in tags:
            continue
        snomed_tag = LABEL_TO_SNOMED_TAG.get(item.semantic_tag)
        if snomed_tag:
            tags[key] = snomed_tag
    return tags


# ── terminology resolution ────────────────────────────────────────────────────
_TERM_TIMEOUT = float(os.getenv("TERM_RESOLVE_TIMEOUT", "300"))


async def resolve_via_api(
    terms: list[str],
    expected_tags: dict[str, str],
    timeout: float | None = None,
    retries: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    timeout = timeout if timeout is not None else _TERM_TIMEOUT
    if not terms:
        return {}
    unique = list(dict.fromkeys(terms))
    body: dict[str, Any] = {"terms": unique}
    if expected_tags:
        body["expected_tags"] = expected_tags

    last_exc: Exception | None = None
    sem = _get_term_semaphore()

    for attempt in range(1, retries + 1):
        # Rotate URL on each attempt so a failed instance is not retried immediately
        base_url = next(_url_cycle)
        try:
            async with sem:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        f"{base_url}/terminology/resolve",
                        json=body,
                    )
                    resp.raise_for_status()
                    return resp.json().get("results", {})
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                import random

                delay = (2**attempt) + random.uniform(0, 1)
                # Log type+repr — str(exc) is often empty for connection errors
                err_detail = f"{type(exc).__name__}: {exc!r}" if exc else "unknown"
                logger.warning(
                    "Terminology API attempt %d/%d failed (%s): %s — retrying in %.1fs…",
                    attempt,
                    retries,
                    base_url,
                    err_detail,
                    delay,
                )
                await asyncio.sleep(delay)

    err_detail = f"{type(last_exc).__name__}: {last_exc!r}" if last_exc else "unknown"
    logger.warning(
        "Terminology API failed after %d attempts (%s): %s",
        retries,
        base_url,
        err_detail,
    )
    return {}


async def warmup_terminology_api() -> bool:
    """Warm up all configured terminology API instances.

    Sends a lightweight resolve call to each instance to load the embedding
    model before the main processing loop begins.  Returns True if at least
    one instance is healthy.
    """
    logger.info(
        "Warming up %d Terminology API instance(s): %s",
        len(_API_URLS),
        ", ".join(_API_URLS),
    )
    healthy = 0
    for url in _API_URLS:
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{url}/terminology/resolve",
                    json={"terms": ["hypertension", "diabetes"]},
                )
                resp.raise_for_status()
                logger.info("  %s — warm-up OK", url)
                healthy += 1
        except Exception as exc:
            logger.error("  %s — warm-up FAILED: %s", url, exc)
    if healthy == 0:
        logger.error(
            "No Terminology API instances responded — resolve calls will return empty results."
        )
        return False
    if healthy < len(_API_URLS):
        logger.warning("%d/%d instances healthy.", healthy, len(_API_URLS))
    else:
        logger.info("All %d Terminology API instances ready.", healthy)
    return True


# ── per-record pipeline ───────────────────────────────────────────────────────
async def process_record(
    rec: dict[str, Any],
    extractor: Any,
    splitter: SentenceSplitter,
    rules: list[PostProcessorRule],
    neo4j_client: PatientGraphClient,
) -> RecordResult:
    label_id = rec["label_id"]
    text = rec["text"]
    loop = asyncio.get_event_loop()

    # Stage 1: Sentence splitting (CPU-bound PyRuSH — run in executor to avoid
    # blocking the event loop so concurrent terminology requests can proceed)
    sentences = await loop.run_in_executor(None, splitter.split, text)
    sent_lookup: dict[str, str] = {s.sentence_id: s.text for s in sentences}
    if not sentences:
        return RecordResult(
            label_id=label_id,
            encounter_id=rec["encounter_id"],
            source=rec["source"],
            quality_score=float(rec.get("quality_score") or 0.0),
            entity_count=0,
            coded_count=0,
            tier1_count=0,
            tier2_count=0,
            tier3_count=0,
            surface_gaps=[],
            low_conf=[],
            assertion_counts={},
            written=False,
            error="no_sentences",
        )

    # Stage 2: Extraction (batched, mirrors pipeline _BATCH_SIZE=5)
    # Run in executor so boto3/Bedrock does not block the event loop.
    by_sentence: dict[str, list[ExtractionItem]] = {}
    try:
        for idx in range(0, len(sentences), BATCH_SIZE):
            batch = sentences[idx : idx + BATCH_SIZE]
            items = await loop.run_in_executor(
                None, extractor.extract_batch, text, batch
            )
            for item in items:
                by_sentence.setdefault(item.sentence_id, []).append(item)
    except Exception as exc:
        logger.warning("Extraction failed for %s: %s", label_id[:16], exc)
        return RecordResult(
            label_id=label_id,
            encounter_id=rec["encounter_id"],
            source=rec["source"],
            quality_score=float(rec.get("quality_score") or 0.0),
            entity_count=0,
            coded_count=0,
            tier1_count=0,
            tier2_count=0,
            tier3_count=0,
            surface_gaps=[],
            low_conf=[],
            assertion_counts={},
            written=False,
            error=f"extraction_failed: {exc}",
        )

    all_items = [item for items in by_sentence.values() for item in items]

    # Stage 3: Unified post-processing (9-layer stack — CPU-bound, run in executor)
    entity_dicts = _items_to_dicts(all_items)
    try:
        processed_dicts = await loop.run_in_executor(
            None,
            lambda: run_post_processing(
                text,
                entity_dicts,
                rules=rules or None,
                enable_disorder_gate=False,
                coding_mode="hitl",
            ),
        )
    except Exception as exc:
        logger.warning("Post-processing failed for %s: %s", label_id[:16], exc)
        processed_dicts = entity_dicts  # fall back to unprocessed

    context_detection_failed = any(
        e.get("context_detection_failed") for e in processed_dicts
    )

    processed_items = [_dict_to_item(e) for e in processed_dicts]

    # Stage 4: Terminology resolution
    terms = list(
        dict.fromkeys(item.normalized for item in processed_items if item.normalized)
    )
    expected_tags = _build_expected_tags(processed_items)
    resolved = await resolve_via_api(terms, expected_tags)

    # Stage 5: Build payload + classify_tier (mirrors _build_sentences_payload)
    entities_to_write: list[dict[str, Any]] = []
    surface_gaps: list[dict] = []
    low_conf: list[dict] = []
    assertion_counts: Counter = Counter()
    tier_counts = {1: 0, 2: 0, 3: 0}
    coded_count = 0

    for item in processed_items:
        candidates = resolved.get(item.normalized, [])
        best = candidates[0] if candidates else {}
        score = float(best.get("score", 0.0) or 0.0)
        sf_status = str(best.get("surface_form_status", "") or "")

        tier = classify_tier(
            assertion=item.assertion or "present",
            context_failed=context_detection_failed,
            terminology_score=score,
            surface_form_status=sf_status,
            coding_mode="hitl",
        )

        assertion_counts[item.assertion or "present"] += 1
        tier_counts[tier.tier] = tier_counts.get(tier.tier, 0) + 1
        if score >= MIN_SCORE_CODED:
            coded_count += 1

        entity_record: dict[str, Any] = {
            "text": item.text,
            "label": item.semantic_tag,
            "start": item.span_start,
            "end": item.span_end,
            "assertion": item.assertion or "present",
            "confidence": item.confidence,
            "normalized": (item.normalized if item.normalized != item.text else None),
            "value": item.numeric_value or None,
            "unit": item.unit or None,
            "reference_range": item.reference_range or None,
            # SNOMED resolution
            "snomed_concept_id": best.get("snomed_concept_id") or None,
            "snomed_term": best.get("snomed_term") or None,
            "read_code": best.get("read_code") or None,
            "snomed_score": round(score, 4) if score > 0 else None,
            # Tier classification
            "decision_tier": tier.tier,
            "tier_decision": tier.decision,
            "tier_reason": tier.reason,
            "audit_flag": tier.decision == "coded_with_flag",
            # Provenance
            "extraction_source": item.source,
        }
        entities_to_write.append(entity_record)

        sent_text = sent_lookup.get(item.sentence_id, "")
        snomed_str = (
            f"{best.get('snomed_term')} ({best.get('snomed_concept_id')}) "
            f"score={score:.3f}"
            if best.get("snomed_concept_id")
            else "NO_CODE"
        )
        logger.debug(
            "  [%s:%s] %r | sent: %r | %s | assertion=%s T%d",
            item.span_start,
            item.span_end,
            item.text,
            sent_text,
            snomed_str,
            item.assertion or "present",
            tier.tier,
        )

        if score < MIN_SCORE_CODED and item.semantic_tag in _CODEABLE_LABELS:
            surface_gaps.append(
                {
                    "text": item.text,
                    "label": item.semantic_tag,
                    "assertion": item.assertion or "present",
                    "confidence": item.confidence,
                    "top_score": round(score, 4),
                    "top_candidate": best.get("snomed_term") or "",
                    "top_candidate_id": best.get("snomed_concept_id") or "",
                }
            )

        if item.confidence < CONFIDENCE_FLAG_THRESHOLD:
            low_conf.append(
                {
                    "text": item.text,
                    "label": item.semantic_tag,
                    "confidence": item.confidence,
                }
            )

    # Write back to Neo4j
    written = False
    error = ""
    try:
        neo4j_client.run(
            WRITE_BACK_QUERY,
            label_id=label_id,
            entities_json=json.dumps(entities_to_write, default=str),
        )
        written = True
    except Exception as exc:
        logger.error("Write-back failed for %s: %s", label_id[:16], exc)
        error = f"write_failed: {exc}"

    return RecordResult(
        label_id=label_id,
        encounter_id=rec["encounter_id"],
        source=rec["source"],
        quality_score=float(rec.get("quality_score") or 0.0),
        entity_count=len(entities_to_write),
        coded_count=coded_count,
        tier1_count=tier_counts.get(1, 0),
        tier2_count=tier_counts.get(2, 0),
        tier3_count=tier_counts.get(3, 0),
        surface_gaps=surface_gaps,
        low_conf=low_conf,
        assertion_counts=dict(assertion_counts),
        written=written,
        error=error,
    )


# ── report generation ─────────────────────────────────────────────────────────
def generate_report(
    results: list[RecordResult],
    extractor_name: str,
    run_start: datetime,
    rules_count: int,
    context_patched: bool = False,
) -> str:
    run_end = datetime.now(timezone.utc)
    duration_s = (run_end - run_start).total_seconds()

    total_records = len(results)
    processed = [r for r in results if not r.error or r.error == ""]
    errored = [r for r in results if r.error]
    written_ok = [r for r in results if r.written]

    total_entities = sum(r.entity_count for r in results)
    total_coded = sum(r.coded_count for r in results)
    total_tier1 = sum(r.tier1_count for r in results)
    total_tier2 = sum(r.tier2_count for r in results)
    total_tier3 = sum(r.tier3_count for r in results)

    coding_pct = (total_coded / total_entities * 100) if total_entities else 0.0

    # Aggregate surface gaps by text+label
    gap_counter: Counter = Counter()
    gap_examples: dict[str, dict] = {}
    for r in results:
        for g in r.surface_gaps:
            key = f"{g['text']}|{g['label']}"
            gap_counter[key] += 1
            if key not in gap_examples:
                gap_examples[key] = g

    # Aggregate low-confidence by text
    low_conf_counter: Counter = Counter()
    low_conf_examples: dict[str, dict] = {}
    for r in results:
        for lc in r.low_conf:
            key = f"{lc['text']}|{lc['label']}"
            low_conf_counter[key] += 1
            if key not in low_conf_examples:
                low_conf_examples[key] = lc

    # Assertion breakdown by label
    assertion_by_label: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        for ent_rec in r.assertion_counts.items():
            pass  # We only have per-record totals; rebuild from surface_gaps below

    # Aggregate assertion counts across all records
    global_assertion: Counter = Counter()
    for r in results:
        for assertion, cnt in r.assertion_counts.items():
            global_assertion[assertion] += cnt

    lines: list[str] = []

    lines.append("# Training Data Pipeline Evaluation Report\n")
    lines.append(f"Generated: {run_end.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    lines.append(f"Duration: {duration_s:.0f}s\n")
    lines.append("")

    # ── Run metadata ─────────────────────────────────────────────────────────
    lines.append("## Run Metadata\n")
    lines.append(f"| Parameter | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Extractor backend | `{extractor_name}` |")
    lines.append(f"| Post-processor rules loaded | {rules_count} |")
    lines.append(f"| Coding mode | `hitl` |")
    lines.append(f"| Min score threshold | {MIN_SCORE_CODED} |")
    lines.append(f"| Confidence flag threshold | {CONFIDENCE_FLAG_THRESHOLD} |")
    lines.append(f"| Eval limit | {EVAL_LIMIT or 'none (all records)'} |")
    lines.append(
        f"| Terminology API instance(s) | {' · '.join(f'`{u}`' for u in _API_URLS)} |"
    )
    lines.append(
        f"| ConText assertion detection | "
        f"{'**DISABLED** (PyRuSH not installed — all entities context_detection_failed=True)' if context_patched else 'enabled'} |"
    )
    lines.append("")

    # ── Pipeline Summary ─────────────────────────────────────────────────────
    lines.append("## Pipeline Summary\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Records fetched | {total_records} |")
    lines.append(f"| Records written back | {len(written_ok)} |")
    lines.append(f"| Records errored | {len(errored)} |")
    lines.append(f"| Total entities extracted | {total_entities} |")
    lines.append(
        f"| Entities coded (score >= {MIN_SCORE_CODED}) | {total_coded} ({coding_pct:.1f}%) |"
    )
    lines.append(f"| Tier 1 — auto_coded | {total_tier1} |")
    lines.append(f"| Tier 2 — coded_with_flag / route_to_review | {total_tier2} |")
    lines.append(f"| Tier 3 — route_to_review / not_coded | {total_tier3} |")
    lines.append(f"| Unique surface form gaps | {len(gap_counter)} |")
    lines.append(f"| Unique low-confidence terms | {len(low_conf_counter)} |")
    lines.append("")

    # Assertion breakdown
    lines.append("### Assertion Distribution\n")
    lines.append("| Assertion | Count |")
    lines.append("|---|---|")
    for assertion, cnt in sorted(global_assertion.items(), key=lambda x: -x[1]):
        lines.append(f"| `{assertion}` | {cnt} |")
    lines.append("")

    # ── Surface Form Gaps ────────────────────────────────────────────────────
    lines.append("## Surface Form Gaps\n")
    lines.append(
        "Entities the pipeline extracted but the terminology API could not code "
        f"(top score < {MIN_SCORE_CODED}). These indicate missing surface forms in the "
        "terminology graph and are the primary actionable output of this report.\n"
    )
    if gap_counter:
        lines.append(
            f"| Occurrences | Entity text | Label | Top candidate | Top score |"
        )
        lines.append("|---|---|---|---|---|")
        for key, count in gap_counter.most_common(100):
            g = gap_examples[key]
            candidate = g.get("top_candidate") or "*(no match)*"
            lines.append(
                f"| {count} | `{g['text']}` | `{g['label']}` | {candidate} | {g['top_score']} |"
            )
    else:
        lines.append(
            "*No surface form gaps detected — all codeable entities resolved successfully.*\n"
        )
    lines.append("")

    # ── Low-Confidence Extractions ───────────────────────────────────────────
    lines.append("## Low-Confidence Extractions\n")
    lines.append(
        f"Pipeline entities with extraction confidence < {CONFIDENCE_FLAG_THRESHOLD}. "
        "These are candidates for HITL review.\n"
    )
    if low_conf_counter:
        lines.append("| Occurrences | Entity text | Label | Confidence |")
        lines.append("|---|---|---|---|")
        for key, count in low_conf_counter.most_common(50):
            lc = low_conf_examples[key]
            lines.append(
                f"| {count} | `{lc['text']}` | `{lc['label']}` | {lc['confidence']:.2f} |"
            )
    else:
        lines.append(
            f"*No low-confidence extractions (all entities >= {CONFIDENCE_FLAG_THRESHOLD}).*\n"
        )
    lines.append("")

    # ── Errors ───────────────────────────────────────────────────────────────
    if errored:
        lines.append("## Processing Errors\n")
        lines.append("| label_id | Error |")
        lines.append("|---|---|")
        for r in errored:
            lines.append(f"| `{r.label_id[:24]}…` | `{r.error}` |")
        lines.append("")

    # ── Per-Record Detail ────────────────────────────────────────────────────
    lines.append("## Per-Record Detail\n")
    lines.append(
        f"Top {MAX_DETAIL_RECORDS} records by surface form gap count. "
        "Shows entities written to `entities_json`.\n"
    )

    top_records = sorted(results, key=lambda r: len(r.surface_gaps), reverse=True)[
        :MAX_DETAIL_RECORDS
    ]

    for r in top_records:
        if r.entity_count == 0:
            continue
        lines.append(
            f"### `{r.label_id[:32]}` "
            f"(source: {r.source}, quality: {r.quality_score:.2f})\n"
        )
        lines.append(
            f"- Entities: {r.entity_count} | "
            f"Coded: {r.coded_count} | "
            f"T1: {r.tier1_count} T2: {r.tier2_count} T3: {r.tier3_count} | "
            f"Surface gaps: {len(r.surface_gaps)} | "
            f"Written: {'yes' if r.written else 'NO'}\n"
        )
        if r.surface_gaps:
            lines.append("**Surface form gaps in this record:**\n")
            lines.append("| text | label | top score | top candidate |")
            lines.append("|---|---|---|---|")
            for g in r.surface_gaps[:10]:
                candidate = g.get("top_candidate") or "*(no match)*"
                lines.append(
                    f"| `{g['text']}` | `{g['label']}` | {g['top_score']} | {candidate} |"
                )
            lines.append("")

    lines.append("\n---\n")
    lines.append(
        f"*Report generated by `scripts/evaluate_training_data.py` — "
        f"{len(written_ok)} TrainingLabel nodes updated.*\n"
    )

    return "\n".join(lines)


# ── main ──────────────────────────────────────────────────────────────────────
async def main() -> None:
    run_start = datetime.now(timezone.utc)
    logger.info("=== Training Data Evaluation starting ===")

    # Apply ConText patch before any post-processing runs
    context_patched = _patch_context_if_needed()

    # Connect to Neo4j
    neo4j_client = PatientGraphClient()

    # Load post-processor rules once
    logger.info("Loading post-processor rules from Neo4j…")
    try:
        rule_rows = neo4j_client.run(GET_ACTIVE_POST_PROCESSOR_RULES)
        rules = parse_rules(rule_rows)
        logger.info("Loaded %d active post-processor rules", len(rules))
    except Exception as exc:
        logger.warning(
            "Could not load post-processor rules (%s) — continuing without them", exc
        )
        rules = []

    # Build extractor (once — may be slow for model backend)
    logger.info("Initialising extractor…")
    extractor = build_extractor()
    logger.info(
        "Extractor ready: backend=%s model=%s v%s",
        extractor.source,
        extractor.model_name,
        extractor.model_version,
    )

    # Initialise sentence splitter
    splitter = SentenceSplitter()
    logger.info("Sentence splitter mode: %s", splitter.mode)

    # Warm up terminology API (loads embedding model on first call)
    api_healthy = await warmup_terminology_api()
    if not api_healthy:
        logger.warning(
            "Proceeding without terminology resolution — entities will have no SNOMED codes."
        )

    # Fetch training records
    logger.info("Fetching TrainingLabel records…")
    rows = neo4j_client.run(FETCH_LABELS_QUERY)
    records = [dict(row) for row in rows]
    if EVAL_LIMIT:
        records = records[:EVAL_LIMIT]
        logger.info(
            "EVAL_LIMIT=%d applied — processing %d records", EVAL_LIMIT, len(records)
        )
    else:
        logger.info("Fetched %d records", len(records))

    if not records:
        logger.error("No TrainingLabel records found. Exiting.")
        return

    # Process records concurrently
    results: list[RecordResult] = []
    total = len(records)
    completed = 0
    semaphore = asyncio.Semaphore(CONCURRENCY)
    logger.info("Processing %d records with concurrency=%d…", total, CONCURRENCY)

    async def _run_one(i: int, rec: dict) -> RecordResult:
        nonlocal completed
        short_id = rec.get("label_id", "?")[:20]
        async with semaphore:
            try:
                result = await process_record(
                    rec, extractor, splitter, rules, neo4j_client
                )
            except Exception as exc:
                logger.error(
                    "Unhandled error on record %s: %s", short_id, exc, exc_info=True
                )
                result = RecordResult(
                    label_id=rec.get("label_id", "unknown"),
                    encounter_id=rec.get("encounter_id", ""),
                    source=rec.get("source", ""),
                    quality_score=0.0,
                    entity_count=0,
                    coded_count=0,
                    tier1_count=0,
                    tier2_count=0,
                    tier3_count=0,
                    surface_gaps=[],
                    low_conf=[],
                    assertion_counts={},
                    written=False,
                    error=str(exc),
                )
            completed += 1
            status = "OK" if result.written else f"ERR:{result.error[:30]}"
            logger.info(
                "[%d/%d] %s  ent=%d  coded=%d  T1=%d T2=%d T3=%d  gaps=%d  %s",
                completed,
                total,
                short_id,
                result.entity_count,
                result.coded_count,
                result.tier1_count,
                result.tier2_count,
                result.tier3_count,
                len(result.surface_gaps),
                status,
            )
            return result

    tasks = [_run_one(i, rec) for i, rec in enumerate(records, start=1)]
    results = list(await asyncio.gather(*tasks))

    # Generate report
    logger.info("Generating report…")
    report_md = generate_report(
        results=results,
        extractor_name=f"{extractor.source}/{extractor.model_name} v{extractor.model_version}",
        run_start=run_start,
        rules_count=len(rules),
        context_patched=context_patched,
    )
    OUTPUT_PATH.write_text(report_md, encoding="utf-8")

    written_count = sum(1 for r in results if r.written)
    total_entities = sum(r.entity_count for r in results)
    total_gaps = sum(len(r.surface_gaps) for r in results)
    logger.info(
        "=== Done === records=%d written=%d total_entities=%d surface_gaps=%d",
        total,
        written_count,
        total_entities,
        total_gaps,
    )
    print(f"\nReport written to: {OUTPUT_PATH}")
    print(f"Records processed : {total}")
    print(f"Records written   : {written_count}")
    print(f"Total entities    : {total_entities}")
    print(f"Surface form gaps : {total_gaps}")


if __name__ == "__main__":
    asyncio.run(main())
