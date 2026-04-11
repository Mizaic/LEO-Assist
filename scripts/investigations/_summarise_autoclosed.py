"""Compact one-line summary for each auto-closed episode.

Shows pid, site, ref_date, reason, and the strongest post-referral signal
(CANCER_CONFIRMED / BENIGN / TREATMENT_ONLY / NO_SIGNAL) so we can quickly
decide which episodes are wrongly classified.

Run:
    python scripts/investigations/_summarise_autoclosed.py
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

# Concept name patterns -> verdict
_CONFIRMED_CANCER = (
    "malignant neoplasm of",
    "malignant tumor of",
    "malignant tumour of",
    "carcinoma of",
    "adenocarcinoma",
    "malignant melanoma",
    "malignant lymphoma",
    "malignant neoplasm of prostate",
    "small lymphocytic",
    "haemopoietic and related tissue",
    "metastatic malignant",
    "primary malignant",
    "ductal carcinoma in situ",
    "intraductal carcinoma",
    "carcinoma in situ",
    "invasive carcinoma",
    "breast cancer",
)
_BENIGN_OUTCOMES = (
    "fibroadenoma",
    "tubular adenoma",
    "haemorrhoid",
    "diverticular",
    "irritable bowel",
    "no evidence of cancer",
    "no evidence of malignancy",
    "benign",
    "lipoma",
    "sebaceous cyst",
    "epidermal cyst",
    "cyst of breast",
    "colonic polyp",
)
_TREATMENT = (
    "mastectomy",
    "chemotherapy",
    "radiotherapy",
    "excision of melanoma",
    "excision of basal cell",
    "letrozole",
    "tamoxifen",
    "docetaxel",
    "biopsy of sentinel",
    "wide re-excision",
)
_HISTORICAL = ("history of malignant", "history of malignant neoplasm")

_Q_EPISODES = """
MATCH (ep:EpisodeOfCare)
WHERE ep.auto_closed = true
RETURN ep.patient_id AS pid,
       ep.cancer_type AS site,
       ep.referral_date AS ref,
       ep.status AS status,
       ep.auto_close_reason AS reason,
       ep.specialist_seen AS spec_seen,
       ep.episode_id AS ep_id
ORDER BY ep.auto_close_reason, ep.cancer_type, ep.referral_date
"""

_Q_CODED = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[doc:DOCUMENTS]->(c)
WHERE p.id = $pid
  AND toString(e.date) >= $from_date
  AND NOT coalesce(doc.assertion, 'present') IN ['historical', 'family', 'absent']
RETURN c.name AS name, c.conceptId AS cid
"""


def _verdict(names: list[str]) -> str:
    name_str = " ".join(n.lower() for n in names if n)
    historical_str = " ".join(
        n.lower() for n in names if n and any(h in n.lower() for h in _HISTORICAL)
    )
    has_confirmed = any(
        p in name_str and p not in historical_str for p in _CONFIRMED_CANCER
    )
    has_benign = any(p in name_str for p in _BENIGN_OUTCOMES)
    has_treatment = any(p in name_str for p in _TREATMENT)

    if has_confirmed:
        matching = [
            n
            for n in names
            if any(p in n.lower() for p in _CONFIRMED_CANCER)
            and not any(h in n.lower() for h in _HISTORICAL)
        ]
        return f"CANCER_CONFIRMED  <- {matching[0][:60] if matching else '?'}"
    if has_benign:
        matching = [n for n in names if any(p in n.lower() for p in _BENIGN_OUTCOMES)]
        return f"BENIGN_OUTCOME    <- {matching[0][:60] if matching else '?'}"
    if has_treatment:
        matching = [n for n in names if any(p in n.lower() for p in _TREATMENT)]
        return f"TREATMENT_CODED   <- {matching[0][:60] if matching else '?'}"
    return "NO_SIGNAL"


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    episodes = client.run(_Q_EPISODES) or []
    print(f"Auto-closed: {len(episodes)}\n")

    verdicts: dict[str, list[str]] = {}
    summary_rows = []

    for ep in episodes:
        pid = str(ep["pid"])
        ref = str(ep["ref"] or "")
        rows = client.run(_Q_CODED, pid=pid, from_date=ref) or []
        names = [str(r.get("name") or "") for r in rows]
        v = _verdict(names)
        verdict_key = v.split()[0]
        verdicts.setdefault(verdict_key, []).append(
            f"  {pid}  {ep['site']:20}  ref={ref}  spec={ep.get('spec_seen',False)}  reason={ep['reason']}"
        )
        summary_rows.append(
            (verdict_key, pid, ep["site"], ref, ep["status"], ep["reason"], v)
        )

    # Print grouped by verdict
    for verdict_key in [
        "CANCER_CONFIRMED",
        "BENIGN_OUTCOME",
        "TREATMENT_CODED",
        "NO_SIGNAL",
    ]:
        lines = verdicts.get(verdict_key, [])
        if lines:
            print(f"=== {verdict_key} ({len(lines)}) ===")
            for line in lines:
                print(line)
            print()

    # Final counts
    print("=== VERDICT COUNTS ===")
    for k, v in sorted(verdicts.items(), key=lambda x: -len(x[1])):
        print(f"  {k:25}: {len(v)}")

    client.close()


if __name__ == "__main__":
    main()
