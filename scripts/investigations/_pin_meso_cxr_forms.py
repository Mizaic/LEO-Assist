"""Pin 'chest X-ray findings suggestive of mesothelioma' to the abnormal CXR concept."""

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


# 1290960005 = Plain X-ray of chest abnormal (finding) -- best broad code for
#              'suggestive of' CXR language; does not commit to a diagnosis
FORMS = [
    ("chest X-ray findings suggestive of mesothelioma", "1290960005"),
    ("chest X-ray findings consistent with mesothelioma", "1290960005"),
    ("chest X-ray findings that suggest mesothelioma", "1290960005"),
    ("CXR findings suggestive of mesothelioma", "1290960005"),
    ("chest X-ray abnormal mesothelioma", "1290960005"),
    ("abnormal chest X-ray mesothelioma", "1290960005"),
    ("chest radiograph findings mesothelioma", "1290960005"),
    ("pleural abnormality on chest X-ray", "1290960005"),
    ("abnormal pleural imaging finding", "1290960005"),
    ("chest X-ray pleural finding", "1290960005"),
    ("thoracic imaging abnormality", "1290960005"),
    ("pleural mass on chest X-ray", "1290960005"),
    ("pleural thickening on chest X-ray", "1290960005"),
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
        for form, cid in FORMS:
            norm = normalize(form)
            existing = list(s.run(_CHECK, normalized=norm))
            if existing and any(r["cid"] == cid for r in existing):
                print(f"  [SKIP] {norm!r:60s}")
                skipped += 1
                continue
            result = list(s.run(_UPSERT, form=form, normalized=norm, cid=cid))
            if result:
                row = result[0]
                print(f"  [ADD ] {norm!r:55s} -> {row['cid']} {row['fsn'][:40]}")
                added += 1
            else:
                print(f"  [ERR ] {norm!r:60s} concept {cid} not in graph")
                errors += 1
    driver.close()
    print(f"\nAdded {added}, skipped {skipped}, errors {errors}/{len(FORMS)}")


if __name__ == "__main__":
    main()
