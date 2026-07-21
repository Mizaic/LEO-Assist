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

extracted = [
    {'text': 'personality change', 'semantic_tag': 'finding'},
    {'text': 'irritable and withdrawn', 'semantic_tag': 'finding'},
    {'text': 'disinhibition', 'semantic_tag': 'finding'},
    {'text': 'new onset visual disturbance in the right field', 'semantic_tag': 'finding'},
    {'text': 'flickering', 'semantic_tag': 'finding'},
    {'text': 'visual loss', 'semantic_tag': 'finding'},
    {'text': 'abnormal MRI brain scan', 'semantic_tag': 'procedure'},
    {'text': 'primary cancer', 'semantic_tag': 'disorder'},
    {'text': 'Hb', 'semantic_tag': 'observable_entity'},
    {'text': 'WCC', 'semantic_tag': 'observable_entity'},
    {'text': 'Plts', 'semantic_tag': 'observable_entity'},
    {'text': 'MCV', 'semantic_tag': 'observable_entity'},
    {'text': 'Na', 'semantic_tag': 'observable_entity'},
    {'text': 'K', 'semantic_tag': 'observable_entity'},
    {'text': 'Creat', 'semantic_tag': 'observable_entity'},
    {'text': 'ALT', 'semantic_tag': 'observable_entity'},
    {'text': 'Alk Phos', 'semantic_tag': 'observable_entity'},
    {'text': 'Bili', 'semantic_tag': 'observable_entity'},
    {'text': 'Alb', 'semantic_tag': 'observable_entity'},
    {'text': 'CRP', 'semantic_tag': 'observable_entity'},
    {'text': 'ESR', 'semantic_tag': 'observable_entity'},
    {'text': 'Ferritin', 'semantic_tag': 'observable_entity'},
    {'text': 'Ca', 'semantic_tag': 'observable_entity'},
    {'text': 'HbA1c', 'semantic_tag': 'observable_entity'}
]

cleaned = _normalise_validation_terms(extracted, case)
result = score_case(case, cleaned, {"casefold": True, "trim": True, "collapse_whitespace": True, "strip_terminal_punctuation": True, "containment_match": True})
print(f"F1: {result['f1']}")
print(f"TP: {result['true_positive']}, FP: {result['false_positive']}, FN: {result['false_negative']}")
print("Missed:")
for m in result['missed_strings']: print("  ", m)
print("Extra:")
for e in result['extra_strings']: print("  ", e)
