"""
Pin surface forms for 'chest signs consistent with lung cancer' type phrases.
The models consistently want 272016000 | On examination - chest finding (finding)
for these phrases. Pin it so it appears in resolver candidates.
Also covers n2 for CXR findings suggestive of lung cancer using the lung mass
concept we added earlier, plus the 'abnormal chest X-ray' concept.
"""

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


# 272016000 = On examination - chest finding (finding)
# 9990010014 = Plain X-ray of chest abnormal (finding)
# 309529002 = Lung mass (finding)  [already pinned]
FORMS = [
    # -- Chest examination signs (lung cancer context) --
    ("chest signs consistent with lung cancer", "272016000"),
    ("chest signs suggestive of lung cancer", "272016000"),
    ("abnormal chest examination finding", "272016000"),
    ("abnormal chest signs", "272016000"),
    ("chest auscultation abnormality", "272016000"),
    ("reduced breath sounds", "272016000"),
    ("chest examination abnormality", "272016000"),
    ("on examination chest finding", "272016000"),
    # -- Abnormal chest X-ray (for CXR findings criterion) --
    ("abnormal chest X-ray finding", "9990010014"),
    ("abnormal chest radiograph", "9990010014"),
    ("chest X-ray abnormality", "9990010014"),
    ("plain X-ray of chest abnormal", "9990010014"),
    ("abnormal findings on chest radiograph", "9990010014"),
    ("suspicious chest X-ray finding", "9990010014"),
    ("chest radiograph abnormality", "9990010014"),
    ("chest radiograph with abnormal findings", "9990010014"),
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
