"""Check terminology search response structure."""

import sys, requests, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))
from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()
from libs.auth.service_auth import get_service_auth_header

HEADERS = get_service_auth_header()
r = requests.get(
    "http://localhost:8001/terminology/search",
    params={"q": "suicidal ideation", "limit": 3},
    headers=HEADERS,
    timeout=30,
)
print("Status:", r.status_code)
body = r.json()
print("Type:", type(body).__name__)
if isinstance(body, list):
    for item in body[:2]:
        print(json.dumps(item, indent=2))
else:
    print(json.dumps(body, indent=2)[:1000])
