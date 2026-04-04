"""SQLite checkpoint database for audit_encounter_coding.py.

Provides crash-safe, per-encounter progress tracking using WAL mode.
All writes are individual commits so a crash loses at most one result.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_ERROR = "error"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS encounters (
    encounter_id  TEXT PRIMARY KEY,
    patient_id    TEXT NOT NULL,
    date          TEXT,
    text_len      INTEGER,
    status        TEXT NOT NULL DEFAULT 'pending',
    result_json   TEXT,
    error_msg     TEXT,
    processed_at  TEXT
);
CREATE TABLE IF NOT EXISTS surface_form_gaps (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    encounter_id        TEXT NOT NULL,
    evidence            TEXT NOT NULL,
    expected_concept_id TEXT NOT NULL,
    expected_name       TEXT,
    semantic_tag        TEXT,
    resolver_top_result TEXT,
    resolver_top_score  REAL,
    gap_type            TEXT NOT NULL,
    UNIQUE(evidence, expected_concept_id)
);
"""


class CheckpointDB:
    """WAL-mode SQLite store for encounter audit progress."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA synchronous=NORMAL")
        self._con.executescript(_SCHEMA)
        self._con.commit()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def insert_encounters(self, rows: list[dict[str, Any]]) -> int:
        """Insert encounters (IGNORE if already present). Returns new rows count."""
        inserted = 0
        for row in rows:
            self._con.execute(
                "INSERT OR IGNORE INTO encounters"
                " (encounter_id, patient_id, date, text_len, status)"
                " VALUES (?, ?, ?, ?, ?)",
                (row["encounter_id"], row["patient_id"],
                 row.get("date"), row.get("text_len"), STATUS_PENDING),
            )
            inserted += self._con.execute("SELECT changes()").fetchone()[0]
        self._con.commit()
        return inserted

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def pending_encounters(self) -> Iterator[dict[str, Any]]:
        cur = self._con.execute(
            "SELECT encounter_id, patient_id, date FROM encounters"
            " WHERE status = ? ORDER BY patient_id, date",
            (STATUS_PENDING,),
        )
        for row in cur:
            yield {"encounter_id": row[0], "patient_id": row[1], "date": row[2]}

    def mark_done(self, encounter_id: str, result: dict[str, Any]) -> None:
        self._con.execute(
            "UPDATE encounters SET status=?, result_json=?, processed_at=?"
            " WHERE encounter_id=?",
            (STATUS_DONE, json.dumps(result), _now(), encounter_id),
        )
        self._con.commit()

    def mark_error(self, encounter_id: str, msg: str) -> None:
        self._con.execute(
            "UPDATE encounters SET status=?, error_msg=?, processed_at=?"
            " WHERE encounter_id=?",
            (STATUS_ERROR, msg[:2000], _now(), encounter_id),
        )
        self._con.commit()

    def upsert_surface_gap(self, gap: dict[str, Any]) -> None:
        self._con.execute(
            "INSERT OR REPLACE INTO surface_form_gaps"
            " (encounter_id, evidence, expected_concept_id, expected_name,"
            "  semantic_tag, resolver_top_result, resolver_top_score, gap_type)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                gap["encounter_id"], gap["evidence"], gap["expected_concept_id"],
                gap.get("expected_name"), gap.get("semantic_tag"),
                gap.get("resolver_top_result"), gap.get("resolver_top_score"),
                gap["gap_type"],
            ),
        )
        self._con.commit()

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def counts(self) -> dict[str, int]:
        c = self._con
        return {
            "total": c.execute("SELECT count(*) FROM encounters").fetchone()[0],
            "pending": c.execute(
                "SELECT count(*) FROM encounters WHERE status='pending'").fetchone()[0],
            "done": c.execute(
                "SELECT count(*) FROM encounters WHERE status='done'").fetchone()[0],
            "error": c.execute(
                "SELECT count(*) FROM encounters WHERE status='error'").fetchone()[0],
            "surface_gaps": c.execute(
                "SELECT count(*) FROM surface_form_gaps").fetchone()[0],
        }

    def all_results(self) -> Iterator[dict[str, Any]]:
        cur = self._con.execute(
            "SELECT encounter_id, patient_id, date, result_json, status"
            " FROM encounters WHERE status IN ('done','error')"
            " ORDER BY patient_id, date",
        )
        for row in cur:
            yield {
                "encounter_id": row[0],
                "patient_id": row[1],
                "date": row[2],
                "result": json.loads(row[3]) if row[3] else None,
                "status": row[4],
            }

    def all_surface_gaps(self) -> list[dict[str, Any]]:
        cur = self._con.execute(
            "SELECT evidence, expected_concept_id, expected_name, semantic_tag,"
            "       resolver_top_result, resolver_top_score, gap_type"
            " FROM surface_form_gaps",
        )
        return [
            {
                "evidence": r[0],
                "expected_snomed": r[1],
                "expected_name": r[2],
                "semantic_tag": r[3],
                "resolver_top_result": r[4],
                "resolver_top_score": r[5],
                "gap_type": r[6],
            }
            for r in cur
        ]

    def close(self) -> None:
        self._con.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
