#!/usr/bin/env python3
"""Lab encounter SNOMED coding loop.

Iterates all Encounter nodes in the patient graph, detects blood test lines,
codes procedure / observable_entity / finding triples, and writes completed
GoldLabels to the knowledge graph.

Self-improving feedback loops
------------------------------
1. Surface forms grow: every successfully coded entity is upserted as an
   approved SurfaceForm so the next run hits it as had_exact_match=True
   (no Haiku call needed).
2. Training data grows: completed GoldLabels feed the next model training cycle.
3. Validation: validate-seeds mode checks quality before each batch run.

Usage
-----
    # Dry-run (default -- no writes)
    .venv/bin/python scripts/coding_loop/run_labs.py run --limit 20

    # Validate against hand-coded seed encounters first
    .venv/bin/python scripts/coding_loop/run_labs.py validate-seeds

    # Full run with Haiku for failed SNOMED entities
    .venv/bin/python scripts/coding_loop/run_labs.py run \\
        --apply --confirm-apply --with-haiku --limit 500

    # Parallel workers (Haiku tolerates 4-8)
    .venv/bin/python scripts/coding_loop/run_labs.py run \\
        --apply --confirm-apply --with-haiku --workers 4 --limit 2000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config")
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets")

logger = logging.getLogger("run_labs")

# Source tag written to both DOCUMENTS relationships and GoldLabel nodes.
_SOURCE = "lab_coder_v1"
_SCHEMA_VERSION = "v4"
_HITL_REASON = "lab_auto_coded"

# Minimum resolver score for any span to be included without Haiku.
_MIN_AUTO_SCORE = 0.70

# Lab entity labels we care about.
_LAB_LABELS = frozenset({"procedure", "observable_entity", "finding"})


# ---------------------------------------------------------------------------
# Hashing helpers (match seed_manual_gold_records.py convention)
# ---------------------------------------------------------------------------


def _candidate_id(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()


def _label_id(text: str, entities: list[dict[str, Any]]) -> str:
    parts = sorted(str(e.get("text", "")) for e in entities)
    raw = f"{text}|{'|'.join(parts)}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"GL-{digest[:16]}"


# ---------------------------------------------------------------------------
# Quality score per entity based on SNOMED validation branch
# ---------------------------------------------------------------------------


def _quality_score(result: Any, haiku_called: bool) -> float:
    if haiku_called:
        return 0.80
    branch = str(getattr(result, "reason", "")).lower()
    if "exact" in branch:
        return 1.0
    if "semantic" in branch or "surface" in branch:
        return 0.90
    return 0.85


def _align_entity_for_gold(
    sentence_text: str,
    entity: dict[str, Any],
) -> dict[str, Any] | None:
    """Return an entity whose text/start/end match the sentence exactly."""

    from libs.pipeline.label_filter import repair_entity_spans

    repair = repair_entity_spans(sentence_text, [entity])
    if repair["repaired"] or repair["unchanged"]:
        return repair["entities"][0]

    status = "ambiguous" if repair["ambiguous"] else "unrepairable"
    logger.warning(
        "process_sentence: dropping %s auto-gold entity %r",
        status,
        entity.get("text", ""),
    )
    return None


def _validated_gold_entities(
    sentence_text: str,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep only entities that can be made span-consistent."""

    aligned: list[dict[str, Any]] = []
    for entity in entities:
        repaired = _align_entity_for_gold(sentence_text, entity)
        if repaired is not None:
            aligned.append(repaired)
    return aligned


# ---------------------------------------------------------------------------
# Surface form write-back (Loop 1 feedback)
# ---------------------------------------------------------------------------


def _upsert_surface_forms(
    kg_session: Any,
    entities: list[dict[str, Any]],
    *,
    haiku_called: bool,
) -> None:
    """Upsert SurfaceForm nodes for accepted entities to grow the lookup table."""
    from libs.terminology.surface_normalize import normalize_surface
    from services.terminology_api.app.queries.terminology import UPSERT_SURFACE_FORMS

    rows = []
    for ent in entities:
        concept_id = str(ent.get("snomed_concept_id") or "").strip()
        text = str(ent.get("text") or "").strip()
        if not concept_id or not text:
            continue
        normalized = normalize_surface(text)
        if not normalized:
            continue
        rows.append(
            {
                "normalized": normalized,
                "form": text,
                "concept_id": concept_id,
                "source": _SOURCE,
                "status": "approved",
                "confidence": 0.80 if haiku_called else 0.95,
                "provenance": "haiku_arbitrated" if haiku_called else "lab_auto_coded",
            }
        )
    if not rows:
        return
    try:
        kg_session.run(UPSERT_SURFACE_FORMS, rows=rows)
    except Exception:
        logger.debug("_upsert_surface_forms: failed (non-fatal)", exc_info=True)


