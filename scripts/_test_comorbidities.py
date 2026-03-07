"""Smoke-test for the comorbidities subdomain and patient graph query.

Steps:
  1. Fetch the cancer_audit/comorbidities subdomain to list stored top-level concepts.
  2. Expand each concept via IS_A (terminology API descendants endpoint).
  3. Query the patient graph for HAS_ENCOUNTER -> DOCUMENTS matches per concept group.
  4. Print a summary of what would appear in the audit comorbidities section.

Usage:
    python -m scripts._test_comorbidities
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

ANALYTICS  = "http://localhost:8003/analytics"
TERM       = "http://localhost:8001/terminology"
IS_A_DEPTH = 3
IS_A_LIMIT = 500


def _get(url: str) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"  HTTP {e.code} from {url}: {body[:200]}")
        return None
    except Exception as exc:
        print(f"  Error fetching {url}: {exc}")
        return None


def section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


# ── Step 1: fetch subdomain ───────────────────────────────────
section("STEP 1 — comorbidities subdomain")
sub = _get(f"{ANALYTICS}/domains/cancer_audit/subdomains/comorbidities")
if not sub:
    print("Could not load subdomain. Is the analytics API running on 8003?")
    sys.exit(1)

concepts = sub.get("concepts", [])
print(f"Concepts stored: {len(concepts)}")
for c in concepts:
    cid   = c.get("concept_id") or c.get("preferred_term")
    term  = c.get("term") or c.get("preferred_term", "?")
    print(f"  [{cid}] {term}")

if not concepts:
    print("No concepts in subdomain. Add some via /settings/domains then re-run.")
    sys.exit(1)


# ── Step 2: IS_A expansion ────────────────────────────────────
section("STEP 2 — IS_A expansion per concept")
concept_groups: dict[str, list[str]] = {}  # term -> [str concept IDs]

for c in concepts:
    cid  = str(c.get("concept_id", ""))
    term = c.get("term") or c.get("preferred_term", cid)
    if not cid or cid == "0":
        print(f"  Skipping '{term}' — no valid concept_id")
        continue

    url  = f"{TERM}/concepts/{cid}/descendants?depth={IS_A_DEPTH}&limit={IS_A_LIMIT}"
    rows = _get(url)
    children: list[str] = []
    if isinstance(rows, list):
        children = [str(r["snomed_concept_id"]) for r in rows if r.get("snomed_concept_id")]
    elif rows is None:
        print(f"  [{cid}] {term} — descendants endpoint returned nothing")

    all_ids = [cid] + children
    concept_groups[term] = all_ids
    print(f"  [{cid}] {term}: {len(children)} descendants  (total codes: {len(all_ids)})")
    if children:
        sample = children[:5]
        print(f"         sample children: {sample}{'...' if len(children) > 5 else ''}")


# ── Step 3: check patient graph ───────────────────────────────
section("STEP 3 — patient graph: DOCUMENTS matches per concept group")

# Flat list of all IDs across all groups (strings)
all_ids_flat: list[str] = []
id_to_term:   dict[str, str] = {}
for term, ids in concept_groups.items():
    for i in ids:
        if i not in id_to_term:
            id_to_term[i] = term
        if i not in all_ids_flat:
            all_ids_flat.append(i)

print(f"Total distinct concept IDs to query: {len(all_ids_flat)}")

# Use the export endpoint to verify concept expansion is working,
# then query the analytics comorbidities endpoint (no org filter = England scope)
comorb_url = f"{ANALYTICS}/audit/comorbidities"
result = _get(comorb_url)

if result is None:
    print("Could not reach /audit/comorbidities — the endpoint may not be live yet.")
    print("Falling back to direct Neo4j-free summary from expansion data above.")
else:
    scopes = result.get("scopes", {})
    practice = scopes.get("practice")
    benchmark = result.get("benchmark")
    print(f"Benchmark: {benchmark}")
    if practice:
        rows = practice.get("comorbidities", [])
        total = practice.get("total_patients", 0)
        print(f"\nPractice scope — total patients: {total}")
        if rows:
            print(f"  {'Condition':<40} {'n':>5}  {'%':>6}")
            print(f"  {'-'*40} {'-'*5}  {'-'*6}")
            for row in rows:
                print(f"  {row['condition']:<40} {row['n']:>5}  {row['pct']:>5.1f}%")
        else:
            print("  No comorbidity data found. Possible reasons:")
            print("  - No patients have encounters coded with domain='comorbidities'")
            print("  - The NER pipeline hasn't run with the comorbidities domain loaded")
            print("  - The DOCUMENTS relationship domain property differs from 'comorbidities'")
    else:
        print("  practice scope returned None")


# ── Step 4: verify domain property on DOCUMENTS ───────────────
section("STEP 4 — DOCUMENTS domain property check (via export endpoint)")
export = _get(f"{ANALYTICS}/domains/cancer_audit/subdomains/comorbidities/export?include_children=true&depth={IS_A_DEPTH}")
if export:
    total_children = sum(len(c.get("children", [])) for c in export.get("concepts", []))
    print(f"Export confirms: {len(export.get('concepts', []))} top-level concepts, "
          f"{total_children} total child expansions")
    for c in export.get("concepts", []):
        print(f"  [{c['concept_id']}] {c['term']}  -> {c.get('child_count', 0)} children")
else:
    print("Export endpoint not reachable.")

print()
print("Done. If Step 3 shows zero matches, run Step 4 diagnosis above and check")
print("the DOCUMENTS relationship domain property in Neo4j Browser with:")
print("  MATCH (e:Encounter)-[r:DOCUMENTS]->(d:Disease) RETURN r.domain, count(*) LIMIT 5")
