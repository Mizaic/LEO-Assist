"""Inventory all cancer pathway encounters for 'no evidence of cancer' phrases.

Loads all encounters for the 93-patient fast-track cohort in a single query,
then matches T1/T2/T3 phrase tiers in Python.  Writes a JSONL inventory and
prints a summary table.

Output: scripts/investigations/encounter_audit/no_cancer_phrase_inventory.jsonl
        scripts/investigations/encounter_audit/no_cancer_t3_review.jsonl

Run:
    python scripts/investigations/_inventory_no_cancer_phrases.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

OUT_DIR = ROOT / "scripts" / "investigations" / "encounter_audit"
OUT_MAIN = OUT_DIR / "no_cancer_phrase_inventory.jsonl"
OUT_T3 = OUT_DIR / "no_cancer_t3_review.jsonl"

CONCEPT_ID = 395100000

# ---------------------------------------------------------------------------
# Phrase tiers
# ---------------------------------------------------------------------------

T1_PHRASES = [
    "no evidence of cancer",
    "no evidence of malignancy",
    "no malignancy",
    "negative for malignancy",
    "neg for malignancy",
    "negative for cancer",
    "malignancy excluded",
    "cancer excluded",
    "sarcoma excluded",
    "malignancy ruled out",
    "cancer ruled out",
    "sarcoma ruled out",
    "no malignant cells",
    "negative for malignant cells",
    "no evidence of malignant cells",
    "no evidence of neoplasm",
    "no neoplasm",
    "no evidence of tumour",
    "no evidence of tumor",
    "no tumour",
    "no tumor",
    "negative for tumour",
    "negative for tumor",
    "no evidence of carcinoma",
    "no evidence of sarcoma",
    "no evidence of metastatic disease",
    "no metastatic disease",
    "no metastases",
    "no mets",
    "no evidence of neoplasia",
    "malignancy not identified",
    "cancer not identified",
    "malignancy not seen",
    "cancer not seen",
    "does not suggest malignancy",
    "does not support malignancy",
    "not in keeping with malignancy",
    "not in keeping with cancer",
    "in keeping with benign",
    "against malignancy",
    "argues against malignancy",
    "inconsistent with malignancy",
    "inconsistent with cancer",
    "malignancy unlikely",
    "cancer unlikely",
    "no evidence of cancer found",
    # NOTE: the following are deliberately excluded -- they all imply a PRIOR
    # cancer diagnosis (post-treatment context), not an exclusion of cancer:
    # "in remission", "complete remission", "disease free", "disease-free",
    # "no evidence of recurrence", "no recurrent disease", "no evidence of
    # residual disease", "no active malignancy", "no evidence of relapse",
    # "complete response", "no evidence of local recurrence"
]

T2_PHRASES = [
    "biopsy benign",
    "biopsy shows benign",
    "biopsy negative for malignancy",
    "pathology benign",
    "pathology negative",
    "histology benign",
    "histology negative for malignancy",
    "cytology benign",
    "cytology negative",
    "specimen benign",
    "sample benign",
    "no malignant cells seen",
    "no tumour cells seen",
    "no tumor cells seen",
    "no neoplastic cells",
    "benign histology",
    "benign pathology",
    "benign cytology",
    "features are benign",
    "findings are benign",
    "consistent with benign lesion",
    "benign on histology",
    "benign on pathology",
    "no histological evidence of malignancy",
    "no pathological evidence of malignancy",
    "reactive changes",
    "reactive process",
    "consistent with reactive change",
]

T3_PHRASES = [
    "benign appearing",
    "benign-appearing",
    "appears benign",
    "appearance benign",
    "likely benign",
    "probably benign",
    "favours benign",
    "favors benign",
    "favoured benign",
    "consistent with benign",
    "compatible with benign",
    "benign process",
    "benign finding",
    "benign features",
    "benign characteristics",
    "benign change",
    "benign neoplasm",
    "radiographically benign",
    "benign radiographic appearance",
    "benign imaging appearance",
    "imaging favours benignity",
    "imaging favors benignity",
    "well circumscribed",
    "well-circumscribed",
    "well defined",
    "well-defined",
    "no aggressive features",
    "without aggressive features",
    "non aggressive features",
    "non-aggressive features",
    "no suspicious features",
    "no sinister features",
    "nothing concerning",
    "no concerning features",
    "no worrisome features",
    "reassuring",
    "reassuring appearance",
    "reassuring features",
    "no aggressive radiographic features",
    "no aggressive imaging features",
    "no cortical destruction",
    "no bone destruction",
    "no destructive lesion",
    "no suspicious mass",
    "no soft tissue mass",
    "narrow zone of transition",
    "sclerotic margin",
    "sharp margin",
    "geographic lesion",
    "no imaging evidence of malignancy",
    "no radiographic evidence of malignancy",
    "unremarkable",
    "incidental benign",
    "innocuous lesion",
    "innocent lesion",
]

# Phrases to EXCLUDE even if they contain a T1/T2 substring (separate clinical class)
EXCLUSION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"rule\s+out\s+malign",
        r"r/o\s+malign",
        r"cannot\s+exclude\s+malign",
        r"can(?:not|'t)\s+rule\s+out",
        r"history\s+of\s+(cancer|malign|carcinoma|tumou?r)",
        r"prior\s+(cancer|malign|carcinoma|tumou?r)",
        r"known\s+(cancer|malign|carcinoma|tumou?r)",
        r"background\s+of\s+(cancer|malign)",
    ]
]

# Also exclude screening-programme phrases (already guarded in post-processing)
SCREENING_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"cervical\s+smear",
        r"cervical\s+cytology",
        r"hpv\s+(test|not\s+detected)",
        r"negative\s+fit\b",
        r"\bfobt\b",
        r"faecal\s+immunochemical",
        r"faecal\s+occult\s+blood",
        r"bowel\s+cancer\s+screening\s+programme",
        r"overall\s+negative\s+result",
        r"sent\s+following\s+(?:an\s+)?overall\s+negative",
        r"normal\s+recall",
    ]
]


def _build_patterns(phrases: list[str]) -> list[tuple[str, re.Pattern]]:
    return [(p, re.compile(re.escape(p), re.IGNORECASE)) for p in phrases]


def _load_patient_ids() -> list[str]:
    ids: set[str] = set()
    for inv in [
        ROOT
        / "scripts"
        / "investigations"
        / "encounter_audit"
        / "fast_track_specialist_encounters.jsonl",
        ROOT
        / "scripts"
        / "investigations"
        / "encounter_audit"
        / "fast_track_referral_encounters.jsonl",
    ]:
        if not inv.exists():
            print(f"WARNING: {inv} not found")
            continue
        with inv.open() as fh:
            for line in fh:
                pid = json.loads(line).get("patient_id", "").strip()
                if pid:
                    ids.add(pid)
    return sorted(ids)


_Q_ENCOUNTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE p.id IN $pids
OPTIONAL MATCH (e)-[:DOCUMENTS]->(c395 {conceptId: 395100000})
WITH
    toString(p.id)                                 AS patient_id,
    toString(e.id)                                 AS encounter_id,
    coalesce(toString(e.date), '')                 AS date,
    coalesce(e.text, e.note, e.description, '')    AS enc_text,
    count(c395) > 0                                AS already_coded
ORDER BY patient_id, date
RETURN patient_id, encounter_id, date, enc_text, already_coded
"""


