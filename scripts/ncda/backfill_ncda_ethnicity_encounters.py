"""Write NCDA ethnicity DOCUMENTS (+ patient HAS_FINDING) links from encounter text.

Uses longest synonym match per encounter against ``snomed_ncda_ethnicity_mapping.json``.
Only writes when encounter text contains a configured synonym substring (case-insensitive).
Skips encounters that already have a DOCUMENTS edge with ``domain = 'ethnicity'``.

Run:
    python scripts/ncda/backfill_ncda_ethnicity_encounters.py --limit 500

Requires Patient Graph Neo4j credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

from libs.cypher.documents_queries import upsert_encounter_documents_link  # noqa: E402
from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

MAPPING_PATH = ROOT / "configs" / "snomed" / "snomed_ncda_ethnicity_mapping.json"
SOURCE = "ncda_ethnicity_backfill"


def _load_synonyms(mapping: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """Return list of (synonym_lower, synonym_surface, concept_id, preferred_term)."""
    rows: list[tuple[str, str, str, str]] = []
    for _label, payload in (mapping.get("mappings") or {}).items():
        cid = str(payload.get("concept_id") or "")
        pt = str(payload.get("preferred_term") or "")
        syns = list(payload.get("guideline_synonyms") or [])
        for s in syns:
            if not s or len(s.strip()) < 3:
                continue
            surf = s.strip()
            rows.append((surf.lower(), surf, cid, pt))
    rows.sort(key=lambda x: len(x[0]), reverse=True)
    return rows


def _pick_best_match(text_lc: str, syn_rows: list[tuple[str, str, str, str]]) -> tuple[str, str, str] | None:
    """Return (concept_id, preferred_term, matched_surface) or None."""
    for low, surf, cid, pt in syn_rows:
        if low in text_lc:
            return cid, pt, surf
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    syn_rows = _load_synonyms(mapping)

    kg = PatientGraphClient()
    written = 0
    with kg.session() as session:
        result = session.run(
            """
            MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
            WHERE e.text IS NOT NULL AND size(trim(e.text)) > 40
              AND (
                toLower(e.text) CONTAINS 'ethnic category'
                OR toLower(e.text) CONTAINS 'ethnic group'
                OR toLower(e.text) CONTAINS ' ethnic '
              )
              AND NOT EXISTS {
                MATCH (e)-[d:DOCUMENTS]->(:Clinical_finding)
                WHERE coalesce(d.domain, '') = 'ethnicity'
              }
            RETURN toString(p.id) AS pid, toString(e.id) AS eid, e.text AS text
            LIMIT $lim
            """,
            lim=int(args.limit),
        )
        rows = [dict(r) for r in result]

        for r in rows:
            text = str(r.get("text") or "")
            text_lc = text.lower()
            picked = _pick_best_match(text_lc, syn_rows)
            if not picked:
                continue
            cid, pt, surf = picked
            upsert_encounter_documents_link(
                session,
                patient_id=str(r["pid"]),
                encounter_id=str(r["eid"]),
                concept_id=cid,
                semantic_tag="Clinical finding",
                name=pt,
                evidence=text[:8000],
                evidence_sentence=surf,
                assertion="present",
                source=SOURCE,
                domain="ethnicity",
                confidence=1.0,
            )
            written += 1

    print(f"Written ethnicity DOCUMENTS links: {written}")


if __name__ == "__main__":
    main()
