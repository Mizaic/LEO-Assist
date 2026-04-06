"""Mark process/communication recommendations as requiresCoding=false.

These recommendations contain no codeable clinical criteria - they describe
communication processes, safety netting procedures, and referral administration.
The extraction pipeline correctly returns coded_criteria=None for these in ~2-3s.

Recs covered:
  CH003 all 21 (1.14.x, 1.15.x, 1.16.x)
  CH002: 1.3.4, 1.5.4, 1.7.7
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

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

PROCESS_REC_IDS = [
    # CH003 - communication, information, safety netting, referral process
    "NG12:v1:CH003:SEC000:R000", "NG12:v1:CH003:SEC000:R001",
    "NG12:v1:CH003:SEC000:R002", "NG12:v1:CH003:SEC000:R003",
    "NG12:v1:CH003:SEC000:R004", "NG12:v1:CH003:SEC000:R005",
    "NG12:v1:CH003:SEC000:R006", "NG12:v1:CH003:SEC000:R007",
    "NG12:v1:CH003:SEC000:R008", "NG12:v1:CH003:SEC000:R009",
    "NG12:v1:CH003:SEC000:R010",
    "NG12:v1:CH003:SEC001:R000", "NG12:v1:CH003:SEC001:R001",
    "NG12:v1:CH003:SEC002:R000", "NG12:v1:CH003:SEC002:R001",
    "NG12:v1:CH003:SEC002:R002", "NG12:v1:CH003:SEC002:R003",
    "NG12:v1:CH003:SEC002:R004", "NG12:v1:CH003:SEC002:R005",
    "NG12:v1:CH003:SEC002:R006", "NG12:v1:CH003:SEC002:R007",
    # CH002 process recs
    "NG12:v1:CH002:SEC002:R003",  # 1.3.4 "consider if people need help to return sample"
    "NG12:v1:CH002:SEC004:R003",  # 1.5.4 "advise woman to return to GP if symptoms worsen"
    "NG12:v1:CH002:SEC006:R006",  # 1.7.7 "follow NICE guidance on skin tumours"
]

SET_QUERY = """
UNWIND $ids AS rid
MATCH (r:Recommendation {id: rid})
SET r.requiresCoding = false,
    r.requiresCodingRationale = 'Process/communication recommendation - no codeable clinical criterion'
RETURN r.id AS id
"""

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
with driver.session() as s:
    result = list(s.run(SET_QUERY, ids=PROCESS_REC_IDS))
driver.close()

updated = [row["id"] for row in result]
print(f"Marked {len(updated)} recommendations as requiresCoding=false:")
for rid in updated:
    print(f"  {rid}")

missing = set(PROCESS_REC_IDS) - set(updated)
if missing:
    print(f"\nWARNING: {len(missing)} IDs not found in graph:")
    for rid in sorted(missing):
        print(f"  {rid}")
