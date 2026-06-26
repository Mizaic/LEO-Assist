#!/usr/bin/env python3
"""Annotate the cancer cohort encounters using the multistep LangGraph pipeline.

Reads per-patient JSONL files produced by
``scripts/cohort/export_cancer_cohort_for_annotation.py`` and writes
annotated JSONL to ``data/cancer_cohort_annotated/``.

Each output line is the encounter row enriched with:
    "annotation": {
        "entities":     [...],
        "relations":    [...],
        "qa_drops":     [...],
        "errors":       [...],
        "encounter_class": "NARRATIVE",
        "llm_calls":    1,
        "total_input_tokens":  1234,
        "total_output_tokens": 456,
        "total_cache_read_tokens": 789,
        "annotation_complete": true
    }

Usage:
    # Dry run: classify + deterministic extraction only (no LLM calls)
    python3 scripts/cohort/annotate_cancer_cohort.py --dry-run

    # Single patient
    python3 scripts/cohort/annotate_cancer_cohort.py --patient 9990000001

    # Full cohort
    python3 scripts/cohort/annotate_cancer_cohort.py

    # Custom parallelism
    python3 scripts/cohort/annotate_cancer_cohort.py --workers 16
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Force a global socket timeout so that any SSL/TCP read blocked inside a
# worker thread cannot stall indefinitely.  Without this, botocore's
# Config(read_timeout=...) can fail to propagate when boto3 is first called
# from a nested ThreadPoolExecutor worker thread.
socket.setdefaulttimeout(120)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("annotate_cancer_cohort")

DEFAULT_INPUT_DIR  = ROOT / "data" / "cancer_cohort"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "cancer_cohort_annotated"
DEFAULT_WORKERS    = 8
MAX_RETRIES        = 2


def load_patient_encounters(
    patient_file: Path,
) -> list[dict[str, Any]]:
    rows = []
    with patient_file.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dry_run_annotate(encounter_row: dict[str, Any]) -> dict[str, Any]:
    """Classify + deterministic extraction only; no LLM calls."""
    from libs.cohort_annotation.classifier import classify
    from libs.cohort_annotation.deterministic_extractor import extract_structured_entities

    text = encounter_row.get("text") or ""
    flags = encounter_row.get("encounter_flags") or ""
    sentences = encounter_row.get("sentences") or []
    ec = classify(text, flags)
    entities = []
    if ec.value != "EMPTY":
        entities = extract_structured_entities(sentences)

    return {
        "entities":              entities,
        "relations":             [],
        "qa_drops":              [],
        "errors":                [],
        "encounter_class":       ec.value,
        "llm_calls":             0,
        "total_input_tokens":    0,
        "total_output_tokens":   0,
        "total_cache_read_tokens": 0,
        "annotation_complete":   True,
    }


def _cost_usd(input_tokens: int, output_tokens: int, cache_tokens: int = 0) -> float:
    """Calculate cost using Haiku 4.5 EU cross-region rates ($1.10/$5.50 per MTok)."""
    from libs.llm_usage import LLMCostConfig, LLMUsage
    cfg = LLMCostConfig.for_tier("small")
    return LLMUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cache_tokens,
    ).cost_usd(cfg)


def build_run_summary(
    results_by_patient: dict[str, list[dict[str, Any]]],
    elapsed_s: float,
    input_dir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    class_counts: dict[str, int] = defaultdict(int)
    label_counts: dict[str, int] = defaultdict(int)
    rel_type_counts: dict[str, int] = defaultdict(int)
    drop_reason_counts: dict[str, int] = defaultdict(int)
    total_encounters = 0
    total_entities   = 0
    total_relations  = 0
    total_drops      = 0
    total_errors     = 0
    total_llm_calls  = 0
    total_in_tok     = 0
    total_out_tok    = 0
    total_cache_tok  = 0

    for pid, rows in results_by_patient.items():
        for row in rows:
            ann = row.get("annotation") or {}
            total_encounters += 1
            class_counts[ann.get("encounter_class", "UNKNOWN")] += 1
            for e in ann.get("entities") or []:
                total_entities += 1
                for lbl in e.get("labels") or []:
                    label_counts[lbl.upper()] += 1
            for r in ann.get("relations") or []:
                total_relations += 1
                rel_type_counts[r.get("type", "?").lower()] += 1
            for d in ann.get("qa_drops") or []:
                total_drops += 1
                reason = d.get("reason") or "unknown"
                drop_reason_counts[reason] += 1
            total_errors   += len(ann.get("errors") or [])
            total_llm_calls += ann.get("llm_calls") or 0
            total_in_tok    += ann.get("total_input_tokens") or 0
            total_out_tok   += ann.get("total_output_tokens") or 0
            total_cache_tok += ann.get("total_cache_read_tokens") or 0

    verbatim_drop = drop_reason_counts.get("quote_not_found_in_sentence", 0)
    verbatim_drop_rate = (
        round(verbatim_drop / max(1, total_entities + verbatim_drop), 4)
        if total_entities or verbatim_drop
        else 0.0
    )

    cost = _cost_usd(total_in_tok, total_out_tok, total_cache_tok)

    return {
        "generated_at":        datetime.now().strftime("%Y%m%dT%H%M%SZ"),
        "dry_run":             dry_run,
        "input_dir":           str(input_dir.resolve().relative_to(ROOT) if input_dir.resolve().is_relative_to(ROOT) else input_dir),
        "elapsed_s":           round(elapsed_s, 1),
        "totals": {
            "patients":         len(results_by_patient),
            "encounters":       total_encounters,
            "entities":         total_entities,
            "relations":        total_relations,
            "qa_drops":         total_drops,
            "errors":           total_errors,
            "llm_calls":        total_llm_calls,
            "input_tokens":     total_in_tok,
            "output_tokens":    total_out_tok,
            "cache_read_tokens": total_cache_tok,
            "cost_usd":         round(cost, 4),
        },
        "verbatim_drop_rate":  verbatim_drop_rate,
        "encounter_class_counts": dict(class_counts),
        "label_counts":           dict(label_counts),
        "relation_type_counts":   dict(rel_type_counts),
        "drop_reason_counts":     dict(drop_reason_counts),
    }


def annotate_patient(
    patient_file: Path,
    output_dir: Path,
    dry_run: bool,
    workers: int,
    lock: threading.Lock,
    progress: dict[str, int],
    total_patients: int,
) -> list[dict[str, Any]]:
    pid = patient_file.stem[1:]  # strip leading 'p'

    out_path = output_dir / f"p{pid}.jsonl"
    if out_path.exists():
        with lock:
            progress["done"] += 1
            done = progress["done"]
        logger.info("[%d/%d] p%s already done — skipping", done, total_patients, pid)
        existing = []
        with out_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    existing.append(json.loads(line))
        return existing

    rows = load_patient_encounters(patient_file)
    if not rows:
        return []

    annotated_rows: list[dict[str, Any]] = []

    if dry_run:
        for row in rows:
            annotation = dry_run_annotate(row)
            row["annotation"] = annotation
            annotated_rows.append(row)
    else:
        from libs.cohort_annotation.runner import annotate_batch

        def cb(p_id: str, e_id: str) -> None:
            logger.info("  enc done  p%s / %s", p_id, e_id)

        logger.info("annotating p%s — %d encounters", pid, len(rows))
        results = annotate_batch(rows, max_workers=min(workers, len(rows)), progress_callback=cb)
        for row, result in zip(rows, results):
            row["annotation"] = result.to_dict()
            annotated_rows.append(row)

    with out_path.open("w") as f:
        for row in annotated_rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")

    enc_count  = len(annotated_rows)
    ent_count  = sum(len((r.get("annotation") or {}).get("entities") or []) for r in annotated_rows)
    llm_calls  = sum((r.get("annotation") or {}).get("llm_calls") or 0 for r in annotated_rows)
    err_count  = sum(len((r.get("annotation") or {}).get("errors") or []) for r in annotated_rows)
    in_tok     = sum((r.get("annotation") or {}).get("total_input_tokens") or 0 for r in annotated_rows)
    out_tok    = sum((r.get("annotation") or {}).get("total_output_tokens") or 0 for r in annotated_rows)
    cache_tok  = sum((r.get("annotation") or {}).get("total_cache_read_tokens") or 0 for r in annotated_rows)
    pat_cost   = _cost_usd(in_tok, out_tok, cache_tok)

    with lock:
        progress["done"]          += 1
        progress["run_in_tok"]    += in_tok
        progress["run_out_tok"]   += out_tok
        progress["run_cache_tok"] += cache_tok
        done          = progress["done"]
        run_in_tok    = progress["run_in_tok"]
        run_out_tok   = progress["run_out_tok"]
        run_cache_tok = progress["run_cache_tok"]

    run_cost = _cost_usd(run_in_tok, run_out_tok, run_cache_tok)
    logger.info(
        "[%d/%d] p%s -> %d encs, %d entities, %d llm_calls, %d errors, "
        "%dk in / %dk out tokens, $%.4f",
        done, total_patients, pid, enc_count, ent_count, llm_calls, err_count,
        in_tok // 1000, out_tok // 1000, pat_cost,
    )
    logger.info(
        "  TOTAL [%d/%d patients]  in: %dk  out: %dk  cache: %dk  running cost: $%.4f",
        done, total_patients,
        run_in_tok // 1000, run_out_tok // 1000, run_cache_tok // 1000, run_cost,
    )
    return annotated_rows


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--input-dir",  type=Path, default=DEFAULT_INPUT_DIR)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--patient", action="append", dest="patients",
                   help="Limit to specific patient ids (repeatable).")
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                   help=(
                       "Concurrent encounters per patient. "
                       "Keep low (1-2) to avoid Bedrock throttling. "
                       f"Default {DEFAULT_WORKERS}."
                   ))
    p.add_argument("--patient-workers", type=int, default=0,
                   help=(
                       "Patients processed in parallel (outer pool). "
                       "Defaults to --workers when not set. "
                       "Total Bedrock concurrency = patient-workers × workers."
                   ))
    p.add_argument("--dry-run", action="store_true",
                   help="Classify + deterministic extraction only, no LLM calls.")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    patient_files = sorted(args.input_dir.glob("p*.jsonl"))
    if args.patients:
        wanted = {str(p) for p in args.patients}
        patient_files = [f for f in patient_files if f.stem[1:] in wanted]

    if not patient_files:
        logger.error("no patient files found in %s", args.input_dir)
        return 1

    args.input_dir  = args.input_dir.resolve()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    patient_workers = args.patient_workers if args.patient_workers > 0 else args.workers
    logger.info(
        "annotating %d patients, dry_run=%s, patient_workers=%d, enc_workers=%d "
        "(total_bedrock_concurrency=%d)",
        len(patient_files), args.dry_run,
        patient_workers, args.workers,
        patient_workers * args.workers,
    )

    started = datetime.now()
    lock: threading.Lock = threading.Lock()
    progress: dict[str, int] = {
        "done": 0, "run_in_tok": 0, "run_out_tok": 0, "run_cache_tok": 0,
    }
    results_by_patient: dict[str, list[dict[str, Any]]] = {}

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=min(patient_workers, len(patient_files))) as pool:
        futures = {
            pool.submit(
                annotate_patient,
                pf, args.output_dir, args.dry_run,
                args.workers, lock, progress, len(patient_files),
            ): pf.stem[1:]
            for pf in patient_files
        }
        for fut in as_completed(futures):
            pid = futures[fut]
            try:
                results_by_patient[pid] = fut.result()
            except Exception as exc:
                logger.error("patient %s FAILED: %s", pid, exc)
                results_by_patient[pid] = []

    elapsed_s = (datetime.now() - started).total_seconds()
    summary = build_run_summary(results_by_patient, elapsed_s, args.input_dir, args.dry_run)

    summary_path = args.output_dir / "cohort_run_summary.json"
    with summary_path.open("w") as f:
        json.dump(summary, f, indent=2)

    totals = summary["totals"]
    logger.info(
        "DONE  -> %d patients, %d encs, %d entities, %d relations, "
        "%d drops (verbatim_drop_rate=%.2f%%), %d llm_calls, %.1fs",
        totals["patients"], totals["encounters"], totals["entities"],
        totals["relations"], totals["qa_drops"],
        summary["verbatim_drop_rate"] * 100,
        totals["llm_calls"], elapsed_s,
    )
    logger.info(
        "LLM usage  -> input: %dk tokens  output: %dk tokens  "
        "cache_read: %dk tokens  total_cost: $%.4f  "
        "(Haiku 4.5 EU: $1.10/MTok in, $5.50/MTok out)",
        totals["input_tokens"] // 1000,
        totals["output_tokens"] // 1000,
        totals["cache_read_tokens"] // 1000,
        totals["cost_usd"],
    )
    try:
        summary_rel = summary_path.relative_to(ROOT)
    except ValueError:
        summary_rel = summary_path
    logger.info("summary: %s", summary_rel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
