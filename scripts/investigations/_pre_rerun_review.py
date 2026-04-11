"""Analyse current audit report to identify improvements before re-run."""

import csv
import json
import pathlib
import collections

RESULTS_DIR = pathlib.Path("scripts/investigations/encounter_audit/results")
SUMMARY_CSV = pathlib.Path("scripts/investigations/encounter_audit/summary.csv")

rows = list(csv.DictReader(open(SUMMARY_CSV)))
total = len(rows)
clean = sum(1 for r in rows if r.get("assessment") == "clean")
print(f"Overall pct_clean: {100*clean/total:.1f}%  ({clean:,}/{total:,})\n")

missing_terms = collections.Counter()
overcoded_terms = collections.Counter()
wrong_assertions = collections.Counter()
long_snomed_searches = []

scanned = 0
for f in list(RESULTS_DIR.glob("*.json"))[:300]:
    try:
        raw = json.loads(f.read_text())
        # Result files are a list of encounter dicts
        enc_list = raw if isinstance(raw, list) else raw.get("encounters", [])
        for enc in enc_list:
            r = enc if isinstance(enc, dict) else {}
            # Handle both direct result and nested result key
            result = r.get("result", r)
            for m in result.get("missing", []):
                ss = (m.get("snomed_search") or m.get("term") or "").strip()
                if ss:
                    missing_terms[ss.lower()] += 1
                    if len(ss.split()) > 5:
                        long_snomed_searches.append(ss)
            for oc in result.get("overcoded", []):
                key = (oc.get("name") or oc.get("conceptId") or "").strip()
                if key:
                    overcoded_terms[key.lower()] += 1
            for wa in result.get("wrong_assertion", []):
                key = (
                    f"{wa.get('current_assertion','')} -> "
                    f"{wa.get('suggested_assertion','')}"
                )
                wrong_assertions[key] += 1
        scanned += 1
    except Exception as e:
        pass

print(f"(Sampled {scanned} patient files)\n")

print("=" * 65)
print("TOP 40 MISSING TERMS (snomed_search field)")
print("=" * 65)
for t, n in missing_terms.most_common(40):
    print(f"  {n:4d}x  {t}")

print()
print("=" * 65)
print("TOP 20 OVERCODED TERMS")
print("=" * 65)
for t, n in overcoded_terms.most_common(20):
    print(f"  {n:4d}x  {t}")

print()
print("=" * 65)
print("WRONG ASSERTION PATTERNS")
print("=" * 65)
for t, n in wrong_assertions.most_common(15):
    print(f"  {n:4d}x  {t}")

if long_snomed_searches:
    print()
    print("=" * 65)
    print("SNOMED SEARCHES STILL TOO LONG (> 5 words) -- prompt issue")
    print("=" * 65)
    seen = set()
    for s in long_snomed_searches:
        if s not in seen:
            seen.add(s)
            print(f"  {s!r}")
        if len(seen) >= 20:
            break
