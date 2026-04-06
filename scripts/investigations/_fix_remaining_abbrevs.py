"""Fix remaining abbreviation surface forms after failed upserts."""
import os, sys, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from neo4j import GraphDatabase

kg_uri  = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

_UPSERT = """
MATCH (c:Concept {id: $concept_id})
WHERE c.active = true
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form, sf.source = 'manual',
              sf.status = 'active', sf.created_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(), m.approved_at = datetime()
SET m.confidence = 1.0, m.provenance = 'audit-fix-abbrev-2026-04'
RETURN sf.normalized AS n, c.id AS id, c.fsn AS fsn
"""

FIXES = [
    # SMI: no specific 'Severe mental illness' concept exists -> use Chronic mental disorder
    ("SMI",   "128293007"),  # Chronic mental disorder
    ("smi",   "128293007"),
    # CMHT: under care of mental health team
    ("CMHT",  "401272006"),  # Under care of mental health team (finding)
    ("cmht",  "401272006"),
    # CRHTT: crisis resolution home treatment team
    ("CRHTT", "401272006"),
    ("crhtt", "401272006"),
    # Weight loss - map to the existing correct concept
    ("weight loss",             "262285001"),  # Weight decreased (finding)
    ("unexplained weight loss", "422868009"),  # Unexplained weight loss (finding)
    # Thrombocytosis -> use existing concept in graph
    ("thrombocytosis",  "415115007"),  # Platelet count above reference range (finding)
    ("high platelet count", "415115007"),
]


def _norm(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
ok = 0
fail = 0

with driver.session() as s:
    for form, cid in FIXES:
        normalized = _norm(form)
        r = s.run(_UPSERT, normalized=normalized, form=form, concept_id=cid).data()
        if r:
            print(f"  OK {form!r} -> {cid} | {r[0]['fsn']}")
            ok += 1
        else:
            print(f"  FAIL {form!r} -> {cid} (concept not in graph?)")
            fail += 1

driver.close()
print(f"\nOK: {ok}  Fail: {fail}")
