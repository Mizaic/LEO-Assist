#!/usr/bin/env python3
"""Confidence-gated auto-prune for non-completed TrainingCandidate rows.

CLI mirror of POST /training/candidates/prune/preview and
POST /training/candidates/prune/execute (DI-LEO-AI-196 / UN-LEO-AI-083).
Defaults to dry-run; --apply is required to actually delete.

Examples
--------
    # Dry-run with default floors against the current backlog:
    .venv/bin/python scripts/prune_low_confidence_candidates.py

    # Dry-run with a tighter surface floor:
    .venv/bin/python scripts/prune_low_confidence_candidates.py \\
        --min-surface-match 0.8

    # Execute (after reviewing the dry-run JSON):
    .venv/bin/python scripts/prune_low_confidence_candidates.py --apply

Outputs
-------
    data/audit/candidate_prune_<UTC>.preview.jsonl
    data/audit/candidate_prune_<UTC>.summary.json
    data/audit/candidate_prune_<UTC>.execute.json   (only with --apply)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config")
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets")

from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402
from libs.terminology.client import TerminologyClient  # noqa: E402
from services.api.app.services.candidate_prune import (  # noqa: E402
    PruneParams,
    assess_candidates,
    execute_prune,
    summarise,
)

logger = logging.getLogger("prune_low_confidence_candidates")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Confidence-gated auto-prune for non-completed TrainingCandidate rows. "
            "Defaults to dry-run; pass --apply to actually delete."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--min-surface-match", type=float, default=0.7)
    p.add_argument("--semantic-vector-floor", type=float, default=0.92)
    p.add_argument("--semantic-min-surface", type=float, default=0.66)
    p.add_argument(
        "--statuses",
        nargs="+",
        default=["pending", "processing", "failed"],
        help="Candidate statuses to scan (status='completed' is always excluded).",
    )
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--max-workers", type=int, default=8)
    p.add_argument(
        "--apply",
        action="store_true",
        help=(
            "After preview, delete the candidates whose verdict is 'delete'. "
            "Without this flag, the script writes preview output only."
        ),
    )
    p.add_argument(
        "--out-dir",
        default="data/audit",
        help="Directory for the preview/summary/execute JSONL output.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _write_preview_outputs(
    out_dir: Path,
    timestamp: str,
    assessments,
    summary,
    params: PruneParams,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    preview_path = out_dir / f"candidate_prune_{timestamp}.preview.jsonl"
    summary_path = out_dir / f"candidate_prune_{timestamp}.summary.json"
    with preview_path.open("w", encoding="utf-8") as fh:
        for a in assessments:
            fh.write(json.dumps(a.to_dict()) + "\n")
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "params": {
                    "min_surface_match": params.min_surface_match,
                    "semantic_vector_floor": params.semantic_vector_floor,
                    "semantic_min_surface": params.semantic_min_surface,
                    "statuses": list(params.statuses),
                    "limit": params.limit,
                },
                "summary": summary,
            },
            fh,
            indent=2,
        )
    return preview_path, summary_path


def _write_execute_output(out_dir: Path, timestamp: str, outcome) -> Path:
    out_path = out_dir / f"candidate_prune_{timestamp}.execute.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(outcome.to_dict(), fh, indent=2)
    return out_path


def main() -> int:
    args = _parse_args()
    _configure_logging(args.verbose)

    params = PruneParams(
        min_surface_match=float(args.min_surface_match),
        semantic_vector_floor=float(args.semantic_vector_floor),
        semantic_min_surface=float(args.semantic_min_surface),
        statuses=tuple(args.statuses),
        limit=int(args.limit),
        max_workers=int(args.max_workers),
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir)

    kg = KnowledgeGraphClient()
    terminology = TerminologyClient()
    started = time.time()
    try:
        logger.info(
            "Running preview: floors=(%.2f,%.2f,%.2f) statuses=%s limit=%d",
            params.min_surface_match,
            params.semantic_vector_floor,
            params.semantic_min_surface,
            params.statuses,
            params.limit,
        )
        assessments = assess_candidates(kg, terminology, params)
        summary = summarise(assessments)
        preview_path, summary_path = _write_preview_outputs(
            out_dir, timestamp, assessments, summary, params
        )
        logger.info(
            "Preview done in %.1fs: %d candidates (delete=%d, review=%d, keep=%d)",
            time.time() - started,
            summary["candidate_count"],
            summary["by_verdict"].get("delete", 0),
            summary["by_verdict"].get("review", 0),
            summary["by_verdict"].get("keep", 0),
        )
        logger.info("Wrote %s", preview_path)
        logger.info("Wrote %s", summary_path)

        if not args.apply:
            print(json.dumps(summary, indent=2))
            return 0

        delete_ids = [a.candidate_id for a in assessments if a.verdict == "delete"]
        if not delete_ids:
            logger.info("No candidates qualified for deletion; nothing to apply.")
            return 0

        logger.info("Executing delete for %d candidate(s)...", len(delete_ids))
        outcome = execute_prune(kg, delete_ids)
        out_path = _write_execute_output(out_dir, timestamp, outcome)
        logger.info(
            "Execute done: requested=%d deleted=%d skipped_completed=%d not_found=%d",
            len(outcome.requested),
            len(outcome.deleted),
            len(outcome.skipped_completed),
            len(outcome.not_found),
        )
        logger.info("Wrote %s", out_path)
        print(json.dumps(outcome.to_dict(), indent=2))
        return 0
    finally:
        kg.close()


if __name__ == "__main__":
    sys.exit(main())
