#!/usr/bin/env python3
"""Dry-run-first repair for request-reason suspected-cancer situations."""

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

from libs.cypher.gold_label_queries import (  # noqa: E402
    GET_ALL_GOLD_LABELS_FOR_EXPORT,
    UPDATE_GOLD_LABEL_ENTITIES,
)
from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402
from libs.ner.request_reason_recovery import (
    recover_request_reason_entities,
)  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist safe repairs.")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit.")
    parser.add_argument(
        "--source", default="", help="Optional GoldLabel source filter."
    )
    parser.add_argument(
        "--report-dir",
        default="artifacts/request_reason_repairs",
        help="Directory for JSON reports.",
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
        rows = rows[:limit]
    return rows


def _repair_row(row: dict[str, Any]) -> dict[str, Any] | None:
    text = str(row.get("text") or "")
    existing = _parse_entities(row.get("entities_json"))
    repaired = recover_request_reason_entities(text, existing)
    added = [
        entity
        for entity in repaired[len(existing) :]
        if str(entity.get("label") or entity.get("semantic_tag") or "") == "situation"
    ]
    if not added:
        return None
    final_entities = [*existing, *added]
    return {
        "label_id": str(row.get("label_id") or ""),
        "candidate_id": str(row.get("candidate_id") or ""),
        "source": str(row.get("source") or ""),
        "text_preview": text[:300],
        "added": [_clean_entity(entity) for entity in added],
        "entities": [_clean_entity(entity) for entity in final_entities],
    }


def _parse_entities(raw: Any) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(str(raw or "[]"))
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [dict(item) for item in parsed if isinstance(item, dict)]


def _clean_entity(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in entity.items()
        if not str(key).startswith("_") and value not in (None, "")
    }


def _write_repairs(client: KnowledgeGraphClient, repairs: list[dict[str, Any]]) -> int:
    applied = 0
    with client.session() as session:
        for item in repairs:
            session.run(
                UPDATE_GOLD_LABEL_ENTITIES,
                label_id=item["label_id"],
                entities_json=json.dumps(item["entities"]),
            )
            applied += 1
    return applied


def _write_report(report_dir: Path, report: dict[str, Any]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    mode = "apply" if report["apply"] else "dry_run"
    path = report_dir / f"request_reason_repair_{mode}_{stamp}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main() -> int:
    args = _parse_args()
    client = KnowledgeGraphClient()
    try:
        rows = _load_rows(client, args.source, args.limit)
        repairs = [repair for row in rows if (repair := _repair_row(row)) is not None]
        applied = _write_repairs(client, repairs) if args.apply else 0
    finally:
        client.close()

    report = {
        "apply": bool(args.apply),
        "source": args.source or None,
        "limit": args.limit or None,
        "applied_labels": applied,
        "summary": {
            "labels_scanned": len(rows),
            "labels_with_request_reason_repairs": len(repairs),
            "entities_added": sum(len(item["added"]) for item in repairs),
        },
        "items": repairs,
    }
    path = _write_report(Path(args.report_dir), report)
    print(
        json.dumps(
            {"report": str(path), **report["summary"], "applied_labels": applied}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
