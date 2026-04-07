"""Discover document_transfer encounters tagged as clinic_letter plus context.

Queries patient graph counts, samples texts, same-day DOCUMENTS concepts,
and optionally calls terminology API for EHR composition descendants.

Run:
    python scripts/investigations/_discover_letter_encounters.py
    python scripts/investigations/_discover_letter_encounters.py --no-terminology
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

_Q_COUNT = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.classification_content_type = 'document_transfer'
  AND 'clinic_letter' IN coalesce(e.classification_encounter_purpose, [])
RETURN count(e) AS letter_encounters,
       count(DISTINCT p) AS unique_patients
"""

_Q_LETTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.classification_content_type = 'document_transfer'
  AND 'clinic_letter' IN coalesce(e.classification_encounter_purpose, [])
RETURN toString(p.id) AS pid,
       toString(e.id) AS eid,
       toString(e.date) AS enc_date,
       e.text AS text,
       e.classification_encounter_purpose AS purpose
ORDER BY enc_date
"""

_Q_WINDOW = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
  AND toString(e.date) >= $start_d
  AND toString(e.date) <= $end_d
RETURN toString(e.id) AS eid,
       toString(e.date) AS enc_date,
       coalesce(e.classification_content_type, '') AS content_type,
       e.text AS text
ORDER BY enc_date, eid
"""

_Q_SAME_DAY_CODES = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid
  AND toString(e.date) = $day
RETURN toString(e.id) AS eid,
       c.conceptId AS cid,
       c.name AS cname,
       coalesce(r.assertion, 'present') AS assertion
ORDER BY eid, cname
LIMIT 40
"""


def _terminology_search(base: str, q: str, limit: int = 20) -> list[dict]:
    try:
        r = httpx.get(
            f"{base.rstrip('/')}/terminology/search",
            params={"q": q, "limit": limit},
            timeout=60.0,
        )
        r.raise_for_status()
        return list(r.json() or [])
    except Exception as exc:  # noqa: BLE001
        print(f"  search failed ({q}): {exc}")
        return []


def _terminology_descendants(base: str, concept_id: str, depth: int = 5) -> list[dict]:
    try:
        r = httpx.get(
            f"{base.rstrip('/')}/terminology/concepts/{concept_id}/descendants",
            params={"depth": depth, "limit": 500},
            timeout=120.0,
        )
        r.raise_for_status()
        return list(r.json() or [])
    except Exception as exc:  # noqa: BLE001
        print(f"  descendants failed ({concept_id}): {exc}")
        return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--no-terminology",
        action="store_true",
        help="Skip HTTP calls to terminology API",
    )
    ap.add_argument(
        "--terminology-url",
        default=os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001"),
        help="Base URL for terminology service",
    )
    args = ap.parse_args()

    pg = PatientGraphClient()
    try:
        cnt_rows = pg.run(_Q_COUNT)
        cnt = (cnt_rows or [{}])[0]
        print("=" * 72)
        print("CLINIC LETTER ENCOUNTERS (document_transfer + clinic_letter)")
        print("=" * 72)
        print(
            f"  letter_encounters={cnt.get('letter_encounters')}  "
            f"unique_patients={cnt.get('unique_patients')}"
        )
        print()

        rows = pg.run(_Q_LETTERS) or []

        for r in rows[:15]:
            pid, eid, d = r["pid"], r["eid"], r["enc_date"]
            text = (r.get("text") or "").replace("\n", " ")[:160]
            print(f"  {d}  pid={pid}  eid={eid}")
            print(f"    text: {text!r}")
            try:
                dt = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            start_d = (dt - timedelta(days=3)).isoformat()
            end_d = (dt + timedelta(days=14)).isoformat()
            w = (
                pg.run(
                    _Q_WINDOW,
                    pid=str(pid),
                    start_d=start_d,
                    end_d=end_d,
                )
                or []
            )
            print(f"    window [-3,+14]d encounters: {len(w)}")
            same = (
                pg.run(
                    _Q_SAME_DAY_CODES,
                    pid=str(pid),
                    day=str(d)[:10],
                )
                or []
            )
            if same:
                print(f"    same-day coded concepts (sample): {same[:6]}")
            print()

        if args.no_terminology:
            return

        base = args.terminology_url
        print("=" * 72)
        print(f"TERMINOLOGY API ({base})")
        print("=" * 72)
        desc = _terminology_descendants(base, "24501000000105", depth=5)
        print(f"  Descendants of 24501000000105 (EHR composition types): {len(desc)}")
        for d in desc[:25]:
            print(
                f"    {d.get('snomed_concept_id')}  "
                f"{d.get('term')}  [{d.get('semantic_tag')}]"
            )
        if len(desc) > 25:
            print(f"    ... and {len(desc) - 25} more")

        for q in (
            "clinic letter",
            "discharge letter",
            "specialist letter",
            "discharge summary",
            "clinical letter",
        ):
            hits = _terminology_search(base, q, limit=12)
            print(f"  search {q!r}: {len(hits)} hits")
            for h in hits[:5]:
                print(f"    {h.get('id')}  {h.get('fsn') or h.get('term')}")
    finally:
        pg.close()


if __name__ == "__main__":
    main()
