#!/usr/bin/env python3
"""Backfill value, unit, and letter date on existing observable DOCUMENTS links.

Atlas trace:
  DI: DI-0BB36B4D
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-0BB36B4D")

Dates come from the same chunk or encounter line as the reading. Two different
dates are not guessed. Today's date is never invented.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
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
from libs.pipeline.observation_date import parse_observation_date  # noqa: E402
from libs.training.lab_span_detector import detect_lab_pattern  # noqa: E402

DEFAULT_REPORT_DIR = _REPO_ROOT / "artifacts" / "observable_measurement_backfills"

_OBS_WITH = (
    "WITH src, r, s, src.text AS chunk_text, "
    "toLower(replace(replace(coalesce(s.semanticTag, ''), '_', ''), ' ', '')) "
    "AS node_tag, "
    "toLower(replace(replace(coalesce(r.semantic_tag, ''), '_', ''), ' ', '')) "
    "AS rel_tag "
)

_OBS_WHERE = (
    "WHERE node_tag IN ['observableentity', 'observable'] "
    "OR rel_tag IN ['observableentity', 'observable'] "
)

_OBS_RETURN = (
    "RETURN elementId(r) AS rel_id, "
    "toString(src.id) AS encounter_id, "
    "toString(s.conceptId) AS concept_id, "
    "coalesce(s.name, s.term) AS term, "
    "coalesce(s.semanticTag, r.semantic_tag) AS semantic_tag, "
    "r.evidence AS evidence, "
    "r.evidence_sentence AS evidence_sentence, "
    "chunk_text, "
    "r.value AS existing_value, "
    "r.unit AS existing_unit, "
    "r.referenceRange AS existing_reference_range, "
    "r.observed_at AS existing_observed_at, "
    "r.source AS source"
)

LIST_CANDIDATES = (
    "MATCH (src:Encounter)-[r:DOCUMENTS]->(s) "
    "WHERE (r.value IS NULL OR r.unit IS NULL OR r.observed_at IS NULL) "
    "AND coalesce(r.evidence, r.evidence_sentence, src.text, '') <> '' "
    f"{_OBS_WITH}{_OBS_WHERE}{_OBS_RETURN} "
    "UNION "
    "MATCH (src:Chunk)-[r:DOCUMENTS]->(s) "
    "WHERE (r.value IS NULL OR r.unit IS NULL OR r.observed_at IS NULL) "
    "AND coalesce(r.evidence, r.evidence_sentence, src.text, '') <> '' "
    f"{_OBS_WITH}{_OBS_WHERE}{_OBS_RETURN}"
)

APPLY_MEASUREMENT = """
MATCH ()-[r:DOCUMENTS]->()
WHERE elementId(r) = $rel_id
SET r.value = coalesce(r.value, $value),
    r.unit = coalesce(r.unit, $unit),
    r.referenceRange = coalesce(r.referenceRange, $reference_range),
    r.observed_at = coalesce(r.observed_at, $observed_at),
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
    observed_at: str | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist parsed values.")
    parser.add_argument(
        "--limit", type=int, default=0, help="Optional candidate limit."
    )
    parser.add_argument(
        "--source",
        default="",
        help="Optional DOCUMENTS source filter, e.g. lab_coder_v1.",
    )
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    return parser.parse_args()


def _load_candidate_rows(
    client: PatientGraphClient, limit: int
) -> list[dict[str, Any]]:
    with client.session() as session:
        rows = [dict(row) for row in session.run(LIST_CANDIDATES)]
    return rows[:limit] if limit > 0 else rows


def _matching_lines(text: str, needle: str) -> list[str]:
    if not text or not needle:
        return []
    token = re.compile(rf"(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])", re.I)
    return [line for line in text.splitlines() if token.search(line)]


def _observed_at_from_row(row: dict[str, Any]) -> str | None:
    existing = str(row.get("existing_observed_at") or "").strip()
    if existing:
        return existing[:10]
    needles = [
        str(row.get("evidence") or "").strip(),
        str(row.get("term") or "").strip(),
    ]
    text = str(row.get("chunk_text") or "").strip()
    lines: list[str] = []
    for needle in needles:
        if needle:
            lines.extend(_matching_lines(text, needle))
    unique_lines = list(dict.fromkeys(lines))
    dates = {parse_observation_date(line) for line in unique_lines}
    dates.discard(None)
    if len(dates) == 1:
        return next(iter(dates))
    if len(unique_lines) == 1:
        return parse_observation_date(unique_lines[0])
    fallback = str(row.get("evidence_sentence") or row.get("evidence") or "")
    return parse_observation_date(fallback)


def _parsed_measurement(row: dict[str, Any]) -> tuple[str, str, str | None]:
    evidence = _best_evidence(row)
    pattern = detect_lab_pattern(evidence)
    if not pattern.matched:
        return "", "", None
    return pattern.numeric_value or "", pattern.unit or "", pattern.reference_range


def _build_backfill_item(row: dict[str, Any]) -> BackfillItem | None:
    existing_value = str(row.get("existing_value") or "").strip()
    existing_unit = str(row.get("existing_unit") or "").strip()
    existing_range = str(row.get("existing_reference_range") or "").strip()
    parsed_value, parsed_unit, parsed_range = _parsed_measurement(row)
    observed_at = _observed_at_from_row(row)
    value = existing_value or parsed_value
    unit = existing_unit or parsed_unit
    reference_range = existing_range or parsed_range
    writes_value = not existing_value and bool(parsed_value)
    writes_unit = not existing_unit and bool(parsed_unit)
    writes_date = not str(row.get("existing_observed_at") or "").strip() and bool(
        observed_at
    )
    if not (writes_value or writes_unit or writes_date):
        return None
    return BackfillItem(
        rel_id=str(row.get("rel_id") or ""),
        encounter_id=str(row.get("encounter_id") or ""),
        concept_id=str(row.get("concept_id") or ""),
        term=str(row.get("term") or ""),
        source=str(row.get("source") or ""),
        evidence=_best_evidence(row),
        value=value,
        unit=unit,
        reference_range=reference_range or None,
        observed_at=observed_at,
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
                    value=item.value or None,
                    unit=item.unit or None,
                    reference_range=item.reference_range,
                    observed_at=item.observed_at,
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
        "dated": sum(1 for item in items if item.observed_at),
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
                    "dated": sum(1 for item in items if item.observed_at),
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
