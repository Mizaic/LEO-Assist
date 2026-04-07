"""
DEPRECATED -- use GET /admin/dq/episodes/infer-outcome or dq_episodes_infer_outcome MCP tool.
Promoted to libs/dq/episodes.py (infer_outcome) and libs/dq/signal_patterns.py. (DI-LEO-AI-089)

180-day post-referral encounter scan -- fallback inference experiment.

Logic:
  Phase 1 (referral window): referral_date to specialist_date
    - used only to confirm specialist attendance; signals here are expected
      and should NOT be used for outcome inference
  Phase 2 (post-specialist window): specialist_date+1 onwards
    - ONLY signals here count for outcome inference
    - cancer post-signals: excision booked, oncology ref, urgent recall,
      pathology result, radiotherapy, surgery
    - benign post-signals: Efudix/fluorouracil, cryotherapy, imiquimod,
      "no further follow-up", "discharged", "routine", AK/solar keratosis
    - private_letter in phase 1: flag as "outcome blocked"
    - no post-signals at all: flag as UNRESOLVABLE -> HITL
"""
from __future__ import annotations
import re
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

PATIENT_ID       = "4203796334"
REFERRAL_DATE    = "2024-08-05"
SPECIALIST_DATE  = "2024-08-30"   # first dermatology attendance
END_DATE         = "2025-02-01"   # ~180 days from referral

Q = """
MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE enc.date >= $from_date AND enc.date <= $to_date
RETURN enc.id AS enc_id, enc.date AS date, enc.flags AS flags, enc.text AS text
ORDER BY enc.date, enc.id
"""

# ---------------------------------------------------------------------------
# Signal sets -- only meaningful POST-specialist
# ---------------------------------------------------------------------------

POST_CANCER = [
    # treatment implying confirmed malignancy
    (r"\bexcis",           "excision"),
    (r"\bmohs\b",          "mohs surgery"),
    (r"\bwide local excision\b", "wide local excision"),
    (r"\bsurgical removal\b",    "surgical removal"),
    (r"\boncolog",         "oncology"),
    (r"\bradiother",       "radiotherapy"),
    (r"\bchemother",       "chemotherapy"),
    (r"\bimmunother",      "immunotherapy"),
    (r"\bsentinel node\b", "sentinel node biopsy"),
    (r"\blymph node\b",    "lymph node"),
    (r"\bpatholog",        "pathology result"),
    (r"\bhistolog",        "histology result"),
    (r"\bbiopsy result\b", "biopsy result"),
    (r"\bstage [1-4ivi]+\b", "staging"),
    (r"\bdo not cancel\b", "urgent recall"),
    (r"\bpriority [ab1]\b","high priority follow-up"),
    (r"\burgent.*follow",  "urgent follow-up"),
    (r"\bcancer referral", "cancer referral"),
    (r"\bscc\b(?!.*suspected)", "SCC confirmed"),
    (r"\bbcc\b(?!.*suspected)", "BCC confirmed"),
    (r"\bmelanoma\b",      "melanoma"),
    (r"\bcarcinoma\b",     "carcinoma"),
    (r"\bmalign",          "malignant"),
    (r"\bclinical trial",  "clinical trial enrolment"),
    (r"\bcpms\b",          "CPMS trial"),
]

POST_BENIGN = [
    (r"\befudix\b",             "Efudix prescribed"),
    (r"\bfluorouracil\b",       "fluorouracil prescribed"),
    (r"\b5[- ]?fu\b",           "5-FU prescribed"),
    (r"\bimiquimod\b",          "imiquimod prescribed"),
    (r"\bphotodynam",           "photodynamic therapy"),
    (r"\bcryother",             "cryotherapy"),
    (r"\bcurette\b",            "curettage"),
    (r"\bak\b",                 "actinic keratosis (AK)"),
    (r"\bactinic keratosis\b",  "actinic keratosis"),
    (r"\bsolar keratosis\b",    "solar keratosis"),
    (r"\bseborrhoeic\b",        "seborrhoeic keratosis"),
    (r"\bbenign\b",             "benign"),
    (r"\bnot malign",           "not malignant"),
    (r"\bnon[- ]?malign",       "non-malignant"),
    (r"\bno evidence of cancer\b", "no cancer found"),
    (r"\bno further follow[- ]?up\b", "no further follow-up"),
    (r"\bdischarg",             "discharged"),
    (r"\broutine.*follow",      "routine follow-up"),
    (r"\b6 months?\b.*review",  "6-month routine review"),
    (r"\breassur",              "reassured"),
    (r"\bnot cancer\b",         "not cancer"),
    (r"\bwait and see\b",       "watchful waiting"),
]

PRIVATE_MARKERS = [
    r"event has been made private",
    r"care started at.*uhl",
]

SPECIALIST_SEEN = [
    r"seen in fast track",
    r"uhl dermatology",
    r"dermatology to .+medical centre",
    r"skin lesion photography",
    r"new lesion template",
    r"dermoscop",
]


def _hits(text: str, patterns: list[tuple]) -> list[tuple[str, str]]:
    """Return (label, snippet) for each matching pattern."""
    tl = text.lower()
    results = []
    for pat, label in patterns:
        m = re.search(pat, tl)
        if m:
            s = max(0, m.start() - 35)
            e = min(len(tl), m.end() + 50)
            snippet = tl[s:e].replace("\n", " ").strip()
            results.append((label, snippet))
    return results


