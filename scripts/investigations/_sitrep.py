"""Quick sitrep across all three workstreams."""

import json
import os
import sqlite3
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

pg_uri = os.getenv("NEO4J_URI", "") or os.getenv(
    "NEO4J_PATIENT_URI", "bolt://localhost:7687"
)
pg_user = os.getenv("NEO4J_USER", "") or os.getenv("NEO4J_PATIENT_USER", "neo4j")
pg_pass = os.getenv("NEO4J_PASSWORD", "") or os.getenv(
    "NEO4J_PATIENT_PASSWORD", "patient-dev"
)

driver = GraphDatabase.driver(pg_uri, auth=(pg_user, pg_pass))
with driver.session() as s:
    # ---- WS1: Encounter coding ----
    total_docs = s.run("MATCH ()-[r:DOCUMENTS]->() RETURN count(r) AS n").single()["n"]
    assertion_counts = {}
    for a in (
        "present",
        "historical",
        "absent",
        "possible",
        "declined",
        "cancelled",
        "family",
        "refuted",
        "planned",
        "hypothetical",
    ):
        old = s.run(
            "MATCH ()-[r:DOCUMENTS]->() WHERE r.context = $v RETURN count(r) AS n", v=a
        ).single()["n"]
        new = s.run(
            "MATCH ()-[r:DOCUMENTS]->() WHERE r.context CONTAINS $v RETURN count(r) AS n",
            v=f'"assertion": "{a}"',
        ).single()["n"]
        if old + new > 0:
            assertion_counts[a] = old + new
    patched = s.run(
        "MATCH ()-[r:DOCUMENTS]->() WHERE r.audit_flag CONTAINS 'assertion_patched' RETURN count(r) AS n"
    ).single()["n"]

    # ---- WS2: Surface forms ----
    sf_total = s.run("MATCH (s:SurfaceForm) RETURN count(s) AS n").single()["n"]
    sf_approved = s.run(
        "MATCH (s:SurfaceForm) WHERE s.status = 'approved' RETURN count(s) AS n"
    ).single()["n"]
    sf_pending_tasks = s.run(
        "MATCH (t:SurfaceFormTask) WHERE t.status = 'pending' RETURN count(t) AS n"
    ).single()["n"]
    sf_approved_tasks = s.run(
        "MATCH (t:SurfaceFormTask) WHERE t.status = 'approved' RETURN count(t) AS n"
    ).single()["n"]

    # ---- WS3: Gold labels / training ----
    gold_total = s.run("MATCH (g:GoldLabel) RETURN count(g) AS n").single()["n"]
    gold_by_source = {}
    for row in s.run("MATCH (g:GoldLabel) RETURN g.source AS src, count(g) AS n"):
        gold_by_source[row["src"]] = row["n"]
    candidates_total = s.run(
        "MATCH (c:TrainingCandidate) RETURN count(c) AS n"
    ).single()["n"]
    candidates_by_status = {}
    for row in s.run(
        "MATCH (c:TrainingCandidate) RETURN c.status AS st, count(c) AS n"
    ):
        candidates_by_status[row["st"]] = row["n"]

driver.close()

# ---- Audit DB ----
audit_db = (
    ROOT / "scripts" / "investigations" / "encounter_audit" / "encounter_audit.db"
)
con = sqlite3.connect(audit_db)
cur = con.cursor()
cur.execute("SELECT assessment, COUNT(*) FROM encounters GROUP BY assessment")
audit_verdicts = dict(cur.fetchall())
cur.execute("SELECT COUNT(*) FROM encounters")
audit_total = cur.fetchone()[0]
con.close()

# ---- Valid gaps file ----
valid_gaps_file = (
    ROOT
    / "scripts"
    / "investigations"
    / "encounter_audit"
    / "surface_form_gaps_valid.json"
)
raw_gaps_file = (
    ROOT / "scripts" / "investigations" / "encounter_audit" / "surface_form_gaps.json"
)
valid_gaps_count = (
    len(json.loads(valid_gaps_file.read_text())) if valid_gaps_file.exists() else 0
)
raw_gaps_count = (
    len(json.loads(raw_gaps_file.read_text())) if raw_gaps_file.exists() else 0
)

print("=" * 65)
print("SITREP -- LEO-AI Data Quality")
print("=" * 65)

print()
print("WORKSTREAM 1 -- Neo4j encounter clinical codes")
print("-" * 50)
print(f"  Encounters audited (LLM):        {audit_total:>7,}")
for verdict, n in sorted(audit_verdicts.items(), key=lambda x: -x[1]):
    print(f"    {verdict:<28} {n:>6,}")
print(f"  Total DOCUMENTS edges:           {total_docs:>7,}")
print(f"  Assertion breakdown:")
for a, n in sorted(assertion_counts.items(), key=lambda x: -x[1]):
    print(f"    {a:<20} {n:>7,}")
print(f"  Edges patched (hypo->planned):   {patched:>7,}")

print()
print("WORKSTREAM 2 -- Surface forms")
print("-" * 50)
print(f"  SurfaceForm nodes (approved):    {sf_approved:>7,}  / {sf_total:>6,} total")
print(f"  SurfaceFormTask queue:")
print(f"    pending                        {sf_pending_tasks:>7,}")
print(f"    approved                       {sf_approved_tasks:>7,}")
print(f"  Audit gap candidates:")
print(f"    raw gaps identified            {raw_gaps_count:>7,}")
print(f"    valid (triaged, stripped)      {valid_gaps_count:>7,}")
print(f"    fed into task queue            NOT YET RUN")

print()
print("WORKSTREAM 3 -- Gold labels / training dataset")
print("-" * 50)
print(f"  GoldLabel nodes:                 {gold_total:>7,}")
for src, n in sorted(gold_by_source.items(), key=lambda x: -x[1]):
    print(f"    {src:<28} {n:>6,}")
print(f"  TrainingCandidate nodes:         {candidates_total:>7,}")
for st, n in sorted(candidates_by_status.items(), key=lambda x: -x[1]):
    print(f"    {st:<28} {n:>6,}")
print()
print("=" * 65)
