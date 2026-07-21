import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import app.config
from app.routers.extraction_scenarios import _score_case_from_node
from tests.helpers.clinical_extraction_scenario_loader import load_expected_strings

doc = load_expected_strings()
case = [c for c in doc["cases"] if c["case_id"] == "brain_cns_email_001"][0]
result = _score_case_from_node(case)
print(f"F1: {result['f1']}, P: {result['precision']}, R: {result['recall']}")
print("Missed:", result['missed_strings'])
print("Extra:", result['extra_strings'])
