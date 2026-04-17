#!/usr/bin/env python3
"""Backfill missing entities on existing GoldLabels.

Why this script exists
----------------------
The gold-label training set in the Knowledge Graph has uneven entity
coverage. An audit on 2026-04-17 showed:

  total GoldLabels                          946
  has_procedure                             405 (43%)
  has_observable_entity                     152 (16%)
  has_finding                               457 (48%)
  full triple (procedure+observable+finding) 37 (3.9%)
  text matches lab grammar                  280 (30%)

Most of the gap is text that DOES contain procedures / observables /
findings (and disorders, in many cases) but where only a subset was
labelled by the original curator. A previous backfill pass attempted to
add observables only and missed every other entity type that appeared
in the same text. This tool fixes both issues:

1. It re-extracts entities from each label's text using the
   PRODUCTION extraction stack (LLM Haiku + post-processing including
   the new layer_3b lab triple recovery), so every entity type the
   runtime would emit is captured.

2. It computes a per-label diff vs the existing entities and writes
   proposed additions to a JSONL audit file. Nothing is written to
   Neo4j unless --apply is passed AND a human reviewer has the audit
   file in front of them.

Cost / safety defaults
----------------------
- Default mode is --recover-only (deterministic, no LLM cost).
- Default action is --dry-run (writes JSONL only).
- --limit defaults to 25 so a single accidental run cannot rack up
  large LLM bills.
- --apply MUST be combined with --confirm-apply to write to Neo4j.

Output
------
data/backfill/gold_label_proposals_<UTC-timestamp>.jsonl
data/backfill/gold_label_proposals_<UTC-timestamp>.summary.json

Usage
-----
    # Cheapest preview (deterministic, dry-run, 25 labels, lab grammar only)
    .venv/bin/python scripts/backfill_gold_lab_triples.py

    # Full LLM re-extraction on a small sample
    .venv/bin/python scripts/backfill_gold_lab_triples.py \\
        --with-llm --limit 10

    # Apply approved proposals to Neo4j (after review)
    .venv/bin/python scripts/backfill_gold_lab_triples.py \\
        --with-llm --limit 10 --apply --confirm-apply
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config")
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets")

from scripts.lib.gold_label_backfill import (  # noqa: E402
    DiffResult,
    diff_entities,
    merge_into_existing,
)
from scripts.lib.gold_label_extractors import (  # noqa: E402
    ExtractorBundle,
    extract_deterministic,
    extract_with_llm,
)

logger = logging.getLogger("backfill")


_LAB_GRAMMAR_RE = re.compile(
    r"[A-Za-z][\w \-/']{2,80}"
    r"\s*\([0-9A-Za-z.]+\)"  # Read/CTV3 code in parens REQUIRED
    r"\s*[<>]?\s*\d+(?:[.,]\d+)?\s*"
    r"[%a-zA-Z][\w/\^\.\-]*"
)


def main() -> int:
    args = _parse_args()
    _configure_logging(args.verbose)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    proposals_path = out_dir / f"gold_label_proposals_{timestamp}.jsonl"
    summary_path = out_dir / f"gold_label_proposals_{timestamp}.summary.json"

    rows = _fetch_labels(args)
    if not rows:
        logger.info("No GoldLabels matched filter; nothing to do")
        return 0

    bundle = _build_bundle(args.with_llm)
    summary = _process_rows(rows, args, bundle, proposals_path)

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("Wrote proposals: %s", proposals_path)
    logger.info("Wrote summary:   %s", summary_path)
    print(json.dumps(summary, indent=2))
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill missing entities on existing GoldLabels.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--label-filter",
        choices=["lab-grammar", "all"],
        default="lab-grammar",
        help="Which GoldLabels to consider (text-pattern filter).",
    )
    p.add_argument(
        "--candidate-status",
        choices=["completed", "pending", "any"],
        default="completed",
        help=(
            "Filter by linked TrainingCandidate.status. 'completed' is the"
            " set of finalised gold labels; 'pending' is in-progress;"
            " 'any' includes both."
        ),
    )
    p.add_argument("--limit", type=int, default=25, help="Maximum labels to process.")
    p.add_argument(
        "--with-llm",
        action="store_true",
        help="Use LLM Haiku extractor (costs tokens). Default is deterministic-only.",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write merged entities back to Neo4j. Requires --confirm-apply.",
    )
    p.add_argument(
        "--confirm-apply",
        action="store_true",
        help="Second-factor confirmation required to actually write to Neo4j.",
    )
    p.add_argument(
        "--apply-extensions",
        action="store_true",
        help=(
            "Also apply 'extension' diffs (longer span replacing existing"
            " short span)."
        ),
    )
    p.add_argument(
        "--output-dir",
        default=str(_REPO_ROOT / "data" / "backfill"),
        help="Where to write JSONL + summary.",
    )
    p.add_argument(
        "--source",
        default=None,
        help="Optional GoldLabel.source equality filter (e.g. 'manual').",
    )
    p.add_argument(
        "--exclude-source",
        action="append",
        default=["manual_gold_draft", "synthetic"],
        help=(
            "Repeatable. GoldLabel.source values to skip. Defaults skip"
            " drafts + synthetic test data."
        ),
    )
    p.add_argument(
        "--include-all-sources",
        action="store_true",
        help=(
            "Override --exclude-source defaults and include every source"
            " (drafts + synthetic). Use when verifying ALL HITL-completed"
            " labels regardless of provenance."
        ),
    )
    p.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "Number of parallel workers for LLM mode. Bedrock Haiku"
            " tolerates 4-8 comfortably."
        ),
    )
    p.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Emit a progress line every N labels processed.",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging.",
    )
    args = p.parse_args()
    if args.apply and not args.confirm_apply:
        p.error("--apply requires --confirm-apply")
    if args.include_all_sources:
        args.exclude_source = []
    if args.workers < 1:
        p.error("--workers must be >= 1")
    return args


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _build_bundle(with_llm: bool) -> ExtractorBundle:
    if not with_llm:
        return ExtractorBundle(available=False)
    bundle = ExtractorBundle.build()
    if not bundle.available:
        logger.warning(
            "LLM extractor not available; --with-llm will fall back to deterministic"
        )
    return bundle


def _fetch_labels(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Pull GoldLabel rows from the Knowledge Graph honouring filters."""
    from libs.neo4j_client.client import KnowledgeGraphClient

    where_clauses = ["g.entities_json IS NOT NULL", "g.text IS NOT NULL"]
    params: dict[str, Any] = {}

    if args.candidate_status != "any":
        where_clauses.append(
            "EXISTS { MATCH (tc:TrainingCandidate)-[:PRODUCED]->(g)"
            " WHERE tc.status = $candidate_status }"
        )
        params["candidate_status"] = args.candidate_status

    if args.label_filter == "lab-grammar":
        # Server-side coarse prefilter: require a Read/CTV3-code-in-parens
        # pattern (e.g. "(42X..)" / "(XE2pb)") so we don't fan out to
        # medication prose. Client-side regex re-checks the full grammar.
        where_clauses.append(
            "(g.text =~ '(?s).*\\\\([0-9A-Za-z.]+\\\\)[^\\\\n]*\\\\d+.*')"
        )
    if args.source:
        where_clauses.append("g.source = $source")
        params["source"] = args.source
    if args.exclude_source:
        where_clauses.append("NOT (g.source IN $exclude_source)")
        params["exclude_source"] = list(args.exclude_source)

    # Over-fetch when we'll re-filter client-side, but cap to the limit.
    fetch_cap = args.limit * 4 if args.label_filter == "lab-grammar" else args.limit
    params["limit"] = int(fetch_cap)
    cypher = f"""
    MATCH (g:GoldLabel)
    WHERE {' AND '.join(where_clauses)}
    RETURN g.label_id AS label_id,
           g.text AS text,
           g.entities_json AS entities_json,
           g.source AS source
    LIMIT $limit
    """
    client = KnowledgeGraphClient()
    with client.session() as session:
        rows = [dict(r) for r in session.run(cypher, params)]
    if args.label_filter == "lab-grammar":
        rows = [r for r in rows if _LAB_GRAMMAR_RE.search(r.get("text") or "")]
    return rows[: args.limit]


