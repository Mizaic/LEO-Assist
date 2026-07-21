import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())
import asyncio
from libs.terminology.client import TerminologyClient
from libs.pipeline_graph.subgraphs.terminology import _is_blocked_mapping

phrases = [
    "CA125", "FIT", "weight loss", "Fasting glucose", "Iron", "approximately 2cm", 
    "LDH", "head and neck urgent suspected cancer referral", "suspected head and neck cancer", 
    "ESR", "HbA1c", "lost approximately 3kg", "BP", "PSA", 
    "suspected brain and CNS cancer pathway", "two-week wait pathway", "CA125 raised", 
    "low haemoglobin", "urgent haematology suspected cancer referral", "approximately 3cm"
]

client = TerminologyClient(timeout=10)
results = client.resolve(phrases)

for p in phrases:
    candidates = results.get(p, [])
    if not candidates:
        print(f"'{p}': NO CANDIDATES")
        continue
    best = candidates[0]
    score = float(best.score or 0)
    is_blocked = _is_blocked_mapping(p, best.concept_id)
    safe = not is_blocked and score >= 1.0
    reason = ""
    if not safe:
        if is_blocked: reason = "(blocked mapping)"
        elif score < 1.0: reason = f"(score {score} < 1.0)"
    
    print(f"'{p}': safe={safe} {reason} -> {best.term} ({best.concept_id}, {best.semantic_tag}, score={score})")

