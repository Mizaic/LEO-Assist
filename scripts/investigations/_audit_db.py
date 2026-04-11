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
    processed_at  TEXT,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    cost_usd      REAL
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
CREATE TABLE IF NOT EXISTS wrong_concepts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    encounter_id        TEXT NOT NULL,
    evidence            TEXT NOT NULL,
    stored_concept_id   TEXT NOT NULL,
    stored_name         TEXT,
    resolved_concept_id TEXT NOT NULL,
    resolved_name       TEXT,
    resolver_score      REAL,
    semantic_tag        TEXT,
    UNIQUE(evidence, stored_concept_id)
);
CREATE TABLE IF NOT EXISTS ner_examples (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    encounter_id    TEXT NOT NULL,
    sentence        TEXT NOT NULL,
    entity          TEXT NOT NULL,
    start_char      INTEGER NOT NULL,
    end_char        INTEGER NOT NULL,
    concept_id      TEXT NOT NULL,
    term            TEXT,
    semantic_tag    TEXT,
    assertion       TEXT,
    UNIQUE(encounter_id, entity, start_char)
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
        self._migrate()
        self._con.commit()

    def _migrate(self) -> None:
        """Add columns introduced after the initial schema. Safe to run repeatedly."""
        new_cols = [
            ("input_tokens", "INTEGER"),
            ("output_tokens", "INTEGER"),
            ("cost_usd", "REAL"),
        ]
        for col, col_type in new_cols:
            try:
                self._con.execute(f"ALTER TABLE encounters ADD COLUMN {col} {col_type}")
            except Exception:
                pass  # column already exists

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
                (
                    row["encounter_id"],
                    row["patient_id"],
                    row.get("date"),
                    row.get("text_len"),
                    STATUS_PENDING,
                ),
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
        meta = result.get("metadata") or {}
        input_tok = meta.get("input_tokens") or None
        output_tok = meta.get("output_tokens") or None
        cost = _compute_cost_usd(input_tok, output_tok, meta.get("model_id") or "")
        self._con.execute(
            "UPDATE encounters"
            " SET status=?, result_json=?, processed_at=?,"
            "     input_tokens=?, output_tokens=?, cost_usd=?"
            " WHERE encounter_id=?",
            (
                STATUS_DONE,
                json.dumps(result),
                _now(),
                input_tok,
                output_tok,
                cost,
                encounter_id,
            ),
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
                gap["encounter_id"],
                gap["evidence"],
                gap["expected_concept_id"],
                gap.get("expected_name"),
                gap.get("semantic_tag"),
                gap.get("resolver_top_result"),
                gap.get("resolver_top_score"),
                gap["gap_type"],
            ),
        )
        self._con.commit()

    def insert_wrong_concept(self, row: dict[str, Any]) -> None:
        """Record a DOCUMENTS relationship where resolver disagrees with stored concept."""
        self._con.execute(
            "INSERT OR REPLACE INTO wrong_concepts"
            " (encounter_id, evidence, stored_concept_id, stored_name,"
            "  resolved_concept_id, resolved_name, resolver_score, semantic_tag)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["encounter_id"],
                row["evidence"],
                row["stored_concept_id"],
                row.get("stored_name"),
                row["resolved_concept_id"],
                row.get("resolved_name"),
                row.get("resolver_score"),
                row.get("semantic_tag"),
            ),
        )
        self._con.commit()

    def insert_ner_example(self, row: dict[str, Any]) -> None:
        """Store one NER training example (sentence + entity span + label)."""
        self._con.execute(
            "INSERT OR IGNORE INTO ner_examples"
            " (encounter_id, sentence, entity, start_char, end_char,"
            "  concept_id, term, semantic_tag, assertion)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["encounter_id"],
                row["sentence"],
                row["entity"],
                row["start_char"],
                row["end_char"],
                row["concept_id"],
                row.get("term"),
                row.get("semantic_tag"),
                row.get("assertion"),
            ),
        )
        self._con.commit()

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def counts(self) -> dict[str, int | float]:
        c = self._con
        tok = c.execute(
            "SELECT coalesce(sum(input_tokens),0),"
            "       coalesce(sum(output_tokens),0),"
            "       coalesce(sum(cost_usd),0.0)"
            " FROM encounters WHERE status='done'"
        ).fetchone()
        return {
            "total": c.execute("SELECT count(*) FROM encounters").fetchone()[0],
            "pending": c.execute(
                "SELECT count(*) FROM encounters WHERE status='pending'"
            ).fetchone()[0],
            "done": c.execute(
                "SELECT count(*) FROM encounters WHERE status='done'"
            ).fetchone()[0],
            "error": c.execute(
                "SELECT count(*) FROM encounters WHERE status='error'"
            ).fetchone()[0],
            "surface_gaps": c.execute(
                "SELECT count(*) FROM surface_form_gaps"
            ).fetchone()[0],
            "wrong_concepts": c.execute(
                "SELECT count(*) FROM wrong_concepts"
            ).fetchone()[0],
            "ner_examples": c.execute("SELECT count(*) FROM ner_examples").fetchone()[
                0
            ],
            "input_tokens": int(tok[0]),
            "output_tokens": int(tok[1]),
            "cost_usd": round(float(tok[2]), 4),
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

    def all_wrong_concepts(self) -> list[dict[str, Any]]:
        cur = self._con.execute(
            "SELECT evidence, stored_concept_id, stored_name,"
            "       resolved_concept_id, resolved_name, resolver_score, semantic_tag,"
            "       count(*) AS encounter_count"
            " FROM wrong_concepts"
            " GROUP BY evidence, stored_concept_id"
            " ORDER BY encounter_count DESC",
        )
        return [
            {
                "evidence": r[0],
                "stored_concept_id": r[1],
                "stored_name": r[2],
                "resolved_concept_id": r[3],
                "resolved_name": r[4],
                "resolver_score": r[5],
                "semantic_tag": r[6],
                "encounter_count": r[7],
            }
            for r in cur
        ]

    def all_ner_examples(self) -> Iterator[dict[str, Any]]:
        cur = self._con.execute(
            "SELECT sentence, entity, start_char, end_char,"
            "       concept_id, term, semantic_tag, assertion"
            " FROM ner_examples",
        )
        for r in cur:
            yield {
                "sentence": r[0],
                "entity": r[1],
                "start_char": r[2],
                "end_char": r[3],
                "concept_id": r[4],
                "term": r[5],
                "semantic_tag": r[6],
                "assertion": r[7],
            }

    def close(self) -> None:
        self._con.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Bedrock on-demand pricing per 1 M tokens (USD), April 2026.
# Sonnet 3.5/3.7 = $3 input / $15 output.
# Haiku 3.5      = $0.80 input / $4 output.
_PRICING: dict[str, tuple[float, float]] = {
    "sonnet": (3.0, 15.0),
    "haiku": (0.80, 4.0),
}
_DEFAULT_PRICING = (3.0, 15.0)


def _compute_cost_usd(
    input_tokens: int | None,
    output_tokens: int | None,
    model_id: str,
) -> float | None:
    """Return estimated cost in USD, or None if token counts are missing."""
    if not input_tokens and not output_tokens:
        return None
    model_lower = (model_id or "").lower()
    if "haiku" in model_lower:
        price_in, price_out = _PRICING["haiku"]
    else:
        price_in, price_out = _PRICING["sonnet"]
    return (input_tokens or 0) * price_in / 1_000_000 + (
        output_tokens or 0
    ) * price_out / 1_000_000
