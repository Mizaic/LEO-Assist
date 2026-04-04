"""Backfill evidence_sentence on DOCUMENTS relationships.

For each DOCUMENTS relationship where evidence_sentence IS NULL and evidence
(span text) is present: load the encounter text, locate the sentence
containing the span, de-identify it, and write evidence_sentence,
evidence_start, evidence_end back to the relationship.

Features
--------
- Batch: 500 relationships per transaction.
- Progress: logged every 1000 relationships processed.
- Resume: WHERE r.evidence_sentence IS NULL skips already-filled rows.
- Dry-run: --dry-run prints the first 10 records without writing.
- Pre-flight: queries total count and estimates duration before starting.

Usage
-----
    python scripts/backfill_evidence_sentences.py
    python scripts/backfill_evidence_sentences.py --dry-run
    python scripts/backfill_evidence_sentences.py --batch-size 200
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402
from libs.utils.deidentify import deidentify_with_span  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_evidence")

_BATCH_SIZE = 500
_LOG_EVERY = 1000
_RECORDS_PER_MINUTE_ESTIMATE = 500

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

_Q_COUNT_MISSING = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(s)
WHERE r.evidence_sentence IS NULL
  AND r.evidence IS NOT NULL
  AND trim(toString(r.evidence)) <> ''
RETURN count(r) AS total
"""

_Q_FETCH_BATCH = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(s)
WHERE r.evidence_sentence IS NULL
  AND r.evidence IS NOT NULL
  AND trim(toString(r.evidence)) <> ''
RETURN
    toString(elementId(r)) AS rel_id,
    toString(e.id)         AS encounter_id,
    coalesce(e.text, '')   AS encounter_text,
    toString(r.evidence)   AS span_text,
    r.sentence_index       AS sentence_index
ORDER BY r.sentence_index
SKIP $skip
LIMIT $limit
"""

_Q_UPDATE_RELATIONSHIP = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(s)
WHERE toString(elementId(r)) = $rel_id
SET
    r.evidence_sentence = $evidence_sentence,
    r.evidence_start    = $evidence_start,
    r.evidence_end      = $evidence_end
"""


# ---------------------------------------------------------------------------
# Sentence finder
# ---------------------------------------------------------------------------

def _find_sentence(text: str, span_text: str, sentence_index: int | None) -> str:
    """Return the sentence most likely containing span_text.

    Strategy:
    1. If sentence_index is set, split naively on sentence boundaries and
       return that index (bounded by list length).
    2. Otherwise scan for the first sentence containing the span (case-insensitive).
    3. Fall back to the full text (truncated to 1000 chars) if not found.
    """
    sentences = _split_sentences(text)
    if sentence_index is not None and 0 <= int(sentence_index) < len(sentences):
        return sentences[int(sentence_index)]
    span_lower = span_text.lower()
    for sent in sentences:
        if span_lower in sent.lower():
            return sent
    return text[:1000]


def _split_sentences(text: str) -> list[str]:
    """Rough sentence splitter for backfill (no NLP dependency required)."""
    import re
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Backfill logic
# ---------------------------------------------------------------------------

def _process_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Return update dict or None if span cannot be located."""
    encounter_text = str(row.get("encounter_text") or "")
    span_text = str(row.get("span_text") or "").strip()
    if not encounter_text or not span_text:
        return None
    sentence = _find_sentence(encounter_text, span_text, row.get("sentence_index"))
    deident, ev_start, ev_end = deidentify_with_span(sentence, span_text)
    if ev_start == -1:
        logger.debug(
            "Span %r not found after de-ident for rel_id=%s -- skip",
            span_text, row.get("rel_id"),
        )
        return None
    return {
        "rel_id": row["rel_id"],
        "evidence_sentence": deident,
        "evidence_start": ev_start,
        "evidence_end": ev_end,
    }


def backfill(batch_size: int, dry_run: bool) -> None:
    client = PatientGraphClient()
    try:
        # Pre-flight count
        with client.session() as session:
            count_row = session.run(_Q_COUNT_MISSING).single()
        total = int(count_row["total"]) if count_row else 0

        if total == 0:
            logger.info("All DOCUMENTS already have evidence_sentence. Nothing to do.")
            return

        est_minutes = max(1, total // _RECORDS_PER_MINUTE_ESTIMATE)
        logger.info(
            "Backfill needed: %d relationships. "
            "Estimated duration: ~%d minute(s) at %d records/min.",
            total, est_minutes, _RECORDS_PER_MINUTE_ESTIMATE,
        )

        if dry_run:
            logger.info("[DRY RUN] Previewing first 10 records ...")

        processed = 0
        written = 0
        skipped = 0
        skip_offset = 0
        preview_shown = 0

        while True:
            with client.session() as session:
                rows = [dict(r) for r in session.run(
                    _Q_FETCH_BATCH, skip=skip_offset, limit=batch_size
                )]

            if not rows:
                break

            updates: list[dict[str, Any]] = []
            for row in rows:
                update = _process_row(row)
                if update:
                    updates.append(update)
                else:
                    skipped += 1

            if dry_run:
                for upd in updates[:max(0, 10 - preview_shown)]:
                    logger.info(
                        "[DRY RUN] rel_id=%s sentence=%r start=%d end=%d",
                        upd["rel_id"],
                        upd["evidence_sentence"][:60],
                        upd["evidence_start"],
                        upd["evidence_end"],
                    )
                    preview_shown += 1
                if preview_shown >= 10:
                    logger.info("[DRY RUN] Preview complete.")
                    return
                skip_offset += batch_size
                processed += len(rows)
                continue

            if updates:
                with client.session() as session:
                    for upd in updates:
                        session.run(
                            _Q_UPDATE_RELATIONSHIP,
                            rel_id=upd["rel_id"],
                            evidence_sentence=upd["evidence_sentence"],
                            evidence_start=upd["evidence_start"],
                            evidence_end=upd["evidence_end"],
                        )
                written += len(updates)

            processed += len(rows)

            if processed % _LOG_EVERY < batch_size:
                logger.info(
                    "Progress: %d/%d processed  written=%d  skipped=%d",
                    processed, total, written, skipped,
                )

            if len(rows) < batch_size:
                break

            # Offset does not advance because written rows no longer match
            # the WHERE clause (evidence_sentence IS NULL). But skipped rows
            # still match, so we advance by the skipped count.
            skip_offset += skipped

        logger.info(
            "Backfill complete. Total processed=%d  written=%d  skipped=%d",
            processed, written, skipped,
        )
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill evidence_sentence on DOCUMENTS")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_BATCH_SIZE,
        metavar="N",
        help=f"Relationships per transaction (default {_BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview first 10 records without writing",
    )
    args = parser.parse_args()
    backfill(batch_size=args.batch_size, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
