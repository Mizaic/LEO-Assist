"""
Pin surface forms for all remaining NG12 gap categories identified by analysis:
  - Ultrasound findings suggestive of soft tissue sarcoma
  - IBS, CA125, PSA ambiguous terms
  - Gall bladder and liver palpable mass forms

Also adds worked examples to the extraction prompt for enlarged-organ
abdominal mass decomposition.
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


# -- Verify these concept IDs exist before running --
# Soft tissue sarcoma: 424952003 (soft tissue sarcoma disorder)
# IBS: 10743008 (irritable bowel syndrome disorder)
# CA-125: 250400007 (CA-125 measurement observable)
# PSA: 63476009 (prostate specific antigen measurement observable)
# Hepatomegaly: 80515008 (hepatomegaly finding)
# Gallbladder enlarged: 300365003 (palpable gallbladder finding)
# Soft tissue lump: 300956001 (lump in soft tissue finding)

FORMS = [
    # --- Ultrasound findings / sarcoma ---
    ("soft tissue sarcoma", "424952003"),
    ("soft tissue mass", "424952003"),
    ("ultrasound findings suggestive of soft tissue sarcoma", "424952003"),
    ("ultrasound scan findings suggestive of soft tissue sarcoma", "424952003"),
    ("ultrasound findings uncertain sarcoma", "424952003"),
    ("soft tissue lump increasing in size", "300956001"),
    ("unexplained lump increasing in size", "300956001"),
    # --- CA-125 ---
    ("CA125", "250400007"),
    ("ca 125", "250400007"),
    ("serum CA125", "250400007"),
    ("CA-125", "250400007"),
    ("CA125 level", "250400007"),
    ("CA125 raised", "250400007"),
    ("CA125 elevated", "250400007"),
    ("CA125 35", "250400007"),
    ("ovarian cancer marker", "250400007"),
    # --- PSA ---
    ("PSA", "63476009"),
    ("PSA level", "63476009"),
    ("PSA raised", "63476009"),
    ("PSA elevated", "63476009"),
    ("prostate specific antigen", "63476009"),
    ("PSA measurement", "63476009"),
    # --- IBS ---
    ("IBS", "10743008"),
    ("irritable bowel syndrome", "10743008"),
    ("irritable bowel", "10743008"),
    # --- Hepatomegaly / palpable liver ---
    ("hepatomegaly", "80515008"),
    ("enlarged liver", "80515008"),
    ("palpable liver", "80515008"),
    ("upper abdominal mass consistent with enlarged liver", "80515008"),
    ("liver mass", "80515008"),
    # --- Palpable gallbladder ---
    ("palpable gallbladder", "300365003"),
    ("enlarged gallbladder", "300365003"),
    ("palpable gall bladder", "300365003"),
    ("upper abdominal mass consistent with enlarged gall bladder", "300365003"),
    ("upper abdominal mass consistent with enlarged gallbladder", "300365003"),
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
                print(f"  [SKIP] {norm!r:60s}")
                skipped += 1
                continue
            result = list(s.run(_UPSERT, form=form, normalized=norm, cid=cid))
            if result:
                row = result[0]
                print(
                    f"  [ADD ] {norm!r:60s} -> {row['cid']:20s}"
                    f" {row['fsn'][:40]}"
                )
                added += 1
            else:
                print(f"  [ERR ] {norm!r:60s} concept {cid} NOT in graph")
                errors += 1
    driver.close()
    print(f"\nAdded {added}, skipped {skipped}, errors {errors}/{len(FORMS)}")


if __name__ == "__main__":
    main()
