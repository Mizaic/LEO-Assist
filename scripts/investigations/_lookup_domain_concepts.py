"""Look up concepts in cancer_audit domain and check patient graph."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

CONCEPT_IDS_INT = [363346000, 395100000, 199251000000107, 382761000000101]
CONCEPT_IDS_STR = [str(c) for c in CONCEPT_IDS_INT]

# -- Check KG with both int and string --
kg = KnowledgeGraphClient()

# Sample what conceptId type is in KG
sample = kg.run(
    "MATCH (c:Concept) RETURN c.conceptId AS id LIMIT 3"
)
print("KG Concept.conceptId sample types:", [(r["id"], type(r["id"]).__name__) for r in sample])

# Try int lookup
rows_int = kg.run(
    "MATCH (c:Concept) WHERE c.conceptId IN $ids "
    "RETURN c.conceptId AS id, c.preferredTerm AS term, c.semanticTag AS tag",
    ids=CONCEPT_IDS_INT,
)
print("\nKG lookup (int IDs):", len(rows_int), "found")
for r in rows_int:
    print(f"  {r['id']}  [{r['tag']}]  {r['term']}")

# Try string lookup
rows_str = kg.run(
    "MATCH (c:Concept) WHERE c.conceptId IN $ids "
    "RETURN c.conceptId AS id, c.preferredTerm AS term, c.semanticTag AS tag",
    ids=CONCEPT_IDS_STR,
)
print("\nKG lookup (str IDs):", len(rows_str), "found")
for r in rows_str:
    print(f"  {r['id']}  [{r['tag']}]  {r['term']}")
kg.close()

# -- Check patient graph for these concepts --
pg = PatientGraphClient()
rows_pg = pg.run(
    "MATCH (d) WHERE d.conceptId IN $ids "
    "RETURN d.conceptId AS id, d.name AS name, labels(d) AS lbl LIMIT 20",
    ids=CONCEPT_IDS_STR,
)
print("\nPatient graph concept nodes found:", len(rows_pg))
for r in rows_pg:
    print(f"  {r['id']}  {r['lbl']}  {r['name']}")
pg.close()
