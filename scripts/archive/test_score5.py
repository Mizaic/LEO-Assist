import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import app.config
from app.routers.extraction_scenarios import _normalise_validation_terms, _entity_texts
from tests.helpers.clinical_extraction_scenario_loader import score_case, load_expected_strings
from app.services.validation_workflow_runner import execute_validation_workflow_sync
from libs.neo4j_client.client import KnowledgeGraphClient

client = KnowledgeGraphClient()
with client.session() as session:
    res = session.run("MATCH (c:ExtractionScenario {case_id: 'brain_cns_email_001'}) RETURN c.markdown_body as body").single()
    body = res["body"]

res = execute_validation_workflow_sync(
    un_id="UN-89E2AE36",
    initial_state={
        "case_id": "brain_cns_email_001",
        "encounter_text": body,
        "source_text": body
    }
)
entities = res.get("final_state", {}).get("entities", [])
texts = _entity_texts(entities)

doc = load_expected_strings()
case = [c for c in doc["cases"] if c["case_id"] == "brain_cns_email_001"][0]

print("BEFORE NORM:")
for t in texts:
    print(t)
    
cleaned = _normalise_validation_terms(texts, case)
print("\nAFTER NORM:")
for c in cleaned:
    print(c)
    
result = score_case(case, cleaned, {"casefold": True, "trim": True, "collapse_whitespace": True, "strip_terminal_punctuation": True, "containment_match": True})
print(f"\nF1: {result['f1']}")
print(f"TP: {result['true_positive']}, FP: {result['false_positive']}, FN: {result['false_negative']}")
print("Missed:")
for m in result['missed_strings']: print("  ", m)
print("Extra:")
for e in result['extra_strings']: print("  ", e)
