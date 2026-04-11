"""Inspect REVIEW items from the audit report.

Shows:
  - All 5 R6_WRONG_SEMANTIC_TAG items
  - All 94 R4_WRONG_SITUATION_NO_ALT items with alternative searches
"""

import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from neo4j import GraphDatabase

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

REPORT = ROOT / "scripts" / "investigations" / "full_surface_form_audit.json"
data = json.loads(REPORT.read_text(encoding="utf-8"))

# ── R6: Wrong semantic tag ──────────────────────────────────────────────────
print("=" * 70)
print("R6_WRONG_SEMANTIC_TAG (5 items)")
print("=" * 70)
for d in data["decisions"]:
    if d["rule"] == "R6_WRONG_SEMANTIC_TAG":
        print(f"  {d['form']!r}")
        print(f"    -> {d['concept_id']} | {d['concept_fsn']}")
        print(
            f"    tag={d['semantic_tag']}  conf={d['confidence']}  prov={d['provenance']}"
        )
        print(f"    reason: {d['reason']}")

# ── R4: Wrong situation with no alternative ─────────────────────────────────
print()
print("=" * 70)
print("R4_WRONG_SITUATION_NO_ALT (94 items) - first 40")
print("=" * 70)
r4_items = [d for d in data["decisions"] if d["rule"] == "R4_WRONG_SITUATION_NO_ALT"]

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

with driver.session() as s:
    for d in r4_items[:40]:
        form = d["form"]
        form_low = form.lower()
        print(f"\n  {form!r} -> {d['concept_id']} | {d['concept_fsn']}")
        print(f"    prov={d['provenance']}  conf={d['confidence']}")

        # Search for a better specific concept
        rows = s.run(
            """
            CALL db.index.fulltext.queryNodes('term_fulltext', $q) YIELD node, score
            MATCH (node)-[:DESCRIBES]->(c:Concept)
            WHERE c.active = true
              AND c.semantic_tag IN ['disorder', 'finding']
            RETURN c.id AS id, c.fsn AS fsn, score
            ORDER BY score DESC LIMIT 3
        """,
            q=form_low,
        ).data()

        if rows and rows[0]["score"] >= 7.0:
            best = rows[0]
            print(
                f"    BETTER?: {best['id']} | {best['fsn']} (score={best['score']:.1f})"
            )
        else:
            top = f"{rows[0]['fsn']} ({rows[0]['score']:.1f})" if rows else "no results"
            print(f"    No good alternative (best: {top})")

driver.close()

print(f"\n... and {len(r4_items) - 40} more R4 items not shown")
print(f"\nTotal review items: {data['review']}")
