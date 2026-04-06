"""Quick diagnostic: what does the resolver return for gallbladder ultrasound action terms."""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.terminology.client import TerminologyClient

client = TerminologyClient()
terms = [
    "ultrasound scan of gallbladder",
    "gallbladder ultrasound",
    "ultrasonography of gallbladder",
    "direct access ultrasound of gallbladder",
    "urgent direct access ultrasound scan of abdomen to assess for gall bladder cancer",
    "urgent direct access ultrasound scan to assess for gall bladder cancer",
]
result = client.resolve(terms)
for t in terms:
    hits = result.get(t) or []
    print(f"\n{t!r}:")
    if not hits:
        print("  (no results)")
    for h in hits[:5]:
        if isinstance(h, dict):
            cid = h.get("concept_id") or h.get("snomed_concept_id") or "?"
            pt = h.get("preferred_term") or "?"
            score = float(h.get("score") or 0.0)
        else:
            cid = getattr(h, "concept_id", None) or getattr(h, "snomed_concept_id", "?")
            pt = getattr(h, "preferred_term", "?")
            score = float(getattr(h, "score", 0.0))
        print(f"  {cid} | {pt} | score={score:.3f}")
