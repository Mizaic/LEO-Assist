import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import app.config
from tests.helpers.clinical_extraction_scenario_loader import score_case, load_expected_strings, _greedy_phrase_match
from app.routers.extraction_scenarios import _normalise_validation_terms

doc = load_expected_strings()
case = [c for c in doc["cases"] if c["case_id"] == "brain_cns_email_001"][0]

extracted = [
    {'text': 'disinhibition', 'semantic_tag': 'finding'}
]

rules = {"casefold": True, "trim": True, "collapse_whitespace": True, "strip_terminal_punctuation": True, "containment_match": True}
expected = list(case.get("expected_strings", []))
expected_dicts = [e if isinstance(e, dict) else {"text": e, "semantic_tag": "finding"} for e in expected]

print("EXPECTED DICTS:")
for e in expected_dicts:
    if e['text'] == 'disinhibition':
        print(e)
        
tp, extra, missed = _greedy_phrase_match(expected_dicts, extracted, rules)
print(f"TP: {tp}")
print("Missed:", missed)
print("Extra:", extra)
