import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
from app.db.neo4j_client import CodingGraphClient
from tests.helpers.clinical_extraction_scenario_loader import load_expected_strings
from app.services.extraction_scenario_crud import _json_dump

doc = load_expected_strings()
cases = {c["case_id"]: c for c in doc["cases"]}

client = CodingGraphClient()
with client.session() as session:
    res = session.run("MATCH (c:ExtractionScenario) RETURN c.case_id as case_id")
    for r in res:
        case_id = r["case_id"]
        if case_id in cases:
            expected = cases[case_id].get("expected_strings", [])
            # In the original create_scenario logic, they use _json_dump:
            # "expected_strings": _json_dump(payload["expected_strings"])
            expected_json = _json_dump(expected)
            session.run("MATCH (c:ExtractionScenario {case_id: $case_id}) SET c.expected_strings = $expected_json", case_id=case_id, expected_json=expected_json)
