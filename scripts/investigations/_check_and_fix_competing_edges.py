"""Find competing MAPS_TO edges on action surface forms and delete the wrong ones.

The fix script added correct edges but existing wrong edges are competing.
This script:
  1. Shows ALL MAPS_TO edges for each form
  2. Deletes all edges EXCEPT the one pointing to the correct concept
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

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

# form -> correct concept ID
CORRECT: dict[str, str] = {
    "direct access upper gastrointestinal endoscopy": "76009000",
    "upper gastrointestinal endoscopy": "76009000",
    "direct access endoscopy": "76009000",
    "OGD": "76009000",
    "gastroscopy": "76009000",
    "PSA test": "63476009",
    "PSA": "63476009",
    "urgent ultrasound": "16310003",
    "direct access ultrasound": "16310003",
    "CA125": "909121000000107",
    "CA 125": "909121000000107",
    "CA-125": "909121000000107",
    "urine dipstick": "167226008",
    "full blood count": "26604007",
    "FBC": "26604007",
    "faecal occult blood test": "104435004",
    "FOBT": "104435004",
}

_FETCH = """
MATCH (sf:SurfaceForm {text: $form})-[r:MAPS_TO]->(c:Concept)
RETURN c.id AS cid, c.fsn AS fsn, r.confidence AS conf, r.provenance AS prov
ORDER BY r.confidence DESC
"""

_DELETE_EXCEPT = """
MATCH (sf:SurfaceForm {text: $form})-[r:MAPS_TO]->(c:Concept)
WHERE c.id <> $keep_cid
DELETE r
RETURN count(r) AS deleted
"""

_BOOST_CORRECT = """
MATCH (sf:SurfaceForm {text: $form})-[r:MAPS_TO]->(c:Concept {id: $cid})
SET r.confidence = 1.0, r.provenance = 'manual-fix-action-concepts'
RETURN r.confidence AS conf
"""


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    total_deleted = 0

    print("Auditing competing MAPS_TO edges on action surface forms\n")

    with driver.session() as s:
        for form, correct_cid in CORRECT.items():
            edges = list(s.run(_FETCH, form=form))
            if not edges:
                continue  # no SurfaceForm node yet -- will be created by upsert

            competing = [e for e in edges if e["cid"] != correct_cid]
            correct_exists = any(e["cid"] == correct_cid for e in edges)

            if not competing and correct_exists:
                continue  # already clean

            print(f"  {form!r}")
            for e in edges:
                marker = "KEEP" if e["cid"] == correct_cid else "DEL "
                print(
                    f"    [{marker}] {e['cid']} | {(e['fsn'] or '?')[:55]} "
                    f"| conf={e['conf']} | prov={e['prov']}"
                )

            if competing:
                rows = list(s.run(_DELETE_EXCEPT, form=form, keep_cid=correct_cid))
                deleted = rows[0]["deleted"] if rows else 0
                print(f"    --> Deleted {deleted} competing edge(s)")
                total_deleted += deleted

            # Ensure the correct edge has full confidence
            s.run(_BOOST_CORRECT, form=form, cid=correct_cid)

    driver.close()

    print(f"\nTotal competing edges deleted: {total_deleted}")

    # Verify via live resolver
    print("\nVerification via live resolver:")
    verify = [
        ("direct access upper gastrointestinal endoscopy", "76009000"),
        ("PSA test", "63476009"),
        ("urgent ultrasound", "16310003"),
        ("CA125", "909121000000107"),
        ("urine dipstick", "167226008"),
        ("full blood count", "26604007"),
        ("faecal occult blood test", "104435004"),
        ("OGD", "76009000"),
        ("gastroscopy", "76009000"),
    ]
    try:
        r = requests.post(
            "http://localhost:8001/terminology/resolve",
            json={"terms": [t for t, _ in verify], "top_k": 1},
            timeout=60,
        )
        if r.ok:
            results = r.json().get("results", {})
            passed = 0
            for term, expected in verify:
                candidates = results.get(term, [])
                got = candidates[0].get("snomed_concept_id") if candidates else "?"
                got_term = (
                    (candidates[0].get("snomed_term") or "?")[:50]
                    if candidates
                    else "?"
                )
                status = "PASS" if got == expected else "FAIL"
                if status == "PASS":
                    passed += 1
                    print(f"  [PASS] {term!r} -> {got}")
                else:
                    print(f"  [FAIL] {term!r}")
                    print(f"         got={got} | {got_term}")
                    print(f"         want={expected}")
            print(f"\n  {passed}/{len(verify)} passed")
        else:
            print(f"  Resolver {r.status_code}")
    except Exception as exc:
        print(f"  Resolver check skipped: {exc}")


if __name__ == "__main__":
    main()