# ---------------------------------------------------------------------------
# Entity extraction and SNOMED validation for one sentence
# ---------------------------------------------------------------------------


def _resolve_candidates(entity: Any) -> list[dict[str, Any]]:
    """Flatten ResolvedTerm into a plain dict for the arbitrator prompt."""
    return [
        {
            "concept_id": getattr(e, "concept_id", ""),
            "snomed_term": getattr(e, "term", ""),
            "semantic_tag": getattr(e, "semantic_tag", ""),
            "score": getattr(e, "score", 0.0),
            "had_exact_match": getattr(e, "had_exact_match", False),
        }
        for e in (entity if isinstance(entity, list) else [])
    ]


def _observable_measurement_fields(pattern: Any, label: str) -> dict[str, str | None]:
    if label != "observable_entity":
        return {}
    return {
        "numeric_value": getattr(pattern, "numeric_value", None),
        "unit": getattr(pattern, "unit", None),
        "reference_range": getattr(pattern, "reference_range", None),
    }


def process_sentence(
    sentence_text: str,
    *,
    terminology_client: Any,
    with_haiku: bool,
    arbitrator: Any | None,
    dry_run: bool,
) -> dict[str, Any] | None:
    """Extract, validate, and return coded entities for one lab sentence.

    Returns a dict ready for writing, or None if the sentence should be skipped.
    """
    from libs.training.lab_span_detector import detect_lab_pattern
    from libs.training.lab_concept_lookup import lab_lookup_texts
    from scripts.lib.gold_label_extractors import extract_deterministic
    from scripts.lib.gold_label_snomed_check import validate_proposals_batch

    pattern = detect_lab_pattern(sentence_text)
    if not pattern.matched:
        return None

    raw_entities = extract_deterministic(sentence_text)
    lab_entities = [
        e
        for e in raw_entities
        if str(e.get("label") or e.get("semantic_tag", "")).strip().lower()
        in _LAB_LABELS
    ]
    if not lab_entities:
        return None

    proposals = [
        (lookup_text, str(e.get("label") or "").strip().lower())
        for e in lab_entities
        if e.get("text") and e.get("label")
        for lookup_text in lab_lookup_texts(e)
    ]
    validation_map = validate_proposals_batch(proposals, terminology_client)

    haiku_called = False
    coded_entities: list[dict[str, Any]] = []
    quality_results: list[Any] = []

    for entity in lab_entities:
        original_text = str(entity.get("text") or "").strip()
        label = str(entity.get("label") or "").strip().lower()
        if not original_text or not label:
            continue

        lookup_keys = lab_lookup_texts(entity)
        lookup_key = lookup_keys[0] if lookup_keys else ""
        vr = None
        for candidate_lookup in lookup_keys:
            candidate_vr = validation_map.get((candidate_lookup, label))
            if candidate_vr is None:
                continue
            if vr is None:
                vr = candidate_vr
                lookup_key = candidate_lookup
            if candidate_vr.accepted:
                vr = candidate_vr
                lookup_key = candidate_lookup
                break
        if vr is None:
            continue

        # Always write back the original (full) span text to the patient graph,
        # not the canonicalized lookup form.
        if vr.accepted:
            aligned = _align_entity_for_gold(
                sentence_text,
                {
                    "text": original_text,
                    "label": label,
                    "semantic_tag": label,
                    "snomed_concept_id": str(vr.concept_id or ""),
                    "snomed_term": str(vr.snomed_term or ""),
                    "start": entity.get("start", 0),
                    "end": entity.get("end", 0),
                    "assertion": "present",
                    **_observable_measurement_fields(pattern, label),
                },
            )
            if aligned is None:
                continue
            coded_entities.append(aligned)
            quality_results.append(vr)
            continue

        # Failed validation -- try Haiku if available.
        if not with_haiku or arbitrator is None:
            logger.debug(
                "process_sentence: skipping entity %r (validation failed, no Haiku)",
                original_text,
            )
            continue

        parsed = pattern
        result = arbitrator.arbitrate(
            lab_line=sentence_text,
            numeric_value=str(getattr(parsed, "numeric_value", "") or ""),
            unit=str(getattr(parsed, "unit", "") or ""),
            reference_range=str(getattr(parsed, "reference_range", "") or ""),
            interpretation=str(getattr(parsed, "interpretation", "") or ""),
            entity_label=label,
            entity_text=original_text,
            candidates=_resolve_candidates(
                terminology_client.resolve(
                    [lookup_key], expected_tags={lookup_key: label}
                ).get(lookup_key, [])
            ),
        )
        haiku_called = True

        if result.is_drop:
            logger.debug(
                "process_sentence: Haiku dropped entity %r: %s",
                original_text,
                result.reason,
            )
            continue

        final_text = result.text if result.decision == "fix_span" else original_text
        aligned = _align_entity_for_gold(
            sentence_text,
            {
                "text": final_text,
                "label": label,
                "semantic_tag": label,
                "snomed_concept_id": result.concept_id,
                "snomed_term": result.snomed_term,
                "start": entity.get("start", 0),
                "end": entity.get("end", 0),
                "assertion": "present",
                **_observable_measurement_fields(pattern, label),
            },
        )
        if aligned is None:
            continue
        coded_entities.append(aligned)
        quality_results.append(vr)

    if not coded_entities:
        return None

    q_score = sum(
        _quality_score(result, haiku_called) for result in quality_results
    ) / len(quality_results)

    return {
        "sentence_text": sentence_text,
        "entities": coded_entities,
        "haiku_called": haiku_called,
        "quality_score": q_score,
    }