def _is_excluded(text: str) -> bool:
    return any(p.search(text) for p in EXCLUSION_PATTERNS) or any(
        p.search(text) for p in SCREENING_PATTERNS
    )


def _match_tier(text: str, patterns: list[tuple[str, re.Pattern]]) -> list[str]:
    return [phrase for phrase, pat in patterns if pat.search(text)]


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    patient_ids = _load_patient_ids()
    print(f"Loaded {len(patient_ids)} patients from inventory.")

    t1_pats = _build_patterns(T1_PHRASES)
    t2_pats = _build_patterns(T2_PHRASES)
    t3_pats = _build_patterns(T3_PHRASES)

    print("Fetching all encounters (single query) ...")
    client = PatientGraphClient()
    rows = []
    with client.session() as session:
        rows = list(session.run(_Q_ENCOUNTERS, pids=patient_ids))
    client.close()
    print(f"Fetched {len(rows)} encounters.")

    stats: dict[str, dict] = {
        "t1": {"already_coded": 0, "uncoded": 0, "excluded": 0},
        "t2": {"already_coded": 0, "uncoded": 0, "excluded": 0},
        "t3": {"already_coded": 0, "uncoded": 0, "excluded": 0},
    }
    phrase_enc_counts: dict[str, int] = defaultdict(int)

    out_rows = []
    t3_rows = []

    for row in rows:
        text = row["enc_text"] or ""
        already_coded = row["already_coded"]
        enc_id = row["encounter_id"]
        pid = row["patient_id"]
        date = row["date"][:10] if row["date"] else ""
        excluded = _is_excluded(text)

        t1 = _match_tier(text, t1_pats)
        t2 = _match_tier(text, t2_pats)
        t3 = _match_tier(text, t3_pats)

        # Filter T3: remove any that are only present because of screening language
        t3 = [p for p in t3 if not any(sp.search(text) for sp in SCREENING_PATTERNS)]

        if not (t1 or t2 or t3):
            continue

        for phrase in t1:
            phrase_enc_counts[phrase] += 1
        for phrase in t2:
            phrase_enc_counts[phrase] += 1

        if t1 or t2:
            tier = "T1" if t1 else "T2"
            matched = (t1 or []) + (t2 or [])
            if excluded:
                stats[tier.lower()]["excluded"] += 1
            elif already_coded:
                stats[tier.lower()]["already_coded"] += 1
            else:
                stats[tier.lower()]["uncoded"] += 1

            record = {
                "patient_id": pid,
                "encounter_id": enc_id,
                "date": date,
                "tier": tier,
                "matched_phrases": matched,
                "already_coded_395100000": already_coded,
                "excluded": excluded,
                "enc_text_snippet": text[:200],
            }
            out_rows.append(record)

        if t3:
            if excluded:
                stats["t3"]["excluded"] += 1
            else:
                stats["t3"]["already_coded" if already_coded else "uncoded"] += 1
            t3_rows.append(
                {
                    "patient_id": pid,
                    "encounter_id": enc_id,
                    "date": date,
                    "tier": "T3",
                    "matched_phrases": t3,
                    "already_coded_395100000": already_coded,
                    "excluded": excluded,
                    "enc_text_snippet": text[:300],
                }
            )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_MAIN.open("w") as fh:
        for r in out_rows:
            fh.write(json.dumps(r) + "\n")

    with OUT_T3.open("w") as fh:
        for r in t3_rows:
            fh.write(json.dumps(r) + "\n")

    print()
    print("=" * 70)
    print(f"INVENTORY COMPLETE")
    print(f"  T1+T2 records written : {len(out_rows)}  -> {OUT_MAIN.name}")
    print(f"  T3 records written    : {len(t3_rows)}  -> {OUT_T3.name}")
    print()
    print(f"  {'Tier':<6}  {'Already coded':>14}  {'Uncoded':>9}  {'Excluded':>9}")
    print(f"  {'-'*6}  {'-'*14}  {'-'*9}  {'-'*9}")
    for tier_key, label in [("t1", "T1"), ("t2", "T2"), ("t3", "T3")]:
        s = stats[tier_key]
        print(
            f"  {label:<6}  {s['already_coded']:>14}  {s['uncoded']:>9}  {s['excluded']:>9}"
        )

    print()
    print("  Top 20 matched phrases (T1+T2):")
    for phrase, cnt in sorted(phrase_enc_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"    {cnt:4d}  {phrase!r}")


if __name__ == "__main__":
    main()
