import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())

from app.routers.extraction_scenarios import trigger_run, RunRequest
from libs.auth.org_scope import CallerScope

scope = CallerScope(is_admin=True, email="admin@test.com", org_ids=[])
class MockAdmin:
    pass

res = trigger_run(body=RunRequest(scope="all"), scope=scope, _admin=MockAdmin())
print(res)
