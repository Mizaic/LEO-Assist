import json

with open("tests/fixtures/clinical_extraction_scenarios/expected_strings.json", "r") as f:
    data = json.load(f)

for case in data.get("cases", []):
    strings = set(case.get("expected_strings", []))
    blood_results = case.get("blood_results", {}).get("results", [])
    for br in blood_results:
        strings.add(br["display_name"])
    case["expected_strings"] = list(strings)

with open("tests/fixtures/clinical_extraction_scenarios/expected_strings.json", "w") as f:
    json.dump(data, f, indent=4)
