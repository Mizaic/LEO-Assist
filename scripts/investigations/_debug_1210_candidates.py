"""Debug: run expand_leaves + code_snomed for 1.2.10, print action candidates."""

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

with GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass)).session() as s:
    row = s.run(
        "MATCH (r:Recommendation {id: $id}) RETURN r.verbatim AS verbatim, r.urgency AS urgency",
        id="NG12:v1:CH002:SEC001:R009",
    ).single()
rec = {
    "id": "NG12:v1:CH002:SEC001:R009",
    "verbatim": row["verbatim"],
    "urgency": row["urgency"],
}
print("Verbatim:", rec["verbatim"][:120])

# Simulate the raw action the LLM would extract (use known phrase)
raw = {
    "logic_tree": {
        "kind": "concept",
        "node_id": "L1",
        "term": {
            "text": "upper abdominal mass consistent with enlarged gall bladder",
            "search_terms": [],
        },
    },
    "action": {
        "text": "urgent direct access ultrasound scan to assess for gall bladder cancer",
        "search_terms": [],
    },
}

from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
    expand_leaves,
    code_snomed,
)

state1 = {"recommendation": rec, "raw_criteria": raw, "errors": []}
expanded = expand_leaves(state1)
print(
    "\nExpanded action search_terms:",
    (expanded.get("expanded_criteria") or {})
    .get("action", {})
    .get("search_terms", [])[:8],
)

state2 = {
    "recommendation": rec,
    "expanded_criteria": expanded.get("expanded_criteria"),
    "raw_criteria": raw,
    "errors": expanded.get("errors") or [],
}
coded_state = code_snomed(state2)
candidate_criteria = coded_state.get("candidate_criteria") or {}
action = candidate_criteria.get("action") or {}
print("\nAction candidates:")
for c in action.get("candidates") or []:
    cid = c.get("concept_id") or "?"
    pt = c.get("preferred_term") or "?"
    score = float(c.get("score") or 0.0)
    print(f"  {cid} | {pt!r} | {score:.3f}")