def _process_rows(
    rows: list[dict[str, Any]],
    args: argparse.Namespace,
    bundle: ExtractorBundle,
    proposals_path: Path,
) -> dict[str, Any]:
    """Run extraction + diff for each label, write JSONL, return summary.

    Threaded when --workers > 1. Bedrock Haiku is the bottleneck so a
    ThreadPoolExecutor (I/O-bound) is sufficient. JSONL writes and
    counter updates are serialised behind a lock so the output file
    stays one-line-per-label.
    """
    started = time.time()
    counts = {
        "labels_seen": 0,
        "labels_with_additions": 0,
        "labels_with_extensions": 0,
        "additions_total": 0,
        "extensions_total": 0,
        "applied": 0,
        "errors": 0,
    }
    by_label: dict[str, int] = {}
    write_lock = threading.Lock()
    total = len(rows)
    progress_every = max(1, int(args.progress_every))
    workers = max(1, int(args.workers))

    logger.info(
        "Processing %d labels with %d worker(s), mode=%s, apply=%s",
        total,
        workers,
        "with_llm" if args.with_llm else "recover_only",
        args.apply,
    )

    with proposals_path.open("w", encoding="utf-8") as fh:

        def _handle(row: dict[str, Any]) -> None:
            label_id = row.get("label_id")
            try:
                diff = _process_one(row, args, bundle)
            except Exception:
                with write_lock:
                    counts["errors"] += 1
                logger.exception("Failed to process label_id=%s", label_id)
                return
            line = json.dumps(_proposal_record(row, diff, args), default=str)
            with write_lock:
                counts["labels_seen"] += 1
                _record_counts(diff, counts, by_label)
                fh.write(line + "\n")
                fh.flush()
                seen = counts["labels_seen"]
            if args.apply and (
                diff.additions or (args.apply_extensions and diff.extensions)
            ):
                _apply_one(row, diff, args, counts, write_lock)
            if seen % progress_every == 0 or seen == total:
                logger.info(
                    "progress %d/%d (additions_so_far=%d, errors=%d)",
                    seen,
                    total,
                    counts["additions_total"],
                    counts["errors"],
                )

        if workers == 1:
            for row in rows:
                _handle(row)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_handle, row) for row in rows]
                for fut in as_completed(futures):
                    fut.result()

    counts["elapsed_sec"] = round(time.time() - started, 2)
    counts["additions_by_label"] = by_label
    counts["mode"] = "with_llm" if args.with_llm else "recover_only"
    counts["dry_run"] = not args.apply
    counts["workers"] = workers
    return counts


