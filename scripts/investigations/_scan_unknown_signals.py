"""Quick signal scan for the 13 UNKNOWN in_progress episode patients.
Prints only encounters with cancer, benign, or referral codings.
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

UNKNOWN_PIDS = [
    ("4842019832", "2024-11-01"),
    ("4247682105", "2025-01-01"),
    ("4998540637", "2025-02-01"),
    ("4867552062", "2025-03-01"),
    ("4926975998", "2025-04-01"),
    ("4300102074", "2025-06-01"),
    ("4246870471", "2025-06-01"),
    ("4202339649", "2025-06-01"),
    ("4644882798", "2025-06-01"),
    ("4203796334", "2025-07-01"),
    ("6012067550", "2025-07-01"),
    ("4920262426", "2025-07-01"),
    ("4983118659", "2025-08-01"),
]

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
    "glioma",
    "adenocarcinoma",
    "metastati",
)
_BENIGN_KW = (
    "no evidence of cancer",
    "no evidence of malignancy",
    "fibroadenoma",
    "adenoma",
    "haemorrhoid",
    "hemorrhoid",
    "hiatus hernia",
    "benign",
    "ulcerative colitis",
    "crohn",
    "diverticular",
    "cyst",
    "polyp",
)
_REFERRAL_KW = (
    "fast track referral",
    "2ww",
    "two week wait",
    "suspected cancer",
    "suspected malignant",
)

_Q = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE p.id = $pid AND toString(e.date) >= $from_date
OPTIONAL MATCH (e)-[doc:DOCUMENTS]->(concept)
WITH e, collect({name: coalesce(concept.name,''), assertion: coalesce(doc.assertion,'')}) AS codings
RETURN
    toString(e.date) AS d,
    codings,
    left(coalesce(e.text, e.note, e.description, ''), 400) AS txt
ORDER BY e.date
"""


def _match(s: str, kws: tuple) -> bool:
    s_lower = s.lower()
    return any(k in s_lower for k in kws)


def _categorise(coded: list[dict]) -> tuple[list[str], list[str], list[str]]:
    cancer, benign, ref = [], [], []
    for c in coded:
        n = c.get("name", "") or ""
        if _match(n, _CANCER_KW):
            label = n
            if c.get("assertion"):
                label += f" [{c['assertion']}]"
            cancer.append(label)
        elif _match(n, _BENIGN_KW):
            benign.append(n)
        elif _match(n, _REFERRAL_KW):
            ref.append(n)
    return cancer, benign, ref


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    for pid, from_date in UNKNOWN_PIDS:
        rows = client.run(_Q, pid=pid, from_date=from_date) or []
        print(f"=== PATIENT {pid} (from {from_date}) ===")
        if not rows:
            print("  (no encounters)")
        for row in rows:
            cancer, benign, ref = _categorise(row["codings"])
            txt = (row["txt"] or "").strip()[:200]
            # Also check raw text
            if _match(txt, _CANCER_KW):
                txt_cancer = "(text has cancer mention)"
            else:
                txt_cancer = ""
            if cancer or benign:
                print(f"  [{row['d']}]")
                if cancer:
                    print(f"    CANCER: {cancer}")
                if benign:
                    print(f"    BENIGN: {benign}")
                if txt:
                    print(f"    TXT: {txt[:200]}")
            elif ref:
                print(f"  [{row['d']}] REF: {ref[0]}")
            elif txt_cancer:
                print(f"  [{row['d']}] {txt_cancer}: {txt[:200]}")
        print()

    client.close()


if __name__ == "__main__":
    main()
