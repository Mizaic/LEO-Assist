import httpx
import os
import sys

res = httpx.post("http://localhost:8000/extraction-scenarios/runs", json={"scope": "all"}, headers={"X-Requested-With": "XMLHttpRequest", "Authorization": "Bearer admin"})
print(res.status_code, res.text)
