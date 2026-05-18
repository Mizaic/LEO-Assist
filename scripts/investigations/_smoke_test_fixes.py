"""Quick smoke test: verify fixed surface forms resolve to correct SNOMED IDs."""

import requests

TERM_API = "http://localhost:8001/terminology/resolve"

TESTS = [
    ("FIT", "1049361000000101"),
    ("FIT result positive", "71711000112103"),
    ("Smoker", "77176002"),
    ("Current smoker", "77176002"),
    ("Obese", "414915002"),
    ("Night sweats", "42984000"),
    ("Congestive heart failure", "42343007"),
    ("Monocyte count - observation", "1107991000000100"),
    ("Pre-existing diabetes mellitus", "73211009"),
    ("low back pain", "279039007"),
    ("chest tightness", "23924001"),
    ("urine protein creatinine ratio", "1028731000000100"),
    ("perennial rhinitis", "61582004"),
    ("urine albumin creatinine ratio", "5801000237100"),
    ("faecal calprotectin", "1002571000000102"),
    ("faecal immunochemical test abnormal", "1101371000000105"),
    ("CIN3", "285636001"),
    # NG12 guideline coding (surface forms + no duplicate MAPS_TO)
    ("new-onset diabetes", "405749004"),
    ("newly diagnosed diabetes mellitus", "405749004"),
    ("chest x ray findings suggestive of mesothelioma", "9990010014"),
    ("chest signs compatible with pleural disease", "272016000"),
]

passed = 0
failed = 0

for term, expected_cid in TESTS:
    try:
        r = requests.post(
            TERM_API,
            json={"terms": [term], "context": "primary_care"},
            timeout=15,
        )
        if r.status_code != 200:
            print(f"  [ERR ] {term!r:40s}  HTTP {r.status_code} {r.text[:80]}")
            failed += 1
            continue

        body = r.json()
        # Response: {"results": {"<term>": [...]}}
        results_map = body.get("results", {})
        results = results_map.get(term, [])
        top_cid = results[0].get("snomed_concept_id", "") if results else ""
        top_fsn = results[0].get("snomed_term", "") if results else ""
        source = results[0].get("source", "") if results else ""

        if top_cid == expected_cid:
            print(f"  [PASS] {term!r:40s}  {top_cid}  [{source}]" f"  {top_fsn[:55]}")
            passed += 1
        else:
            print(
                f"  [FAIL] {term!r:40s}  got {top_cid} want {expected_cid}"
                f"  {top_fsn[:45]}"
            )
            failed += 1

    except requests.exceptions.Timeout:
        print(f"  [TOUT] {term!r:40s}  timeout")
        failed += 1

print(f"\n{passed}/{passed + failed} passed")
