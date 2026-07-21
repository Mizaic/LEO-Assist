import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import app.config
from app.db.neo4j_client import CodingGraphClient

client = CodingGraphClient()
with client.session() as session:
    res = session.run("MATCH (r:ExtractionValidationRun) RETURN r.status as status, r.completed_at as completed_at, r.per_case_results as results ORDER BY r.triggered_at DESC LIMIT 1").single()
    if res and res["results"]:
        data = json.loads(res["results"])
        case = [c for c in data if c["case_id"] == "brain_cns_email_001"][0]
        print("MISSED:")
        for m in case.get("missed_strings_raw", case.get("missed_strings", [])):
            print(f"  {m}")
        print("EXTRA:")
        for e in case.get("extra_strings_raw", case.get("extra_strings", [])):
            print(f"  {e}")
