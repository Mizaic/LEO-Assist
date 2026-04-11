"""Re-run episode detection for patients with 'Seen in fast track' encounters.

After _writeback_fast_track_specialist_docs.py has written DOCUMENTS relationships
for the affected encounters, those patients now have specialist_visit anchors that
were missing before. This script re-runs anchor detection and episode building for
each affected patient so their EpisodeOfCare nodes reflect the new data.

Input: scripts/investigations/encounter_audit/fast_track_specialist_encounters.jsonl
Domain: cancer_audit (default, override with --domain-id)

Run:
    python scripts/investigations/_rerun_episodes_for_fast_track_patients.py

    # Different domain:
    python scripts/investigations/_rerun_episodes_for_fast_track_patients.py --domain-id my_domain
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

logging.basicConfig(level=logging.WARNING)

INVENTORY = (
    ROOT
    / "scripts"
    / "investigations"
    / "encounter_audit"
    / "fast_track_specialist_encounters.jsonl"
)

# Wide date window to capture all historical encounters
_START_DATE = "2010-01-01"
_END_DATE = "2030-12-31"


def _load_patient_ids() -> list[str]:
    if not INVENTORY.exists():
        print(f"ERROR: Inventory not found: {INVENTORY}")
        print("Run _inventory_fast_track_specialist_encounters.py first.")
        sys.exit(1)
    ids: set[str] = set()
    with INVENTORY.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            pid = (row.get("patient_id") or "").strip()
            if pid:
                ids.add(pid)
    return sorted(ids)


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

    return {
        "patient_id": patient_id,
        "referral_anchors": len(anchors.referral_anchors),
        "diagnosis_anchors": len(anchors.diagnosis_anchors),
        "specialist_visit_anchors": len(anchors.specialist_visit_anchors),
        "episodes_created": result.episodes_created,
        "episode_ids": result.episode_ids,
        "errors": result.errors,
    }


async def main(domain_id: str) -> None:
    from libs.neo4j_client.client import PatientGraphClient
    from libs.pipeline_graph.subgraphs.anchor import _load_registry

    patient_ids = _load_patient_ids()
    print(f"Loaded {len(patient_ids)} unique patients from inventory.")
    print(f"Domain: {domain_id}")
    print()

    print("Loading domain registry ...")
    registry = _load_registry(domain_id)
    print(
        f"Registry loaded. Milestone types: {list(registry.get_milestone_domains().keys())}"
    )
    print()

    patient_client = PatientGraphClient()
    summary: list[dict] = []

    try:
        for i, patient_id in enumerate(patient_ids, 1):
            print(f"[{i}/{len(patient_ids)}] Patient {patient_id} ...")
            try:
                result = await _run_patient(
                    patient_id, registry, patient_client, domain_id
                )
                summary.append(result)
                print(
                    f"  Referrals={result['referral_anchors']}  "
                    f"Diagnoses={result['diagnosis_anchors']}  "
                    f"SpecialistVisits={result['specialist_visit_anchors']}  "
                    f"Episodes={result['episodes_created']}"
                )
                if result["errors"]:
                    print(f"  ERRORS: {result['errors']}")
            except Exception as exc:
                print(f"  ERROR: {exc}")
                summary.append({"patient_id": patient_id, "error": str(exc)})
    finally:
        patient_client.close()

    print()
    print("=" * 70)
    total_episodes = sum(r.get("episodes_created", 0) for r in summary)
    total_specialists = sum(r.get("specialist_visit_anchors", 0) for r in summary)
    errors = sum(1 for r in summary if r.get("errors") or r.get("error"))
    print(f"Done. Patients processed: {len(patient_ids)}")
    print(f"  Total episodes created/updated: {total_episodes}")
    print(f"  Total specialist visit anchors: {total_specialists}")
    print(f"  Patients with errors: {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Re-run episode detection for fast-track specialist visit patients"
    )
    parser.add_argument(
        "--domain-id",
        default="cancer_audit",
        help="Domain ID to load from the KG (default: cancer_audit)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.domain_id))
