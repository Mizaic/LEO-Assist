"""Run episode detection for ALL fast-track patients (specialist + referral cohorts).

Combines both inventories (93 unique patients), re-runs anchor detection and
episode building, then prints a summary table of referrals, first specialist
visits, and diagnoses across all episodes.

Run:
    python scripts/investigations/_run_episodes_and_stats.py
    python scripts/investigations/_run_episodes_and_stats.py --domain-id cancer_audit
"""

from __future__ import annotations

import argparse
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

_START_DATE = "2010-01-01"
_END_DATE = "2030-12-31"

# Query EpisodeOfCare nodes created/updated for a patient
_Q_EPISODES = """
MATCH (ep:EpisodeOfCare {patient_id: $patient_id})
RETURN
    ep.episode_id         AS episode_id,
    ep.status             AS status,
    ep.cancer_type        AS cancer_type,
    ep.condition_type     AS condition_type,
    ep.referral_date      AS referral_date,
    ep.specialist_seen    AS specialist_seen,
    ep.referral_site      AS referral_site
ORDER BY ep.referral_date
"""


def _load_patient_ids() -> list[str]:
    ids: set[str] = set()
    for inv in (_SPECIALIST_INV, _REFERRAL_INV):
        if not inv.exists():
            print(f"WARNING: Inventory not found: {inv}")
            continue
        with inv.open(encoding="utf-8") as fh:
            for line in fh:
                pid = (json.loads(line).get("patient_id") or "").strip()
                if pid:
                    ids.add(pid)
    return sorted(ids)


def _anchor_concepts(anchor_list) -> list[str]:
    """Extract concept names from an anchor list, handling various schemas."""
    names = []
    for a in anchor_list:
        name = (
            getattr(a, "concept_name", None)
            or getattr(a, "name", None)
            or (a.get("concept_name") if isinstance(a, dict) else None)
            or (a.get("name") if isinstance(a, dict) else None)
            or ""
        )
        if name:
            names.append(name)
    return names


async def _run_patient(
    patient_id: str,
    registry,
    patient_client,
    domain_id: str,
) -> dict:
    from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors
    from services.analysis_worker.app.analyzers.episode_builder import build_episodes

    anchors = detect_anchors(
        patient_id=patient_id,
        start_date=_START_DATE,
        end_date=_END_DATE,
        patient_client=patient_client,
        registry=registry,
    )

    result = await build_episodes(
        patient_id=patient_id,
        anchors=anchors,
        patient_client=patient_client,
        domain_id=domain_id,
    )

    # Deduplicate concept names per patient: each unique concept name
    # contributes exactly once to the frequency table, regardless of how
    # many times it is coded across encounters.  A patient with two
    # referral episodes (breast + lung) still contributes one count for
    # each distinct referral concept.
    return {
        "patient_id": patient_id,
        "referral_anchors": len(anchors.referral_anchors),
        "diagnosis_anchors": len(anchors.diagnosis_anchors),
        "specialist_visit_anchors": len(anchors.specialist_visit_anchors),
        "treatment_anchors": len(anchors.treatment_anchors),
        "benign_closure_anchors": len(anchors.benign_closure_anchors),
        "referral_concepts": list(
            dict.fromkeys(_anchor_concepts(anchors.referral_anchors))
        ),
        "diagnosis_concepts": list(
            dict.fromkeys(_anchor_concepts(anchors.diagnosis_anchors))
        ),
        "specialist_concepts": list(
            dict.fromkeys(_anchor_concepts(anchors.specialist_visit_anchors))
        ),
        "treatment_concepts": list(
            dict.fromkeys(_anchor_concepts(anchors.treatment_anchors))
        ),
        "episodes_created": result.episodes_created,
        "episode_ids": result.episode_ids,
        "errors": result.errors,
    }


def _pull_episode_counts(
    patient_ids: list[str],
) -> tuple[dict[str, int], dict[str, int]]:
    """Query Neo4j for EpisodeOfCare counts and status breakdown per patient."""
    from libs.neo4j_client.client import PatientGraphClient

    counts: dict[str, int] = {}
    status_counts: dict[str, int] = defaultdict(int)
    client = PatientGraphClient()
    try:
        with client.session() as session:
            for pid in patient_ids:
                rows = list(session.run(_Q_EPISODES, patient_id=pid))
                counts[pid] = len(rows)
                for row in rows:
                    st = row.get("status") or "unknown"
                    status_counts[st] += 1
    finally:
        client.close()
    return counts, dict(status_counts)


