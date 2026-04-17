#!/usr/bin/env python3
"""Re-validate a backfill proposals JSONL against SNOMED.

Why this script exists
----------------------
`scripts/backfill_gold_lab_triples.py` produces a JSONL of proposed
GoldLabel additions (and extensions) using the LLM extractor + the
production post-processing stack. The LLM can be over-eager and
propose surface spans that:

- have NO sensible SNOMED code (e.g. raw lab values "5.14 10^9/L"),
- have a top-1 candidate with the WRONG semantic tag (e.g. fluoxetine
  -> top hit is "medicinal_product" but the LLM said "substance"),
- have a top-1 candidate that drifts semantically from the surface
  (e.g. "Co-existing benign naevus: Present" -> "Melanocytic nevus
  of skin").

Auto-applying these would teach the NER model to emit spans the
downstream coder cannot represent. This script re-validates each
proposed addition against the production terminology service and
splits the input into:

    accepted   - kept additions with attached SNOMED concept_id /
                 preferred term / surface_match score / resolver_score.
    rejected   - dropped additions with a structured reason and the
                 closest candidate (if any) for human review.

Outputs
-------
    <input>.validated.jsonl   - one record per input row, with
                                 "additions" rewritten to only the
                                 accepted ones, and a new
                                 "rejected_additions" array carrying
                                 the structured reasons.
    <input>.validated.summary.json  - aggregate counts.

Examples
--------
    .venv/bin/python scripts/validate_backfill_snomed.py \\
        data/backfill/gold_label_proposals_20260417T130126Z.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config")
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets")

from libs.terminology.client import TerminologyClient  # noqa: E402
from scripts.lib.gold_label_snomed_check import (  # noqa: E402
    ValidationResult,
    validate_proposals_batch,
)

logger = logging.getLogger("validate_backfill_snomed")


def main() -> int:
    args = _parse_args()
    _configure_logging(args.verbose)

    in_path = Path(args.input)
    if not in_path.exists():
        logger.error("Input file not found: %s", in_path)
        return 2
    out_path = in_path.with_suffix(in_path.suffix + ".validated.jsonl")
    summary_path = in_path.with_suffix(in_path.suffix + ".validated.summary.json")

    rows = _load_jsonl(in_path)
    logger.info("Loaded %d records from %s", len(rows), in_path)

    pairs = _collect_unique_pairs(rows)
    logger.info(
        "Validating %d unique (surface, label) pairs against SNOMED at %s",
        len(pairs),
        TerminologyClient().__dict__.get("_base_url", "<default>"),
    )

    started = time.time()
    client = TerminologyClient(timeout=float(args.timeout))
    validations = validate_proposals_batch(
        pairs,
        client,
        min_surface_match=float(args.min_surface),
        semantic_vector_floor=float(args.semantic_vector_floor),
        semantic_min_surface=float(args.semantic_min_surface),
        top_n=int(args.top_n),
    )
    logger.info(
        "Resolved %d pairs in %.1fs (avg %.2fs / pair)",
        len(validations),
        time.time() - started,
        (time.time() - started) / max(1, len(validations)),
    )

    summary = _write_outputs(rows, validations, out_path, summary_path)
    logger.info("Wrote %s", out_path)
    logger.info("Wrote %s", summary_path)
    print(json.dumps(summary, indent=2))
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Re-validate backfill proposals against SNOMED.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("input", help="Path to a *.jsonl produced by backfill_gold_lab_triples.")
    p.add_argument("--min-surface", type=float, default=0.7,
                   help="Minimum surface-match (containment) for the SURFACE branch.")
    p.add_argument("--semantic-vector-floor", type=float, default=0.92,
                   help="Minimum vector_raw cosine for the SEMANTIC branch.")
    p.add_argument("--semantic-min-surface", type=float, default=0.66,
                   help="Minimum surface-match for the SEMANTIC branch (sanity guard).")
    p.add_argument("--top-n", type=int, default=10,
                   help="Walk this many candidates when picking the best match.")
    p.add_argument("--timeout", type=float, default=30.0,
                   help="Per-resolver-call HTTP timeout in seconds.")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args()


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rows.append(json.loads(raw))
            except json.JSONDecodeError:
                logger.warning("Skipping malformed line in %s", path)
    return rows


def _collect_unique_pairs(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for row in rows:
        for entity in row.get("additions") or []:
            text = str(entity.get("text") or "").strip()
            label = str(entity.get("label") or "").strip()
            if not text or not label:
                continue
            key = (text, label)
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
    return out


def _write_outputs(
    rows: list[dict[str, Any]],
    validations: dict[tuple[str, str], ValidationResult],
    out_path: Path,
    summary_path: Path,
) -> dict[str, Any]:
    counts = {
        "input_records": len(rows),
        "input_additions": 0,
        "kept_additions": 0,
        "dropped_additions": 0,
        "kept_with_synonym_tag": 0,
        "records_with_kept_additions": 0,
        "records_unchanged": 0,
        "records_emptied": 0,
        "drop_reasons": {},
        "kept_by_label": {},
        "dropped_by_label": {},
    }

    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            additions = row.get("additions") or []
            counts["input_additions"] += len(additions)
            kept: list[dict[str, Any]] = []
            rejected: list[dict[str, Any]] = []
            for entity in additions:
                text = str(entity.get("text") or "").strip()
                label = str(entity.get("label") or "").strip()
                key = (text, label)
                vr = validations.get(key)
                if vr is None:
                    rejected.append(
                        {**entity, "validation": {"accepted": False,
                                                   "reason": "not_validated"}}
                    )
                    continue
                if vr.accepted:
                    enriched = dict(entity)
                    enriched.update(
                        snomed_concept_id=vr.concept_id,
                        snomed_term=vr.snomed_term,
                        snomed_semantic_tag=vr.semantic_tag,
                        resolver_score=round(vr.resolver_score, 3),
                        surface_match=round(vr.surface_match, 3),
                        tag_synonym=vr.tag_synonym,
                    )
                    kept.append(enriched)
                    counts["kept_additions"] += 1
                    if vr.tag_synonym:
                        counts["kept_with_synonym_tag"] += 1
                    counts["kept_by_label"][label] = (
                        counts["kept_by_label"].get(label, 0) + 1
                    )
                else:
                    val_payload = vr.to_dict()
                    if vr.debug:
                        val_payload.update(vr.debug)
                    rejected.append(
                        {**entity, "validation": val_payload}
                    )
                    counts["dropped_additions"] += 1
                    counts["drop_reasons"][vr.reason] = (
                        counts["drop_reasons"].get(vr.reason, 0) + 1
                    )
                    counts["dropped_by_label"][label] = (
                        counts["dropped_by_label"].get(label, 0) + 1
                    )

            new_row = dict(row)
            new_row["additions"] = kept
            new_row["rejected_additions"] = rejected
            new_row["validation_summary"] = {
                "input_additions": len(additions),
                "kept_additions": len(kept),
                "dropped_additions": len(rejected),
            }
            fh.write(json.dumps(new_row, default=str) + "\n")

            if kept and not rejected:
                counts["records_unchanged"] += 1 if len(kept) == len(additions) else 0
            if kept:
                counts["records_with_kept_additions"] += 1
            if additions and not kept:
                counts["records_emptied"] += 1

    summary_path.write_text(json.dumps(counts, indent=2), encoding="utf-8")
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
