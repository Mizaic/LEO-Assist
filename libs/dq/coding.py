"""Encounter coding quality service -- reads from audit SQLite DBs."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

from libs.dq._models import CodingIssueSummary, CodingIssueRow

logger = logging.getLogger(__name__)


def _connect(db_path: str) -> sqlite3.Connection:
    p = Path(db_path)
    if not p.exists():
        raise FileNotFoundError(f"Audit DB not found: {db_path}")
    return sqlite3.connect(str(p))


def get_coding_summary(db_path: str) -> CodingIssueSummary:
    """Return aggregate coding quality summary from an audit DB."""
    con = _connect(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT assessment, count(*) AS cnt " "FROM encounters GROUP BY assessment"
        )
        status_rows = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute(
            "SELECT json_extract(result, '$.missing_critical') as crit, "
            "       json_extract(result, '$.missing_high') as high, "
            "       json_extract(result, '$.missing_medium') as med, "
            "       json_extract(result, '$.missing_low') as low "
            "FROM encounters WHERE assessment = 'has_issues'"
        )
        sev_rows = cur.fetchall()
        crit = sum(int(r[0] or 0) for r in sev_rows)
        high = sum(int(r[1] or 0) for r in sev_rows)
        med = sum(int(r[2] or 0) for r in sev_rows)
        low_ = sum(int(r[3] or 0) for r in sev_rows)

        cur.execute(
            "SELECT json_extract(result, '$.missing') as missing_json "
            "FROM encounters WHERE assessment = 'has_issues' LIMIT 500"
        )
        concept_counter: dict[str, int] = {}
        for (raw,) in cur.fetchall():
            try:
                missing = json.loads(raw or "[]")
                for item in (missing if isinstance(missing, list) else []):
                    label = item.get("concept") or item.get("label") or str(item)
                    concept_counter[label] = concept_counter.get(label, 0) + 1
            except Exception:
                logging.getLogger(__name__).debug(
                    "Skipping malformed missing-concept JSON row", exc_info=True
                )

        top_missing = sorted(
            [{"concept": k, "count": v} for k, v in concept_counter.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:20]

        total = sum(status_rows.values())
        clean = status_rows.get("clean", 0)
        has_issues = status_rows.get("has_issues", 0)
        return CodingIssueSummary(
            total_assessed=total,
            clean_count=clean,
            has_issues_count=has_issues,
            critical_count=crit,
            high_count=high,
            medium_count=med,
            low_count=low_,
            top_missing=top_missing,
        )
    finally:
        con.close()


def get_coding_issues(
    db_path: str,
    severity: Optional[str] = None,
    limit: int = 100,
) -> list[CodingIssueRow]:
    """Return encounters with coding issues, filtered by severity."""
    con = _connect(db_path)
    try:
        cur = con.cursor()
        where = "WHERE assessment = 'has_issues'"
        if severity == "critical":
            where += " AND json_extract(result, '$.missing_critical') > 0"
        elif severity == "high":
            where += (
                " AND (json_extract(result, '$.missing_critical') > 0"
                " OR json_extract(result, '$.missing_high') > 0)"
            )
        cur.execute(
            f"SELECT encounter_id, patient_id, date, assessment, result "
            f"FROM encounters {where} LIMIT ?",
            (limit,),
        )
        rows = []
        for r in cur.fetchall():
            try:
                res = json.loads(r[4] or "{}")
            except Exception:
                res = {}
            rows.append(
                CodingIssueRow(
                    encounter_id=r[0] or "",
                    patient_id=r[1],
                    date=r[2],
                    assessment=r[3] or "",
                    missing_critical=int(res.get("missing_critical") or 0),
                    missing_high=int(res.get("missing_high") or 0),
                    overcoded=int(res.get("overcoded") or 0),
                    wrong_assertion=int(res.get("wrong_assertion") or 0),
                )
            )
        return rows
    finally:
        con.close()


def get_coding_progress(db_path: str) -> dict:
    """Return done/pending/error counts and throughput from audit DB."""
    con = _connect(db_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT status, count(*) FROM encounters GROUP BY status")
        counts = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute("SELECT max(updated_at) FROM encounters WHERE status = 'done'")
        row = cur.fetchone()
        last_updated = row[0] if row else None
        return {
            "done": counts.get("done", 0),
            "pending": counts.get("pending", 0),
            "error": counts.get("error", 0),
            "total": sum(counts.values()),
            "last_updated": last_updated,
        }
    finally:
        con.close()