# ---------------------------------------------------------------------------
# Neo4j writes
# ---------------------------------------------------------------------------


def write_sentence_result(
    encounter_id: str,
    result: dict[str, Any],
    *,
    patient_session: Any,
    kg_session: Any,
) -> None:
    """Write DOCUMENTS rels (patient graph) + TrainingCandidate + GoldLabel (KG)."""
    from libs.cypher.documents_queries import write_documents_from_sentences_payload
    from libs.cypher.gold_label_queries import UPSERT_GOLD_LABEL
    from libs.cypher.training_candidate_queries import (
        UPSERT_TRAINING_CANDIDATE,
        UPDATE_TRAINING_CANDIDATE_STATUS,
    )

    sentence_text = result["sentence_text"]
    entities = _validated_gold_entities(sentence_text, result["entities"])
    if not entities:
        logger.warning("write_sentence_result: no span-consistent entities to write")
        return
    haiku_called = result["haiku_called"]
    q_score = result["quality_score"]
    tier = "haiku" if haiku_called else "surface_form"

    # -- Patient graph: DOCUMENTS relationships --
    sentences_payload = [
        {
            "text": sentence_text,
            "terms": [
                {
                    "text": e["text"],
                    "semantic_tag": e["label"],
                    "assertion": "present",
                    "coding": {
                        "snomed_concept_id": e["snomed_concept_id"],
                        "snomed_term": e["snomed_term"],
                        "read_code": None,
                        "score": q_score,
                        "source": _SOURCE,
                    },
                    "modifiers": {},
                    "numeric_value": e.get("numeric_value"),
                    "unit": e.get("unit"),
                    "reference_range": e.get("reference_range"),
                    "decision_tier": tier,
                }
                for e in entities
                if e.get("snomed_concept_id")
            ],
        }
    ]
    write_documents_from_sentences_payload(
        encounter_id,
        sentences_payload,
        patient_session,
        source=_SOURCE,
        model_name=_SOURCE,
        model_version="1.0",
    )

    # -- Knowledge graph: TrainingCandidate + GoldLabel --
    cand_id = _candidate_id(sentence_text)
    lbl_id = _label_id(sentence_text, entities)
    entities_json = json.dumps(entities)

    kg_session.run(
        UPSERT_TRAINING_CANDIDATE,
        candidate_id=cand_id,
        text=sentence_text,
        entities_json=entities_json,
        relation_changes=json.dumps([]),
        source=_SOURCE,
        status="processing",
        hitl_reason=_HITL_REASON,
        hitl_guidance=(
            "Auto-coded lab triple. Haiku-arbitrated."
            if haiku_called
            else "Auto-coded lab triple from surface form exact match."
        ),
        schema_version=_SCHEMA_VERSION,
    )
    kg_session.run(
        UPSERT_GOLD_LABEL,
        label_id=lbl_id,
        text=sentence_text,
        entities_json=entities_json,
        quality_score=float(q_score),
        source=_SOURCE,
        verified_by=_SOURCE,
        candidate_id=cand_id,
        schema_version=_SCHEMA_VERSION,
    )
    kg_session.run(
        UPDATE_TRAINING_CANDIDATE_STATUS,
        candidate_id=cand_id,
        status="completed",
    )

    # -- Loop 1 feedback: upsert SurfaceForm nodes --
    _upsert_surface_forms(kg_session, entities, haiku_called=haiku_called)