def _print_stats(
    summary: list[dict],
    ep_counts: dict[str, int],
    status_counts: dict[str, int],
    domain_id: str,
) -> None:
    processed = len(summary)
    errors = sum(1 for r in summary if r.get("errors") or r.get("error"))

    # Aggregate from in-memory anchor detection results
    patients_with_referral = sum(1 for r in summary if r.get("referral_anchors", 0) > 0)
    patients_with_specialist = sum(
        1 for r in summary if r.get("specialist_visit_anchors", 0) > 0
    )
    patients_with_diagnosis = sum(
        1 for r in summary if r.get("diagnosis_anchors", 0) > 0
    )
    patients_with_treatment = sum(
        1 for r in summary if r.get("treatment_anchors", 0) > 0
    )
    patients_with_episodes = sum(1 for v in ep_counts.values() if v > 0)
    patients_with_benign_closure = sum(
        1 for r in summary if r.get("benign_closure_anchors", 0) > 0
    )

    total_referrals = sum(r.get("referral_anchors", 0) for r in summary)
    total_specialists = sum(r.get("specialist_visit_anchors", 0) for r in summary)
    total_diagnoses = sum(r.get("diagnosis_anchors", 0) for r in summary)
    total_treatments = sum(r.get("treatment_anchors", 0) for r in summary)
    total_benign_closures = sum(r.get("benign_closure_anchors", 0) for r in summary)
    total_episodes = sum(ep_counts.values())

    # Pathway completeness breakdown
    full_pathway = sum(
        1
        for r in summary
        if r.get("referral_anchors", 0) > 0
        and r.get("specialist_visit_anchors", 0) > 0
        and r.get("diagnosis_anchors", 0) > 0
    )
    ref_and_spec = sum(
        1
        for r in summary
        if r.get("referral_anchors", 0) > 0
        and r.get("specialist_visit_anchors", 0) > 0
        and r.get("diagnosis_anchors", 0) == 0
    )
    ref_and_diag = sum(
        1
        for r in summary
        if r.get("referral_anchors", 0) > 0
        and r.get("diagnosis_anchors", 0) > 0
        and r.get("specialist_visit_anchors", 0) == 0
    )
    ref_only = sum(
        1
        for r in summary
        if r.get("referral_anchors", 0) > 0
        and r.get("specialist_visit_anchors", 0) == 0
        and r.get("diagnosis_anchors", 0) == 0
    )
    no_ref = sum(
        1
        for r in summary
        if r.get("referral_anchors", 0) == 0
        and (
            r.get("specialist_visit_anchors", 0) > 0
            or r.get("diagnosis_anchors", 0) > 0
        )
    )

    # Concept frequency tables from anchor objects
    ref_concepts: dict[str, int] = defaultdict(int)
    spec_concepts: dict[str, int] = defaultdict(int)
    diag_concepts: dict[str, int] = defaultdict(int)
    treat_concepts: dict[str, int] = defaultdict(int)
    for r in summary:
        for name in r.get("referral_concepts", []):
            ref_concepts[name] += 1
        for name in r.get("specialist_concepts", []):
            spec_concepts[name] += 1
        for name in r.get("diagnosis_concepts", []):
            diag_concepts[name] += 1
        for name in r.get("treatment_concepts", []):
            treat_concepts[name] += 1

    print()
    print("=" * 70)
    print(f"EPISODE DETECTION STATS  (domain: {domain_id})")
    print("=" * 70)
    print(f"  Patients processed          : {processed}")
    print(f"  Patients with episodes      : {patients_with_episodes}")
    print(f"  Total episodes              : {total_episodes}")
    print(f"  Patients with errors        : {errors}")
    print()
    # Distinct concept counts: unique concept names per patient, summed across patients
    distinct_refs = sum(len(set(r.get("referral_concepts", []))) for r in summary)
    distinct_specs = sum(len(set(r.get("specialist_concepts", []))) for r in summary)
    distinct_diags = sum(len(set(r.get("diagnosis_concepts", []))) for r in summary)
    distinct_treats = sum(len(set(r.get("treatment_concepts", []))) for r in summary)

    print("  Anchor counts (distinct concept per patient -- no double-counting):")
    print(
        f"    Referrals                 : {distinct_refs}  ({patients_with_referral} patients)"
    )
    print(
        f"    First specialist seen     : {distinct_specs}  ({patients_with_specialist} patients)"
    )
    print(
        f"    Diagnoses                 : {distinct_diags}  ({patients_with_diagnosis} patients)"
    )
    print(
        f"    Treatments                : {distinct_treats}  ({patients_with_treatment} patients)"
    )
    print(
        f"    Benign closures (395100000): {total_benign_closures}  ({patients_with_benign_closure} patients)"
    )
    print()
    print("  Episode status breakdown (in Neo4j):")
    _NORMAL_STATUSES = ("completed", "closed_benign", "in_progress")
    _AUTO_STATUSES = (
        "stale_post_specialist",
        "stale_no_diagnosis",
        "closed_phantom",
        "closed_related",
    )
    for st in _NORMAL_STATUSES:
        n = status_counts.get(st, 0)
        print(f"    {st:<35}: {n}")
    print(f"    {'--- auto-closed (HITL flagged) ---':<35}")
    hitl_total = 0
    for st in _AUTO_STATUSES:
        n = status_counts.get(st, 0)
        if n:
            print(f"    {st:<35}: {n}")
            hitl_total += n
    # Any other statuses not in the known lists
    for st, n in status_counts.items():
        if st not in _NORMAL_STATUSES and st not in _AUTO_STATUSES and st != "unknown":
            print(f"    {st:<35}: {n}")
            hitl_total += n
    if hitl_total:
        print(f"    {'HITL total':<35}: {hitl_total}")
    print()
    print("  Pathway completeness (per patient):")
    print(f"    Referral + Specialist + Diagnosis  : {full_pathway}")
    print(f"    Referral + Specialist only          : {ref_and_spec}")
    print(f"    Referral + Diagnosis only           : {ref_and_diag}")
    print(f"    Referral only (no specialist/diag)  : {ref_only}")
    print(f"    Specialist/Diagnosis without referral: {no_ref}")
    print()

    def _top(counts: dict[str, int], n: int = 8) -> list[tuple[str, int]]:
        return sorted(counts.items(), key=lambda x: -x[1])[:n]

    print("  Top referral types  (patients with this referral type):")
    for name, cnt in _top(ref_concepts):
        print(f"    {cnt:4d}  {name}")

    print()
    print("  Top specialist visit types  (patients seen at this clinic type):")
    for name, cnt in _top(spec_concepts):
        print(f"    {cnt:4d}  {name}")

    print()
    print("  Top diagnoses  (patients with this diagnosis concept):")
    for name, cnt in _top(diag_concepts):
        print(f"    {cnt:4d}  {name}")

    print()
    print("  Top treatments  (patients with this treatment concept):")
    for name, cnt in _top(treat_concepts):
        print(f"    {cnt:4d}  {name}")

    print("=" * 70)


