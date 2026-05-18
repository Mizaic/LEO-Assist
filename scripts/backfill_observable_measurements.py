#!/usr/bin/env python3
"""Backfill value/unit fields on existing observable DOCUMENTS links."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_REPO_ROOT / "secrets" / ".env", override=False)
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets", override=False)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402
from libs.training.lab_span_detector import detect_lab_pattern  # noqa: E402

DEFAULT_REPORT_DIR = _REPO_ROOT / "artifacts" / "observable_measurement_backfills"

LIST_CANDIDATES = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(s)
WHERE (r.value IS NULL OR r.unit IS NULL)
  AND coalesce(r.evidence, r.evidence_sentence, '') <> ''
WITH e, r, s,
     toLower(replace(replace(coalesce(s.semanticTag, ''), '_', ''), ' ', '')) AS node_tag,
     toLower(replace(replace(coalesce(r.semantic_tag, ''), '_', ''), ' ', '')) AS rel_tag
WHERE node_tag IN ['observableentity', 'observable']
   OR rel_tag IN ['observableentity', 'observable']
RETURN elementId(r) AS rel_id,
       toString(e.id) AS encounter_id,
       toString(s.conceptId) AS concept_id,
       coalesce(s.name, s.term) AS term,
       coalesce(s.semanticTag, r.semantic_tag) AS semantic_tag,
       r.evidence AS evidence,
       r.evidence_sentence AS evidence_sentence,
       r.value AS existing_value,
       r.unit AS existing_unit,
       r.referenceRange AS existing_reference_range,
       r.source AS source
ORDER BY e.id, s.conceptId
"""

APPLY_MEASUREMENT = """
MATCH ()-[r:DOCUMENTS]->()
WHERE elementId(r) = $rel_id
SET r.value = $value,
    r.unit = $unit,
    r.referenceRange = $reference_range,
    r.measurement_backfilled_at = datetime(),
    r.measurement_backfilled_by = 'backfill_observable_measurements'
RETURN elementId(r) AS rel_id
"""


@dataclass(frozen=True)
class BackfillItem:
    rel_id: str
    encounter_id: str
    concept_id: str
    term: str
    source: str
    evidence: str
    value: str
    unit: str
    reference_range: str | None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist parsed values.")
    parser.add_argument("--limit", type=int, default=0, help="Optional candidate limit.")
    parser.add_argument(
        "--source",
        default="",
        help="Optional DOCUMENTS source filter, e.g. lab_coder_v1.",
    )
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    return parser.parse_args()


def _load_candidate_rows(client: PatientGraphClient, limit: int) -> list[dict[str, Any]]:
    with client.session() as session:
        rows = [dict(row) for row in session.run(LIST_CANDIDATES)]
    return rows[:limit] if limit > 0 else rows


def _build_backfill_item(row: dict[str, Any]) -> BackfillItem | None:
    evidence = _best_evidence(row)
    pattern = detect_lab_pattern(evidence)
    if not pattern.matched or not pattern.numeric_value or not pattern.unit:
        return None
    return BackfillItem(
        rel_id=str(row.get("rel_id") or ""),
        encounter_id=str(row.get("encounter_id") or ""),
        concept_id=str(row.get("concept_id") or ""),
        term=str(row.get("term") or ""),
        source=str(row.get("source") or ""),
        evidence=evidence,
        value=pattern.numeric_value,
        unit=pattern.unit,
        reference_range=pattern.reference_range,
    )


def _best_evidence(row: dict[str, Any]) -> str:
    for key in ("evidence", "evidence_sentence"):
        value = str(row.get(key) or "").strip()
        if value and detect_lab_pattern(value).matched:
            return value
    return str(row.get("evidence") or row.get("evidence_sentence") or "").strip()


def _apply_items(client: PatientGraphClient, items: list[BackfillItem]) -> int:
    written = 0
    with client.session() as session:
        for item in items:
            rows = list(
                session.run(
                    APPLY_MEASUREMENT,
                    rel_id=item.rel_id,
                    value=item.value,
                    unit=item.unit,
                    reference_range=item.reference_range,
                )
            )
            if rows:
                written += 1
    return written


def _write_report(
    report_dir: Path,
    *,
    apply: bool,
    candidates: int,
    items: list[BackfillItem],
    written: int,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    mode = "apply" if apply else "dry_run"
    path = report_dir / f"observable_measurement_backfill_{mode}_{stamp}.json"
    payload = {
        "apply": apply,
        "candidates": candidates,
        "parsable": len(items),
        "written": written,
        "items": [item.__dict__ for item in items],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def main() -> int:
    args = _parse_args()
    client = PatientGraphClient()
    try:
        rows = _load_candidate_rows(client, args.limit)
        if args.source:
            rows = [row for row in rows if str(row.get("source") or "") == args.source]
        items = [
            item
            for row in rows
            if (item := _build_backfill_item(row)) is not None and item.rel_id
        ]
        written = _apply_items(client, items) if args.apply else 0
        report_path = _write_report(
            args.report_dir,
            apply=args.apply,
            candidates=len(rows),
            items=items,
            written=written,
        )
        print(
            json.dumps(
                {
                    "apply": args.apply,
                    "candidates": len(rows),
                    "parsable": len(items),
                    "written": written,
                    "report": str(report_path),
                },
                indent=2,
            )
        )
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
