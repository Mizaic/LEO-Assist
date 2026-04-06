"""
Find correct SNOMED concept IDs for radiological lung findings via the
Terminology API search endpoint.
"""
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402
load_keyvault_secrets()
from libs.auth.service_auth import get_service_auth_header  # noqa: E402

BASE = "http://localhost:8001"
SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

SEARCHES = [
    "ground glass opacity lung",
    "ground glass opacity finding",
    "atelectasis",
    "lung collapse",
    "pulmonary atelectasis",
    "hilar lymphadenopathy",
    "mediastinal lymphadenopathy",
    "bilateral hilar enlargement",
    "lung consolidation",
    "pulmonary consolidation",
]


def search(term: str) -> list:
    try:
        r = SESSION.post(
            f"{BASE}/terminology/search",
            json={"query": term, "limit": 5, "filter_semantic_tags": [
                "finding", "disorder", "morphologic abnormality"
            ]},
            timeout=30,
        )
        body = r.json()
        return body if isinstance(body, list) else body.get("results", [])
    except Exception as exc:
        return [{"error": str(exc)}]


def main() -> None:
    for term in SEARCHES:
        print(f"\n-- {term} --")
        results = search(term)
        for r in results[:4]:
            if "error" in r:
                print(f"  ERROR: {r['error']}")
                continue
            cid = r.get("snomed_concept_id") or r.get("concept_id") or "?"
            fsn = r.get("fsn") or r.get("preferred_term") or r.get("term") or "?"
            tag = r.get("semantic_tag") or "?"
            print(f"  {cid:20s} [{tag:25s}] {fsn[:60]}")
        time.sleep(0.3)


if __name__ == "__main__":
    main()
