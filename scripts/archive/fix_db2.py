import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
from app.db.neo4j_client import CodingGraphClient
from tests.helpers.clinical_extraction_scenario_loader import load_expected_strings

doc = load_expected_strings()
cases = {c["case_id"]: c for c in doc["cases"]}

client = CodingGraphClient()
with client.session() as session:
    res = session.run("MATCH (c:ExtractionScenario) RETURN c.case_id as case_id, c.expected_strings as e")
    for r in res:
        case_id = r["case_id"]
        if case_id in cases:
            # We want expected_strings to be a literal string containing JSON
            # Make sure it's serialized correctly
            print(f"Current type: {type(r['e'])}")
            print(f"Current value: {r['e']}")
            break
