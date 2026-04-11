"""Deep audit: for every patient, pull all coded concepts from Neo4j, run
anchor detection, then map anchors to episodes on a timeline.

Highlights episodes left in_progress despite coded diagnosis/benign concepts
being present on the patient's encounters -- i.e. concepts the anchor detector
is NOT picking up.

Run:
    python scripts/investigations/_deep_episode_audit.py
"""

from __future__ import annotations

import asyncio
import json
import logging
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

logging.basicConfig(level=logging.WARNING)

from libs.neo4j_client.client import PatientGraphClient
from libs.pipeline_graph.subgraphs.anchor import _load_registry
from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors
from services.analysis_worker.app.analyzers.episode_builder import (
    build_episodes,
    _extract_condition_key,
)

_START = "2010-01-01"
_END = "2030-12-31"

_SPECIALIST_INV = (
    ROOT
    / "scripts"
    / "investigations"
    / "encounter_audit"
    / "fast_track_specialist_encounters.jsonl"
)
_REFERRAL_INV = (
    ROOT
    / "scripts"
    / "investigations"
    / "encounter_audit"
    / "fast_track_referral_encounters.jsonl"
)

_Q_ALL_DOCS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid
RETURN
    toString(e.id)   AS enc_id,
    toString(e.date) AS enc_date,
    c.conceptId      AS concept_id,
    c.name           AS concept_name,
    c.semanticTag    AS semantic_tag,
    coalesce(r.assertion, 'present') AS assertion
ORDER BY enc_date, c.conceptId
"""

_Q_EPISODES = """
MATCH (ep:EpisodeOfCare {patient_id: $pid})
RETURN
    ep.episode_id      AS eid,
    ep.status          AS status,
    ep.cancer_type     AS cancer_type,
    ep.referral_date   AS referral_date,
    ep.end_date        AS end_date,
    ep.specialist_seen AS specialist_seen
