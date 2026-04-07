"""
Cohort scan: apply post-specialist fallback inference to every
stale_post_specialist episode.

For each episode:
  - Phase 1 (referral -> specialist): confirm attendance, detect private letter
  - Phase 2 (specialist+1 -> specialist+180d): scan for post-outcome signals only

Outputs:
  - Summary verdict breakdown
  - Per-episode CSV rows to results/stale_post_specialist_inference.csv
"""
from __future__ import annotations
import csv
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)
OUT_CSV = RESULTS_DIR / "stale_post_specialist_inference.csv"

POST_WINDOW_DAYS = 180

Q_EPISODES = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = 'stale_post_specialist'
  AND ep.specialist_visit_date IS NOT NULL
RETURN
    ep.patient_id            AS patient_id,
    ep.episode_id            AS episode_id,
    ep.cancer_type           AS cancer_type,
    ep.referral_date         AS referral_date,
    ep.specialist_visit_date AS specialist_date
ORDER BY ep.patient_id, ep.specialist_date
"""

Q_ENCOUNTERS = """
MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE enc.date >= $from_date AND enc.date <= $to_date
RETURN enc.date AS date, enc.flags AS flags, enc.text AS text
ORDER BY enc.date
"""

# ---------------------------------------------------------------------------
# Signal sets
# ---------------------------------------------------------------------------

POST_CANCER: list[tuple[str, str]] = [
    (r"\bexcis",                  "excision"),
    (r"\bmohs\b",                 "mohs surgery"),
    (r"\bwide local excision\b",  "wide local excision"),
    (r"\bsurgical removal\b",     "surgical removal"),
    (r"\boncolog",                "oncology"),
    (r"\bradiother",              "radiotherapy"),
    (r"\bchemother",              "chemotherapy"),
    (r"\bimmunother",             "immunotherapy"),
    (r"\bsentinel node\b",        "sentinel node"),
    (r"\blymph node\b",           "lymph node"),
    (r"\bpatholog",               "pathology"),
    (r"\bhistolog",               "histology"),
    (r"\bbiopsy result\b",        "biopsy result"),
    (r"\bstage [1-4ivi]+\b",      "staging"),
    (r"\bdo not cancel\b",        "urgent recall"),
    (r"\bpriority [ab1]\b",       "high priority f/u"),
    (r"\burgent.*follow",         "urgent follow-up"),
    (r"\bcancer referral",        "cancer referral"),
    (r"\bcarcinoma\b",            "carcinoma"),
    (r"\bmalign",                 "malignant"),
    (r"\bcpms\b",                 "CPMS trial"),
    (r"\bclinical trial",         "clinical trial"),
]

POST_BENIGN: list[tuple[str, str]] = [
    (r"\befudix\b",                    "Efudix"),
    (r"\bfluorouracil\b",              "fluorouracil"),
    (r"\b5[- ]?fu\b",                  "5-FU"),
    (r"\bimiquimod\b",                 "imiquimod"),
    (r"\bphotodynam",                  "photodynamic therapy"),
    (r"\bcryother",                    "cryotherapy"),
    (r"\bcurette\b",                   "curettage"),
    (r"\bak\b",                        "AK"),
    (r"\bactinic keratosis\b",         "actinic keratosis"),
    (r"\bsolar keratosis\b",           "solar keratosis"),
    (r"\bseborrhoeic\b",               "seborrhoeic"),
    (r"\bbenign\b",                    "benign"),
    (r"\bnot malign",                  "not malignant"),
    (r"\bnon[- ]?malign",              "non-malignant"),
    (r"\bno evidence of cancer\b",     "no cancer"),
    (r"\bno further follow[- ]?up\b",  "no further f/u"),
    (r"\bdischarg",                    "discharged"),
    (r"\broutine.*follow",             "routine f/u"),
    (r"\breassur",                     "reassured"),
    (r"\bnot cancer\b",                "not cancer"),
]

PRIVATE_MARKERS = [
    r"event has been made private",
    r"care started at.*uhl",
]

SPECIALIST_SEEN = [
    r"seen in fast track",
    r"uhl dermatology",
    r"uhl.*service",
    r"dermatology to .+",
    r"skin lesion photography",
    r"new lesion template",
    r"dermoscop",
    r"outpatient.*derm",
]


def _hits(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    tl = text.lower()
    return [label for pat, label in patterns if re.search(pat, tl)]


def _has_any(text: str, patterns: list[str]) -> bool:
    tl = text.lower()
    return any(re.search(p, tl) for p in patterns)


def _date_add(d: str, days: int) -> str:
    return (date.fromisoformat(d) + timedelta(days=days)).isoformat()


def _verdict(nc: int, nb: int, private: bool) -> str:
    if nc == 0 and nb == 0:
        return "HITL_REQUIRED"
    if nc > 0 and nb == 0:
        return "INFERRED_CANCER"
    if nb > 0 and nc == 0:
        return "INFERRED_BENIGN"
    if nc > nb:
        return "INFERRED_CANCER_WEAK"
    if nb > nc:
        return "INFERRED_BENIGN_WEAK"
    return "HITL_REQUIRED"


def analyse_episode(s, ep: dict) -> dict:
    pid            = ep["patient_id"]
    episode_id     = ep["episode_id"]
    referral_date  = ep["referral_date"]
    specialist_date = ep["specialist_date"]
    cancer_type    = ep["cancer_type"] or ""

    phase1_end  = specialist_date
    phase2_start = _date_add(specialist_date, 1)
    phase2_end   = _date_add(specialist_date, POST_WINDOW_DAYS)

    rows = s.run(
        Q_ENCOUNTERS,
        pid=pid,
        from_date=referral_date,
        to_date=phase2_end,
    ).data()

    phase1 = [r for r in rows if r["date"] <= phase1_end]
    phase2 = [r for r in rows if r["date"] > phase1_end]

    private_letter = any(
        _has_any((r["text"] or "") + " " + (r["flags"] or ""), PRIVATE_MARKERS)
        for r in phase1
    )
    specialist_confirmed = any(
        _has_any((r["text"] or "") + " " + (r["flags"] or ""), SPECIALIST_SEEN)
        for r in phase1
    )

    cancer_labels: list[str] = []
    benign_labels: list[str] = []
    for r in phase2:
        combined = (r["text"] or "") + " " + (r["flags"] or "")
        cancer_labels.extend(_hits(combined, POST_CANCER))
        benign_labels.extend(_hits(combined, POST_BENIGN))

    nc = len(cancer_labels)
    nb = len(benign_labels)
    v  = _verdict(nc, nb, private_letter)

    return {
        "episode_id":           episode_id,
        "patient_id":           pid,
        "cancer_type":          cancer_type,
        "referral_date":        referral_date,
        "specialist_date":      specialist_date,
        "specialist_confirmed": specialist_confirmed,
        "private_letter":       private_letter,
        "phase2_encounters":    len(phase2),
        "cancer_signal_count":  nc,
        "benign_signal_count":  nb,
        "cancer_signals":       "; ".join(sorted(set(cancer_labels))),
        "benign_signals":       "; ".join(sorted(set(benign_labels))),
        "verdict":              v,
    }


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            episodes = s.run(Q_EPISODES).data()
            print(f"stale_post_specialist episodes: {len(episodes)}")
            print(f"Running inference scan (180d post-specialist window)...\n")

            results = []
            verdict_counts: Counter = Counter()
            cancer_type_counts: dict[str, Counter] = {}

            for i, ep in enumerate(episodes, 1):
                r = analyse_episode(s, ep)
                results.append(r)
                verdict_counts[r["verdict"]] += 1
                ct = r["cancer_type"] or "unknown"
                cancer_type_counts.setdefault(ct, Counter())[r["verdict"]] += 1

                if i % 20 == 0 or i == len(episodes):
                    print(f"  {i}/{len(episodes)} processed...", flush=True)

    finally:
        client.close()

    # -- Console summary ------------------------------------------------------
    total = len(results)
    print(f"\n{'=' * 70}")
    print(f"COHORT VERDICT SUMMARY  (n={total})")
    print(f"{'=' * 70}")
    for verdict, count in sorted(verdict_counts.items(), key=lambda x: -x[1]):
        pct = 100 * count / total if total else 0
        bar = "#" * int(pct / 2)
        print(f"  {verdict:<30} {count:4d}  ({pct:5.1f}%)  {bar}")

    print(f"\nBY CANCER TYPE:")
    for ct in sorted(cancer_type_counts):
        vc = cancer_type_counts[ct]
        ct_total = sum(vc.values())
        parts = ", ".join(f"{v}:{n}" for v, n in sorted(vc.items()))
        print(f"  {ct:<20} n={ct_total:4d}  [{parts}]")

    # -- Private letter breakdown
    n_private = sum(1 for r in results if r["private_letter"])
    n_hitl    = verdict_counts["HITL_REQUIRED"]
    n_hitl_private = sum(
        1 for r in results
        if r["verdict"] == "HITL_REQUIRED" and r["private_letter"]
    )
    print(f"\nPRIVATE LETTER ANALYSIS:")
    print(f"  Episodes with private/blocked letter : {n_private} / {total}")
    print(f"  HITL_REQUIRED episodes               : {n_hitl} / {total}")
    print(f"  HITL caused by private letter        : {n_hitl_private} / {n_hitl}")

    # -- Top cancer signals seen
    all_cancer_sigs: Counter = Counter()
    all_benign_sigs: Counter = Counter()
    for r in results:
        for sig in r["cancer_signals"].split("; "):
            if sig:
                all_cancer_sigs[sig] += 1
        for sig in r["benign_signals"].split("; "):
            if sig:
                all_benign_sigs[sig] += 1

    if all_cancer_sigs:
        print(f"\nTOP POST-SPECIALIST CANCER SIGNALS:")
        for sig, cnt in all_cancer_sigs.most_common(10):
            print(f"  {cnt:4d}  {sig}")
    if all_benign_sigs:
        print(f"\nTOP POST-SPECIALIST BENIGN SIGNALS:")
        for sig, cnt in all_benign_sigs.most_common(10):
            print(f"  {cnt:4d}  {sig}")

    # -- CSV export -----------------------------------------------------------
    fieldnames = list(results[0].keys()) if results else []
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nDetailed results written to: {OUT_CSV}")


if __name__ == "__main__":
    main()