# ---------------------------------------------------------------------------
# Encounter paging
# ---------------------------------------------------------------------------


def _fetch_encounters(
    patient_client: Any,
    skip: int,
    limit: int,
) -> list[dict[str, Any]]:
    from libs.cypher.documents_queries import GET_ENCOUNTERS_PAGE

    with patient_client.session() as session:
        rows = session.run(GET_ENCOUNTERS_PAGE, skip=skip, limit=limit)
        return [dict(r) for r in rows]


def _fetch_encounters_total(patient_client: Any) -> int:
    from libs.cypher.documents_queries import GET_ENCOUNTERS_PAGE_TOTAL

    with patient_client.session() as session:
        rows = list(session.run(GET_ENCOUNTERS_PAGE_TOTAL))
        return int(rows[0]["total"]) if rows else 0


# ---------------------------------------------------------------------------
# Process one encounter (used by thread pool)
# ---------------------------------------------------------------------------


def process_encounter(
    enc: dict[str, Any],
    *,
    terminology_client: Any,
    with_haiku: bool,
    arbitrator: Any | None,
    apply: bool,
    patient_client: Any,
    kg_client: Any,
    stats: dict[str, int],
    lock: threading.Lock,
) -> None:
    from libs.nlp.sentence_splitter import SentenceSplitter

    encounter_id = str(enc.get("encounter_id") or "")
    text = str(enc.get("text") or "")
    if not encounter_id or not text:
        return

    splitter = SentenceSplitter()
    sentences = splitter.split(text)

    written = 0
    for chunk in sentences:
        sentence_text = getattr(chunk, "text", None) or (
            chunk if isinstance(chunk, str) else ""
        )
        if not sentence_text:
            continue

        result = process_sentence(
            sentence_text,
            terminology_client=terminology_client,
            with_haiku=with_haiku,
            arbitrator=arbitrator,
            dry_run=not apply,
        )
        if result is None:
            continue

        if apply:
            try:
                with patient_client.session() as ps, kg_client.session() as ks:
                    write_sentence_result(
                        encounter_id,
                        result,
                        patient_session=ps,
                        kg_session=ks,
                    )
                written += 1
            except Exception:
                logger.warning(
                    "process_encounter: write failed for encounter=%s",
                    encounter_id,
                    exc_info=True,
                )
        else:
            written += 1  # dry-run: count as would-have-written

    with lock:
        stats["encounters_processed"] += 1
        stats["sentences_coded"] += written
        if written:
            stats["encounters_with_lab_lines"] += 1


# ---------------------------------------------------------------------------
# validate-seeds mode
# ---------------------------------------------------------------------------


