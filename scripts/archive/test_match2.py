import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
from tests.helpers.clinical_extraction_scenario_loader import load_expected_strings
doc = load_expected_strings()
case = [c for c in doc["cases"] if c["case_id"] == "brain_cns_known_primary_001"][0]
print("EXPECTED:")
for s in case["expected_strings"]:
    if "breast cancer" in s.get("text", ""):
        print(s)
