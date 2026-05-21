import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import app.config
from tests.helpers.clinical_extraction_scenario_loader import score_case, load_expected_strings
from app.routers.extraction_scenarios import _normalise_validation_terms

doc = load_expected_strings()
case = [c for c in doc["cases"] if c["case_id"] == "brain_cns_email_001"][0]
print("EXPECTED IN GOLD:")
for s in case["expected_strings"]:
    print(s)