def _process_one(
    row: dict[str, Any],
    args: argparse.Namespace,
    bundle: ExtractorBundle,
) -> DiffResult:
    label_id = str(row.get("label_id") or "")
    text = str(row.get("text") or "")
    try:
        existing = json.loads(row.get("entities_json") or "[]")
    except json.JSONDecodeError:
        existing = []

    if args.with_llm:
        proposed = extract_with_llm(text, bundle)
    else:
        proposed = extract_deterministic(text)

    return diff_entities(label_id, text, existing, proposed)


def _record_counts(
    diff: DiffResult,
    counts: dict[str, int],
    by_label: dict[str, int],
) -> None:
    if diff.additions:
        counts["labels_with_additions"] += 1
        counts["additions_total"] += len(diff.additions)
        for entity in diff.additions:
            by_label[entity["label"]] = by_label.get(entity["label"], 0) + 1
    if diff.extensions:
        counts["labels_with_extensions"] += 1
        counts["extensions_total"] += len(diff.extensions)


def _proposal_record(
    row: dict[str, Any],
    diff: DiffResult,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "label_id": diff.label_id,
        "source": row.get("source"),
        "text": diff.text,
        "existing_count": diff.existing_count,
        "proposed_count": diff.proposed_count,
        "additions": diff.additions,
        "extensions": diff.extensions,
        "overlaps_count": len(diff.overlaps),
        "mode": "with_llm" if args.with_llm else "recover_only",
    }


def _apply_one(
    row: dict[str, Any],
    diff: DiffResult,
    args: argparse.Namespace,
    counts: dict[str, int],
    write_lock: threading.Lock | None = None,
) -> None:
    """Write merged entities back to Neo4j via the canonical updater."""
    from libs.cypher.gold_label_queries import UPDATE_GOLD_LABEL_ENTITIES
    from libs.neo4j_client.client import KnowledgeGraphClient

    try:
        existing = json.loads(row.get("entities_json") or "[]")
    except json.JSONDecodeError:
        existing = []
    merged = merge_into_existing(
        existing, diff, apply_extensions=args.apply_extensions
    )

    client = KnowledgeGraphClient()
    with client.session() as session:
        session.run(
            UPDATE_GOLD_LABEL_ENTITIES,
            {
                "label_id": diff.label_id,
                "entities_json": json.dumps(merged),
            },
        )
    if write_lock is not None:
        with write_lock:
            counts["applied"] += 1
    else:
        counts["applied"] += 1
    logger.info(
        "Applied %d additions to label_id=%s",
        len(diff.additions),
        diff.label_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
