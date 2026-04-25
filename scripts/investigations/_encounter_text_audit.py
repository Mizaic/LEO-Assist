"""
Audit encounter text as source of truth.

For each stale episode patient:
  - Show coding_status breakdown (coded vs uncoded)
  - Show encounter text around the referral date
  - Look for cancer/treatment keywords in text that are NOT in coded SNOMED concepts

Also show the overall coding_status breakdown across the cohort.
"""

import sys, re
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

# Overall coding status across all patients in cohort
_Q_CODING_STATUS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) IN $pids
RETURN e.coding_status AS coding_status, count(e) AS cnt
ORDER BY cnt DESC
"""

# For a patient: encounters in date window with text, ranked by clinical significance
_Q_TEXT_ENCOUNTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
  AND e.date >= $from_date AND e.date <= $to_date
  AND e.text IS NOT NULL AND trim(e.text) <> ''
  AND coalesce(e.classification_content_type, '') <> 'admin_only'
RETURN e.id AS eid, e.date AS date,
       e.coding_status AS coding_status,
       e.classification_content_type AS content_type,
       e.classification_clinical_significance AS significance,
       e.classification_domains AS domains,
       e.classification_encounter_purpose AS purpose,
       e.text AS text
ORDER BY
  CASE e.classification_clinical_significance WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
  e.date
LIMIT 8
"""

# What SNOMED codes were extracted for a patient in a date window
_Q_CODED_CONCEPTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid
  AND e.date >= $from_date AND e.date <= $to_date
RETURN e.date AS date, c.name AS concept, c.conceptId AS cid,
       c.semanticTag AS tag, coalesce(r.assertion, 'present') AS assertion
ORDER BY e.date, c.name
"""

# Keyword patterns in encounter text
_CANCER_PATTERNS = re.compile(
    r"\b(cancer|carcinoma|malignant|melanoma|lymphoma|leukaemia|leukemia|myeloma|"
    r"tumou?r|neoplasm|metastas|oncolog|chemotherapy|radiotherapy|immunotherapy|"
    r"mastectomy|colectomy|resection|excision of|biopsy confirmed|histology|"
    r"diagnosis of|diagnosed with|confirmed|adenocarcinoma|sarcoma|squamous cell|"
    r"basal cell|glioblastoma|mesothelioma)\b",
    re.IGNORECASE,
)
_TREATMENT_PATTERNS = re.compile(
    r"\b(chemotherapy|radiotherapy|immunotherapy|hormone therapy|tamoxifen|letrozole|"
    r"mastectomy|lumpectomy|excision|colectomy|resection|nephrectomy|prostatectomy|"
    r"cystectomy|orchiectomy|thyroidectomy|surgery|operation|SACT|systemic anti-cancer|"
    r"clinical trial|oncology clinic|started treatment)\b",
    re.IGNORECASE,
)

# Stale episodes: patient + referral date
STALE_EPISODES = [
    ("9990002010", "2024-08-05", "skin SCC"),
    ("9990003002", "2024-11-01", "skin melanoma"),
    ("9990002011", "2024-03-01", "skin SCC"),
    ("9990010023", "2024-05-23", "lymphoma head/neck"),
    ("9990010049", "2024-01-22", "lung stale-spec"),
    ("9990010037", "2024-01-18", "lower GI stale-spec"),
    ("9990010063", "2024-04-09", "breast stale-spec"),
    ("9990002012", "2025-01-17", "lower GI stale-nodiag"),
]

# All cohort pids
_Q_ALL_PIDS = """
MATCH (ep:EpisodeOfCare) RETURN DISTINCT ep.patient_id AS pid
"""


def _snippet(text: str, n_chars: int = 400) -> str:
    text = (text or "").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:n_chars] + ("..." if len(text) > n_chars else "")


def main():
    pg = PatientGraphClient()
    try:
        with pg.session() as s:
            pid_rows = s.run(_Q_ALL_PIDS).data()
        all_pids = [r["pid"] for r in pid_rows]

        # 1. Overall coding status
        print("=" * 70)
        print("OVERALL CODING STATUS ACROSS COHORT")
        print("=" * 70)
        with pg.session() as s:
            rows = s.run(_Q_CODING_STATUS, pids=all_pids).data()
        total = sum(r["cnt"] for r in rows)
        for r in rows:
            pct = 100 * r["cnt"] / total if total else 0
            print(f"  {r['coding_status'] or 'None':20s}  {r['cnt']:6d}  ({pct:.1f}%)")
        print(f"  {'TOTAL':20s}  {total:6d}")

        # 2. Per-episode text audit
        for pid, ref_date, label in STALE_EPISODES:
            from datetime import date, timedelta

            ref_dt = date.fromisoformat(ref_date)
            window_end = (ref_dt + timedelta(days=180)).isoformat()

            print()
            print("=" * 70)
            print(
                f"Patient {pid}  |  {label}  |  ref={ref_date}  window={ref_date}..{window_end}"
            )
            print("=" * 70)

            # Coded concepts in window
            with pg.session() as s:
                coded = s.run(
                    _Q_CODED_CONCEPTS, pid=pid, from_date=ref_date, to_date=window_end
                ).data()
            if coded:
                print(f"  Coded concepts ({len(coded)}):")
                for c in coded:
                    print(
                        f"    {c['date']}  [{c['assertion']}]  {c['concept']}  ({c['tag']})"
                    )
            else:
                print("  Coded concepts: NONE")

            # Text encounters in window
            with pg.session() as s:
                texts = s.run(
                    _Q_TEXT_ENCOUNTERS, pid=pid, from_date=ref_date, to_date=window_end
                ).data()
            print(f"\n  Clinical text encounters ({len(texts)}):")
            for t in texts:
                sig = t.get("significance") or "?"
                domains = ", ".join(t.get("domains") or [])
                purpose = ", ".join(t.get("purpose") or [])
                status = t.get("coding_status") or "?"
                text = t.get("text") or ""
                cancer_hits = _CANCER_PATTERNS.findall(text)
                treat_hits = _TREATMENT_PATTERNS.findall(text)
                print(f"\n  [{t['date']}]  sig={sig}  coding={status}")
                print(f"    domains={domains}  purpose={purpose}")
                if cancer_hits:
                    unique = list(dict.fromkeys(h.lower() for h in cancer_hits))[:8]
                    print(f"    CANCER KEYWORDS: {unique}")
                if treat_hits:
                    unique = list(dict.fromkeys(h.lower() for h in treat_hits))[:8]
                    print(f"    TREATMENT KEYWORDS: {unique}")
                print(f"    TEXT: {_snippet(text, 350)}")

    finally:
        pg.close()


if __name__ == "__main__":
    main()
