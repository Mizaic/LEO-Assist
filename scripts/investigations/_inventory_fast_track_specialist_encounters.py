"""Inventory all encounters containing 'Seen in fast track' phrases.

Queries the patient graph for encounters whose text contains the phrase,
extracts the specific clinic phrase using regex, and writes a JSONL file
for use by subsequent pinning, writeback, and episode-rerun scripts.

Output: scripts/investigations/encounter_audit/fast_track_specialist_encounters.jsonl

Each line:
  {
    "patient_id": "...",
    "encounter_id": "...",
    "date": "...",
    "matched_phrase": "Seen in fast track suspected X clinic",
    "existing_doc_count": 0
  }

Run:
    python scripts/investigations/_inventory_fast_track_specialist_encounters.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

# -- Output path --
OUT_DIR = ROOT / "scripts" / "investigations" / "encounter_audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "fast_track_specialist_encounters.jsonl"

# -- Regex to extract the specific clinic phrase from encounter text --
# Matches e.g. "Seen in fast track suspected breast cancer clinic"
# Also handles "Seen in 2WW Clinic" variants and template-wrapped forms
_PHRASE_RE = re.compile(
    r"[Ss]een\s+in\s+(?:fast\s+track|2WW)\s+(?:suspected\s+)?[\w\s]+?(?:cancer|tumour|malignancy|clinic)\s*(?:clinic)?",
    re.IGNORECASE,
)

# Normalised fallback for template entries like "2WW Seen in 2WW Clinic?: Seen in fast track..."
_FAST_TRACK_SIMPLE_RE = re.compile(
    r"[Ss]een\s+in\s+fast\s+track\s+suspected\s+[\w\s]+?clinic",
    re.IGNORECASE,
)

# -- Cypher: find all encounters with 'seen in fast track' in any text field --
_Q_TEXT = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toLower(
        coalesce(e.text, '') + ' ' +
        coalesce(e.note, '') + ' ' +
        coalesce(e.description, '') + ' ' +
        coalesce(e.title, '')
      ) CONTAINS 'seen in fast track'
RETURN
    toString(p.id)   AS patient_id,
    toString(e.id)   AS encounter_id,
    coalesce(toString(e.date), '') AS date,
    coalesce(e.text, e.note, e.description, e.title, '') AS enc_text
ORDER BY patient_id, date
"""

# -- Cypher: count existing DOCUMENTS on one encounter --
_Q_DOC_COUNT = """
MATCH (e:Encounter)-[:DOCUMENTS]->(c)
WHERE toString(e.id) = $eid
RETURN count(c) AS n
"""


def _extract_phrases(text: str) -> list[str]:
    """Return all distinct 'Seen in fast track...' phrases found in text."""
    hits = _FAST_TRACK_SIMPLE_RE.findall(text)
    if not hits:
        hits = _PHRASE_RE.findall(text)
    # Normalise whitespace and deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for h in hits:
        norm = " ".join(h.strip().split())
        if norm.lower() not in seen:
            seen.add(norm.lower())
            out.append(norm)
    return out


def main() -> None:
    client = PatientGraphClient()
    rows: list[dict] = []

    try:
        with client.session() as session:
            results = list(session.run(_Q_TEXT))
            print(f"Found {len(results)} encounters with 'seen in fast track' text.")

            for rec in results:
                patient_id = rec["patient_id"]
                encounter_id = rec["encounter_id"]
                date = rec["date"]
                enc_text = rec["enc_text"] or ""

                phrases = _extract_phrases(enc_text)
                if not phrases:
                    # Keep entry with empty phrase so we do not silently drop it
                    phrases = [""]

                # Count existing DOCUMENTS relationships
                doc_result = session.run(_Q_DOC_COUNT, eid=encounter_id).single()
                existing_docs = int(doc_result["n"]) if doc_result else 0

                for phrase in phrases:
                    rows.append(
                        {
                            "patient_id": patient_id,
                            "encounter_id": encounter_id,
                            "date": date,
                            "matched_phrase": phrase,
                            "existing_doc_count": existing_docs,
                        }
                    )
    finally:
        client.close()

    with OUT_FILE.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    unique_patients = len({r["patient_id"] for r in rows})
    unique_encounters = len({r["encounter_id"] for r in rows})
    unique_phrases = len(
        {r["matched_phrase"].lower() for r in rows if r["matched_phrase"]}
    )

    print()
    print(f"Written {len(rows)} rows to {OUT_FILE}")
    print(f"  Unique patients   : {unique_patients}")
    print(f"  Unique encounters : {unique_encounters}")
    print(f"  Unique phrases    : {unique_phrases}")
    print()
    print("Phrase breakdown:")
    from collections import Counter

    counts = Counter(r["matched_phrase"].lower() for r in rows if r["matched_phrase"])
    for phrase, count in counts.most_common():
        print(f"  {count:4d}  {phrase}")


if __name__ == "__main__":
    main()
