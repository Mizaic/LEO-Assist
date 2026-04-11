"""Re-apply normalize_observable_entities AND create missing qualifier_value /
finding entities for already-truncated observable entities.

Two populations:
1. Entities where text still contains the full lab line (normalize can split).
2. Entities where our overcapture fix already truncated text to just the test
   name, but value/unit are populated and the encounter text still has the full
   line — we derive qualifier_value and finding from the encounter text.

Usage:
    python scripts/_fix_observable_split.py --dry-run   # preview
    python scripts/_fix_observable_split.py              # write to Neo4j
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
from libs.ner.observable_post_processor import (
    normalize_observable_entities,
    _detect_interpretation,
    _find_nearest_start,
)

BATCH_SIZE = 500


def _is_observable(label: str) -> bool:
    return label.lower().replace(" ", "_") == "observable_entity"


def _emit_extras_from_encounter(
    encounter_text: str,
    entities: list[dict],
) -> list[dict]:
    """For observable entities where text is already clean (no value/unit in
    text) but value + unit ARE populated, find the value+unit and any
    interpretation suffix in the encounter text and emit extra entities.
    """
    extras: list[dict] = []
    existing_qv_texts = {
        e.get("text", "").strip().lower()
        for e in entities
        if e.get("label") == "qualifier_value"
    }
    existing_interp_qualifiers = {
        e.get("interpretation_qualifier", "")
        for e in entities
        if e.get("label") == "finding" and e.get("interpretation_qualifier")
    }

    for ent in entities:
        if not _is_observable(str(ent.get("label", ""))):
            continue

        value = str(ent.get("value") or "").strip()
        unit = str(ent.get("unit") or "").strip()
        ent_text = str(ent.get("text") or "").strip()

        if not value or not unit:
            continue

        value_span = f"{value} {unit}"
        # If the entity text already contains the value, normalize will handle it
        if value_span.lower() in ent_text.lower():
            continue

        # Find value+unit in the encounter text
        vu_start = _find_nearest_start(
            encounter_text,
            value_span,
            around=int(ent.get("end", 0) or 0),
            existing_entities=entities + extras,
        )
        if vu_start is None:
            continue

        # Emit qualifier_value
        if value_span.lower() not in existing_qv_texts:
            extras.append(
                {
                    "text": value_span,
                    "label": "qualifier_value",
                    "start": vu_start,
                    "end": vu_start + len(value_span),
                    "confidence": float(ent.get("confidence", 0.0) or 0.0),
                }
            )

        # Check for interpretation suffix after value+unit in encounter text
        after_vu_pos = vu_start + len(value_span)
        # Skip reference range bracket if present
        remaining = encounter_text[after_vu_pos:]
        ref_match = re.match(r"\s*\[[^\]]*\]", remaining)
        if ref_match:
            remaining = remaining[ref_match.end() :]

        interp = _detect_interpretation(remaining)
        if interp:
            interp_text, interp_qualifier = interp
            if interp_qualifier not in existing_interp_qualifiers:
                interp_start = _find_nearest_start(
                    encounter_text,
                    interp_text,
                    around=after_vu_pos,
                )
                if interp_start is not None:
                    extras.append(
                        {
                            "text": interp_text,
                            "label": "finding",
                            "start": interp_start,
                            "end": interp_start + len(interp_text),
                            "confidence": float(ent.get("confidence", 0.0) or 0.0),
                            "interpretation_qualifier": interp_qualifier,
                            "parent_observable_text": ent_text,
                        }
                    )

    return extras


def main(dry_run: bool) -> None:
    client = PatientGraphClient()
    try:
        print("Fetching included TrainingLabel records...")
        rows = client.run("""
            MATCH (tl:TrainingLabel)
            WHERE tl.include = true AND tl.entities_json IS NOT NULL
            RETURN tl.label_id AS label_id, tl.text AS encounter_text,
                   tl.entities_json AS ej
            """)
        print(f"  Found {len(rows)} records")

        updates: list[dict] = []
        total_new_qv = 0
        total_new_finding = 0
        total_records_changed = 0
        examples: list[dict] = []

        for row in rows:
            label_id = row["label_id"]
            encounter_text = row.get("encounter_text") or ""
            try:
                entities = json.loads(row["ej"])
            except Exception:
                continue

            has_observable = any(
                _is_observable(str(e.get("label", ""))) for e in entities
            )
            if not has_observable:
                continue

            # Pass 1: run normalize (handles entities where text still has full line)
            normalized = normalize_observable_entities(
                encounter_text,
                entities,
                add_qualifier_value=True,
                emit_interpretation_finding=True,
            )

            # Pass 2: for already-clean entities, derive extras from encounter text
            encounter_extras = _emit_extras_from_encounter(encounter_text, normalized)
            if encounter_extras:
                normalized = normalized + encounter_extras

            if len(normalized) == len(entities):
                continue

            new_qv = sum(
                1
                for e in normalized
                if e.get("label") == "qualifier_value"
                and not any(
                    orig.get("label") == "qualifier_value"
                    and orig.get("text") == e.get("text")
                    for orig in entities
                )
            )
            new_finding = sum(
                1
                for e in normalized
                if e.get("label") == "finding"
                and e.get("interpretation_qualifier")
                and not any(
                    orig.get("interpretation_qualifier")
                    == e.get("interpretation_qualifier")
                    and orig.get("parent_observable_text")
                    == e.get("parent_observable_text")
                    for orig in entities
                )
            )

            total_new_qv += new_qv
            total_new_finding += new_finding
            total_records_changed += 1

            updates.append(
                {
                    "label_id": label_id,
                    "entities_json": json.dumps(normalized, default=str),
                }
            )

            if len(examples) < 15:
                examples.append(
                    {
                        "label_id": label_id[:20],
                        "before": len(entities),
                        "after": len(normalized),
                        "new_qv": new_qv,
                        "new_finding": new_finding,
                        "encounter": encounter_text[:90],
                    }
                )

        print(f"\nRecords to update      : {total_records_changed}")
        print(f"New qualifier_value    : {total_new_qv}")
        print(f"New finding entities   : {total_new_finding}")

        if examples:
            print("\nSample changes:")
            for ex in examples:
                print(
                    f"  {ex['label_id']} | {ex['before']} -> {ex['after']} entities "
                    f"(+{ex['new_qv']} qv, +{ex['new_finding']} finding)"
                )
                print(f"    {ex['encounter']!r}")

        if dry_run:
            print("\n[DRY RUN] No changes written.")
            return

        if not updates:
            print("Nothing to update.")
            return

        print(f"\nWriting {len(updates)} records in batches of {BATCH_SIZE}...")
        written = 0
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i : i + BATCH_SIZE]
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

        print(
            f"\nDone. {total_records_changed} records updated: "
            f"+{total_new_qv} qualifier_value, +{total_new_finding} finding entities."
        )

    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to Neo4j",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
