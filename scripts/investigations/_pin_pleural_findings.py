"""Pin pleural finding surface forms for mesothelioma CXR pattern."""
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


# Pleural thickening: 56825002 (disorder)
# Pleural plaque: 415068001 (disorder)
FORMS = [
    # 233655000 = Asbestos-induced bilateral diffuse pleural thickening (disorder)
    # only pleural thickening concept in graph
    ("pleural thickening", "233655000"),
    ("bilateral pleural thickening", "233655000"),
    ("diffuse pleural thickening", "233655000"),
    ("asbestos induced pleural thickening", "233655000"),
    # Mesothelioma CXR phrases -> pleural effusion (60046008)
    # most common initial CXR finding for mesothelioma
    ("chest x ray findings suggestive of mesothelioma", "60046008"),
    ("chest x ray findings mesothelioma", "60046008"),
    ("chest x ray pleural abnormality", "60046008"),
    # Asbestos-induced pleural plaque -> 196005004 in graph
    ("pleural plaque", "196005004"),
    ("asbestos pleural plaque", "196005004"),
    ("asbestos induced pleural plaque", "196005004"),
    ("calcified pleural plaque", "196005004"),
]

_UPSERT = """
MATCH (c:Concept {id: $cid})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form,
              sf.source = 'manual',
              sf.status = 'active',
              sf.created_at = datetime()
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
    added = 0
    skipped = 0
    errors = 0
    with driver.session() as s:
        for form, cid in FORMS:
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
                    f"  [ADD ] {norm!r:55s} -> {row['cid']:15s}"
                    f" {row['fsn'][:40]}"
                )
                added += 1
            else:
                print(f"  [ERR ] {norm!r:55s} concept {cid} not in graph")
                errors += 1
    driver.close()
    print(f"\nAdded {added}, skipped {skipped}, errors {errors}/{len(FORMS)}")


if __name__ == "__main__":
    main()