ORDER BY ep.referral_date
"""

# Cancer-related semantic tags / keywords to flag as potentially missed
_CANCER_KEYWORDS = {
    "malignant",
    "carcinoma",
    "melanoma",
    "lymphoma",
    "leukaemia",
    "leukemia",
    "sarcoma",
    "neoplasm",
    "tumour",
    "tumor",
    "cancer",
    "metasta",
    "adenocarcinoma",
    "myeloma",
}
_BENIGN_KEYWORDS = {
    "no evidence of cancer",
    "benign",
    "no malignancy",
    "cancer excluded",
    "not cancer",
    "normal biopsy",
    "negative biopsy",
}
_SPECIALIST_KEYWORDS = {
    "seen in fast track",
    "seen in 2ww",
    "2ww clinic",
    "fast track suspected",
    "cancer clinic",
}


def _is_cancer_concept(name: str) -> bool:
    low = (name or "").lower()
    return any(k in low for k in _CANCER_KEYWORDS)


def _is_benign_concept(name: str) -> bool:
    low = (name or "").lower()
    return any(k in low for k in _BENIGN_KEYWORDS)


def _is_specialist_concept(name: str) -> bool:
    low = (name or "").lower()
    return any(k in low for k in _SPECIALIST_KEYWORDS)


def _is_referral_concept(name: str) -> bool:
    low = (name or "").lower()
    return "fast track referral" in low or "2ww referral" in low


def _load_patient_ids() -> list[str]:
    ids: set[str] = set()
    for inv in (_SPECIALIST_INV, _REFERRAL_INV):
        if not inv.exists():
            continue
        with inv.open(encoding="utf-8") as fh:
            for line in fh:
                pid = (json.loads(line).get("patient_id") or "").strip()
                if pid:
                    ids.add(pid)
    return sorted(ids)


def _audit_patient(pid: str, session, registry, patient_client) -> dict:
    # 1. Pull ALL coded concepts
    all_docs = list(session.run(_Q_ALL_DOCS, pid=pid))

    # 2. Classify coded concepts
    coded_referrals = []
    coded_specialists = []
    coded_cancers = []
    coded_benign = []
    for doc in all_docs:
        name = doc["concept_name"] or ""
        assertion = doc["assertion"]
        row = {
            "date": doc["enc_date"],
            "enc": doc["enc_id"][:12],
            "cid": doc["concept_id"],
            "name": name[:60],
            "assertion": assertion,
        }
        if _is_referral_concept(name) and assertion == "present":
            coded_referrals.append(row)
        if _is_specialist_concept(name) and assertion == "present":
            coded_specialists.append(row)
        if _is_cancer_concept(name) and assertion == "present":
            coded_cancers.append(row)
        if (
            _is_benign_concept(name) or doc["concept_id"] == 395100000
        ) and assertion == "present":
            coded_benign.append(row)

    # 3. Run anchor detection
    anchors = detect_anchors(
        patient_id=pid,
        start_date=_START,
        end_date=_END,
        patient_client=patient_client,
        registry=registry,
    )

    # 4. Pull current episode nodes
    episodes = list(session.run(_Q_EPISODES, pid=pid))

    # 5. Find missed concepts: coded in graph but NOT detected as anchors
    detected_ref_enc = {
        str(a.get("encounter_id") or "")[:12] for a in anchors.referral_anchors
    }
    detected_diag_enc = {
        str(a.get("encounter_id") or "")[:12] for a in anchors.diagnosis_anchors
    }
    detected_spec_enc = {
        str(a.get("encounter_id") or "")[:12] for a in anchors.specialist_visit_anchors
    }
    detected_benign_enc = {
        str(a.get("encounter_id") or "")[:12] for a in anchors.benign_closure_anchors
    }

    missed_cancers = [c for c in coded_cancers if c["enc"] not in detected_diag_enc]
    missed_specialists = [
        c for c in coded_specialists if c["enc"] not in detected_spec_enc
    ]
    missed_benign = [c for c in coded_benign if c["enc"] not in detected_benign_enc]

    in_progress_episodes = [e for e in episodes if e["status"] == "in_progress"]

    return {
        "pid": pid,
        "coded_referrals": len(coded_referrals),
        "coded_specialists": len(coded_specialists),
        "coded_cancers": len(coded_cancers),
        "coded_benign": len(coded_benign),
        "detected_referrals": len(anchors.referral_anchors),
        "detected_diagnoses": len(anchors.diagnosis_anchors),
        "detected_specialists": len(anchors.specialist_visit_anchors),
        "detected_benign": len(anchors.benign_closure_anchors),
        "total_episodes": len(episodes),
        "in_progress_episodes": len(in_progress_episodes),
        "episodes": [
            {
                "status": e["status"],
                "type": e["cancer_type"],
                "ref_date": str(e["referral_date"] or ""),
                "end_date": str(e["end_date"] or ""),
                "spec_seen": e["specialist_seen"],
            }
            for e in episodes
        ],
        "missed_cancers": missed_cancers,
        "missed_specialists": missed_specialists,
        "missed_benign": missed_benign,
        "coded_cancer_details": coded_cancers,
        "coded_specialist_details": coded_specialists,
        "coded_benign_details": coded_benign,
        "coded_referral_details": coded_referrals,
    }


def main() -> None:
    patient_ids = _load_patient_ids()
    print(f"Auditing {len(patient_ids)} patients ...\n")

    registry = _load_registry("cancer_audit")
    print(
        f"Registry milestone types: {list(registry.get_milestone_domains().keys())}\n"
    )

    # Show which concept IDs are in each bucket
    for domain_name, cfg in registry.get_milestone_domains().items():
        cids = registry.get_concept_ids(domain_name)
        print(f"  {domain_name} ({cfg.milestone_type}): {len(cids)} concept IDs")
        if len(cids) <= 20:
            for cid in sorted(cids):
                c = registry.get_concept_by_id(cid)
                name = c.preferred_term if c else "?"
                print(f"    {cid}  {name[:55]}")
        else:
            for cid in sorted(cids)[:5]:
                c = registry.get_concept_by_id(cid)
                name = c.preferred_term if c else "?"
                print(f"    {cid}  {name[:55]}")
            print(f"    ... and {len(cids) - 5} more")
    print()

    client = PatientGraphClient()
    results = []
    try:
        with client.session() as session:
            for i, pid in enumerate(patient_ids, 1):
                r = _audit_patient(pid, session, registry, client)
                results.append(r)

                has_problem = r["in_progress_episodes"] > 0 and (
                    r["missed_cancers"] or r["missed_benign"]
                )
                flag = " *** MISSED ANCHORS ***" if has_problem else ""
                print(
                    f"[{i:2d}/{len(patient_ids)}] {pid}  "
                    f"ep={r['total_episodes']}({r['in_progress_episodes']} open)  "
                    f"coded: ref={r['coded_referrals']} spec={r['coded_specialists']} "
                    f"cancer={r['coded_cancers']} benign={r['coded_benign']}  "
                    f"detected: ref={r['detected_referrals']} diag={r['detected_diagnoses']} "
                    f"spec={r['detected_specialists']} benign={r['detected_benign']}"
                    f"{flag}"
                )
    finally:
        client.close()

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    total_in_progress = sum(r["in_progress_episodes"] for r in results)
    patients_with_open = sum(1 for r in results if r["in_progress_episodes"] > 0)
    patients_with_missed_cancer = [
        r for r in results if r["in_progress_episodes"] > 0 and r["missed_cancers"]
    ]
    patients_with_missed_benign = [
        r for r in results if r["in_progress_episodes"] > 0 and r["missed_benign"]
    ]

    print(f"\nTotal in_progress episodes: {total_in_progress}")
    print(f"Patients with open episodes: {patients_with_open}")
    print(
        f"Patients with MISSED cancer concepts (open episodes): {len(patients_with_missed_cancer)}"
    )
    print(
        f"Patients with MISSED benign concepts (open episodes): {len(patients_with_missed_benign)}"
    )

    # Detail the missed concepts
    if patients_with_missed_cancer:
        print(
            "\n--- Patients with coded cancer concepts NOT detected as diagnosis anchors ---"
        )
        missed_concept_freq: dict[str, int] = defaultdict(int)
        for r in patients_with_missed_cancer:
            print(f"\n  pid={r['pid']}  open_episodes={r['in_progress_episodes']}")
            print(f"    Episodes:")
            for ep in r["episodes"]:
                print(
                    f"      {ep['status']:<15} {ep['type']:<20} ref={ep['ref_date']}  end={ep['end_date']}  spec={ep['spec_seen']}"
                )
            print(f"    Missed cancer concepts (coded but not anchored):")
            for mc in r["missed_cancers"][:10]:
                print(f"      {mc['date']}  {mc['cid']:>12}  {mc['name']}")
                missed_concept_freq[f"{mc['cid']}|{mc['name']}"] += 1

        print("\n--- Missed cancer concept frequency (across all patients) ---")
        for key, cnt in sorted(missed_concept_freq.items(), key=lambda x: -x[1])[:25]:
            cid, name = key.split("|", 1)
            print(f"  {cnt:3d}x  {cid:>12}  {name}")

    if patients_with_missed_benign:
        print(
            "\n--- Patients with coded benign concepts NOT detected as benign closure anchors ---"
        )
        for r in patients_with_missed_benign[:10]:
            print(f"\n  pid={r['pid']}  open_episodes={r['in_progress_episodes']}")
            for mc in r["missed_benign"][:5]:
                print(f"      {mc['date']}  {mc['cid']:>12}  {mc['name']}")

    # Patients with ALL episodes in_progress (zero completed, zero closed_benign)
    all_open = [
        r
        for r in results
        if r["total_episodes"] > 0
        and all(ep["status"] == "in_progress" for ep in r["episodes"])
    ]
    if all_open:
        print(f"\n--- {len(all_open)} patients where EVERY episode is in_progress ---")
        for r in all_open:
            print(
                f"  pid={r['pid']}  episodes={r['total_episodes']}  "
                f"coded_cancer={r['coded_cancers']}  coded_benign={r['coded_benign']}"
            )


if __name__ == "__main__":
    main()
