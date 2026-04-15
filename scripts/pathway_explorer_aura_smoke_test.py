"""Pathway Explorer -- live Aura smoke test.

Connects directly to the real Neo4j Aura instance, inspects the data, tries
to build every GDS projection, and runs every algorithm.  Prints a clear
pass / fail / warn report.

Usage:
    .venv/bin/python3 scripts/pathway_explorer_aura_smoke_test.py

Credentials are read from secrets/.env.secrets (NEO4J_URI / NEO4J_PASSWORD /
NEO4J_USER) in the same way the application does at startup.
"""

from __future__ import annotations

import os
import sys
import textwrap
import time
from collections import Counter
from pathlib import Path

# -- Load secrets from .env.secrets before importing app modules -------------
_REPO = Path(__file__).resolve().parents[1]
_SECRETS = _REPO / "secrets" / ".env.secrets"
if _SECRETS.exists():
    with open(_SECRETS) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_CONFIG = _REPO / "secrets" / ".env.config"
if _CONFIG.exists():
    with open(_CONFIG) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(_REPO))

# -- Colour helpers ----------------------------------------------------------
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

TICK = f"{GREEN}PASS{RESET}"
WARN = f"{YELLOW}WARN{RESET}"
FAIL = f"{RED}FAIL{RESET}"
INFO = f"{BLUE}INFO{RESET}"

results: list[dict] = []


def section(title: str) -> None:
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")


def record(status: str, name: str, detail: str = "") -> None:
    results.append({"status": status, "name": name, "detail": detail})
    tag = {"PASS": TICK, "WARN": WARN, "FAIL": FAIL, "INFO": INFO}[status]
    line = f"  [{tag}]  {name}"
    if detail:
        line += f"\n         {textwrap.shorten(detail, 120)}"
    print(line)


# ============================================================================
# 1.  Direct Bolt connection
# ============================================================================
section("1. Neo4j Aura connection")

NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

print(f"  URI  : {NEO4J_URI}")
print(f"  User : {NEO4J_USER}")

from neo4j import GraphDatabase  # noqa: E402

try:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    record("PASS", "Bolt connection")
except Exception as exc:
    record("FAIL", "Bolt connection", str(exc))
    print("\nCannot continue without a working connection.")
    sys.exit(1)


def run(cypher: str, **params):
    with driver.session() as s:
        result = s.run(cypher, **params)
        return result.data()


# ============================================================================
# 2.  Schema / data inventory
# ============================================================================
section("2. Data inventory")

node_labels = [
    "Patient", "Encounter", "EpisodeOfCare",
    "Clinical_finding", "Disease", "Observable_entity",
    "Procedure", "Situation", "SnomedConcept",
    "GPPractice", "Organization", "ReferralRequest",
    "Service", "Workflow",
]

counts: dict[str, int] = {}
for label in node_labels:
    try:
        rows = run(f"MATCH (n:{label}) RETURN count(n) AS cnt")
        cnt = rows[0]["cnt"] if rows else 0
        counts[label] = cnt
        status = "PASS" if cnt > 0 else "WARN"
        record(status, f":{label}", f"{cnt:,} nodes")
    except Exception as exc:
        counts[label] = 0
        record("FAIL", f":{label}", str(exc))

rel_types = [
    ("Patient", "HAS_FINDING", None),
    ("Patient", "HAS_DISORDER", None),
    ("Patient", "HAS_ENCOUNTER", "Encounter"),
    ("Patient", "HAS_EPISODE_OF_CARE", "EpisodeOfCare"),
    ("Patient", "HAS_GENERAL_PRACTITIONER", "GPPractice"),
    ("Encounter", "IS_PART_OF", "EpisodeOfCare"),
    ("ReferralRequest", "FOR_PATIENT", "Patient"),
]

print()
for src, rel, tgt in rel_types:
    tgt_match = f"(t:{tgt})" if tgt else "(t)"
    try:
        rows = run(f"MATCH (s:{src})-[:{rel}]->{tgt_match} RETURN count(*) AS cnt")
        cnt = rows[0]["cnt"] if rows else 0
        status = "PASS" if cnt > 0 else "WARN"
        record(
            status,
            f"(:{src})-[:{rel}]->",
            f"{cnt:,} relationships",
        )
    except Exception as exc:
        record("FAIL", f"(:{src})-[:{rel}]->", str(exc))

# Milestone check for bottleneck algorithm
try:
    rows = run(
        "MATCH ()-[r:IS_PART_OF]->(:EpisodeOfCare) "
        "WHERE r.milestone_type IS NOT NULL "
        "RETURN count(r) AS cnt"
    )
    cnt = rows[0]["cnt"] if rows else 0
    status = "PASS" if cnt > 0 else "WARN"
    record(status, "IS_PART_OF.milestone_type", f"{cnt:,} milestone encounters (needed for bottleneck)")
