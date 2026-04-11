"""Apply the 9 confirmed DELETE decisions from the full surface form audit.

Decision log
------------
DELETE (wrong edge, better specific alternative exists):
  bone metastases       -> 128462008 (Metastatic malignant neoplasm - broad)
                           KEEP 94222008 (Metastatic to bone - specific)

  CMHT / cmht           -> 74732009 (Mental disorder - GCL generic)
                           KEEP 401272006 (Under care of MH team)

  CRHTT / crhtt         -> 74732009 (Mental disorder - GCL generic)
                           KEEP 401272006 (Under care of MH team)

  Lewy body dementia    -> 74732009 (Mental disorder - GCL generic)
                           KEEP 312991009 (Late onset dementia due to Lewy body)

  FIT                   -> 149421000000109 (Provision of FIT kit - procedure)
                           KEEP 1049361000000101 (Quantitative FIT - observable entity)

  HbA1c                 -> 43396009 (HbA1c measurement - procedure)
                           KEEP 1003671000000109 (Haemoglobin A1c level - observable entity)

  urine albumin creatinine ratio
                        -> 313500004 (Urine PROTEIN/creatinine ratio - WRONG analyte)
                           KEEP 271075006 (Urine ALBUMIN/creatinine ratio - correct)

REVERSE (FIT positive / faecal immunochemical test positive):
  The manual-fix-2026-04-05 added 59614000 (general Occult blood) which is LESS
  specific than the existing 71711000112103 (Occult blood by immunoassay). The
  audit-fix was wrong in this case. Delete the general edge; keep the specific one.

  faecal immunochemical test positive -> 59614000 (DELETE)
                                         KEEP 71711000112103 (immunoassay - specific)

  FIT positive          -> 59614000 (DELETE)
                           KEEP 71711000112103 (immunoassay - specific)
"""

import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from neo4j import GraphDatabase

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

# (normalized_form, concept_id_to_delete, reason)
DELETES = [
    ("bone metastases", "128462008", "broad catch-all, specific 94222008 exists"),
    ("cmht", "74732009", "GCL generic, 401272006 now correct"),
    ("crhtt", "74732009", "GCL generic, 401272006 now correct"),
    ("lewy body dementia", "74732009", "GCL generic, 312991009 now correct"),
    ("fit", "149421000000109", "Provision procedure, observable entity better"),
    ("hba1c", "43396009", "Procedure, observable entity 1003671000000109 better"),
    (
        "urine albumin creatinine ratio",
        "313500004",
        "Wrong analyte: protein vs albumin",
    ),
    # FIT positive: delete the less-specific general occult blood (my audit-fix was wrong)
    (
        "faecal immunochemical test positive",
        "59614000",
        "Immunoassay-specific 71711000112103 is better",
    ),
    ("fit positive", "59614000", "Immunoassay-specific 71711000112103 is better"),
]

_DELETE = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept {id: $concept_id})
DELETE m RETURN count(m) AS deleted
"""

_CHECK = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[m:MAPS_TO]->(c:Concept)
RETURN c.id AS id, c.fsn AS fsn, c.semantic_tag AS tag,
       m.confidence AS conf, m.provenance AS prov
ORDER BY m.confidence DESC
"""

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
total = 0

with driver.session() as s:
    for norm, cid, reason in DELETES:
        r = s.run(_DELETE, normalized=norm, concept_id=cid).data()
        n = r[0]["deleted"] if r else 0
        total += n
        status = "OK" if n > 0 else "MISS"
        print(f"  [{status}] {norm!r} -> {cid}  ({reason})")

    print(f"\nTotal edges deleted: {total}")

    # Verify final state for each form
    print("\n=== Verification ===")
    for norm, cid, _ in DELETES:
        rows = s.run(_CHECK, normalized=norm).data()
        print(f"\n{norm!r}:")
        for r in rows:
            print(f"  {r['id']} | {r['fsn'][:60]} conf={r['conf']} [{r['prov']}]")

driver.close()
