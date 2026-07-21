import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import app.config
from app.db.neo4j_client import CodingGraphClient
from tests.helpers.clinical_extraction_scenario_loader import score_case, _greedy_phrase_match
from app.routers.extraction_scenarios import _terms_from_validation_output, _json_loads_safe
from libs.cypher.extraction_scenario_queries import LIST_EXTRACTION_SCENARIOS
from app.routers.extraction_scenarios import _normalise_row

client = CodingGraphClient()
with client.session() as session:
    rows = client.run(LIST_EXTRACTION_SCENARIOS, status=None, site=None, search=None)
    cases = [_normalise_row(dict(r)) for r in rows]
    s = [s for s in cases if s["case_id"] == 'brain_cns_known_primary_001'][0]

    case = {
        "case_id": s["case_id"],
        "expected_strings": s["expected_strings"],
        "expected_observables": []
    }

    from app.db.neo4j_client import PatientGraphClient
    pg = PatientGraphClient()
    res = pg.run("MATCH (ae:AuditEvent) WHERE ae.run_id CONTAINS 'brain_cns_known_primary_001' AND ae.validation_output IS NOT NULL RETURN ae.validation_output as output ORDER BY ae.timestamp DESC LIMIT 1")[0]
    row = {"validation_output": res["output"]}
    
    extracted = _terms_from_validation_output(row, case)
    print("RAW PAYLOAD:", _json_loads_safe(row.get("validation_output")))
    expected = [json.loads(s) if isinstance(s, str) else s for s in case["expected_strings"]]
    print("EXPECTED from raw case dictionary:")
    for e in expected:
        print("  ", e)
    print("EXTRACTED:")
    for e in extracted:
        print("  ", e)
    
    tp, extra, missed = _greedy_phrase_match(expected, extracted, {"casefold": True, "trim": True, "collapse_whitespace": True, "strip_terminal_punctuation": True, "containment_match": True})
    
    print("\nTP:", tp)
    print("\nMissed:")
    for m in missed:
        print("  ", m)
    print("\nExtra:")
    for e in extra:
        print("  ", e)

    
    print("Missed raw:")
    for m in missed:
        print(f"  {m}")
    print("Extra raw:")
    for e in extra:
        print(f"  {e}")
