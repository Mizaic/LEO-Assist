"""
Test known_terms.json against the terminology Neo4j graph.

For each term, attempts resolution via:
  1. Exact normalized match on Term.normalized_form
  2. Fulltext search on Term.surface_form
  3. SurfaceForm node match (already loaded)

Reports coverage statistics and unresolved terms.
"""

import asyncio
import json
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

EXACT_MATCH = """
MATCH (t:Term)-[d:DESCRIBES]->(c:Concept)
WHERE t.normalized_form = $norm AND c.active = true
OPTIONAL MATCH (c)<-[:SAME_AS]-(u:UmlsConcept)
OPTIONAL MATCH (c)-[:MAPS_TO_ICD10]->(icd:Icd10Code)
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
RETURN c.id AS snomed, c.fsn AS fsn, c.semantic_tag AS sem_tag,
       u.cui AS cui, u.semantic_types AS sem_types,
       collect(DISTINCT icd.code)[..3] AS icd10,
       collect(DISTINCT rd.code)[..3] AS read_codes,
       d.acceptability AS acceptability
LIMIT 5
"""

FULLTEXT_MATCH = """
CALL db.index.fulltext.queryNodes('term_fulltext', $query)
YIELD node AS t, score
WHERE score > 1.0
MATCH (t)-[:DESCRIBES]->(c:Concept {active: true})
RETURN c.id AS snomed, c.fsn AS fsn, score
ORDER BY score DESC
LIMIT 3
"""


def normalize(term: str) -> str:
    t = term.strip().lower()
    if t.endswith(")"):
        paren = t.rfind("(")
        if paren > 0:
            t = t[:paren].strip()
    return t


async def main():
    load_dotenv(Path("secrets") / ".env")
    uri = os.environ["CODING_GRAPH_NEO4J_URI"]
    user = os.environ["CODING_GRAPH_NEO4J_USERNAME"]
    pw = os.environ["CODING_GRAPH_NEO4J_PASSWORD"]

    with open(
        Path("external_content") / "known_terms.json", encoding="utf-8"
    ) as f:
        terms = json.load(f)

    terms = [t.strip() for t in terms if t.strip()]
    total = len(terms)
    print(f"Testing {total} known terms against Neo4j graph\n")

    driver = AsyncGraphDatabase.driver(uri, auth=(user, pw))

    exact_hits = 0
    fulltext_hits = 0
    with_cui = 0
    with_icd10 = 0
    with_read = 0
    sem_tag_counts = Counter()
    unresolved = []
    fulltext_only = []

    async with driver.session() as session:
        for i, term in enumerate(terms):
            norm = normalize(term)

            result = await session.run(EXACT_MATCH, norm=norm)
            records = await result.data()

            if records:
                exact_hits += 1
                rec = records[0]
                if rec["cui"]:
                    with_cui += 1
                if rec["icd10"]:
                    with_icd10 += 1
                if rec["read_codes"]:
                    with_read += 1
                tag = rec.get("sem_tag") or "unknown"
                sem_tag_counts[tag] += 1
            else:
                try:
                    ft_result = await session.run(
                        FULLTEXT_MATCH, query=norm
                    )
                    ft_records = await ft_result.data()
                except Exception:
                    ft_records = []

                if ft_records:
                    fulltext_hits += 1
                    fulltext_only.append(
                        (term, ft_records[0]["fsn"], ft_records[0]["score"])
                    )
                else:
                    unresolved.append(term)

            if (i + 1) % 500 == 0:
                print(f"  Processed {i + 1}/{total}...")

    await driver.close()

    resolved = exact_hits + fulltext_hits
    print(f"\n{'=' * 60}")
    print(f"  RESULTS: {total} known terms tested")
    print(f"{'=' * 60}")
    print(f"  Exact match:    {exact_hits:>5} ({exact_hits/total*100:.1f}%)")
    print(f"  Fulltext match: {fulltext_hits:>5} ({fulltext_hits/total*100:.1f}%)")
    print(f"  Total resolved: {resolved:>5} ({resolved/total*100:.1f}%)")
    print(f"  Unresolved:     {len(unresolved):>5} ({len(unresolved)/total*100:.1f}%)")
    print()
    print(f"  With UMLS CUI:  {with_cui:>5} ({with_cui/exact_hits*100:.1f}% of exact)")
    print(f"  With ICD-10:    {with_icd10:>5} ({with_icd10/exact_hits*100:.1f}% of exact)")
    print(f"  With Read code: {with_read:>5} ({with_read/exact_hits*100:.1f}% of exact)")

    print(f"\n  Top semantic tags (from exact matches):")
    for tag, cnt in sem_tag_counts.most_common(15):
        print(f"    {tag:40s} {cnt:>5}")

    if fulltext_only:
        print(f"\n  Sample fulltext-only matches (top 10):")
        for term, fsn, score in fulltext_only[:10]:
            print(f"    '{term}' -> {fsn} (score={score:.2f})")

    if unresolved:
        print(f"\n  Sample unresolved terms (first 30):")
        for t in unresolved[:30]:
            print(f"    '{t}'")

    out_path = Path("services/terminology/scripts/known_terms_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "total": total,
                "exact_match": exact_hits,
                "fulltext_match": fulltext_hits,
                "unresolved_count": len(unresolved),
                "unresolved_terms": unresolved,
                "fulltext_only": [
                    {"term": t, "matched_fsn": fsn, "score": score}
                    for t, fsn, score in fulltext_only
                ],
            },
            f,
            indent=2,
        )
    print(f"\n  Full results written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
