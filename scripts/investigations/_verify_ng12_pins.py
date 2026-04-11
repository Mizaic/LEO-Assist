"""Verify that key pinned SNOMED concepts are returned by the terminology resolver.

Checks:
  1. Mesothelioma CXR findings -> 1290960005
  2. Pleural disease chest signs -> 272016000
  3. New-onset diabetes -> 405749004
  4. Ascites (finding) -> look for it
  5. Palpable/enlarged gallbladder -> look for it
"""

import asyncio, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.terminology.client import TerminologyClient

CHECKS = [
    {
        "label": "Mesothelioma CXR findings",
        "terms": [
            "chest X-ray findings suggestive of mesothelioma",
            "pleural mesothelioma radiological finding",
            "CXR mesothelioma",
        ],
        "want_id": "1290960005",
    },
    {
        "label": "Chest signs compatible with pleural disease",
        "terms": [
            "chest signs compatible with pleural disease",
            "chest signs pleural disease examination",
            "on examination chest finding",
        ],
        "want_id": "272016000",
    },
    {
        "label": "New-onset diabetes mellitus",
        "terms": [
            "new-onset diabetes mellitus",
            "newly diagnosed diabetes mellitus",
            "405749004 newly diagnosed diabetes",
        ],
        "want_id": "405749004",
    },
    {
        "label": "Ascites (finding)",
        "terms": [
            "ascites",
            "ascites finding",
            "abdominal ascites",
        ],
        "want_id": None,
    },
    {
        "label": "Palpable enlarged gallbladder",
        "terms": [
            "palpable gallbladder",
            "enlarged gallbladder",
            "upper abdominal mass gallbladder",
        ],
        "want_id": None,
    },
]


async def check_term(client: TerminologyClient, term: str) -> list[dict]:
    try:
        result = await client.resolve(term)
        return result or []
    except Exception as exc:
        return [{"error": str(exc)}]


async def main() -> None:
    client = TerminologyClient()
    for check in CHECKS:
        print(f"\n=== {check['label']} (want: {check['want_id'] or 'any'}) ===")
        for term in check["terms"]:
            candidates = await check_term(client, term)
            ids_found = [c.get("concept_id") for c in candidates if "concept_id" in c]
            found_target = check["want_id"] in ids_found if check["want_id"] else False
            flag = (
                "FOUND" if found_target else ("?" if not check["want_id"] else "MISS")
            )
            print(f"  [{flag}] {term!r}")
            for c in candidates[:5]:
                cid = c.get("concept_id", "?")
                pt = c.get("preferred_term", c.get("error", "?"))
                marker = " <-- TARGET" if cid == check["want_id"] else ""
                print(f"         {cid} | {pt}{marker}")


if __name__ == "__main__":
    asyncio.run(main())
