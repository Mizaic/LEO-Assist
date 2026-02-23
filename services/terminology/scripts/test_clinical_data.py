"""
Test encounter_analysis.json and clinical_term_analysis.json against Neo4j.

Tests:
  1. Read code resolution — do the actual Read codes from patient data exist
     in our graph and link to SNOMED concepts?
  2. Abbreviation resolution — can we match GP abbreviations?
  3. Clinical phrase terms — can we resolve the terms from structured phrases?
  4. Encounter text clinical phrases — can we resolve embedded codes like (XaMeF)?
"""

import asyncio
import json
import os
import re
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase


READ_CODE_LOOKUP = """
MATCH (rd:ReadCode {code: $code})
OPTIONAL MATCH (c:Concept)-[:MAPS_TO_READ]->(rd)
WHERE c.active = true
OPTIONAL MATCH (c)<-[:SAME_AS]-(u:UmlsConcept)
RETURN rd.code AS read_code, rd.term AS read_term, rd.version AS version,
       c.id AS snomed, c.fsn AS fsn,
       u.cui AS cui
LIMIT 1
"""

TERM_LOOKUP = """
MATCH (t:Term)-[:DESCRIBES]->(c:Concept)
WHERE t.normalized_form = $norm AND c.active = true
RETURN c.id AS snomed, c.fsn AS fsn
LIMIT 1
"""

ABBREV_LOOKUP = """
MATCH (t:Term)-[:DESCRIBES]->(c:Concept)
WHERE t.normalized_form = $norm AND c.active = true
RETURN c.id AS snomed, c.fsn AS fsn
LIMIT 1
"""


def normalize(term: str) -> str:
    t = term.strip().lower()
    if t.endswith(")"):
        paren = t.rfind("(")
        if paren > 0:
            t = t[:paren].strip()
    return t


def extract_read_code_from_phrase(phrase: str) -> tuple[str, str] | None:
    """Extract Read code like (XaMeF) or (Xa02q) from a phrase."""
    m = re.search(r"\(([A-Za-z0-9]{5,7})\)\s*$", phrase)
    if m:
        code = m.group(1)
        term = phrase[: m.start()].strip()
        return code, term
    return None


async def test_read_codes(session, clinical_data: dict) -> dict:
    """Test Read codes from clinical_term_analysis against graph."""
    ga = clinical_data["global_analysis"]
    top_codes = ga.get("top_read_codes", [])

    found = 0
    with_snomed = 0
    with_cui = 0
    missing = []

    for item in top_codes:
        code = item[0] if isinstance(item, list) else item
        freq = item[1] if isinstance(item, list) and len(item) > 1 else 0

        result = await session.run(READ_CODE_LOOKUP, code=code)
        rec = await result.single()

        if rec and rec["read_code"]:
            found += 1
            if rec["snomed"]:
                with_snomed += 1
            if rec["cui"]:
                with_cui += 1
        else:
            missing.append({"code": code, "freq": freq})

    return {
        "total": len(top_codes),
        "found": found,
        "with_snomed": with_snomed,
        "with_cui": with_cui,
        "missing": missing,
    }


async def test_abbreviations(session, encounter_data: dict) -> dict:
    """Test GP abbreviations against the graph."""
    abbrevs = encounter_data.get("summary", {}).get("abbreviations_in_use", {})

    found = 0
    missing = []

    for abbrev, freq in sorted(abbrevs.items(), key=lambda x: -x[1]):
        norm = normalize(abbrev)
        result = await session.run(TERM_LOOKUP, norm=norm)
        rec = await result.single()

        if rec:
            found += 1
        else:
            missing.append({"abbrev": abbrev, "freq": freq})

    return {
        "total": len(abbrevs),
        "found": found,
        "missing": missing,
    }


async def test_clinical_phrases(session, encounter_data: dict) -> dict:
    """Test clinical phrases — extract embedded Read codes and terms."""
    phrases = encounter_data.get("summary", {}).get(
        "sample_clinical_phrases", []
    )

    embedded_codes_found = 0
    embedded_codes_total = 0
    term_matches = 0
    term_total = 0
    samples = []

    for phrase in phrases:
        extracted = extract_read_code_from_phrase(phrase)
        if extracted:
            code, term_text = extracted
            embedded_codes_total += 1
            result = await session.run(READ_CODE_LOOKUP, code=code)
            rec = await result.single()
            if rec and rec["read_code"]:
                embedded_codes_found += 1
                samples.append({
                    "phrase": phrase[:80],
                    "code": code,
                    "resolved_term": rec["read_term"],
                    "snomed": rec["snomed"],
                    "fsn": rec["fsn"],
                })

        norm = normalize(phrase)
        if len(norm) > 3 and len(norm) < 80:
            term_total += 1
            result = await session.run(TERM_LOOKUP, norm=norm)
            rec = await result.single()
            if rec:
                term_matches += 1

    return {
        "embedded_codes_total": embedded_codes_total,
        "embedded_codes_found": embedded_codes_found,
        "term_matches": term_matches,
        "term_total": term_total,
        "samples": samples[:15],
    }


