import httpx
import os

token = os.environ.get("TEST_JWT")
res = httpx.post("http://localhost:8000/extraction-scenarios/runs", json={"scope": "all"}, headers={"X-Requested-With": "XMLHttpRequest", "Authorization": f"Bearer {token}"})
print(res.status_code, res.text)
