"""Inventory all encounters containing fast-track referral phrases.

Mirrors _inventory_fast_track_specialist_encounters.py but for referrals.
Searches for 'fast track referral', '2WW referral', 'two week wait referral'
in encounter text, extracts the specific cancer-site phrase, checks whether a
matching DOCUMENTS relationship already exists, and writes a JSONL report.

Output: scripts/investigations/encounter_audit/fast_track_referral_encounters.jsonl

Run:
    python scripts/investigations/_inventory_fast_track_referral_encounters.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

OUT_DIR = ROOT / "scripts" / "investigations" / "encounter_audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "fast_track_referral_encounters.jsonl"

# -- Match referral phrases from encounter text --
_PHRASE_RE = re.compile(
    r"fast\s+track\s+referral\s+for\s+suspected\s+[\w][\w\s\-]+?(?:cancer|tumour|malignancy|symptoms)"
    r"|two\s+week\s+wait\s+referral(?:\s+for\s+[\w\s\-]+?(?:cancer|tumour|malignancy))?"
    r"|2\s*ww\s+referral(?:\s+for\s+[\w\s\-]+?(?:cancer|tumour|malignancy))?",
    re.IGNORECASE,
)

_Q_TEXT = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toLower(
        coalesce(e.text, '') + ' ' +
        coalesce(e.note, '') + ' ' +
        coalesce(e.description, '')
      ) CONTAINS 'fast track referral'
   OR toLower(
        coalesce(e.text, '') + ' ' +
        coalesce(e.note, '') + ' ' +
        coalesce(e.description, '')
      ) CONTAINS 'two week wait referral'
   OR toLower(
        coalesce(e.text, '') + ' ' +
        coalesce(e.note, '') + ' ' +
        coalesce(e.description, '')
      ) CONTAINS '2ww referral'
RETURN
    toString(p.id)  AS patient_id,
    toString(e.id)  AS encounter_id,
    coalesce(toString(e.date), '') AS date,
    coalesce(e.text, e.note, e.description, '') AS enc_text
ORDER BY patient_id, date
"""

# Count DOCUMENTS that look like fast-track referrals on this encounter
_Q_DOC_COUNT = """
MATCH (e:Encounter)-[:DOCUMENTS]->(c)
WHERE toString(e.id) = $eid
  AND (toLower(coalesce(c.name,'')) CONTAINS 'fast track'
       OR toLower(coalesce(c.name,'')) CONTAINS 'referral')
RETURN count(c) AS n
"""

# All DOCUMENTS on the encounter regardless of concept
_Q_ALL_DOC_COUNT = """
MATCH (e:Encounter)-[:DOCUMENTS]->(c)
WHERE toString(e.id) = $eid
RETURN count(c) AS n
"""


def _extract_phrases(text: str) -> list[str]:
    hits = _PHRASE_RE.findall(text)
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
    phrase_counter: Counter = Counter()
    uncoded_count = 0

    try:
        with client.session() as session:
            results = list(session.run(_Q_TEXT))
            print(f"Found {len(results)} encounters with fast-track referral text.")
            unique_patients = len({r['patient_id'] for r in results})
            print(f"Unique patients: {unique_patients}")
            print()

            for rec in results:
                patient_id = rec["patient_id"]
                encounter_id = rec["encounter_id"]
                date = rec["date"]
                enc_text = rec["enc_text"] or ""

                phrases = _extract_phrases(enc_text)
                if not phrases:
                    phrases = [""]

                ref_doc_result = session.run(_Q_DOC_COUNT, eid=encounter_id).single()
                referral_doc_count = int(ref_doc_result["n"]) if ref_doc_result else 0

                all_doc_result = session.run(_Q_ALL_DOC_COUNT, eid=encounter_id).single()
                all_doc_count = int(all_doc_result["n"]) if all_doc_result else 0

                for phrase in phrases:
                    if phrase:
                        phrase_counter[phrase.lower()] += 1
                    rows.append({
                        "patient_id": patient_id,
                        "encounter_id": encounter_id,
                        "date": date,
                        "matched_phrase": phrase,
                        "referral_doc_count": referral_doc_count,
                        "all_doc_count": all_doc_count,
                    })

                if phrases and phrases[0] and referral_doc_count == 0:
                    uncoded_count += 1

    finally:
        client.close()

    with OUT_FILE.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    unique_patients_out = len({r["patient_id"] for r in rows})
    unique_encounters_out = len({r["encounter_id"] for r in rows})
    unique_phrases_out = len({r["matched_phrase"].lower() for r in rows if r["matched_phrase"]})

    print(f"Written {len(rows)} rows to {OUT_FILE}")
    print(f"  Unique patients   : {unique_patients_out}")
    print(f"  Unique encounters : {unique_encounters_out}")
    print(f"  Unique phrases    : {unique_phrases_out}")
    print(f"  Encounters with phrase but NO referral DOCUMENTS: {uncoded_count}")
    print()
    print("Phrase breakdown (top 30):")
    for phrase, count in phrase_counter.most_common(30):
        print(f"  {count:4d}  {phrase}")


if __name__ == "__main__":
    main()
