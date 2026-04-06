"""Fix incorrect pins and add missing CA-125 / soft tissue lump forms."""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402
load_keyvault_secrets()
from neo4j import GraphDatabase  # noqa: E402

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
pwd = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


# Delete wrong edges for these norms (mapped to Low Back Strain 300956001)
WRONG_EDGES = [
    ("soft tissue lump increasing in size", "300956001"),
    ("unexplained lump increasing in size", "300956001"),
]

# Correct pins:
#   282331005 = Additional swelling / lump observation (finding)
#   1027511000000100 = Cancer antigen 125 level (observable entity)
#   432519008 = Cancer antigen 125 above reference range (finding)
NEW_FORMS = [
    # Soft tissue lump / swelling - correct concept
    ("soft tissue lump increasing in size", "282331005"),
    ("unexplained lump increasing in size", "282331005"),
    ("unexplained soft tissue lump", "282331005"),
    ("soft tissue swelling", "282331005"),
    # CA-125 - observable entity
    ("CA125", "1027511000000100"),
    ("ca 125", "1027511000000100"),
    ("serum CA125", "1027511000000100"),
    ("CA-125", "1027511000000100"),
    ("CA125 level", "1027511000000100"),
    ("cancer antigen 125", "1027511000000100"),
    ("cancer antigen 125 level", "1027511000000100"),
    ("ovarian cancer marker CA125", "1027511000000100"),
    # CA-125 raised - finding
    ("CA125 raised", "432519008"),
    ("CA125 elevated", "432519008"),
    ("raised CA125", "432519008"),
    ("CA125 35", "432519008"),
    ("CA125 above reference range", "432519008"),
]

_DELETE_EDGE = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[r:MAPS_TO]->(c:Concept {id: $cid})
DELETE r
RETURN count(r) AS deleted
"""

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
    with driver.session() as s:
        print("Deleting wrong edges...")
        for form, cid in WRONG_EDGES:
            norm = normalize(form)
            res = s.run(_DELETE_EDGE, normalized=norm, cid=cid).single()
            deleted = res["deleted"] if res else 0
            print(f"  [DEL ] {norm!r:55s} deleted {deleted} edge(s) to {cid}")

        print("\nPinning correct forms...")
        added = skipped = errors = 0
        for form, cid in NEW_FORMS:
            norm = normalize(form)
            existing = list(s.run(_CHECK, normalized=norm))
            if existing and any(r["cid"] == cid for r in existing):
                print(f"  [SKIP] {norm!r:55s}")
                skipped += 1
                continue
            result = list(s.run(_UPSERT, form=form, normalized=norm, cid=cid))
            if result:
                row = result[0]
                print(
                    f"  [ADD ] {norm!r:55s} -> {row['cid']:25s}"
                    f" {row['fsn'][:35]}"
                )
                added += 1
            else:
                print(f"  [ERR ] {norm!r:55s} concept {cid} not in graph")
                errors += 1

    driver.close()
    print(f"\nAdded {added}, skipped {skipped}, errors {errors}/{len(NEW_FORMS)}")


if __name__ == "__main__":
    main()
