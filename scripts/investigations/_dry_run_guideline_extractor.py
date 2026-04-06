"""Dry-run the guidance_rule_extraction subgraph WITHOUT writing to Neo4j.

Invokes the extraction subgraph for a single NG12 recommendation and prints
the coded concept IDs for verification before any rule is committed to Neo4j.

Usage:
    python scripts/investigations/_dry_run_guideline_extractor.py
    python scripts/investigations/_dry_run_guideline_extractor.py --rec NG12:v1:CH002:SEC000:R001
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

import os

from neo4j import GraphDatabase

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

_FETCH_REC = """
MATCH (g:Guideline {id: $gid})-[:HAS_RECOMMENDATION]->(r:Recommendation {id: $rid})
RETURN r.id AS id, r.verbatim AS verbatim, r.title AS title,
       r.urgency AS urgency, r.strength AS strength
"""

_DEFAULT_REC = {
    "id": "NG12:v1:CH002:SEC000:R002",
    "verbatim": (
        "1.1.3 Consider an urgent chest X-ray (to be done within 2 weeks) to assess "
        "for lung cancer in people aged 40 and over with any of the following: "
        "persistent or recurrent chest infection finger clubbing "
        "supraclavicular lymphadenopathy or persistent cervical lymphadenopathy "
        "chest signs consistent with lung cancer thrombocytosis. [2015]"
    ),
    "title": "1.1.3",
    "urgency": "urgent_2w",
    "strength": "consider",
}


def _fetch_rec(rec_id: str) -> dict:
    driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
    with driver.session() as s:
        rows = s.run(_FETCH_REC, gid="NG12", rid=rec_id).data()
    driver.close()
    return rows[0] if rows else {}


def _collect_coded(tree: dict | None, out: list[dict]) -> None:
    if not tree:
        return
    if tree.get("kind") == "concept":
        crit = tree.get("criterion") or {}
        out.append({
            "term": crit.get("term"),
            "snomed_concept_id": crit.get("snomed_concept_id"),
            "preferred_term": crit.get("preferred_term"),
            "semantic_tag": crit.get("semantic_tag"),
            "confidence": crit.get("confidence"),
            "verification_status": crit.get("verification_status"),
        })
        return
    for child in tree.get("children") or []:
        _collect_coded(child, out)


def run(rec: dict) -> None:
    print("=" * 70)
    print(f"Recommendation: {rec.get('id')}")
    print(f"Text: {str(rec.get('verbatim', ''))[:200]}")
    print("=" * 70)

    from libs.pipeline_graph.registry import get_registry

    subgraph = get_registry().build("guidance_rule_extraction")
    result = subgraph.invoke({
        "recommendation": rec,
        "guideline_id": "NG12",
    })

    coded = result.get("coded_criteria")
    errors = result.get("errors") or []

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  {e}")

    if coded is None:
        print("\nRESULT: coded_criteria=None -- rule would NOT be written.")
        return

    coded_leaves: list[dict] = []
    _collect_coded(coded.get("logic_tree"), coded_leaves)

    print(f"\nCoded leaves ({len(coded_leaves)}):")
    for leaf in coded_leaves:
        status = leaf.get("verification_status", "?")
        cid = leaf.get("snomed_concept_id", "NONE")
        term = leaf.get("preferred_term", "?")
        stag = leaf.get("semantic_tag", "?")
        conf = leaf.get("confidence", 0.0)
        flag = "  [OK]" if status == "verified" and cid else "[WARN]"
        print(
            f"  {flag} {leaf.get('term', '?')!r:40s} -> "
            f"{cid} | {term} ({stag}) conf={conf:.2f}"
        )

    action = coded.get("action")
    if action:
        acid = action.get("snomed_concept_id", "NONE")
        aterm = action.get("preferred_term", "?")
        print(f"\nAction: {acid} | {aterm}")
    else:
        print("\nAction: None")

    print("\nFull coded_criteria JSON (truncated):")
    print(json.dumps(coded, indent=2, ensure_ascii=True)[:3000])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dry-run guidance rule extractor on a single recommendation"
    )
    parser.add_argument(
        "--rec",
        default="NG12:v1:CH002:SEC000:R002",
        help="Recommendation ID to test (default: NG12:v1:CH002:SEC000:R002)",
    )
    args = parser.parse_args()

    if args.rec == "NG12:v1:CH002:SEC000:R002":
        rec = _DEFAULT_REC
    else:
        rec = _fetch_rec(args.rec)
        if not rec:
            print(f"Recommendation {args.rec!r} not found in Neo4j.")
            sys.exit(1)

    run(rec)


if __name__ == "__main__":
    main()
