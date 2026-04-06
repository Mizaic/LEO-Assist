"""Sitrep across all three workstreams - Neo4j queries only."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from neo4j import GraphDatabase
import warnings
warnings.filterwarnings("ignore")

pg_uri = os.getenv("NEO4J_URI", "") or os.getenv("NEO4J_PATIENT_URI", "bolt://localhost:7687")
pg_user = os.getenv("NEO4J_USER", "") or os.getenv("NEO4J_PATIENT_USER", "neo4j")
pg_pass = os.getenv("NEO4J_PASSWORD", "") or os.getenv("NEO4J_PATIENT_PASSWORD", "patient-dev")

driver = GraphDatabase.driver(pg_uri, auth=(pg_user, pg_pass))

def q(cypher, **params):
    with driver.session() as s:
        return list(s.run(cypher, **params))

# WS1
total_docs = q("MATCH ()-[r:DOCUMENTS]->() RETURN count(r) AS n")[0]["n"]
assertions = {}
for a in ("present", "historical", "absent", "possible", "declined",
          "cancelled", "family", "refuted", "planned", "hypothetical"):
    plain = q("MATCH ()-[r:DOCUMENTS]->() WHERE r.context = $v RETURN count(r) AS n", v=a)[0]["n"]
    json_match = q(
        "MATCH ()-[r:DOCUMENTS]->() WHERE r.context CONTAINS $v RETURN count(r) AS n",
        v=f'"assertion": "{a}"'
    )[0]["n"]
    if plain + json_match > 0:
        assertions[a] = plain + json_match

patched = q(
    "MATCH ()-[r:DOCUMENTS]->() WHERE r.audit_flag IS NOT NULL RETURN count(r) AS n"
)[0]["n"]

# Edges with no evidence_sentence
no_ev_sentence = q(
    "MATCH ()-[r:DOCUMENTS]->() WHERE r.evidence_sentence IS NULL RETURN count(r) AS n"
)[0]["n"]

# Encounters with at least one DOCUMENTS edge
encounters_with_coding = q(
    "MATCH (e:Encounter)-[:DOCUMENTS]->() RETURN count(DISTINCT e) AS n"
)[0]["n"]

total_encounters = q("MATCH (e:Encounter) RETURN count(e) AS n")[0]["n"]

# WS2
uncoded_total = q("MATCH (u:UncodedItem) RETURN count(u) AS n")[0]["n"]
review_by_status = {}
for row in q("MATCH (t:ReviewTask) RETURN t.status AS s, count(t) AS n"):
    review_by_status[row["s"]] = row["n"]

# WS3
tl_total = q("MATCH (t:TrainingLabel) RETURN count(t) AS n")[0]["n"]
tl_by_type = {}
for row in q("MATCH (t:TrainingLabel) RETURN t.label_type AS lt, count(t) AS n ORDER BY n DESC"):
    if row["lt"]:
        tl_by_type[row["lt"]] = row["n"]
ec_total = q("MATCH (e:EncounterCandidate) RETURN count(e) AS n")[0]["n"]
ar_total = q("MATCH (a:AuditRun) RETURN count(a) AS n")[0]["n"]

driver.close()

print("=" * 65)
print("SITREP -- LEO-AI Clinical Data Quality")
print("=" * 65)

print()
print("WORKSTREAM 1 -- Neo4j encounter clinical codes")
print("-" * 50)
print(f"  Total encounters:                {total_encounters:>8,}")
print(f"  Encounters with coding:          {encounters_with_coding:>8,}")
print(f"  Total DOCUMENTS edges:           {total_docs:>8,}")
print()
print(f"  Assertion breakdown:")
for a, n in sorted(assertions.items(), key=lambda x: -x[1]):
    print(f"    {a:<22} {n:>8,}")
print()
print(f"  Edges with evidence_sentence:    {total_docs-no_ev_sentence:>8,}")
print(f"  Edges WITHOUT evidence_sentence: {no_ev_sentence:>8,}")
print(f"  Edges patched (audit_flag set):  {patched:>8,}")
print()
print("  Audit run (LLM-reviewed encounters): 30,741 done, 8 errors")
print("  Surface gaps found: 14,410 raw | 5,177 valid (triaged)")

print()
print("WORKSTREAM 2 -- Surface forms")
print("-" * 50)
print(f"  UncodedItem nodes (gap queue):   {uncoded_total:>8,}")
print(f"  ReviewTask nodes by status:")
for st, n in sorted(review_by_status.items(), key=lambda x: -x[1]):
    print(f"    {st:<22} {n:>8,}")
print()
print("  * 5,177 valid gap phrases in surface_form_gaps_valid.json")
print("    NOT YET FED into ReviewTask/UncodedItem queue")

print()
print("WORKSTREAM 3 -- Gold labels / spaCy training")
print("-" * 50)
print(f"  AuditRun nodes:                  {ar_total:>8,}")
print(f"  EncounterCandidate nodes:        {ec_total:>8,}")
print(f"  TrainingLabel nodes:             {tl_total:>8,}")
for lt, n in sorted(tl_by_type.items(), key=lambda x: -x[1]):
    print(f"    {lt:<22} {n:>8,}")
print()
print("  STATUS: Gold labels NOT yet generated from audit results.")
print("  The audit produced verdicts in encounter_audit.db but the")
print("  write-to-KG pipeline (kg_verified_writeback.py) has not")
print("  been run against the 30,741 audited encounters.")
print("=" * 65)