def _has(text: str, patterns: list[str]) -> bool:
    tl = text.lower()
    return any(re.search(p, tl) for p in patterns)


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            rows = s.run(
                Q, pid=PATIENT_ID, from_date=REFERRAL_DATE, to_date=END_DATE
            ).data()
    finally:
        client.close()

    print(f"=== Patient {PATIENT_ID} | {REFERRAL_DATE} -> {END_DATE} | {len(rows)} encounters ===")
    print(f"    Referral date   : {REFERRAL_DATE}")
    print(f"    Specialist date : {SPECIALIST_DATE}  (signals before this are PRE-outcome)")
    print()

    phase1_rows = [r for r in rows if r["date"] <= SPECIALIST_DATE]
    phase2_rows = [r for r in rows if r["date"] >  SPECIALIST_DATE]

    # -- Phase 1 summary ------------------------------------------------------
    private_in_phase1 = any(
        _has((r["text"] or "") + (r["flags"] or ""), PRIVATE_MARKERS)
        for r in phase1_rows
    )
    specialist_confirmed = any(
        _has((r["text"] or "") + (r["flags"] or ""), SPECIALIST_SEEN)
        for r in phase1_rows
    )

    print(f"PHASE 1 -- pre-outcome ({len(phase1_rows)} encounters, up to {SPECIALIST_DATE}):")
    print(f"  Specialist attendance confirmed : {'YES' if specialist_confirmed else 'NO'}")
    print(f"  Private/blocked letter present  : {'YES -- outcome hidden' if private_in_phase1 else 'no'}")

    # -- Phase 2 -- post-specialist signals only ------------------------------
    post_cancer_hits: list[tuple[str, str, str]] = []   # (date, label, snippet)
    post_benign_hits: list[tuple[str, str, str]] = []

    print(f"\nPHASE 2 -- post-specialist ({len(phase2_rows)} encounters, {SPECIALIST_DATE}+1 onwards):")

    cur_date = None
    for r in phase2_rows:
        if r["date"] != cur_date:
            cur_date = r["date"]
            print(f"\n  -- {cur_date} --")

        text = (r["text"] or "").strip()
        flags = (r["flags"] or "").strip()
        combined = text + " " + flags

        c_hits = _hits(combined, POST_CANCER)
        b_hits = _hits(combined, POST_BENIGN)

        for label, snippet in c_hits:
            post_cancer_hits.append((r["date"], label, snippet))
        for label, snippet in b_hits:
            post_benign_hits.append((r["date"], label, snippet))

        flags_short = flags[:70].replace("\n", " ")
        text_short  = text[:150].replace("\n", " ")
        print(f"  [{r['enc_id'][-8:]}]  {flags_short}")
        print(f"           {text_short}")
        if c_hits:
            for label, snip in c_hits:
                print(f"           >> [CANCER POST-SIGNAL]  {label}: \"{snip}\"")
        if b_hits:
            for label, snip in b_hits:
                print(f"           >> [BENIGN POST-SIGNAL]  {label}: \"{snip}\"")
        if not c_hits and not b_hits:
            print(f"           (no outcome signals)")

    # -- Verdict --------------------------------------------------------------
    print(f"\n{'=' * 80}")
    print(f"FALLBACK INFERENCE VERDICT")
    print(f"{'=' * 80}")
    print(f"  Post-specialist cancer signals : {len(post_cancer_hits)}")
    for date, label, snip in post_cancer_hits:
        print(f"    {date}  {label}")
    print(f"  Post-specialist benign signals : {len(post_benign_hits)}")
    for date, label, snip in post_benign_hits:
        print(f"    {date}  {label}")

    nc = len(post_cancer_hits)
    nb = len(post_benign_hits)

    if nc == 0 and nb == 0 and private_in_phase1:
        verdict = "UNRESOLVABLE -- outcome letter is private, no post-clinic signals"
        flag    = "HITL_REQUIRED"
    elif nc == 0 and nb == 0:
        verdict = "UNRESOLVABLE -- no post-specialist signals of any kind"
        flag    = "HITL_REQUIRED"
    elif nb > 0 and nc == 0:
        verdict = "INFERRED BENIGN -- benign-only post-clinic signals"
        flag    = "INFERRED_BENIGN"
    elif nc > 0 and nb == 0:
        verdict = "INFERRED CANCER -- cancer-only post-clinic signals"
        flag    = "INFERRED_CANCER"
    elif nc > nb:
        verdict = f"INFERRED CANCER (weighted: {nc} cancer vs {nb} benign)"
        flag    = "INFERRED_CANCER_WEAK"
    elif nb > nc:
        verdict = f"INFERRED BENIGN (weighted: {nb} benign vs {nc} cancer)"
        flag    = "INFERRED_BENIGN_WEAK"
    else:
        verdict = "AMBIGUOUS -- equal cancer and benign signals"
        flag    = "HITL_REQUIRED"

    print(f"\n  >> {verdict}")
    print(f"  >> flag: {flag}")
    print(f"  >> private letter blocked: {private_in_phase1}")


if __name__ == "__main__":
    main()
