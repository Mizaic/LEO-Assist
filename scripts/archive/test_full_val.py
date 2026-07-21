import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import app.config
from app.db.neo4j_client import CodingGraphClient

client = CodingGraphClient()
with client.session() as session:
    res = session.run("MATCH (r:ExtractionValidationRun) WHERE r.per_case_results IS NOT NULL RETURN r.per_case_results as results ORDER BY r.completed_at DESC LIMIT 1").single()
    data = json.loads(res["results"])
    case_res = [c for c in data if c["case_id"] == "brain_cns_known_primary_001"][0]
    
    print("Missed:")
    for m in case_res.get("missed_strings_raw", case_res.get("missed_strings", [])):
        print(f"  {m}")
    print("Extra:")
    for e in case_res.get("extra_strings_raw", case_res.get("extra_strings", [])):
        print(f"  {e}")
