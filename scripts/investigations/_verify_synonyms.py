"""
Query the terminology server to verify SNOMED concepts for clinical synonym
surface forms and structured result format phrases identified in the April 2026
audit surface_form_gaps.json analysis.

Outputs:
  synonym_verification.json        - full results
  structured_results_analysis.txt  - explanation of structured phrase patterns
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

BASE = "http://localhost:8001"
SEARCH_URL = f"{BASE}/terminology/search"


def search(q: str, tag: str = None, limit: int = 6) -> list[dict]:
    params = {"q": q, "limit": limit}
    if tag:
        params["semantic_tag"] = tag
    try:
        r = requests.get(SEARCH_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return [{"error": str(exc)}]


def top(hits: list[dict]) -> tuple[str | None, str | None, float]:
    for h in hits:
        if "snomed_concept_id" in h:
            return h["snomed_concept_id"], h["term"], round(h.get("score", 0), 2)
    return None, None, 0.0


# ---------------------------------------------------------------------------
# Synonym surface forms grouped by target concept area
# Format: (surface_form, lookup_query, expected_tag, group_label)
# ---------------------------------------------------------------------------
SYNONYMS = [
    # -- Fatigue / energy
    ("tiredness", "fatigue", "finding", "Fatigue"),
    ("tired", "fatigue", "finding", "Fatigue"),
    ("exhaustion", "fatigue", "finding", "Fatigue"),
    ("lethargy", "lethargy", "finding", "Fatigue"),
    ("lethargic", "lethargy", "finding", "Fatigue"),
    ("no energy", "lack of energy", "finding", "Fatigue"),
    ("lack of energy", "lack of energy", "finding", "Fatigue"),
    ("chronically tired", "chronic fatigue", "finding", "Fatigue"),
    ("fatigue", "fatigue", "finding", "Fatigue"),
    # -- Appetite
    ("poor appetite", "poor appetite", "finding", "Appetite"),
    ("loss of appetite", "loss of appetite", "finding", "Appetite"),
    ("reduced appetite", "reduced appetite", "finding", "Appetite"),
    ("decreased appetite", "decreased appetite", "finding", "Appetite"),
    ("not eating", "decreased appetite", "finding", "Appetite"),
    ("appetite reduced", "reduced appetite", "finding", "Appetite"),
    ("anorexia", "anorexia", "finding", "Appetite"),
    # -- Back pain
    ("backache", "backache", "finding", "Back pain"),
    ("back ache", "back pain", "finding", "Back pain"),
    ("low back pain", "low back pain", "finding", "Back pain"),
    ("lower back pain", "lower back pain", "finding", "Back pain"),
    ("lumbar pain", "lumbar pain", "finding", "Back pain"),
    ("lumbago", "lumbago", "finding", "Back pain"),
    ("thoracic back pain", "thoracic back pain", "finding", "Back pain"),
    # -- Breathlessness
    ("breathlessness", "dyspnoea", "finding", "Breathlessness"),
    ("short of breath", "dyspnoea", "finding", "Breathlessness"),
    ("difficulty breathing", "difficulty breathing", "finding", "Breathlessness"),
    ("breathing difficulty", "difficulty breathing", "finding", "Breathlessness"),
    ("can't breathe", "dyspnoea", "finding", "Breathlessness"),
    # -- Weight / appetite
    ("weight loss", "weight loss", "finding", "Weight"),
    ("losing weight", "weight loss", "finding", "Weight"),
    ("unintentional weight loss", "unintentional weight loss", "finding", "Weight"),
    ("unexplained weight loss", "unexplained weight loss", "finding", "Weight"),
    ("weight gain", "weight gain", "finding", "Weight"),
    # -- Abdominal / GI symptoms
    ("tummy pain", "abdominal pain", "finding", "Abdominal pain"),
    ("stomach pain", "abdominal pain", "finding", "Abdominal pain"),
    ("belly pain", "abdominal pain", "finding", "Abdominal pain"),
    ("abdo pain", "abdominal pain", "finding", "Abdominal pain"),
    ("nausea", "nausea", "finding", "Nausea/vomiting"),
    ("vomiting", "vomiting", "finding", "Nausea/vomiting"),
    ("nausea and vomiting", "nausea and vomiting", "finding", "Nausea/vomiting"),
    ("diarrhoea", "diarrhoea", "finding", "Bowel"),
    ("diarrhea", "diarrhoea", "finding", "Bowel"),
    ("loose stools", "loose stools", "finding", "Bowel"),
    ("constipation", "constipation", "finding", "Bowel"),
    ("bloating", "abdominal bloating", "finding", "Bowel"),
    ("wind", "flatulence", "finding", "Bowel"),
    ("indigestion", "indigestion", "finding", "Bowel"),
    ("heartburn", "heartburn", "finding", "Bowel"),
    ("reflux", "gastro-oesophageal reflux", "disorder", "Bowel"),
    ("dyspepsia", "dyspepsia", "finding", "Bowel"),
    ("rectal bleeding", "rectal haemorrhage", "finding", "Bowel"),
    ("blood in stool", "blood in stool", "finding", "Bowel"),
    # -- Urinary
    ("blood in urine", "haematuria", "finding", "Urinary"),
    ("haematuria", "haematuria", "finding", "Urinary"),
    ("passing blood", "haematuria", "finding", "Urinary"),
    ("urinary frequency", "urinary frequency", "finding", "Urinary"),
    ("frequency of urination", "urinary frequency", "finding", "Urinary"),
    ("nocturia", "nocturia", "finding", "Urinary"),
    ("dysuria", "dysuria", "finding", "Urinary"),
    ("burning urine", "dysuria", "finding", "Urinary"),
    ("urinary incontinence", "urinary incontinence", "finding", "Urinary"),
    # -- Other symptoms
    ("night sweats", "night sweats", "finding", "Systemic"),
    ("drenching sweats", "night sweats", "finding", "Systemic"),
    ("dizziness", "dizziness", "finding", "Systemic"),
    ("dizzy", "dizziness", "finding", "Systemic"),
    ("headache", "headache", "finding", "Systemic"),
    ("palpitations", "palpitations", "finding", "Systemic"),
    ("swollen glands", "lymphadenopathy", "finding", "Systemic"),
    ("lymph node swelling", "lymphadenopathy", "finding", "Systemic"),
    ("swollen lymph nodes", "lymphadenopathy", "finding", "Systemic"),
    ("ankle swelling", "ankle oedema", "finding", "Systemic"),
    ("oedema", "oedema", "finding", "Systemic"),
    ("jaundice", "jaundice", "finding", "Systemic"),
    ("itch", "pruritus", "finding", "Systemic"),
    ("itching", "pruritus", "finding", "Systemic"),
    ("pruritus", "pruritus", "finding", "Systemic"),
    ("rash", "rash", "finding", "Systemic"),
    ("lump", "lump", "finding", "Systemic"),
    ("mass", "mass", "finding", "Systemic"),
    ("bruising", "bruising", "finding", "Systemic"),
    ("easy bruising", "easy bruising", "finding", "Systemic"),
    # -- Pain (non-back)
    ("chest tightness", "chest tightness", "finding", "Pain"),
    ("pleuritic pain", "pleuritic chest pain", "finding", "Pain"),
    ("bone pain", "bone pain", "finding", "Pain"),
    ("joint pain", "joint pain", "finding", "Pain"),
    ("arthralgia", "arthralgia", "finding", "Pain"),
    ("myalgia", "myalgia", "finding", "Pain"),
    ("muscle pain", "myalgia", "finding", "Pain"),
    ("hip pain", "hip pain", "finding", "Pain"),
    ("knee pain", "knee pain", "finding", "Pain"),
    ("shoulder pain", "shoulder pain", "finding", "Pain"),
    ("neck pain", "neck pain", "finding", "Pain"),
    # -- Cognition / mood
    ("low mood", "low mood", "finding", "Mental health"),
    ("depression", "depression", "disorder", "Mental health"),
    ("anxiety", "anxiety", "finding", "Mental health"),
    ("brain fog", "cognitive impairment", "finding", "Mental health"),
    ("memory problems", "memory impairment", "finding", "Mental health"),
    ("confusion", "confusion", "finding", "Mental health"),
]


def main() -> None:
    results = []
    seen_queries: dict[str, tuple] = {}  # cache by (query, tag)

    print("Querying terminology server for clinical synonym surface forms...")
    print()

    for surface_form, query, tag, group in SYNONYMS:
        cache_key = (query, tag)
        if cache_key in seen_queries:
            cid, term, score = seen_queries[cache_key]
        else:
            hits = search(query, tag)
            cid, term, score = top(hits)
            seen_queries[cache_key] = (cid, term, score)
            time.sleep(0.04)

        results.append(
            {
                "group": group,
                "surface_form": surface_form,
                "lookup_query": query,
                "semantic_tag": tag,
                "recommended_concept_id": cid,
                "recommended_term": term,
                "score": score,
            }
        )

    out = Path("scripts/investigations/synonym_verification.json")
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Print grouped table
    current_group = None
    print(
        f"{'Surface Form':<30} {'SNOMED Concept ID':<18} {'Preferred Term':<55} {'Score'}"
    )
    print("=" * 115)

    for r in results:
        if r["group"] != current_group:
            current_group = r["group"]
            print(f"\n-- {current_group} --")
        cid = r["recommended_concept_id"] or "NOT FOUND"
        term = (r["recommended_term"] or "")[:53]
        sf = r["surface_form"]
        score = r["score"]
        print(f"  {sf:<28} {cid:<18} {term:<55} {score}")

    found = sum(1 for r in results if r["recommended_concept_id"])
    print(
        f"\n{len(results)} surface forms checked. {found} resolved. {len(results)-found} not found."
    )
    print(f"Written: {out}")


if __name__ == "__main__":
    main()
