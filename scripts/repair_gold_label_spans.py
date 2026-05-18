#!/usr/bin/env python3
"""Dry-run-first bulk repair for GoldLabel entity spans."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config")
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets")

from libs.cypher.gold_label_queries import (
    GET_ALL_GOLD_LABELS_FOR_EXPORT,
    UPDATE_GOLD_LABEL_ENTITIES,
)
from libs.neo4j_client.client import KnowledgeGraphClient
from libs.pipeline.label_filter import repair_entity_spans


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist deterministic repairs. Defaults to dry-run only.",
    )
    parser.add_argument(
        "--drop-unrepairable",
        action="store_true",
        help="Remove entities whose surface text cannot be found.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of labels to inspect.",
    )
    parser.add_argument(
        "--source",
        default="",
        help="Optional GoldLabel source filter.",
    )
    parser.add_argument(
        "--report-dir",
        default="artifacts/gold_label_span_repairs",
        help="Directory for the JSON repair report.",
    )
    return parser.parse_args()


def _load_rows(
    client: KnowledgeGraphClient, source: str, limit: int
) -> list[dict[str, Any]]:
    with client.session() as session:
        rows = [dict(row) for row in session.run(GET_ALL_GOLD_LABELS_FOR_EXPORT)]
    if source:
        rows = [row for row in rows if str(row.get("source") or "") == source]
    if limit > 0:
        return rows[:limit]
    return rows


def _repair_row(row: dict[str, Any], *, drop_unrepairable: bool) -> dict[str, Any]:
    entities = json.loads(str(row.get("entities_json") or "[]"))
    repair = repair_entity_spans(
        str(row.get("text") or ""),
        entities,
        drop_unrepairable=drop_unrepairable,
    )
    return {
        "label_id": str(row.get("label_id") or ""),
        "source": str(row.get("source") or ""),
        "candidate_id": str(row.get("candidate_id") or ""),
        "dropped_unrepairable_count": (
            len(repair["unrepairable"]) if drop_unrepairable else 0
        ),
        "repaired_count": len(repair["repaired"]),
        "unchanged_count": len(repair["unchanged"]),
        "unrepairable_count": len(repair["unrepairable"]),
        "ambiguous_count": len(repair["ambiguous"]),
        "repaired": repair["repaired"],
        "unrepairable": repair["unrepairable"],
        "ambiguous": repair["ambiguous"],
        "entities": repair["entities"],
    }


def _has_writable_change(item: dict[str, Any]) -> bool:
    return item["repaired_count"] > 0 or item["dropped_unrepairable_count"] > 0


def _write_repairs(client: KnowledgeGraphClient, repairs: list[dict[str, Any]]) -> int:
    applied = 0
    with client.session() as session:
        for item in repairs:
            if not _has_writable_change(item):
                continue
            session.run(
                UPDATE_GOLD_LABEL_ENTITIES,
                label_id=item["label_id"],
                entities_json=json.dumps(item["entities"]),
            )
            applied += 1
    return applied


def _build_summary(
    rows: list[dict[str, Any]], repairs: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "labels_scanned": len(rows),
        "labels_with_changes": sum(1 for item in repairs if _has_writable_change(item)),
        "labels_with_repairs": sum(1 for item in repairs if item["repaired_count"] > 0),
        "labels_with_unrepairable_drops": sum(
            1 for item in repairs if item["dropped_unrepairable_count"] > 0
        ),
        "entities_dropped_unrepairable": sum(
            item["dropped_unrepairable_count"] for item in repairs
        ),
        "entities_repaired": sum(item["repaired_count"] for item in repairs),
        "entities_unrepairable": sum(item["unrepairable_count"] for item in repairs),
        "entities_ambiguous": sum(item["ambiguous_count"] for item in repairs),
    }


def _write_report(report_dir: Path, report: dict[str, Any]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    mode = "apply" if report["apply"] else "dry_run"
    path = report_dir / f"gold_label_span_repair_{mode}_{stamp}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main() -> int:
    args = _parse_args()
    client = KnowledgeGraphClient()
    try:
        rows = _load_rows(client, args.source, args.limit)
        repairs = [
            _repair_row(row, drop_unrepairable=args.drop_unrepairable) for row in rows
        ]
        applied = _write_repairs(client, repairs) if args.apply else 0
    finally:
        client.close()

    report = {
        "apply": bool(args.apply),
        "source": args.source or None,
        "limit": args.limit or None,
        "drop_unrepairable": bool(args.drop_unrepairable),
        "applied_labels": applied,
        "summary": _build_summary(rows, repairs),
        "items": [
            _strip_entities(item)
            for item in repairs
            if item["repaired_count"]
            or item["unrepairable_count"]
            or item["ambiguous_count"]
        ],
    }
    path = _write_report(Path(args.report_dir), report)
    print(
        json.dumps(
            {"report": str(path), **report["summary"], "applied_labels": applied}
        )
    )
    return 0


def _strip_entities(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key != "entities"}


if __name__ == "__main__":
    raise SystemExit(main())
