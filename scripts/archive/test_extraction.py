import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import app.config
from libs.neo4j_client.client import KnowledgeGraphClient
from app.services.validation_workflow_runner import execute_validation_workflow_sync

client = KnowledgeGraphClient()
with client.session() as session:
    res = session.run("MATCH (c:ExtractionScenario {case_id: 'brain_cns_known_primary_001'}) RETURN c.markdown_body as body").single()
    body = res["body"]

res = execute_validation_workflow_sync(
    un_id="UN-89E2AE36",
    initial_state={
        "case_id": "brain_cns_known_primary_001",
        "encounter_text": body,
        "source_text": body
    }
)
entities = res.get("final_state", {}).get("entities", [])
for e in entities:
    if "breast cancer" in e.get("text", ""):
        print(f"Text: {e.get('text', '')}, Label: {e.get('label', '')}, Assertion: {e.get('assertion', '')}")
