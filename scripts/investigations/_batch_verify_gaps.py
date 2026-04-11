"""Batch-verify top missing terms against terminology server."""

import sys, requests, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from libs.terminology.client import TerminologyClient

TERMS = [
    "hypothyroidism",
    "underactive thyroid",
    "iron deficiency anaemia",
    "GORD",
    "gastro-oesophageal reflux disease",
    "heart failure",
    "congestive heart failure",
    "anaemia",
    "hypertriglyceridaemia",
    "haemoptysis",
    "atrial fibrillation",
    "AF",
    "paroxysmal atrial fibrillation",
    "persistent atrial fibrillation",
    "benign prostatic hyperplasia",
    "BPH",
    "enlarged prostate",
    "allergic rhinitis",
    "hayfever",
    "dry eye syndrome",
    "erectile dysfunction",
    "raised blood pressure reading",
    "elevated blood pressure",
    "medication review done",
    "structured medication review",
    "total cholesterol HDL ratio",
    "non-alcoholic fatty liver disease",
    "NAFLD",
    "sleep apnoea",
    "obstructive sleep apnoea",
    "OSA",
    "peripheral neuropathy",
    "diabetic neuropathy",
    "lower back pain",
    "chronic back pain",
    "peripheral arterial disease",
    "PAD",
    "psoriasis",
    "eczema",
    "atopic eczema",
    "basal cell carcinoma",
    "squamous cell carcinoma",
    "neuropathic pain",
    "macrocytosis",
    "vitamin B12 deficiency",
    "vitamin D deficiency",
    "folate deficiency",
    "folic acid deficiency",
    "IDA",
    "BCC",
    "chronic pain syndrome",
]

print("Resolving in one batch ...")
client = TerminologyClient()
results = client.resolve(TERMS)

print(f"\n{'TERM':<45} {'CONCEPT ID':<16} {'SNOMED NAME'}")
print("-" * 110)

needs_mapping = []
already_mapped = []

for term in TERMS:
    hits = results.get(term, [])
    if hits:
        top = hits[0]
        cid = top.concept_id
        name = top.term
        score = top.score or 0
        marker = "OK" if score >= 0.8 else "low-score"
        print(f"  {term:<43} [{cid}] {name[:55]}  ({marker} {score:.2f})")
        already_mapped.append((term, cid, name, score))
    else:
        print(f"  {term:<43} NOT RESOLVED")
        needs_mapping.append(term)

print(f"\n=== SUMMARY ===")
print(f"Resolved : {len(already_mapped)}")
print(f"Not found: {len(needs_mapping)}")
if needs_mapping:
    print("Not found terms:")
    for t in needs_mapping:
        print(f"  - {t}")
