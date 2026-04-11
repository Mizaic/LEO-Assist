"""Add the 12 missing FIT surface form variants."""

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


# (form_display, concept_id)
MISSING = [
    # Observable - the test itself
    ("quantitative FIT", "1049361000000101"),
    ("fecal immunochemical test", "1049361000000101"),
    ("FIT level", "1049361000000101"),
    ("FIT value", "1049361000000101"),
    # Positive / raised result
    ("FIT raised", "71711000112103"),
    ("FIT abnormal", "71711000112103"),
    ("raised FIT", "71711000112103"),
    ("occult blood detected in faeces by immunoassay", "71711000112103"),
    ("occult blood detected in feces by immunoassay", "71711000112103"),
    # Negative / not detected
    ("negative FIT", "167667006"),
    ("occult blood not detected in faeces", "167667006"),
    ("occult blood not detected in feces", "167667006"),
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
RETURN sf.normalized AS norm, c.fsn AS fsn
"""

_CHECK = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[:MAPS_TO]->(c:Concept)
RETURN c.id AS cid, c.fsn AS fsn
"""


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    added = 0
    skipped = 0
    with driver.session() as s:
        for form, cid in MISSING:
            norm = normalize(form)
            existing = list(s.run(_CHECK, normalized=norm))
            if existing:
                existing_cids = [r["cid"] for r in existing]
                if cid in existing_cids:
                    print(f"  [SKIP] {norm!r:50s} already -> {cid}")
                    skipped += 1
                    continue
            result = s.run(_UPSERT, form=form, normalized=norm, cid=cid)
            row = result.single()
            print(f"  [ADD ] {norm!r:50s} -> {row['fsn'][:60]}")
            added += 1
    driver.close()
    print(f"\nAdded {added}, skipped {skipped}/{len(MISSING)}")


if __name__ == "__main__":
    main()
