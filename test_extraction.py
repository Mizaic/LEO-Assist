import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import app.config
from libs.neo4j_client.client import KnowledgeGraphClient
from app.services.validation_workflow_runner import execute_validation_workflow_sync

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
from app.routers.extraction_scenarios import _normalise_validation_terms, _entity_texts
from tests.helpers.clinical_extraction_scenario_loader import load_expected_strings
doc = load_expected_strings()
case = [c for c in doc["cases"] if c["case_id"] == "brain_cns_email_001"][0]
print("Entities before normalise:")
texts = _entity_texts(entities)
for t in texts:
    print(t)
    
print("\nEntities after normalise:")
cleaned = _normalise_validation_terms(texts, case)
for c in cleaned:
    print(c)