async def main(domain_id: str) -> None:
    from libs.neo4j_client.client import PatientGraphClient
    from libs.pipeline_graph.subgraphs.anchor import _load_registry

    patient_ids = _load_patient_ids()
    print(f"Loaded {len(patient_ids)} unique patients (specialist + referral cohorts).")
    print(f"Domain: {domain_id}")
    print()

    print("Loading domain registry ...")
    registry = _load_registry(domain_id)
    milestones = list(registry.get_milestone_domains().keys())
    print(f"Registry loaded. Milestone types: {milestones}")
    print()

    patient_client = PatientGraphClient()
    summary: list[dict] = []

    try:
        for i, patient_id in enumerate(patient_ids, 1):
            print(
                f"[{i:2d}/{len(patient_ids)}] Patient {patient_id} ...",
                end=" ",
                flush=True,
            )
            try:
                result = await _run_patient(
                    patient_id, registry, patient_client, domain_id
                )
                summary.append(result)
                print(
                    f"ref={result['referral_anchors']}  "
                    f"spec={result['specialist_visit_anchors']}  "
                    f"diag={result['diagnosis_anchors']}  "
                    f"treat={result['treatment_anchors']}  "
                    f"ep={result['episodes_created']}"
                )
                if result["errors"]:
                    print(f"  ERRORS: {result['errors']}")
            except Exception as exc:
                print(f"ERROR: {exc}")
                summary.append({"patient_id": patient_id, "error": str(exc)})
    finally:
        patient_client.close()

    print()
    print("Pulling episode counts from Neo4j ...")
    ep_counts, status_counts = _pull_episode_counts(patient_ids)

    _print_stats(summary, ep_counts, status_counts, domain_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run episode detection for all fast-track patients and report stats"
    )
    parser.add_argument(
        "--domain-id",
        default="cancer_audit",
        help="Domain ID to load from the KG (default: cancer_audit)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.domain_id))
