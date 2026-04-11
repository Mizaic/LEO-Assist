"""Updated stats + targeted investigations - using TerminologyClient correctly."""

import sqlite3, pathlib, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
try:
    from libs.keyvault.loader import load_keyvault_secrets

    load_keyvault_secrets()
except Exception as e:
    print(f"[WARN] KV: {e}")

from libs.terminology.client import TerminologyClient

DB = pathlib.Path("scripts/investigations/encounter_audit/remediation.db")
conn = sqlite3.connect(str(DB))

total = conn.execute("SELECT COUNT(*) FROM remediated").fetchone()[0]
applied = conn.execute("SELECT COUNT(*) FROM remediated WHERE applied=1").fetchone()[0]
skipped = conn.execute(
    "SELECT COUNT(*) FROM remediated WHERE applied=0 AND sonnet_reason='terminology_not_found'"
).fetchone()[0]
disputed = conn.execute(
    "SELECT COUNT(*) FROM remediated WHERE applied=0 AND sonnet_reason!='terminology_not_found'"
).fetchone()[0]
enc = conn.execute("SELECT COUNT(*) FROM enc_processed").fetchone()[0]

print(f"Encounters : {enc}/~10136  ({100*enc/10136:.1f}%)")
print(
    f"Proposed   : {total}  Applied={applied} ({100*applied/total:.1f}%) "
    f"Skipped={skipped} ({100*skipped/total:.1f}%) "
    f"Disputed={disputed} ({100*disputed/total:.1f}%)"
)

# -- Test what the client actually resolves for the top-failing terms ------
print("\n--- Resolve test via TerminologyClient (same path as remediate script) ---")
client = TerminologyClient("http://localhost:8001")

TEST_TERMS = [
    "weight loss",
    "weight loss finding",  # tag-stripped form should hit "weight loss"
    "type 2 diabetes mellitus",
    "hypertension",
    "suicidal ideation",  # newly added surface form
    "statin declined",  # newly added surface form
    "facial flushing",  # newly added surface form
    "change in bowel habit",  # newly added surface form
    "generalised anxiety disorder",  # newly added surface form
    "palliative care",
    "abdominal pain",
    "influenza vaccination",
    "chemotherapy in progress",
    "prediabetes",
    "urinary catheter in situ",
]

results = client.resolve(TEST_TERMS)
for term in TEST_TERMS:
    candidates = results.get(term, [])
    if candidates:
        top = candidates[0]
        cid = getattr(top, "concept_id", None) or (
            top.get("concept_id") if isinstance(top, dict) else "?"
        )
        disp = getattr(top, "display", None) or (
            top.get("display") if isinstance(top, dict) else "?"
        )
        conf = getattr(top, "confidence", None)
        print(f"  OK   {term!r:42s} -> {cid} | {disp}  conf={conf}")
    else:
        print(f"  MISS {term!r:42s}")

conn.close()