async def test_structured_terms(session, clinical_data: dict) -> dict:
    """Test terms from the structured phrases (problems, diagnoses)."""
    ga = clinical_data["global_analysis"]
    structured = ga.get("structured_phrases", {})

    results = {}
    for category in ["problem", "diagnosis", "history"]:
        items = structured.get(category, [])
        found = 0
        total = 0

        for item in items[:30]:
            phrase = item[0] if isinstance(item, list) else item

            extracted = extract_read_code_from_phrase(phrase)
            if extracted:
                code, term_text = extracted
                total += 1
                r = await session.run(READ_CODE_LOOKUP, code=code)
                rec = await r.single()
                if rec and rec["read_code"]:
                    found += 1
            else:
                norm = normalize(phrase)
                if len(norm) > 3:
                    total += 1
                    r = await session.run(TERM_LOOKUP, norm=norm)
                    rec = await r.single()
                    if rec:
                        found += 1

        results[category] = {"total": total, "found": found}

    return results


async def test_top_read_terms(session, clinical_data: dict) -> dict:
    """Test the top Read code terms as normalized lookups."""
    ga = clinical_data["global_analysis"]
    top_terms = ga.get("top_read_terms", [])

    found = 0
    missing = []

    for item in top_terms[:50]:
        term = item[0] if isinstance(item, list) else item
        freq = item[1] if isinstance(item, list) and len(item) > 1 else 0
        norm = normalize(term)

        result = await session.run(TERM_LOOKUP, norm=norm)
        rec = await result.single()

        if rec:
            found += 1
        else:
            missing.append({"term": term, "freq": freq})

    return {
        "total": min(50, len(top_terms)),
        "found": found,
        "missing": missing[:20],
    }


async def main():
    load_dotenv(Path("secrets") / ".env")
    uri = os.environ["CODING_GRAPH_NEO4J_URI"]
    user = os.environ["CODING_GRAPH_NEO4J_USERNAME"]
    pw = os.environ["CODING_GRAPH_NEO4J_PASSWORD"]

    with open("external_content/encounter_analysis.json", encoding="utf-8") as f:
        encounter_data = json.load(f)
    with open(
        "external_content/clinical_term_analysis.json", encoding="utf-8"
    ) as f:
        clinical_data = json.load(f)

    driver = AsyncGraphDatabase.driver(uri, auth=(user, pw))

    async with driver.session() as session:

        print("=" * 60)
        print("  TEST 1: Read Code Resolution (top 50 from patient data)")
        print("=" * 60)
        rc = await test_read_codes(session, clinical_data)
        print(f"  Found in graph:  {rc['found']}/{rc['total']}")
        print(f"  With SNOMED:     {rc['with_snomed']}")
        print(f"  With UMLS CUI:   {rc['with_cui']}")
        if rc["missing"]:
            print(f"  Missing codes:")
            for m in rc["missing"][:10]:
                print(f"    {m['code']} (freq={m['freq']})")

        print()
        print("=" * 60)
        print("  TEST 2: GP Abbreviation Resolution")
        print("=" * 60)
        ab = await test_abbreviations(session, encounter_data)
        pct = ab["found"] / ab["total"] * 100 if ab["total"] else 0
        print(f"  Resolved: {ab['found']}/{ab['total']} ({pct:.0f}%)")
        if ab["missing"]:
            print(f"  Unresolved abbreviations:")
            for m in ab["missing"]:
                print(f"    '{m['abbrev']}' (used {m['freq']}x)")

        print()
        print("=" * 60)
        print("  TEST 3: Clinical Phrase Resolution (encounter text)")
        print("=" * 60)
        cp = await test_clinical_phrases(session, encounter_data)
        print(
            f"  Embedded Read codes resolved: "
            f"{cp['embedded_codes_found']}/{cp['embedded_codes_total']}"
        )
        print(
            f"  Full phrase term matches: "
            f"{cp['term_matches']}/{cp['term_total']}"
        )
        if cp["samples"]:
            print(f"  Sample resolved phrases:")
            for s in cp["samples"][:8]:
                print(f"    '{s['phrase']}'")
                print(
                    f"      -> {s['code']} = {s['resolved_term']} "
                    f"| SNOMED {s['snomed']} ({s['fsn']})"
                )

        print()
        print("=" * 60)
        print("  TEST 4: Structured Phrase Terms (problems/diagnoses)")
        print("=" * 60)
        sp = await test_structured_terms(session, clinical_data)
        for cat, counts in sp.items():
            pct = (
                counts["found"] / counts["total"] * 100
                if counts["total"]
                else 0
            )
            print(
                f"  {cat:15s}: {counts['found']}/{counts['total']} "
                f"({pct:.0f}%)"
            )

        print()
        print("=" * 60)
        print("  TEST 5: Top Read Code Terms (normalized term lookup)")
        print("=" * 60)
        rt = await test_top_read_terms(session, clinical_data)
        pct = rt["found"] / rt["total"] * 100 if rt["total"] else 0
        print(f"  Resolved: {rt['found']}/{rt['total']} ({pct:.0f}%)")
        if rt["missing"]:
            print(f"  Unresolved terms (first 20):")
            for m in rt["missing"]:
                print(f"    '{m['term']}' (freq={m['freq']})")

    await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
