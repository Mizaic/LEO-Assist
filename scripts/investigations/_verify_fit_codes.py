"""Verify SNOMED codes for FIT test variants and add missing surface forms."""

import sys, requests, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

BASE = "http://localhost:8001"


def search(q: str, limit: int = 3) -> list[dict]:
    r = requests.get(
        f"{BASE}/terminology/search", params={"q": q, "limit": limit}, timeout=10
    )
    return r.json() if r.status_code == 200 else []


# Verify the three distinct clinical concepts
CONCEPTS = [
    ("1049361000000101", "FIT test - quantitative observable"),
    ("59614000", "Occult blood DETECTED (positive)"),
    ("71711000112103", "Occult blood detected by immunoassay (BCSP positive)"),
    ("167667006", "Occult blood NOT detected (negative)"),
]

print("=== Verifying FIT concept IDs ===\n")
for cid, desc in CONCEPTS:
    results = search(cid, 1)
    name = results[0]["term"] if results else "NOT FOUND"
    ok = "OK" if results else "MISSING"
    print(f"  [{ok}] {cid}")
    print(f"         Expected: {desc}")
    print(f"         Got:      {name}")
    print()
    time.sleep(0.1)

# Also search for any more specific FIT positive/negative codes
print("=== Searching for FIT-specific SNOMED codes ===\n")
for query in [
    "faecal immunochemical test positive",
    "faecal immunochemical test negative",
    "quantitative faecal immunochemical",
    "fit test result",
]:
    results = search(query, 3)
    print(f"  Search: '{query}'")
    for r in results:
        print(f"    [{r['snomed_concept_id']}] score={r['score']:.1f}  {r['term']}")
    print()
    time.sleep(0.1)