except Exception as exc:
    record("FAIL", "IS_PART_OF.milestone_type", str(exc))

# ============================================================================
# 3.  GDS availability
# ============================================================================
section("3. GDS plugin")

try:
    rows = run("RETURN gds.version() AS v")
    ver = rows[0]["v"] if rows else "unknown"
    record("PASS", "GDS plugin available", f"version {ver}")
    gds_available = True
except Exception as exc:
    record("FAIL", "GDS plugin available", str(exc))
    gds_available = False

if not gds_available:
    print("\nGDS is not installed on this Aura instance.")
    print("Aura Professional/Enterprise includes GDS.  Check your plan.")
    driver.close()
    sys.exit(1)

# ============================================================================
# 4.  GDS Python client + projections
# ============================================================================
section("4. GDS projections")

try:
    from graphdatascience import GraphDataScience
    gds = GraphDataScience(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    record("PASS", "graphdatascience Python client")
except Exception as exc:
    record("FAIL", "graphdatascience Python client", str(exc))
    driver.close()
    sys.exit(1)

# Drop any stale projections from previous test runs
PROJ_NAMES = [
    "smoke-patient-condition",
    "smoke-condition-cooccur",
    "smoke-patient-journey",
]

for pname in PROJ_NAMES:
    try:
        df = gds.graph.list()
        if pname in df["graphName"].tolist():
            gds.graph.drop(gds.graph.get(pname))
    except Exception:
        pass


def try_project_cypher(name: str, query: str, **params):
    """Create a GDS Cypher projection (directed).

    The query must end with RETURN gds.graph.project($graph_name, src, tgt, {...})
    """
    t0 = time.time()
    try:
        g, result = gds.graph.cypher.project(query, graph_name=name, **params)
        elapsed = time.time() - t0
        nc = g.node_count()
        rc = g.relationship_count()
        record(
            "PASS" if nc > 0 else "WARN",
            f"Projection: {name}",
            f"{nc:,} nodes / {rc:,} rels ({elapsed:.1f}s)",
        )
        return g
    except Exception as exc:
        elapsed = time.time() - t0
        record("FAIL", f"Projection: {name}", f"{exc} ({elapsed:.1f}s)")
        return None


def try_project_native(name: str, node_proj: dict, rel_proj: dict):
    """Create a native GDS projection (supports UNDIRECTED orientation).

    Needed for Leiden, WCC, LCC which require UNDIRECTED relationships.
    """
    t0 = time.time()
    try:
        g, result = gds.graph.project(name, node_proj, rel_proj)
        elapsed = time.time() - t0
        nc = g.node_count()
        rc = g.relationship_count()
        record(
            "PASS" if nc > 0 else "WARN",
            f"Projection: {name}",
            f"{nc:,} nodes / {rc:,} rels ({elapsed:.1f}s)",
        )
        return g
    except Exception as exc:
        elapsed = time.time() - t0
        record("FAIL", f"Projection: {name}", f"{exc} ({elapsed:.1f}s)")
        return None


# -- patient-condition: Patient bipartite to SNOMED entity nodes ----
# Leiden / WCC require UNDIRECTED. Use native projection (gds.graph.project)
# which supports orientation: UNDIRECTED.  Cypher projection does NOT support
# the orientation config key (GDS 2026.03).
# Also includes HAS_CLINICAL_FINDING (10,032) and HAS_OBSERVABLE_ENTITY (26,065)
# which are the richer relationship types that were previously missing.
_PC_NODES = {
    "Patient": {},
    "Clinical_finding": {},
    "Disease": {},
    "Observable_entity": {},
    "Procedure": {},
    "Situation": {},
    "SnomedConcept": {},
}
_PC_RELS = {
    "HAS_CLINICAL_FINDING": {"orientation": "UNDIRECTED"},
    "HAS_OBSERVABLE_ENTITY": {"orientation": "UNDIRECTED"},
    "HAS_DISEASE": {"orientation": "UNDIRECTED"},
    "HAS_FINDING": {"orientation": "UNDIRECTED"},
    "HAS_DISORDER": {"orientation": "UNDIRECTED"},
    "HAS_PROCEDURE": {"orientation": "UNDIRECTED"},
    "HAS_SITUATION": {"orientation": "UNDIRECTED"},
    "HAS_CONCEPT": {"orientation": "UNDIRECTED"},
}
g_pc = try_project_native("smoke-patient-condition", _PC_NODES, _PC_RELS)

# -- condition-cooccur: SNOMED entity nodes linked by shared patient count ----
# Cypher projection (directed via UNION ALL for bidirectionality).
# Includes richer relationship types: HAS_CLINICAL_FINDING, HAS_OBSERVABLE_ENTITY.
_ALL_RELS = (
    "HAS_CLINICAL_FINDING|HAS_OBSERVABLE_ENTITY|HAS_DISEASE|"
    "HAS_FINDING|HAS_DISORDER|HAS_PROCEDURE|HAS_SITUATION|HAS_CONCEPT"
)
CC_QUERY = (
    "CALL { "
    f"  MATCH (p:Patient)-[:{_ALL_RELS}]->(e1) "
    f"  MATCH (p)-[:{_ALL_RELS}]->(e2) "
    "  WHERE id(e1) < id(e2) "
    "  WITH e1, e2, count(DISTINCT p) AS weight "
    "  WHERE weight >= 2 "
    "  RETURN e1, e2, weight "
    "  UNION ALL "
    f"  MATCH (p:Patient)-[:{_ALL_RELS}]->(e1) "
    f"  MATCH (p)-[:{_ALL_RELS}]->(e2) "
    "  WHERE id(e1) < id(e2) "
    "  WITH e1, e2, count(DISTINCT p) AS weight "
    "  WHERE weight >= 2 "
    "  RETURN e2 AS e1, e1 AS e2, weight "
    "} "
    "RETURN gds.graph.project("
    "  $graph_name, e1, e2, {"
    "    sourceNodeLabels: labels(e1),"
    "    targetNodeLabels: labels(e2),"
    "    relationshipType: 'CO_OCCURS_WITH',"
    "    relationshipProperties: {weight: weight}"
    "  })"
)
g_cc = try_project_cypher("smoke-condition-cooccur", CC_QUERY)

# -- patient-journey: Patient -> Encounter -> EpisodeOfCare ----
PJ_QUERY = (
    "MATCH (source)-[r]->(target) "
    "WHERE (source:Patient AND target:Encounter AND type(r) = 'HAS_ENCOUNTER') "
    "   OR (source:Encounter AND target:EpisodeOfCare AND type(r) = 'IS_PART_OF') "
    "RETURN gds.graph.project("
    "  $graph_name, source, target, {"
    "    sourceNodeLabels: labels(source),"
    "    targetNodeLabels: labels(target),"
    "    relationshipType: type(r)"
    "  })"
)
g_pj = try_project_cypher("smoke-patient-journey", PJ_QUERY)


# ============================================================================
# 5.  GDS algorithms
# ============================================================================
section("5. GDS algorithms")


def try_algo(label: str, fn, *args, **kwargs):
    t0 = time.time()
    try:
        df = fn(*args, **kwargs)
        rows = df.to_dict("records")
        elapsed = time.time() - t0
        record("PASS", label, f"{len(rows):,} rows ({elapsed:.1f}s)")
        return rows
    except Exception as exc:
        elapsed = time.time() - t0
        record("FAIL", label, f"{exc} ({elapsed:.1f}s)")
        return None


# -- patient-condition algorithms
if g_pc:
    try_algo("Leiden (community detection)", gds.leiden.stream, g_pc)
    try_algo("WCC (weakly connected components)", gds.wcc.stream, g_pc)
else:
    record("WARN", "Leiden", "Skipped - projection unavailable")
    record("WARN", "WCC", "Skipped - projection unavailable")

# -- condition-cooccur algorithms
if g_cc:
    try_algo("PageRank (condition importance)", gds.pageRank.stream, g_cc,
             dampingFactor=0.85, maxIterations=20)
    try_algo("Degree centrality (busiest conditions)", gds.degree.stream, g_cc)
    # LCC requires UNDIRECTED; condition-cooccur is Cypher-derived (directed).
    # Use Label Propagation as the community-detection replacement for this graph.
    try_algo("Label Propagation (condition clusters)", gds.labelPropagation.stream, g_cc)
    try_algo("Betweenness Centrality (bridges)", gds.betweenness.stream, g_cc)

    # Adamic-Adar: renamed to gds.linkprediction.adamicAdar in GDS 2026.
    # Pre-filter via shared patients before calling the function to avoid
    # an O(n^2) cartesian product over all 1,988+ Clinical_finding nodes.
    try:
        t0 = time.time()
        aa_rows = run(
            "MATCH (n1:Clinical_finding)<-[:HAS_CLINICAL_FINDING]"
            "-(p:Patient)-[:HAS_CLINICAL_FINDING]->(n2:Clinical_finding) "
            "WHERE id(n1) < id(n2) "
            "WITH DISTINCT n1, n2 "
            "WITH n1, n2, gds.linkprediction.adamicAdar(n1, n2) AS score "
            "WHERE score > 0 "
            "RETURN n1.preferredTerm AS term1, n2.preferredTerm AS term2, score "
            "ORDER BY score DESC LIMIT 10"
        )
        elapsed = time.time() - t0
        record("PASS", "Adamic-Adar link prediction (Cypher)",
               f"{len(aa_rows):,} pairs ({elapsed:.1f}s)")
    except Exception as exc:
        elapsed = time.time() - t0
        record("FAIL", "Adamic-Adar link prediction (Cypher)", f"{exc} ({elapsed:.1f}s)")

    # nodeSimilarity: Jaccard similarity on 100k+ rel graph takes 2-5 minutes.
    # Run as async background job only -- skip in smoke test.
    record(
        "WARN",
        "Node Similarity / Jaccard",
        "Skipped in smoke test -- takes 2-5 min on 102k rels. "
        "Background job only.",
    )
else:
    for algo in ("PageRank", "Degree", "Label Propagation",
                 "Betweenness", "Adamic-Adar", "NodeSimilarity"):
        record("WARN", algo, "Skipped - condition-cooccur projection unavailable")

# -- patient-journey algorithms
if g_pj:
    try_algo("SCC (circular journeys)", gds.scc.stream, g_pj)
else:
    record("WARN", "SCC", "Skipped - patient-journey projection unavailable")

# -- Bottleneck: pure Cypher, no GDS needed
section("5b. Bottleneck algorithm (Cypher-only)")
try:
    t0 = time.time()
    rows = run(
        "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        "MATCH (e1:Encounter)-[r1:IS_PART_OF]->(ep) "
        "MATCH (e2:Encounter)-[r2:IS_PART_OF]->(ep) "
        "WHERE r1.milestone_type IS NOT NULL "
        "  AND r2.milestone_type IS NOT NULL "
        "  AND e1.date IS NOT NULL AND e2.date IS NOT NULL "
        "  AND e2.date > e1.date "
        "WITH r2.milestone_type AS label, "
        "     avg(duration.inDays(date(toString(e1.date)), "
        "                         date(toString(e2.date))).days) AS avg_wait, "
        "     count(DISTINCT p.id) AS patient_count "
        "RETURN label, avg_wait, patient_count "
        "ORDER BY avg_wait DESC LIMIT 10"
    )
    elapsed = time.time() - t0
    if rows:
        record("PASS", "Bottleneck (milestone wait times)", f"{len(rows)} milestone steps ({elapsed:.1f}s)")
        for r in rows[:3]:
            print(f"           {r['label']!r:30s}  avg wait: {r['avg_wait']:.1f} days  "
                  f"({r['patient_count']} patients)")
    else:
        record("WARN", "Bottleneck (milestone wait times)",
               f"Query ran but returned 0 rows ({elapsed:.1f}s). "
               "Milestone IS_PART_OF.milestone_type may not be populated yet.")
except Exception as exc:
    record("FAIL", "Bottleneck (milestone wait times)", str(exc))

# ============================================================================
# 6.  Cleanup
# ============================================================================
section("6. Cleanup")
for pname in PROJ_NAMES:
    try:
        df = gds.graph.list()
        existing = set(df["graphName"].tolist()) if len(df) > 0 else set()
        if pname in existing:
            gds.graph.drop(gds.graph.get(pname))
        record("PASS", f"Dropped / absent projection: {pname}")
    except Exception as exc:
        record("WARN", f"Drop projection: {pname}", str(exc))

try:
    gds.close()
    driver.close()
except Exception:
    pass

# ============================================================================
# 7.  Summary
# ============================================================================
section("7. Summary")

counts_by_status = Counter(r["status"] for r in results)
total = len(results)
print(f"  Total checks : {total}")
print(f"  {TICK} PASS     : {counts_by_status.get('PASS', 0)}")
print(f"  {WARN} WARN     : {counts_by_status.get('WARN', 0)}")
print(f"  {FAIL} FAIL     : {counts_by_status.get('FAIL', 0)}")

fails = [r for r in results if r["status"] == "FAIL"]
warns = [r for r in results if r["status"] == "WARN"]

if fails:
    print(f"\n{BOLD}Failures:{RESET}")
    for r in fails:
        print(f"  - {r['name']}: {r['detail']}")

if warns:
    print(f"\n{BOLD}Warnings:{RESET}")
    for r in warns:
        print(f"  - {r['name']}: {r['detail']}")

if not fails and not warns:
    print(f"\n{GREEN}{BOLD}All checks passed -- Pathway Explorer is ready on this Aura instance.{RESET}")
elif not fails:
    print(f"\n{YELLOW}{BOLD}No failures, but review warnings above.{RESET}")
else:
    print(f"\n{RED}{BOLD}Failures detected -- see above for details.{RESET}")
    sys.exit(1)
