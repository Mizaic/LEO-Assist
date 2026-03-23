"""Fix over-captured lab entity text spans in anchor_mining TrainingLabel nodes.

For structured GP lab result lines the anchor mining captured the full line:
    "Serum urea level (XM0lt) 10.4 mmol/L [2.5 - 7.8] - Outside reference range"

The entity should be just the observable name:
    "Serum urea level"

The entity dict already has `value`, `unit`, and `normalized` parsed correctly
by the extraction pipeline — only `text` and `end` need correcting.

Truncation strategy (applied in order):
  1. If `value` + `unit` both present: find "{value} {unit}" in text, truncate before it.
  2. Elif UK GP Read code pattern `(XYZ..)` followed by a digit: truncate before it.
  3. Elif ` - observation` / ` - Outside reference range` type suffix: strip it,
     then try rule 2 again on the cleaned string.
  4. Else: leave unchanged (can't safely infer the boundary).

Usage:
    python scripts/_fix_lab_entity_overcapture.py --dry-run   # preview only
    python scripts/_fix_lab_entity_overcapture.py             # write to Neo4j
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(_REPO_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_REPO_ROOT / "secrets" / ".env", override=False)

from libs.neo4j_client.client import PatientGraphClient

# UK GP Read code: alphanumeric + dots, no hyphens, 3-8 chars, in parens,
# followed by whitespace and a digit (the result value).
_READ_CODE_THEN_DIGIT = re.compile(r'\s*\([A-Za-z0-9.]{3,8}\)\s+\d')

# Trailing Read code at end of string (no digit follows — already truncated).
_TRAILING_READ_CODE = re.compile(r'\s*\([A-Za-z0-9.]{3,8}\)\s*$')

# Observation-type trailing suffixes added by GP system exports.
_OBS_SUFFIX = re.compile(
    r'\s*-\s*(?:observation|outside reference range|inside reference range|'
    r'out of range|in range|high|low|normal|abnormal|borderline)[^(\[]*$',
    re.IGNORECASE,
)

BATCH_SIZE = 500


def _strip_read_code(text: str) -> str:
    """Remove a trailing UK GP Read code in parens, e.g. 'Serum urea level (XM0lt)'."""
    return _TRAILING_READ_CODE.sub("", text).strip()


def _truncate(text: str, value: str | None, unit: str | None) -> str | None:
    """Return truncated text, or None if no truncation needed/safe."""
    if not text:
        return None

    candidate = text

    # Rule 1: value + unit both known — most precise anchor.
    if value and unit:
        needle = f"{value} {unit}"
        idx = candidate.find(needle)
        if idx > 0:
            new_text = _strip_read_code(candidate[:idx].rstrip(" -(["))
            if new_text and new_text != candidate:
                return new_text

    # Rule 2: Read code pattern followed by a digit — truncate before Read code.
    m = _READ_CODE_THEN_DIGIT.search(candidate)
    if m and m.start() > 0:
        new_text = candidate[:m.start()].strip()
        if new_text and new_text != candidate:
            return new_text

    # Rule 3: Strip observation-type suffix, then retry rule 2.
    cleaned = _OBS_SUFFIX.sub("", candidate).strip()
    if cleaned != candidate:
        m = _READ_CODE_THEN_DIGIT.search(cleaned)
        if m and m.start() > 0:
            new_text = cleaned[:m.start()].strip()
            if new_text and new_text != candidate:
                return new_text
        # Suffix removed but no Read code — return de-suffixed form.
        if cleaned and cleaned != candidate:
            return cleaned

    return None  # no safe truncation found


def _fix_entities(entities: list[dict]) -> tuple[list[dict], int]:
    """Apply truncation to each entity. Returns (updated_list, n_changed)."""
    changed = 0
    result = []
    for ent in entities:
        text = ent.get("text") or ""
        value = str(ent.get("value") or "").strip()
        unit = str(ent.get("unit") or "").strip()
        start = int(ent.get("start") or 0)

        new_text = _truncate(text, value or None, unit or None)
        if new_text:
            ent = dict(ent)  # don't mutate original
            ent["text"] = new_text
            ent["end"] = start + len(new_text)
            changed += 1
        result.append(ent)
    return result, changed


def main(dry_run: bool) -> None:
    client = PatientGraphClient()
    try:
        print("Fetching anchor_mining TrainingLabel nodes…")
        rows = client.run(
            """
            MATCH (tl:TrainingLabel)
            WHERE tl.source = 'anchor_mining'
              AND tl.include = true
              AND tl.entities_json IS NOT NULL
            RETURN tl.label_id AS label_id, tl.entities_json AS ej
            """
        )
        print(f"  Found {len(rows)} records")

        updates: list[dict] = []
        total_entities = 0
        total_changed = 0
        example_changes: list[tuple[str, str]] = []

        for row in rows:
            label_id = row["label_id"]
            try:
                entities = json.loads(row["ej"])
            except Exception:
                continue

            total_entities += len(entities)
            fixed, n_changed = _fix_entities(entities)

            if n_changed:
                total_changed += n_changed
                updates.append({
                    "label_id": label_id,
                    "entities_json": json.dumps(fixed, default=str),
                })
                # Collect first few examples for display
                if len(example_changes) < 20:
                    for orig, upd in zip(entities, fixed):
                        if orig.get("text") != upd.get("text"):
                            example_changes.append((orig["text"], upd["text"]))

        print(f"\nEntities inspected : {total_entities}")
        print(f"Entities to fix    : {total_changed}")
        print(f"Records to update  : {len(updates)}")

        if example_changes:
            print("\nSample changes (before -> after):")
            for before, after in example_changes[:10]:
                print(f"  BEFORE: {before[:80]!r}")
                print(f"  AFTER : {after!r}")
                print()

        if dry_run:
            print("\n[DRY RUN] No changes written.")
            return

        if not updates:
            print("Nothing to update.")
            return

        print(f"\nWriting {len(updates)} records in batches of {BATCH_SIZE}…")
        written = 0
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i:i + BATCH_SIZE]
            client.run(
                """
                UNWIND $rows AS r
                MATCH (tl:TrainingLabel {label_id: r.label_id})
                SET tl.entities_json = r.entities_json,
                    tl.updated_at    = datetime()
                """,
                rows=batch,
            )
            written += len(batch)
            print(f"  {written}/{len(updates)} written")

        print(f"\nDone. {total_changed} entity spans corrected across {len(updates)} records.")

    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing to Neo4j")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
