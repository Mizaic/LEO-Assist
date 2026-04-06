"""Diagnose why newly added SurfaceForm edges are losing to existing Term matches.

Queries:
  1. Show all SurfaceForm nodes for the target texts
  2. Show the Term nodes that match these texts in SNOMED
  3. Show what the resolver's EXACT_SURFACE_FORM_QUERY actually returns
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from neo4j import GraphDatabase

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
pwd = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

CHECK_FORMS = [
    ("PSA test",             "63476009"),
    ("urgent ultrasound",    "16310003"),
    ("CA125",                "909121000000107"),
    ("urine dipstick",       "167226008"),
    ("full blood count",     "26604007"),
    ("faecal occult blood test", "104435004"),
    ("gastroscopy",          "76009000"),
]

# -- Raw SNOMED Term matches (what the Term lookup branch finds) ------
_TERM_MATCH = """
MATCH (t:Term)-[:TERM_OF]->(c:Concept)
WHERE toLower(t.text) = toLower($text)
  AND c.active = true
RETURN t.text AS term_text, c.id AS cid, c.fsn AS fsn, c.active AS active
LIMIT 5
"""

# -- SurfaceForm matches (case-insensitive, like resolver does) -------
_SF_MATCH = """
MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept)
WHERE toLower(sf.text) = toLower($text)
RETURN sf.text AS sf_text, c.id AS cid, c.fsn AS fsn,
       r.confidence AS conf, r.provenance AS prov
ORDER BY r.confidence DESC
"""

# -- Exact SurfaceForm lookup as resolver uses (case-sensitive) -------
_SF_EXACT = """
MATCH (sf:SurfaceForm {text: $text})-[r:MAPS_TO]->(c:Concept)
RETURN sf.text AS sf_text, c.id AS cid, c.fsn AS fsn,
       r.confidence AS conf, r.provenance AS prov
ORDER BY r.confidence DESC
"""


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))

    with driver.session() as s:
        for form, want_cid in CHECK_FORMS:
            print(f"\n{'='*60}")
            print(f"FORM: {form!r}  (want -> {want_cid})")

            # Term matches
            term_rows = list(s.run(_TERM_MATCH, text=form))
            print(f"  Term matches (case-insensitive, {len(term_rows)} rows):")
            for r in term_rows:
                print(f"    {r['cid']} | {(r['fsn'] or '?')[:55]}")

            # SurfaceForm - case-insensitive
            sf_ci_rows = list(s.run(_SF_MATCH, text=form))
            print(f"  SurfaceForm (case-insensitive, {len(sf_ci_rows)} rows):")
            for r in sf_ci_rows:
                hit = "**CORRECT**" if r["cid"] == want_cid else "WRONG"
                print(f"    [{hit}] {r['cid']} conf={r['conf']} prov={r['prov']}"
                      f" sf_text={r['sf_text']!r}")

            # SurfaceForm - case-sensitive exact (as resolver uses)
            sf_cs_rows = list(s.run(_SF_EXACT, text=form))
            print(f"  SurfaceForm (case-sensitive exact, {len(sf_cs_rows)} rows):")
            for r in sf_cs_rows:
                hit = "**CORRECT**" if r["cid"] == want_cid else "WRONG"
                print(f"    [{hit}] {r['cid']} conf={r['conf']} prov={r['prov']}")

    driver.close()


if __name__ == "__main__":
    main()
