"""Build GoldLabel records from the cancer cohort annotation output.

Pipeline
--------
1. Read data/cancer_cohort_annotated/*.jsonl (output of annotate_cancer_cohort.py)
2. Span-align every entity quote to absolute char offsets using the
   sentences[] array embedded in each record.
3. Convert absolute offsets to sentence-relative (start - sent.start) since
   GoldLabel.text is the sentence, not the full encounter.
4. Batch-resolve SNOMED concepts via the Terminology API.
   - auto_accept: high-confidence exact semantic-tag + lexical match.
   - needs_review: candidates exist but not confident enough.
   - no_match: nothing found.
5. Write outputs to artifacts/cohort_gold/:
   - gold_label_records.jsonl   -- sentence-grouped, KG-ready records
   - needs_review.csv           -- entities for human concept selection
   - run_summary.json

Usage
-----
    python scripts/cohort/build_gold_labels_from_cohort.py [--dry-run] [--patient <id>]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("build_gold_labels")

from libs.cohort_annotation.span_aligner import align_entities, validate_spans
from libs.cohort_annotation.snomed_resolver import SnomedResolver
from libs.terminology.client import TerminologyClient
from libs.utils.deidentify import deidentify_text, detect_phi


ANNOTATED_DIR = ROOT / "data" / "cancer_cohort_annotated"


def _deid_span(deid_sentence: str, quote: str) -> tuple[str, int, int]:
    """Locate quote in an already-de-identified sentence.

    Returns (deid_sentence, rel_start, rel_end).
    rel_start == -1 signals the quote was obliterated by a PHI replacement.
    Entity text is clinical — never PII — so this should be rare.
    """
    idx = deid_sentence.find(quote)
    if idx >= 0:
        return deid_sentence, idx, idx + len(quote)
    # Case-insensitive fallback
    idx = deid_sentence.lower().find(quote.lower())
    if idx >= 0:
        return deid_sentence, idx, idx + len(quote)
    return deid_sentence, -1, -1
OUTPUT_DIR = ROOT / "artifacts" / "cohort_gold"
SCHEMA_VERSION = "cohort_v1"
SOURCE = "cancer_cohort_annotation_v1"


def _candidate_id_for_sentence(encounter_id: str, sentence_id: int) -> str:
    """Stable UUID from encounter + sentence."""
    key = f"cohort|{encounter_id}|s{sentence_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _label_id_for_sentence(encounter_id: str, sentence_id: int) -> str:
    key = f"cohort_gold|{encounter_id}|s{sentence_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def process_encounter(
    rec: dict,
    resolver: SnomedResolver,
    *,
    dry_run: bool = False,
) -> dict:
    """Return a dict with per-sentence GoldLabel records for one encounter."""
    encounter_id = rec.get("encounter_id") or ""
    text = rec.get("text") or ""
    sentences = rec.get("sentences") or []
    ann = rec.get("annotation") or {}
    raw_entities = ann.get("entities") or []

    if not raw_entities or not sentences:
        return {"encounter_id": encounter_id, "sentence_records": [], "skipped_entities": []}

    # Step 1: span-align to absolute document offsets
    aligned = align_entities(raw_entities, sentences, encounter_id=encounter_id)

    # Step 2: validate (text[start:end] == quote)
    valid, invalid = validate_spans(aligned, text, encounter_id=encounter_id)

    # Step 3: SNOMED resolution (skip in dry-run)
    if dry_run:
        resolved = [{**e, "resolution_status": "dry_run"} for e in valid]
    else:
        resolved = resolver.resolve_batch(valid)

    # Step 4: convert absolute offsets → sentence-relative offsets and group by sentence
    # Build a sent_start lookup
    sent_start_by_id: dict[int, int] = {
        int(s["sentence_id"]): int(s["start"]) for s in sentences
    }
    sent_text_by_id: dict[int, str] = {
        int(s["sentence_id"]): s["text"] for s in sentences
    }

    by_sentence: dict[int, list[dict]] = defaultdict(list)
    for ent in resolved:
        sid = int(ent.get("sentence_id") or 0)
        by_sentence[sid].append(ent)

    sentence_records: list[dict] = []
    phi_drop_count = 0
    for sid, ents in sorted(by_sentence.items()):
        raw_sent_text = sent_text_by_id.get(sid, "")
        offset = sent_start_by_id.get(sid, 0)
        candidate_id = _candidate_id_for_sentence(encounter_id, sid)
        label_id = _label_id_for_sentence(encounter_id, sid)

        # -- DE-ID: redact PII from sentence text before storing in GoldLabel --
        deid_sent_text = deidentify_text(raw_sent_text)
        phi_types = detect_phi(raw_sent_text)
        if phi_types:
            logger.debug(
                "encounter=%s sentence=%d: redacted PHI types %s",
                encounter_id, sid, phi_types,
            )

        entities_json: list[dict] = []
        for ent in ents:
            abs_start = ent.get("start", -1)
            abs_end = ent.get("end", -1)
            quote = ent.get("quote") or ""

            # Re-locate the entity span within the de-identified sentence text.
            # Entity text (clinical terms) is never PII, so it should always be
            # found. deidentify_with_span returns rel_start=-1 only when the
            # quote overlapped a redacted token — those entities must be dropped.
            if phi_types and quote:
                # sentence-relative quote (re-find within de-identified text)
                deid_sent, rel_start, rel_end = _deid_span(deid_sent_text, quote)
                if rel_start == -1:
                    logger.warning(
                        "encounter=%s entity=%s: quote %r overlapped PHI, dropped",
                        encounter_id, ent.get("id"), quote[:40],
                    )
                    phi_drop_count += 1
                    continue
            else:
                # No PHI in sentence — sentence-relative offset from abs span
                rel_start = abs_start - offset if abs_start >= 0 else -1
                rel_end = abs_end - offset if abs_end >= 0 else -1

            snomed_id = ent.get("snomed_concept_id")
            snomed_term = ent.get("snomed_term")
            snomed_tag = ent.get("snomed_semantic_tag")
            labels = ent.get("labels") or []
            primary_label = labels[0].lower() if labels else "unknown"

            entities_json.append({
                "snomed_concept_id": snomed_id,
                "snomed_term": snomed_term,
                "start": rel_start,
                "end": rel_end,
                "assertion": ent.get("assertion", "present"),
                "text": quote,
                "label": primary_label,
                "semantic_tag": snomed_tag or primary_label,
                # Extra metadata (stripped before KG write)
                "_entity_id": ent.get("id"),
                "_labels": labels,
                "_resolution_status": ent.get("resolution_status", "unknown"),
                "_resolution_score": ent.get("resolution_score", 0.0),
                "_expected_snomed_tag": ent.get("expected_snomed_tag"),
                "_resolution_candidates": ent.get("resolution_candidates", []),
                "_match_type": ent.get("match_type"),
                "_source": ent.get("source"),
            })

        if not entities_json:
            continue  # all entities dropped due to PHI overlap — skip sentence

        sentence_records.append({
            "label_id": label_id,
            "candidate_id": candidate_id,
            "encounter_id": encounter_id,
            "patient_id": rec.get("patient_id") or ann.get("patient_id") or "",
            "encounter_date": rec.get("encounter_date") or "",
            "sentence_id": sid,
            "text": deid_sent_text,   # de-identified sentence stored in KG
            "phi_redacted": bool(phi_types),
            "phi_types": phi_types,
            "entities": entities_json,
            "schema_version": SCHEMA_VERSION,
            "source": SOURCE,
        })

    skipped = [e.get("id") for e in invalid]
    return {
        "encounter_id": encounter_id,
        "sentence_records": sentence_records,
        "skipped_entities": skipped,
        "phi_drop_count": phi_drop_count,
    }


def _strip_metadata_for_kg(entities: list[dict]) -> list[dict]:
    """Remove _ prefixed fields before writing to KG."""
    cleaned = []
    for e in entities:
        cleaned.append({k: v for k, v in e.items() if not k.startswith("_")})
    return cleaned


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GoldLabel records from cohort annotations")
    parser.add_argument("--dry-run", action="store_true", help="Skip SNOMED API calls")
    parser.add_argument("--patient", help="Process only this patient ID")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    term_client = TerminologyClient(
        base_url=os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001"),
        timeout=30.0,
    )
    resolver = SnomedResolver(term_client, search_limit=6)

    files = sorted(ANNOTATED_DIR.glob("*.jsonl"))
    if args.patient:
        files = [f for f in files if args.patient in f.name]

    all_records: list[dict] = []
    needs_review_rows: list[dict] = []
    total_entities = 0
    auto_accept_count = 0
    needs_review_count = 0
    no_match_count = 0
    skipped_span_count = 0
    phi_drop_count = 0
    dry_run_count = 0
    processed_encounters = 0

    for f in files:
        patient_id = f.stem
        logger.info("Processing %s", patient_id)
        lines = f.read_text().splitlines()

        for line in lines:
            if not line.strip():
                continue
            rec = json.loads(line)
            ann = rec.get("annotation") or {}
            if not (ann.get("entities")):
                continue

            result = process_encounter(rec, resolver, dry_run=args.dry_run)
            processed_encounters += 1
            skipped_span_count += len(result["skipped_entities"])
            phi_drop_count += result.get("phi_drop_count", 0)

            for sr in result["sentence_records"]:
                all_records.append(sr)
                for ent in sr["entities"]:
                    total_entities += 1
                    status = ent.get("_resolution_status", "unknown")
                    if status == "auto_accept":
                        auto_accept_count += 1
                    elif status == "needs_review":
                        needs_review_count += 1
                        # Write to review CSV
                        for cand_i, cand in enumerate(ent.get("_resolution_candidates", [])[:6]):
                            needs_review_rows.append({
                                "label_id": sr["label_id"],
                                "encounter_id": sr["encounter_id"],
                                "sentence_id": sr["sentence_id"],
                                "entity_id": ent.get("_entity_id"),
                                "quote": ent["text"],
                                "label": ent["label"],
                                "assertion": ent["assertion"],
                                "expected_snomed_tag": ent.get("_expected_snomed_tag"),
                                "candidate_rank": cand_i + 1,
                                "concept_id": cand.get("concept_id"),
                                "preferred_term": cand.get("preferred_term"),
                                "semantic_tag": cand.get("semantic_tag"),
                                "score": cand.get("score"),
                                "had_exact_match": cand.get("had_exact_match"),
                                "lexical_raw": cand.get("lexical_raw"),
                                # Human fills in: accepted = yes/no
                                "accepted": "",
                            })
                    elif status == "no_match":
                        no_match_count += 1
                    elif status == "dry_run":
                        dry_run_count += 1

    # Write all records (with metadata) for downstream apply script
    records_path = OUTPUT_DIR / f"gold_label_records_{ts}.jsonl"
    with records_path.open("w") as fh:
        for rec in all_records:
            fh.write(json.dumps(rec) + "\n")
    logger.info("Wrote %d sentence records to %s", len(all_records), records_path)

    # Write KG-ready records (metadata stripped)
    kg_path = OUTPUT_DIR / f"gold_label_records_kg_ready_{ts}.jsonl"
    with kg_path.open("w") as fh:
        for rec in all_records:
            kg_rec = {k: v for k, v in rec.items() if k != "entities"}
            kg_rec["entities_json"] = json.dumps(
                _strip_metadata_for_kg(rec["entities"]),
                ensure_ascii=False,
            )
            fh.write(json.dumps(kg_rec) + "\n")

    # Write needs_review CSV
    if needs_review_rows:
        review_path = OUTPUT_DIR / f"needs_review_{ts}.csv"
        with review_path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(needs_review_rows[0].keys()))
            writer.writeheader()
            writer.writerows(needs_review_rows)
        logger.info("Wrote %d rows to %s", len(needs_review_rows), review_path)

    # Summary
    summary = {
        "generated_at": ts,
        "dry_run": args.dry_run,
        "processed_encounters": processed_encounters,
        "total_entities": total_entities,
        "skipped_span_failures": skipped_span_count,
        "auto_accept": auto_accept_count,
        "needs_review": needs_review_count,
        "no_match": no_match_count,
        "dry_run_skipped": dry_run_count,
        "sentence_records": len(all_records),
        "phi_dropped_entities": phi_drop_count,
        "auto_accept_pct": round(100 * auto_accept_count / max(1, total_entities), 1),
        "outputs": {
            "records": str(records_path),
            "kg_ready": str(kg_path),
        },
    }
    summary_path = OUTPUT_DIR / f"run_summary_{ts}.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    logger.info("=== DONE ===")
    logger.info("Encounters processed: %d", processed_encounters)
    logger.info("Total entities:       %d", total_entities)
    logger.info("  auto_accept:        %d (%.1f%%)", auto_accept_count, summary["auto_accept_pct"])
    logger.info("  needs_review:       %d", needs_review_count)
    logger.info("  no_match:           %d", no_match_count)
    logger.info("  span failures:      %d", skipped_span_count)
    logger.info("  phi overlaps:       %d (entity quote touched a redacted token)", phi_drop_count)
    logger.info("Sentence records:     %d", len(all_records))


if __name__ == "__main__":
    main()
