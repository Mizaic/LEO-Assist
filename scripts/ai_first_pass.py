#!/usr/bin/env python3
"""AI first-pass over the non-completed TrainingCandidate backlog.

CLI mirror of POST /training/candidates/ai-first-pass/jobs
(DI-LEO-AI-208 / DI-LEO-AI-209 / UN-LEO-AI-085).

For each non-completed TrainingCandidate the script:
  1. Loads BioClinicalBERT few-shot exemplars from the gold pool.
  2. Asks Haiku to extract the entities for the candidate's text
     using those exemplars (falls back to the original entities_json
     if the model fails).
  3. Runs the SNOMED resolver + validator on each AI-extracted entity,
     re-asking Haiku for an alternative search term up to N times when
     the validator rejects.
  4. Assigns one of three verdicts:
       pre_done -> overwrite entities_json (audit copy preserved)
       delete   -> cascade-delete the candidate
       review   -> leave it alone for the human reviewer
  5. Writes the verdict + action back to disk unless --dry-run is set.

Defaults are conservative: --dry-run is required to actually write to
the graph. Without it the script writes preview JSON only.

Examples
--------
    # Dry-run with default floors against the current backlog:
    .venv/bin/python scripts/ai_first_pass.py

    # Dry-run with a tighter surface floor and 50 candidates only:
    .venv/bin/python scripts/ai_first_pass.py \\
        --min-surface-match 0.8 --limit 50

    # Apply (after reviewing the dry-run JSON):
    .venv/bin/python scripts/ai_first_pass.py --apply

Outputs
-------
    data/audit/ai_first_pass_<UTC>.preview.jsonl
    data/audit/ai_first_pass_<UTC>.summary.json
    data/audit/ai_first_pass_<UTC>.execute.json   (only with --apply)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config")
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets")

from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402
from libs.terminology.client import TerminologyClient  # noqa: E402
from services.api.app.services.candidate_ai_first_pass import (  # noqa: E402
    AIFirstPassParams,
    fetch_candidates,
    get_few_shot_selector,
    process_one,
    summarise,
)

logger = logging.getLogger("ai_first_pass")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "AI first-pass over the non-completed TrainingCandidate backlog. "
            "Defaults to dry-run; pass --apply to actually write back."
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
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument(
        "--few-shot-k",
        type=int,
        default=5,
        help="Number of gold exemplars passed to the Haiku extractor.",
    )
    p.add_argument(
        "--few-shot-pool-limit",
        type=int,
        default=1500,
        help="Cap on the gold pool loaded into the BioClinicalBERT vectoriser.",
    )
    p.add_argument(
        "--coder-max-retries",
        type=int,
        default=2,
        help="Haiku alt-search-term retries per entity.",
    )
    p.add_argument(
        "--haiku-tier",
        default="small",
        help="LLM tier for both the extractor and the smart coder. "
        "Keep this on 'small' (Haiku) per UN-LEO-AI-085.",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help=(
            "After preview, write pre_done overrides and delete the "
            "candidates whose verdict is 'delete'. Without this flag, "
            "the script writes preview output only and never mutates "
            "the graph."
        ),
    )
    p.add_argument(
        "--out-dir",
        default="data/audit",
        help="Directory for the preview/summary/execute JSON output.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _build_params(args: argparse.Namespace, *, dry_run: bool) -> AIFirstPassParams:
    return AIFirstPassParams(
        min_surface_match=float(args.min_surface_match),
        semantic_vector_floor=float(args.semantic_vector_floor),
        semantic_min_surface=float(args.semantic_min_surface),
        statuses=tuple(args.statuses),
        limit=int(args.limit),
        max_workers=int(args.max_workers),
        few_shot_k=int(args.few_shot_k),
        few_shot_pool_limit=int(args.few_shot_pool_limit),
        coder_max_retries=int(args.coder_max_retries),
        haiku_tier=str(args.haiku_tier),
        dry_run=dry_run,
    )


def _params_dict(params: AIFirstPassParams) -> dict[str, object]:
    return {
        "min_surface_match": params.min_surface_match,
        "semantic_vector_floor": params.semantic_vector_floor,
        "semantic_min_surface": params.semantic_min_surface,
        "statuses": list(params.statuses),
        "limit": params.limit,
        "max_workers": params.max_workers,
        "few_shot_k": params.few_shot_k,
        "few_shot_pool_limit": params.few_shot_pool_limit,
        "coder_max_retries": params.coder_max_retries,
        "haiku_tier": params.haiku_tier,
        "dry_run": params.dry_run,
    }


def _write_preview(
    out_dir: Path,
    timestamp: str,
    outcomes: list,
    summary: dict,
    params: AIFirstPassParams,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    preview_path = out_dir / f"ai_first_pass_{timestamp}.preview.jsonl"
    summary_path = out_dir / f"ai_first_pass_{timestamp}.summary.json"
    with preview_path.open("w", encoding="utf-8") as fh:
        for o in outcomes:
            fh.write(json.dumps(o.to_dict()) + "\n")
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {"params": _params_dict(params), "summary": summary},
            fh,
            indent=2,
        )
    return preview_path, summary_path


def _write_execute(
    out_dir: Path,
    timestamp: str,
    outcomes: list,
    summary: dict,
    params: AIFirstPassParams,
    run_id: str,
) -> Path:
    out_path = out_dir / f"ai_first_pass_{timestamp}.execute.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "run_id": run_id,
                "params": _params_dict(params),
                "summary": summary,
                "outcomes": [o.to_dict() for o in outcomes],
            },
            fh,
            indent=2,
        )
    return out_path


def _run_pass(
    *,
    kg: KnowledgeGraphClient,
    terminology: TerminologyClient,
    params: AIFirstPassParams,
    run_id: str,
) -> list:
    candidates = fetch_candidates(kg, params)
    logger.info("Fetched %d candidate(s) for AI first-pass", len(candidates))
    if not candidates:
        return []

    selector = get_few_shot_selector(kg, limit=params.few_shot_pool_limit)
    outcomes: list = []
    for idx, cand in enumerate(candidates, start=1):
        outcome = process_one(
            cand,
            client=kg,
            terminology=terminology,
            selector=selector,
            params=params,
            run_id=run_id,
        )
        outcomes.append(outcome)
        if idx % 25 == 0 or idx == len(candidates):
            logger.info(
                "Processed %d/%d (last verdict=%s action=%s)",
                idx,
                len(candidates),
                outcome.verdict,
                outcome.action,
            )
    return outcomes


def main() -> int:
    args = _parse_args()
    _configure_logging(args.verbose)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir)
    run_id_dry = f"ai-pass-cli-dry-{uuid.uuid4().hex[:12]}"
    run_id_apply = f"ai-pass-cli-{uuid.uuid4().hex[:12]}"

    kg = KnowledgeGraphClient()
    terminology = TerminologyClient()
    started = time.time()
    try:
        # 1) Always run dry-run first so the operator has a JSON
        #    preview to inspect before any writes happen.
        dry_params = _build_params(args, dry_run=True)
        logger.info(
            "Dry-run preview: floors=(%.2f,%.2f,%.2f) statuses=%s limit=%d",
            dry_params.min_surface_match,
            dry_params.semantic_vector_floor,
            dry_params.semantic_min_surface,
            dry_params.statuses,
            dry_params.limit,
        )
        dry_outcomes = _run_pass(
            kg=kg,
            terminology=terminology,
            params=dry_params,
            run_id=run_id_dry,
        )
        dry_summary = summarise(dry_outcomes)
        preview_path, summary_path = _write_preview(
            out_dir, timestamp, dry_outcomes, dry_summary, dry_params
        )
        logger.info(
            "Preview done in %.1fs: %d candidates "
            "(pre_done=%d, delete=%d, review=%d, errors=%d)",
            time.time() - started,
            dry_summary["candidate_count"],
            dry_summary["by_verdict"].get("pre_done", 0),
            dry_summary["by_verdict"].get("delete", 0),
            dry_summary["by_verdict"].get("review", 0),
            dry_summary["errors"],
        )
        logger.info("Wrote %s", preview_path)
        logger.info("Wrote %s", summary_path)

        if not args.apply:
            print(json.dumps(dry_summary, indent=2))
            return 0

        # 2) Apply: re-run with dry_run=False so writeback fires.
        apply_params = _build_params(args, dry_run=False)
        logger.info(
            "Apply pass run_id=%s (this will write to the graph)", run_id_apply
        )
        apply_outcomes = _run_pass(
            kg=kg,
            terminology=terminology,
            params=apply_params,
            run_id=run_id_apply,
        )
        apply_summary = summarise(apply_outcomes)
        out_path = _write_execute(
            out_dir, timestamp, apply_outcomes, apply_summary, apply_params, run_id_apply
        )
        logger.info(
            "Apply done: candidates=%d pre_done=%d delete=%d errors=%d",
            apply_summary["candidate_count"],
            apply_summary["by_action"].get("upserted_pre_done", 0),
            apply_summary["by_action"].get("deleted", 0),
            apply_summary["errors"],
        )
        logger.info("Wrote %s", out_path)
        print(json.dumps(apply_summary, indent=2))
        return 0
    finally:
        kg.close()


if __name__ == "__main__":
    sys.exit(main())
