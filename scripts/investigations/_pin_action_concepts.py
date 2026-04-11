"""
Pin action concept surface forms that the resolver is failing to find:
  1. OGD procedure (76009000) for 'direct access upper GI endoscopy' terms
  2. Fast track lung cancer referral (276491000000101) for mesothelioma terms
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


# 76009000 = Esophagogastroduodenoscopy (procedure)
# 276491000000101 = Fast track referral for suspected lung cancer (procedure)
# 276491000000101 is used for mesothelioma too (no separate UK code exists)
FORMS = [
    # -- OGD / direct access upper GI endoscopy --
    ("esophagogastroduodenoscopy", "76009000"),
    ("oesophagogastroduodenoscopy", "76009000"),
    ("OGD", "76009000"),
    ("direct access upper gastrointestinal endoscopy", "76009000"),
    ("non-urgent direct access upper gastrointestinal endoscopy", "76009000"),
    ("direct access OGD", "76009000"),
    ("direct access gastroscopy", "76009000"),
    ("upper GI endoscopy", "76009000"),
    ("gastroscopy", "76009000"),
    # -- Mesothelioma referral -> lung cancer 2WW pathway --
    ("fast track referral for suspected mesothelioma", "276491000000101"),
    ("suspected mesothelioma referral", "276491000000101"),
    ("suspected mesothelioma fast track referral", "276491000000101"),
    ("2 week wait referral mesothelioma", "276491000000101"),
    ("two week wait referral mesothelioma", "276491000000101"),
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
                print(f"  [ADD ] {norm!r:60s} -> {row['cid']:20s} {row['fsn'][:40]}")
                added += 1
            else:
                print(f"  [ERR ] {norm!r:60s} concept {cid} not in graph")
                errors += 1
    driver.close()
    print(f"\nAdded {added}, skipped {skipped}, errors {errors}/{len(FORMS)}")


if __name__ == "__main__":
    main()
