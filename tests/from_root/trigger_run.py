import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import app.config

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Override the require_admin dependency
from app.services.auth import require_admin
async def mock_require_admin():
    from app.services.auth import CallerScope
    return CallerScope(user_id="test", email="test@example.com", roles=["admin"])

app.dependency_overrides[require_admin] = mock_require_admin

resp = client.post("/api/extraction-scenarios/runs", json={"scope": "all"})
print("Status:", resp.status_code)
# print("Response:", resp.json())