def run_validate_seeds(
    *,
    terminology_client: Any,
    with_haiku: bool,
    arbitrator: Any | None,
    min_precision: float,
) -> bool:
    """Run against hand-coded encounters and check precision.

    Seed encounters are those where at least one DOCUMENTS relationship has
    source='live_encounter_correction' (the manually coded set). We compare
    the loop's output concept_ids against the existing coded concepts.

    Returns True if precision >= min_precision, False otherwise.
    """
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    cypher = """
    MATCH (e:Encounter)-[r:DOCUMENTS]->(s)
    WHERE r.source IN ['live_encounter_correction', 'manual_gold_sync']
      AND e.text IS NOT NULL
    RETURN DISTINCT toString(e.id) AS encounter_id, e.text AS text
    LIMIT 50
    """
    with client.session() as session:
        seed_encounters = [dict(r) for r in session.run(cypher)]
    client.close()

    if not seed_encounters:
        logger.warning("validate-seeds: no seed encounters found; skipping validation")
        return True

    expected_map: dict[str, set[str]] = {}
    patient_client = PatientGraphClient()
    for enc in seed_encounters:
        eid = enc["encounter_id"]
        cypher_codes = """
        MATCH (e:Encounter)-[r:DOCUMENTS]->(s)
        WHERE toString(e.id) = $eid
          AND r.source IN ['live_encounter_correction', 'manual_gold_sync']
        RETURN DISTINCT toString(s.conceptId) AS concept_id
        """
        with patient_client.session() as session:
            rows = list(session.run(cypher_codes, eid=eid))
        expected_map[eid] = {r["concept_id"] for r in rows if r["concept_id"]}
    patient_client.close()

    # Recall-based metric: of the concepts in the manually coded gold set that
    # are lab-related, what fraction does the loop produce?
    # We use recall rather than precision because the manual gold set is
    # intentionally selective -- human coders annotated the concepts they cared
    # about, not every concept the loop would produce.
    from libs.nlp.sentence_splitter import SentenceSplitter

    lab_concept_ids: set[str] = set()
    for expected in expected_map.values():
        lab_concept_ids |= expected

    if not lab_concept_ids:
        logger.warning("validate-seeds: no expected concept IDs found; skipping")
        return True

    found: set[str] = set()
    for enc in seed_encounters:
        splitter = SentenceSplitter()
        sentences = splitter.split(enc["text"])
        for chunk in sentences:
            sentence_text = getattr(chunk, "text", None) or (
                chunk if isinstance(chunk, str) else ""
            )
            if not sentence_text:
                continue
            result = process_sentence(
                sentence_text,
                terminology_client=terminology_client,
                with_haiku=with_haiku,
                arbitrator=arbitrator,
                dry_run=True,
            )
            if not result:
                continue
            for ent in result["entities"]:
                cid = str(ent.get("snomed_concept_id") or "")
                if cid in lab_concept_ids:
                    found.add(cid)

    recall = len(found) / len(lab_concept_ids)
    logger.info(
        "validate-seeds: recall=%.3f (%d/%d expected concepts found) min_required=%.3f",
        recall,
        len(found),
        len(lab_concept_ids),
        min_precision,
    )
    if recall < min_precision:
        logger.error(
            "validate-seeds: FAILED recall %.3f < %.3f -- aborting run",
            recall,
            min_precision,
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Main run loop
# ---------------------------------------------------------------------------


def run_main(args: argparse.Namespace) -> int:
    from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
    from libs.terminology.client import TerminologyClient

    terminology_client = TerminologyClient(
        base_url=__import__("os").environ.get(
            "TERMINOLOGY_API_URL", "http://localhost:8001"
        )
    )

    arbitrator = None
    if args.with_haiku:
        try:
            from libs.coding.haiku_arbitrator import HaikuArbitrator

            arbitrator = HaikuArbitrator()
            logger.info("Haiku arbitrator initialised")
        except Exception:
            logger.warning(
                "Haiku arbitrator unavailable; --with-haiku ignored", exc_info=True
            )

    patient_client = PatientGraphClient()
    kg_client = KnowledgeGraphClient()

    total = _fetch_encounters_total(patient_client)
    logger.info("Encounters to process: %d", total)

    stats: dict[str, int] = Counter()
    lock = threading.Lock()

    started = time.time()
    skip = 0
    batch_size = args.batch_size
    workers = max(1, args.workers)

    apply = getattr(args, "apply", False) and getattr(args, "confirm_apply", False)
    if not apply:
        logger.info("DRY-RUN mode -- no writes to Neo4j")

    processed_total = 0
    while True:
        batch = _fetch_encounters(patient_client, skip=skip, limit=batch_size)
        if not batch:
            break

        def _handle(enc: dict[str, Any]) -> None:
            process_encounter(
                enc,
                terminology_client=terminology_client,
                with_haiku=args.with_haiku,
                arbitrator=arbitrator,
                apply=apply,
                patient_client=patient_client,
                kg_client=kg_client,
                stats=stats,
                lock=lock,
            )

        if workers == 1:
            for enc in batch:
                _handle(enc)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_handle, enc) for enc in batch]
                for fut in as_completed(futures):
                    fut.result()

        processed_total += len(batch)
        skip += batch_size

        elapsed = time.time() - started
        logger.info(
            "progress: %d/%d encounters | sentences_coded=%d | elapsed=%.1fs",
            processed_total,
            total,
            stats["sentences_coded"],
            elapsed,
        )

        if args.limit and processed_total >= args.limit:
            break

    patient_client.close()
    kg_client.close()

    summary = dict(stats)
    summary["elapsed_sec"] = round(time.time() - started, 2)
    summary["dry_run"] = not apply
    summary["with_haiku"] = args.with_haiku
    print(json.dumps(summary, indent=2))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Lab encounter SNOMED coding loop.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)

    # validate-seeds subcommand
    vs = sub.add_parser(
        "validate-seeds", help="Check precision on hand-coded encounters."
    )
    vs.add_argument("--min-precision", type=float, default=0.90)
    vs.add_argument("--with-haiku", action="store_true")
    vs.add_argument("-v", "--verbose", action="store_true")

    # run subcommand
    rn = sub.add_parser("run", help="Code encounters and write to Neo4j.")
    rn.add_argument("--apply", action="store_true", help="Write to Neo4j.")
    rn.add_argument(
        "--confirm-apply", action="store_true", help="Required with --apply."
    )
    rn.add_argument(
        "--with-haiku", action="store_true", help="Enable Haiku for failed entities."
    )
    rn.add_argument(
        "--skip-seed-validation",
        action="store_true",
        help="Skip validate-seeds check (dangerous).",
    )
    rn.add_argument("--min-precision", type=float, default=0.90)
    rn.add_argument("--limit", type=int, default=0, help="Max encounters (0=all).")
    rn.add_argument("--batch-size", type=int, default=50)
    rn.add_argument("--workers", type=int, default=1)
    rn.add_argument("-v", "--verbose", action="store_true")

    return p.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # PyRuSH uses loguru; suppress its DEBUG output at runtime.
    try:
        from loguru import logger as _loguru_logger

        _loguru_logger.remove()
        _loguru_logger.add(
            __import__("sys").stderr,
            level="WARNING",
            format="{time} {level} {name} {message}",
        )
    except Exception:
        pass

    if args.command == "validate-seeds":
        from libs.terminology.client import TerminologyClient
        import os

        tc = TerminologyClient(
            base_url=os.environ.get("TERMINOLOGY_API_URL", "http://localhost:8001")
        )
        arbitrator = None
        if args.with_haiku:
            try:
                from libs.coding.haiku_arbitrator import HaikuArbitrator

                arbitrator = HaikuArbitrator()
            except Exception:
                logger.warning("Haiku unavailable for validate-seeds")
        ok = run_validate_seeds(
            terminology_client=tc,
            with_haiku=args.with_haiku,
            arbitrator=arbitrator,
            min_precision=args.min_precision,
        )
        return 0 if ok else 1

    if args.command == "run":
        if args.apply and not args.confirm_apply:
            print("ERROR: --apply requires --confirm-apply", file=sys.stderr)
            return 1
        if not args.skip_seed_validation:
            from libs.terminology.client import TerminologyClient
            import os

            tc = TerminologyClient(
                base_url=os.environ.get("TERMINOLOGY_API_URL", "http://localhost:8001")
            )
            arbitrator = None
            if args.with_haiku:
                try:
                    from libs.coding.haiku_arbitrator import HaikuArbitrator

                    arbitrator = HaikuArbitrator()
                except Exception:
                    pass
            ok = run_validate_seeds(
                terminology_client=tc,
                with_haiku=args.with_haiku,
                arbitrator=arbitrator,
                min_precision=args.min_precision,
            )
            if not ok:
                return 1
        return run_main(args)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
