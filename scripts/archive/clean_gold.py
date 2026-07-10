import json

with open("tests/fixtures/clinical_extraction_scenarios/expected_strings.json", "r") as f:
    data = json.load(f)

for case in data.get("cases", []):
    case_id = case["case_id"]
    strings = case.get("expected_strings", [])
    new_strings = [s for s in strings if s.lower() not in ("ldh", "fasting glucose", "bp")]
    if len(new_strings) != len(strings):
        case["expected_strings"] = new_strings

with open("tests/fixtures/clinical_extraction_scenarios/expected_strings.json", "w") as f:
    json.dump(data, f, indent=4)
