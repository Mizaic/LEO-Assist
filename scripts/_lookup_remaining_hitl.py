"""Query all remaining pending HITL items, search each against the Terminology API,
and write a markdown table with the results for human review.

Usage:
    .venv\\Scripts\\python scripts\\_lookup_remaining_hitl.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env")
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from neo4j import GraphDatabase

TERM_API = "http://localhost:8001"

# ---------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------


def get_neo4j_driver():
    uri = os.getenv("NEO4J_URI", "")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    driver.verify_connectivity()
    return driver


GET_PENDING_HITL = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE cr.resolved = false AND t.include = true
RETURN cr.entity_text        AS entity_text,
       cr.entity_label       AS entity_label,
       cr.assertion          AS assertion,
       cr.snomed_concept_id  AS snomed_concept_id,
       cr.snomed_term        AS snomed_term,
       cr.decision_tier      AS tier,
       cr.suggested_label    AS suggested_label,
       cr.tag_mismatch_delta AS tag_mismatch_delta,
       count(cr)             AS occurrences
ORDER BY count(cr) DESC, cr.entity_text
"""


def search_term_api(client: httpx.Client, text: str, limit: int = 3) -> list[dict]:
    """Search the Terminology API. Returns top N results."""
    try:
        resp = client.get(
            f"{TERM_API}/terminology/search",
            params={"q": text, "limit": limit},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("results", data.get("items", []))
        return [{"error": f"HTTP {resp.status_code}"}]
    except Exception as exc:
        return [{"error": str(exc)}]


def format_result(r: dict) -> str:
    """Format one terminology search result into a short string."""
    if "error" in r:
        return f"ERROR: {r['error']}"
    cid = (
        r.get("snomed_concept_id")
        or r.get("conceptId")
        or r.get("concept_id")
        or r.get("id")
        or "?"
    )
    term = (
        r.get("term") or r.get("fsn") or r.get("preferredTerm") or r.get("name") or "?"
    )
    tag = r.get("semantic_tag") or r.get("semanticTag") or ""
    score = r.get("score")
    score_str = f" score={score:.2f}" if score is not None else ""
    return f"{cid} {term} ({tag}){score_str}"


def categorise(row: dict) -> str:
    """Categorise a HITL item."""
    if row["snomed_concept_id"] is None and row["suggested_label"] is None:
        return "Uncoded"
    if row["snomed_concept_id"] is None and row["suggested_label"] is not None:
        return "Uncoded+TagHint"
    if row["suggested_label"] and row["suggested_label"] != row["entity_label"]:
        return f"Mismatch: {row['entity_label']}→{row['suggested_label']}"
    return "Low-confidence"


def main():
    driver = get_neo4j_driver()
    print("Connected to Neo4j, fetching pending HITL items...", file=sys.stderr)

    with driver.session() as session:
        rows = list(session.run(GET_PENDING_HITL))
    driver.close()

    print(f"Found {len(rows)} unique entity_text groups", file=sys.stderr)

    client = httpx.Client()

    lines: list[dict] = []
    for idx, row in enumerate(rows):
        text = row["entity_text"]
        label = row["entity_label"]
        assertion = row["assertion"] or "present"
        occurrences = row["occurrences"]
        tier = row["tier"]
        snomed_id = row["snomed_concept_id"] or ""
        snomed_term = row["snomed_term"] or ""
        suggested = row["suggested_label"] or ""
        delta = row["tag_mismatch_delta"]
        category = categorise(dict(row))

        if idx % 25 == 0:
            print(f"  Searching {idx}/{len(rows)}...", file=sys.stderr)

        results = search_term_api(client, text, limit=3)
        time.sleep(0.05)

        top1 = format_result(results[0]) if results else "No results"
        top2 = format_result(results[1]) if len(results) > 1 else ""
        top3 = format_result(results[2]) if len(results) > 2 else ""

        lines.append(
            {
                "entity_text": text,
                "label": label,
                "assertion": assertion,
                "n": occurrences,
                "tier": tier,
                "category": category,
                "current_snomed": f"{snomed_id} {snomed_term}" if snomed_id else "",
                "suggested_label": suggested,
                "delta": f"{delta:.2f}" if delta is not None else "",
                "top1": top1,
                "top2": top2,
                "top3": top3,
            }
        )

    client.close()

    # Write markdown
    out = ROOT / "scripts" / "hitl_remaining_lookup.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write("# Remaining HITL Items — Terminology API Lookup\n\n")
        f.write(f"**Total unique entity texts: {len(lines)}**\n\n")

        # Group by category
        categories = {}
        for line in lines:
            cat = line["category"]
            categories.setdefault(cat, []).append(line)

        for cat in sorted(categories.keys()):
            items = categories[cat]
            total_occ = sum(i["n"] for i in items)
            f.write(
                f"\n## {cat} ({len(items)} unique texts, {total_occ} total reviews)\n\n"
            )
            f.write(
                "| # | Entity Text | Label | Assertion | Count | Tier | Current SNOMED | Top 1 Match | Top 2 Match | Top 3 Match | Action |\n"
            )
            f.write(
                "|---|-------------|-------|-----------|-------|------|----------------|-------------|-------------|-------------|--------|\n"
            )
            for i, item in enumerate(items, 1):
                et = item["entity_text"].replace("|", "\\|")
                f.write(
                    f"| {i} "
                    f"| {et} "
                    f"| {item['label']} "
                    f"| {item['assertion']} "
                    f"| {item['n']} "
                    f"| {item['tier']} "
                    f"| {item['current_snomed'].replace('|', '\\|') if item['current_snomed'] else '-'} "
                    f"| {item['top1']} "
                    f"| {item['top2']} "
                    f"| {item['top3']} "
                    f"| |\n"
                )

    print(f"\nWritten to {out}", file=sys.stderr)
    print(
        f"Categories: {', '.join(f'{k}={len(v)}' for k, v in sorted(categories.items()))}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
