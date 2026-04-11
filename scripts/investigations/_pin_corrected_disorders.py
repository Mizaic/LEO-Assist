"""Pin corrected concepts for atypical depression and separation anxiety."""

import os
import re
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
PROV = "sf-quality-fix-2026-04-05"


def normalize_surface(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


_UPSERT = """
MATCH (c:Concept {id: $cid})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form, sf.source = 'manual',
              sf.status = 'active', sf.created_at = datetime()
SET sf.form = $form
MERGE (sf)-[r:MAPS_TO]->(c)
ON CREATE SET r.created_at = datetime(), r.approved_at = datetime()
SET r.confidence = $conf, r.provenance = $prov
RETURN sf.normalized AS normalized, c.id AS cid, r.confidence AS conf
"""

FORMS = [
    # Atypical depressive disorder
    ("Atypical depression", "191659001", 1.0),
    ("atypical depression", "191659001", 1.0),
    ("atypical depressive disorder", "191659001", 1.0),
    # Separation anxiety
    ("Separation anxiety", "126943008", 1.0),
    ("separation anxiety", "126943008", 1.0),
    ("separation anxiety disorder", "126943008", 1.0),
]


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    with driver.session() as s:
        for form, cid, conf in FORMS:
            norm = normalize_surface(form)
            rows = list(
                s.run(
                    _UPSERT, normalized=norm, form=form, cid=cid, conf=conf, prov=PROV
                )
            )
            status = "OK" if rows else "MISS (concept not in graph)"
            print(f"  {status}  {form!r} -> {cid}")
    driver.close()

    print("\nVerifying via resolver:")
    checks = [
        ("atypical depression", "191659001"),
        ("separation anxiety", "126943008"),
    ]
    try:
        resp = requests.post(
            "http://localhost:8001/terminology/resolve",
            json={"terms": [t for t, _ in checks], "top_k": 1},
            timeout=60,
        )
        if resp.ok:
            results = resp.json().get("results", {})
            for term, expected in checks:
                candidates = results.get(term, [])
                got = candidates[0].get("snomed_concept_id") if candidates else "?"
                got_term = (
                    (candidates[0].get("snomed_term") or "?")[:60]
                    if candidates
                    else "?"
                )
                status = "PASS" if got == expected else "FAIL"
                print(f"  [{status}] {term!r} -> {got} | {got_term}")
    except Exception as exc:
        print(f"  Resolver skipped: {exc}")


if __name__ == "__main__":
    main()
