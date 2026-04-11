"""Resolve all fast-track referral phrases found in the inventory."""

from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from libs.auth.service_auth import get_service_auth_header
import requests

BASE = "http://localhost:8001"
SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

INVENTORY = (
    ROOT
    / "scripts"
    / "investigations"
    / "encounter_audit"
    / "fast_track_referral_encounters.jsonl"
)

phrases: set[str] = set()
with INVENTORY.open() as fh:
    for line in fh:
        row = json.loads(line)
        p = (row.get("matched_phrase") or "").strip()
        if p:
            phrases.add(p)

terms = sorted(phrases)
print(f"Resolving {len(terms)} unique phrases ...\n")

r = SESSION.post(f"{BASE}/terminology/resolve", json={"terms": terms}, timeout=30)
results = r.json().get("results") or {}

print(f"{'PHRASE':<65} {'CONCEPT_ID':<20} {'RESOLVED TERM'}")
print("-" * 130)
for term in terms:
    hits = results.get(term) or []
    top = hits[0] if hits else {}
    cid = top.get("snomed_concept_id", "NOT FOUND")
    label = top.get("snomed_term", "")
    score = top.get("score", 0)
    match = (
        "OK " if label.lower().strip("()") in term.lower() or score == 1.0 else "CHECK"
    )
    print(f"[{match}] {term:<63} {str(cid):<20} {label}")
