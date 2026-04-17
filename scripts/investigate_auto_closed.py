"""Investigate WHY auto-closed episodes are missing pathway milestones.

For each auto-closed patient, this:
  1. Re-runs the text anchor detector
  2. Looks for explicit text evidence the regex missed
  3. Categorises the failure mode (regex miss, missing benign vocab,
     persistence bug, false-positive referral)
  4. Produces a per-patient and aggregate report
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.domain_config.registry import DomainRegistry  # noqa: E402
from libs.neo4j_client.client import PatientGraphClient  # noqa: E402
from services.analysis_worker.app.analyzers.anchor_detector import (  # noqa: E402
    detect_anchors,
    _RE_FIRST_SEEN,
    _RE_NO_CANCER,
    _RE_REFERRAL,
    _RE_REFERRAL_PRISM,
)

# Phrases the system should be detecting but currently isn't.
RE_FT_REFERRAL_TEXT = re.compile(
    r"\bFast\s+track\s+referral\s+for\s+suspected\b", re.I
)
RE_FT_CLINIC_TEXT = re.compile(
    r"\bSeen\s+in\s+fast\s+track\s+suspected\b.{0,40}clinic\b", re.I
)
RE_2WW_PROFORMA = re.compile(r"\b2WW\b.{0,40}\b(?:proforma|patient awaiting)\b", re.I)

# Common benign/normal histology results that should close pathways
RE_BENIGN_HISTOLOGY = re.compile(
    r"\b(?:lipoma|fibroadenoma|sebaceous cyst|epidermal cyst|seborrhoeic keratosis|"
    r"actinic keratosis|skin tag|benign naevus|dermatofibroma|"
    r"no abnormality detected|normal appearance|"
    r"no evidence of malignancy|no malignant cells|"
    r"unremarkable|polyp removed|inflammatory change|reactive change)\b",
    re.I,
)

# Histology-style confirmed cancer phrasing
RE_HISTOLOGY_CANCER = re.compile(
    r"\b(?:adenocarcinoma|carcinoma|invasive ductal|invasive lobular|"
    r"DCIS|LCIS|melanoma in situ|squamous cell carcinoma|basal cell carcinoma|"
    r"BCC|SCC|grade [123]|Gleason|T[1234][a-c]?N[0-3]M[01]|"
    r"poorly differentiated|moderately differentiated|well differentiated|"
    r"high grade|low grade|metastatic|invasive)\b",
    re.I,
)


def fetch_auto_closed(client: PatientGraphClient) -> list[dict]:
    return client.run(
        """
        MATCH (e:EpisodeOfCare)
        WHERE e.auto_closed = true
        RETURN
            e.patient_id AS pid,
            e.episode_id AS eid,
            e.status AS status,
            e.referral_date AS ref_date,
            e.first_seen_date AS first_seen_date,
            e.specialist_visit_date AS spec_date,
            e.cancer_type AS cancer,
            e.referral_site AS site,
            e.auto_close_reason AS reason
        ORDER BY e.patient_id, e.referral_date
        """
    )


def fetch_encounter_texts(client: PatientGraphClient, pid: str) -> list[dict]:
    return client.run(
        """
        MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(e:Encounter)
        WHERE e.text IS NOT NULL AND e.date IS NOT NULL AND trim(e.text) <> ''
        RETURN toString(e.date) AS dt, toString(e.id) AS eid, e.text AS text
        ORDER BY e.date
        """,
        pid=pid,
    )


def categorise_failures(pid: str, ep: dict, anchors, texts: list[dict]) -> dict:
    fails: list[str] = []

    has_ft_text = any(RE_FT_REFERRAL_TEXT.search(t["text"]) for t in texts)
    has_ft_clinic_text = any(RE_FT_CLINIC_TEXT.search(t["text"]) for t in texts)
    has_2ww_proforma = any(RE_2WW_PROFORMA.search(t["text"]) for t in texts)
    has_benign_hist = any(RE_BENIGN_HISTOLOGY.search(t["text"]) for t in texts)
    has_hist_cancer = any(RE_HISTOLOGY_CANCER.search(t["text"]) for t in texts)

    if has_ft_text and not anchors.referral_anchors:
        fails.append("missed_ft_referral_text")
    if has_2ww_proforma and not anchors.referral_anchors:
        fails.append("missed_2ww_proforma")
    if has_ft_clinic_text and not anchors.first_seen_anchors:
        fails.append("missed_first_seen_text")
    if anchors.first_seen_anchors and not ep.get("first_seen_date"):
        fails.append("first_seen_detected_but_not_persisted")
    if has_benign_hist and not anchors.benign_closure_anchors:
        fails.append("missed_benign_histology_vocab")
    if has_hist_cancer and not anchors.diagnosis_anchors:
        fails.append("missed_histology_cancer_diagnosis")
    if "Text: specialist clinic attendance" in (ep.get("site") or ""):
        if not has_ft_text and not has_2ww_proforma:
            fails.append("specialist_visit_no_real_referral")

    return {
        "fails": fails,
        "anchors": {
            "ref": len(anchors.referral_anchors),
            "first_seen": len(anchors.first_seen_anchors),
            "diag": len(anchors.diagnosis_anchors),
            "benign": len(anchors.benign_closure_anchors),
            "treat": len(anchors.treatment_anchors),
        },
        "text_evidence": {
            "ft_referral_text": has_ft_text,
            "ft_clinic_text": has_ft_clinic_text,
            "2ww_proforma": has_2ww_proforma,
            "benign_histology": has_benign_hist,
            "hist_cancer": has_hist_cancer,
        },
    }


def main() -> None:
    client = PatientGraphClient()
    auto_closed = fetch_auto_closed(client)
    print(f"Investigating {len(auto_closed)} auto-closed episodes\n")

    by_patient: dict[str, list[dict]] = defaultdict(list)
    for ep in auto_closed:
        by_patient[ep["pid"]].append(ep)

    fail_counter: Counter = Counter()
    per_patient_report: list[dict] = []
    registry = DomainRegistry.from_defaults()

    for pid, eps in by_patient.items():
        anchors = detect_anchors(
            patient_id=pid,
            start_date="2000-01-01",
            end_date="2030-12-31",
            patient_client=client,
            registry=registry,
        )
        texts = fetch_encounter_texts(client, pid)
        for ep in eps:
            cats = categorise_failures(pid, ep, anchors, texts)
            for f in cats["fails"]:
                fail_counter[f] += 1
            per_patient_report.append({"pid": pid, "ep": ep, **cats})

    print("=" * 80)
    print("FAILURE MODE COUNTS")
    print("=" * 80)
    for fail, n in fail_counter.most_common():
        print(f"  {fail:<45} {n}")

    print(f"\n{'='*80}\nPER-PATIENT DETAIL\n{'='*80}")
    for row in per_patient_report:
        ep = row["ep"]
        a = row["anchors"]
        t = row["text_evidence"]
        fails = ",".join(row["fails"]) or "OK"
        print(
            f"\n{row['pid']}  ref={ep['ref_date']}  status={ep['status']}"
        )
        print(
            f"  Anchors: ref={a['ref']} first_seen={a['first_seen']} "
            f"diag={a['diag']} benign={a['benign']} treat={a['treat']}"
        )
        print(
            f"  Text:    ft_ref={t['ft_referral_text']} "
            f"ft_clin={t['ft_clinic_text']} 2ww_pf={t['2ww_proforma']} "
            f"ben_hist={t['benign_histology']} hist_ca={t['hist_cancer']}"
        )
        print(f"  Fails:   {fails}")

    client.close()


if __name__ == "__main__":
    main()
