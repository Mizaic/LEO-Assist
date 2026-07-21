import sys
import os
import time
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())

from app.routers.extraction_scenarios import get_run
from libs.auth.org_scope import CallerScope

scope = CallerScope(is_admin=True, email="admin@test.com", org_ids=[])
run_id = "08190932-f060-46fd-bcec-35ae539ad3cc"

while True:
    try:
        res = get_run(run_id, _scope=scope)
        print(res["status"], res.get("progress", 0))
        if res["status"] in ("completed", "failed"):
            print(f"Overall F1: {res.get('overall_f1', 0):.1%}")
            for c in res.get("per_case_results", []):
                if c["case_id"] == "brain_cns_email_001":
                    print("brain_cns_email_001 F1:", c["f1"])
                if c["case_id"] == "brain_cns_known_primary_001":
                    print("brain_cns_known_primary_001 F1:", c["f1"])
            break
    except Exception as e:
        print(e)
    time.sleep(5)
