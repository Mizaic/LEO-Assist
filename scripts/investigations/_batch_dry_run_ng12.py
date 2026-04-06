"""Batch dry-run of guidance_rule_extraction for all NG12 normative recommendations.

Runs the full extraction pipeline (LLM + resolver + verifier) for every
normative Recommendation in NG12 WITHOUT writing anything to Neo4j.

Produces a structured JSON report:
  scripts/investigations/ng12_dry_run_report.json

and a human-readable summary printed to stdout with:
  - coded leaves per recommendation
  - any unresolved (WARN) leaves
  - the chosen concept ID and preferred term for each leaf

Usage:
    python scripts/investigations/_batch_dry_run_ng12.py

    # Run a single recommendation for fast feedback:
    python scripts/investigations/_batch_dry_run_ng12.py --rec NG12:v1:CH002:SEC000:R001

    # Use AWS Bedrock Haiku for extraction + verifier consensus (default is Sonnet / big):
    # PowerShell:  $env:CONSENSUS_AWS_TIER = "small"
    # bash:        export CONSENSUS_AWS_TIER=small
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
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

_FETCH_RECS = """
MATCH (g:Guideline {id: 'NG12'})-[:HAS_RECOMMENDATION]->(r:Recommendation)
WHERE coalesce(r.isNormative, false) = true
RETURN r.id AS id, r.verbatim AS verbatim, r.title AS title,
       r.urgency AS urgency, r.strength AS strength,
       coalesce(r.requiresCoding, true) AS requiresCoding
