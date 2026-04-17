"""Backfill missing procedure / observable_entity / finding spans on lab rows.

The NER training set under-teaches multi-label lab spans: most gold records
for "Reticulocyte count (42X..) 62 10^9/L [20 - 80]" carry only one of the
three expected labels. The annotation guideline (rules 4 and 9 in
``libs/prompts/annotation_guidelines_v1.py``) says each lab line should
produce overlapping procedure, observable_entity and (when interpreted)
finding spans. This script inspects every completed GoldLabel, detects the
lab shape deterministically, and adds the missing overlapping spans.

Safety
------
- Dry-run by default. ``--apply`` is required to write to Neo4j.
- Never modifies or deletes existing entities; only appends new spans with
  ``_backfilled = true``.
- Backfilled spans carry no SNOMED code; the gold-dataset UI flags these
  for reviewer attention (existing "needs a code" chip).

Output
------
Writes ``reports/lab_triple_backfill_<timestamp>.json`` with the full per-
record plan so it can be audited or re-run.

Parent design input: DI-LEO-AI-054 (automated training label auditor).

Usage
-----
::

    # Dry run - print plan, write report, make no changes.
    .venv/bin/python scripts/backfill_lab_triple_labels.py

    # Apply to Neo4j.
    .venv/bin/python scripts/backfill_lab_triple_labels.py --apply
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env")
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.cypher.gold_label_queries import (  # noqa: E402
    GET_ALL_GOLD_LABELS_FOR_EXPORT,
    UPDATE_GOLD_LABEL_ENTITIES,
)
from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402
from libs.training.lab_span_detector import plan_triple_backfill  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to Neo4j. Without this flag the script is read-only.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after inspecting N records (0 = no limit).",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=ROOT / "reports",
        help="Directory to write the JSON report into.",
    )
    return parser.parse_args()


def _load_records(client: KnowledgeGraphClient, limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with client.session() as session:
        rows = session.run(GET_ALL_GOLD_LABELS_FOR_EXPORT)
        for row in rows:
            records.append(
                {
                    "label_id": str(row["label_id"]),
                    "text": str(row["text"] or ""),
                    "entities_json": row["entities_json"] or "[]",
                }
            )
            if limit and len(records) >= limit:
                break
    return records


def _build_plan(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Return per-record backfill plans plus an aggregate summary."""
    plans: list[dict[str, Any]] = []
    totals = {
        "inspected": 0,
        "lab_records": 0,
        "already_complete": 0,
        "records_needing_backfill": 0,
        "spans_proposed": 0,
    }
    by_label: dict[str, int] = {}

    for rec in records:
        totals["inspected"] += 1
        entities = _safe_json_load(rec["entities_json"])
        plan = plan_triple_backfill(rec["text"], entities)
        if not plan.matched:
            continue
        totals["lab_records"] += 1

        if not plan.proposed:
            totals["already_complete"] += 1
            continue

        totals["records_needing_backfill"] += 1
        totals["spans_proposed"] += len(plan.proposed)
        for ent in plan.proposed:
            label = str(ent.get("label", ""))
            by_label[label] = by_label.get(label, 0) + 1

        plans.append(
            {
                "label_id": rec["label_id"],
                "text": rec["text"],
                "existing_labels": sorted(plan.existing_labels),
                "proposed": plan.proposed,
            }
        )

    totals["proposed_by_label"] = dict(sorted(by_label.items()))
    return {"totals": totals, "plans": plans}


def _safe_json_load(raw: Any) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _merge_entities(
    existing: list[dict[str, Any]], proposed: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Append proposed entities to the existing list, preserving order."""
    return [*existing, *proposed]


def _apply_plan(
    client: KnowledgeGraphClient, plans: list[dict[str, Any]]
) -> dict[str, Any]:
    """Write the backfilled entities_json back to each GoldLabel."""
    updated = 0
    failed: list[dict[str, str]] = []
    with client.session() as session:
        for item in plans:
            try:
                # Re-load current entities in the same tx to avoid stomping a
                # concurrent reviewer edit. The planner runs again defensively.
                row = session.run(
                    "MATCH (g:GoldLabel {label_id: $id}) "
                    "RETURN g.entities_json AS entities_json",
                    id=item["label_id"],
                ).single()
                if row is None:
                    failed.append({"label_id": item["label_id"], "reason": "not_found"})
                    continue

                current_entities = _safe_json_load(row["entities_json"])
                re_plan = plan_triple_backfill(item["text"], current_entities)
                if not re_plan.matched or not re_plan.proposed:
                    # Another reviewer already fixed it.
                    continue

                merged = _merge_entities(current_entities, re_plan.proposed)
                session.run(
                    UPDATE_GOLD_LABEL_ENTITIES,
                    label_id=item["label_id"],
                    entities_json=json.dumps(merged, ensure_ascii=True),
                )
                updated += 1
            except Exception as exc:  # pragma: no cover - network/DB guard
                failed.append(
                    {"label_id": item["label_id"], "reason": str(exc)[:200]}
                )
    return {"updated": updated, "failed": failed}


def _write_report(
    report_dir: Path, plan: dict[str, Any], apply_result: dict[str, Any] | None
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    path = report_dir / f"lab_triple_backfill_{stamp}.json"
    payload = {
        "generated_at_utc": dt.datetime.utcnow().isoformat() + "Z",
        "totals": plan["totals"],
        "plans": plan["plans"],
    }
    if apply_result is not None:
        payload["apply"] = apply_result
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True))
    return path


def main() -> int:
    args = _parse_args()
    client = KnowledgeGraphClient()
    try:
        records = _load_records(client, args.limit)
        logger.info("Inspecting %d GoldLabel records.", len(records))

        plan = _build_plan(records)
        totals = plan["totals"]
        logger.info(
            "Detected %d lab-shape records (%d already complete, %d need backfill).",
            totals["lab_records"],
            totals["already_complete"],
            totals["records_needing_backfill"],
        )
        logger.info(
            "Would add %d spans: %s",
            totals["spans_proposed"],
            totals.get("proposed_by_label", {}),
        )

        apply_result: dict[str, Any] | None = None
        if args.apply:
            logger.warning("Applying backfill to Neo4j...")
            apply_result = _apply_plan(client, plan["plans"])
            logger.info(
                "Applied to %d records; %d failed.",
                apply_result["updated"],
                len(apply_result["failed"]),
            )
        else:
            logger.info("Dry run -- no changes written. Use --apply to commit.")

        report_path = _write_report(args.report_dir, plan, apply_result)
        logger.info("Report written to %s", report_path)
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
