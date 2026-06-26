import json
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())

import app.config  # Load KeyVault secrets
from libs.neo4j_client.client import KnowledgeGraphClient

def update_neo4j():
    with open("tests/fixtures/clinical_extraction_scenarios/expected_strings.json", "r") as f:
        data = json.load(f)
        
    client = KnowledgeGraphClient()
    updated = 0
    with client.session() as session:
        for case in data.get("cases", []):
            case_id = case["case_id"]
            expected_strings = case.get("expected_strings", [])
            query = """
            MATCH (c:ExtractionScenario {case_id: $case_id})
            SET c.expected_strings = $expected_strings
            RETURN c.case_id
            """
            res = session.run(query, case_id=case_id, expected_strings=json.dumps(expected_strings)).single()
            if res:
                updated += 1
                
    print(f"Updated expected_strings for {updated} scenarios in Neo4j.")

if __name__ == "__main__":
    update_neo4j()