ORDER BY r.id
"""

OUTPUT_PATH = ROOT / "scripts" / "investigations" / "ng12_dry_run_report.json"


def _fetch_recs(only_id: str | None = None) -> list[dict]:
    driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
    with driver.session() as s:
        rows = [dict(r) for r in s.run(_FETCH_RECS)]
    driver.close()
    if only_id:
        rows = [r for r in rows if r["id"] == only_id]
    return rows


def _collect_leaves(tree: dict | None, out: list[dict]) -> None:
    """Walk the coded logic tree and collect all concept leaves."""
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
            "needs_human_review": crit.get("needs_human_review"),
            "source_text": crit.get("source_text"),
        })
        return
    for child in tree.get("children") or []:
        _collect_leaves(child, out)


def _run_one(subgraph, rec: dict) -> dict:
    if not rec.get("requiresCoding", True):
        return {
            "rec_id": rec["id"],
            "title": rec["title"],
            "urgency": rec.get("urgency"),
            "status": "skipped",
            "skip_reason": "process_recommendation",
            "errors": [],
            "leaves": [],
            "action": None,
            "elapsed_s": 0.0,
        }

    t0 = time.monotonic()
    result = subgraph.invoke({
        "recommendation": rec,
        "guideline_id": "NG12",
    })
    elapsed = round(time.monotonic() - t0, 1)

    coded = result.get("coded_criteria")
    errors = result.get("errors") or []

    if coded is None:
        return {
            "rec_id": rec["id"],
            "title": rec["title"],
            "urgency": rec.get("urgency"),
            "status": "failed",
            "errors": errors,
            "leaves": [],
            "action": None,
            "elapsed_s": elapsed,
        }

    leaves: list[dict] = []
    _collect_leaves(coded.get("logic_tree"), leaves)
    action = coded.get("action")

    return {
        "rec_id": rec["id"],
        "title": rec["title"],
        "urgency": rec.get("urgency"),
        "status": "ok",
        "errors": errors,
        "leaves": leaves,
        "action": {
            "term": action.get("term"),
            "snomed_concept_id": action.get("snomed_concept_id"),
            "preferred_term": action.get("preferred_term"),
            "semantic_tag": action.get("semantic_tag"),
        } if action else None,
        "elapsed_s": elapsed,
    }


def _print_result(r: dict) -> None:
    status = r["status"]
    if status == "skipped":
        print(f"\n[SKIP] {r['rec_id']} ({r['title']}) - process recommendation, no coding required")
        return
    status_label = "OK " if status == "ok" else "FAIL"
    print(f"\n[{status_label}] {r['rec_id']} ({r['title']}) urgency={r['urgency']} "
          f"elapsed={r['elapsed_s']}s")
    if r["errors"]:
        for e in r["errors"]:
            print(f"  WARN  {e}")
    if status == "failed":
        print("  >> coded_criteria=None -- rule would NOT be written")
        return
    for leaf in r["leaves"]:
        cid = leaf.get("snomed_concept_id") or "UNRESOLVED"
        pterm = leaf.get("preferred_term") or "?"
        stag = leaf.get("semantic_tag") or "?"
        conf = leaf.get("confidence") or 0.0
        flag = "  [OK]" if cid != "UNRESOLVED" else "[WARN]"
        review = " *HUMAN_REVIEW*" if leaf.get("needs_human_review") else ""
        print(
            f"  {flag} {(leaf.get('term') or '?')!r:42s} "
            f"-> {cid} | {pterm} ({stag}) conf={conf:.2f}{review}"
        )
    if r["action"]:
        a = r["action"]
        acid = a.get("snomed_concept_id") or "UNRESOLVED"
        aterm = a.get("preferred_term") or "?"
        flag = "  [OK]" if acid != "UNRESOLVED" else "[WARN]"
        print(f"  {flag} [ACTION] {(a.get('term') or '?')!r:38s} -> {acid} | {aterm}")


def _print_summary(results: list[dict]) -> None:
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total = len(results)
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "failed")
    warn_leaves = [
        (r["rec_id"], leaf)
        for r in results
        for leaf in r["leaves"]
        if not leaf.get("snomed_concept_id")
    ]
    human_review = [
        (r["rec_id"], leaf)
        for r in results
        for leaf in r["leaves"]
        if leaf.get("needs_human_review")
    ]
    print(f"  Recommendations: {total}")
    print(f"  Skipped (process recs, no coding required): {skipped}")
    print(f"  Failed (no coded_criteria): {failed}")
    print(f"  Leaves with UNRESOLVED concept: {len(warn_leaves)}")
    print(f"  Leaves flagged for human review: {len(human_review)}")
    if warn_leaves:
        print("\n  UNRESOLVED leaves (candidates for surface form additions):")
        for rec_id, leaf in warn_leaves:
            print(f"    [{rec_id}] term={leaf.get('term')!r}")
    if human_review:
        print("\n  Human-review leaves (low confidence / no safe match):")
        for rec_id, leaf in human_review:
            cid = leaf.get("snomed_concept_id") or "UNRESOLVED"
            pterm = leaf.get("preferred_term") or "?"
            print(f"    [{rec_id}] term={leaf.get('term')!r} -> {cid} | {pterm}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch dry-run guidance extractor for all NG12 recommendations"
    )
    parser.add_argument(
        "--rec",
        default=None,
        help="Run only a single recommendation by ID",
    )
    args = parser.parse_args()

    recs = _fetch_recs(args.rec)
    if not recs:
        print(f"No recommendations found (filter: {args.rec!r})")
        sys.exit(1)

    print(f"Running extraction for {len(recs)} NG12 recommendation(s) ...")
    print("(No rules will be written to Neo4j.)")

    from libs.pipeline_graph.registry import get_registry
    subgraph = get_registry().build("guidance_rule_extraction")

    results: list[dict] = []
    for idx, rec in enumerate(recs, 1):
        print(f"\n--- [{idx}/{len(recs)}] {rec['id']} ({rec['title']}) ---")
        r = _run_one(subgraph, rec)
        _print_result(r)
        results.append(r)

    _print_summary(results)

    OUTPUT_PATH.write_text(
        json.dumps(results, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    print(f"\nFull report written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
