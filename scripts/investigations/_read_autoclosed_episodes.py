"""Pull all auto-closed episodes and show their post-referral codings.

Prints each episode with its reason, then the coded concepts from encounters
after the referral date so we can verify the auto-close was correct.

Run:
    python scripts/investigations/_read_autoclosed_episodes.py
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

_CANCER_KW = (
    "malign",
    "carcinoma",
    "cancer",
    "sarcoma",
    "lymphoma",
    "melanoma",
    "neoplasm",
    "leukaemia",
    "leukemia",
    "myeloma",
    "adenocarcinoma",
    "metastati",
    "dcis",
    "in situ",
)
_TREATMENT_KW = (
    "mastectomy",
    "chemotherapy",
    "radiotherapy",
    "excision",
    "resection",
    "biopsy",
    "colectomy",
    "cystectomy",
    "orchiectomy",
    "nephrectomy",
    "letrozole",
    "tamoxifen",
    "docetaxel",
    "capecitabine",
    "rituximab",
)
_BENIGN_KW = (
    "no evidence of cancer",
    "no evidence of malignancy",
    "benign",
    "fibroadenoma",
    "haemorrhoid",
    "diverticular",
    "irritable bowel",
    "395100000",
)

_Q_AUTO = """
MATCH (ep:EpisodeOfCare)
WHERE ep.auto_closed = true
RETURN ep.patient_id     AS pid,
       ep.cancer_type    AS site,
       ep.referral_date  AS ref_date,
       ep.status         AS status,
       ep.auto_close_reason AS reason,
       ep.specialist_seen   AS spec_seen,
       ep.episode_id        AS ep_id
ORDER BY ep.auto_close_reason, ep.patient_id, ep.referral_date
"""

_Q_CODED = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE p.id = $pid
  AND toString(e.date) >= $from_date
OPTIONAL MATCH (e)-[doc:DOCUMENTS]->(concept)
WITH e,
     collect({
         name: coalesce(concept.name, ''),
         cid:  coalesce(toString(concept.conceptId), ''),
         assertion: coalesce(doc.assertion, '')
     }) AS codings
RETURN toString(e.date) AS edate,
       codings,
       left(coalesce(e.text, e.note, e.description, ''), 250) AS txt
ORDER BY e.date
"""


def _flag(codings: list[dict], txt: str) -> str:
    all_text = " ".join(c.get("name", "") for c in codings) + " " + txt
    lower = all_text.lower()
    flags = []
    if any(k in lower for k in _CANCER_KW):
        flags.append("CANCER")
    if any(k in lower for k in _TREATMENT_KW):
        flags.append("TREATMENT")
    if any(k in lower for k in _BENIGN_KW):
        flags.append("BENIGN")
    return ",".join(flags) if flags else ""


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    episodes = client.run(_Q_AUTO) or []
    print(f"Auto-closed episodes: {len(episodes)}\n")

    for ep in episodes:
        pid = str(ep["pid"])
        ref_date = str(ep["ref_date"] or "")
        status = ep["status"]
        reason = ep.get("reason") or ""
        site = ep.get("site") or ""
        spec = ep.get("spec_seen", False)

        print(f"{'='*72}")
        print(f"PID={pid}  site={site}  ref={ref_date}  spec={spec}")
        print(f"  status={status}  reason={reason}")

        encs = client.run(_Q_CODED, pid=pid, from_date=ref_date) or []
        if not encs:
            print("  (no encounters after referral)")
        else:
            for enc in encs:
                coded = [
                    c["name"]
                    for c in enc["codings"]
                    if c.get("name") and len(c["name"]) > 5
                ]
                flag = _flag(enc["codings"], enc["txt"] or "")
                if flag or coded:
                    assertion_coded = [
                        (
                            c["name"]
                            + (
                                " [" + c["assertion"] + "]"
                                if c.get("assertion")
                                else ""
                            )
                        )
                        for c in enc["codings"]
                        if c.get("name") and len(c["name"]) > 5
                    ]
                    print(f"  [{enc['edate']}] {flag or '---'}")
                    if assertion_coded:
                        print(f"    {' | '.join(assertion_coded[:6])}")
        print()

    client.close()


if __name__ == "__main__":
    main()
