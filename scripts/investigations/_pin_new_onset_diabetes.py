"""
Pin surface forms for NG12 'new-onset diabetes' (1.2.5) so resolver returns
405749004 | Newly diagnosed diabetes (disorder) in the verifier candidate list.

Sonnet rejected generic diabetes mellitus when 405749004 was missing from candidates.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402
load_keyvault_secrets()
from libs.terminology.surface_normalize import normalize_surface  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
pwd = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

CID = "405749004"

FORMS = [
    "new-onset diabetes",
    "new onset diabetes",
    "newly diagnosed diabetes",
    "newly diagnosed diabetes mellitus",
    "new onset diabetes mellitus",
    "new-onset diabetes mellitus",
    "recent onset diabetes",
    "recent onset diabetes mellitus",
    "diabetes mellitus new onset",
    "new diagnosis of diabetes",
    "newly diagnosed type 2 diabetes",
    "newly diagnosed type 2 diabetes mellitus",
]

_UPSERT = """
MATCH (c:Concept {id: $cid})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form, sf.source = 'manual',
              sf.status = 'active', sf.created_at = datetime()
SET sf.form = $form
WITH sf, c
MERGE (sf)-[r:MAPS_TO]->(c)
ON CREATE SET r.confidence = 1.0, r.source = 'manual'
RETURN sf.normalized AS norm, c.id AS cid, c.fsn AS fsn
"""

_CHECK = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[:MAPS_TO]->(c:Concept)
RETURN c.id AS cid
"""


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    added = skipped = errors = 0
    with driver.session() as s:
        for form in FORMS:
            norm = normalize_surface(form)
            existing = list(s.run(_CHECK, normalized=norm))
            if existing and any(r["cid"] == CID for r in existing):
                print(f"  [SKIP] {norm!r:55s}")
                skipped += 1
                continue
            result = list(s.run(_UPSERT, form=form, normalized=norm, cid=CID))
            if result:
                row = result[0]
                print(f"  [ADD ] {norm!r:55s} -> {row['cid']} {row['fsn'][:45]}")
                added += 1
            else:
                print(f"  [ERR ] {norm!r:55s} concept {CID} not in graph")
                errors += 1
    driver.close()
    print(f"\nAdded {added}, skipped {skipped}, errors {errors}/{len(FORMS)}")


if __name__ == "__main__":
    main()
