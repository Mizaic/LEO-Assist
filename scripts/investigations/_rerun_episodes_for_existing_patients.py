"""Rebuild episodes for all patients that already have EpisodeOfCare rows.

Use after episode_builder logic changes so stored episode dates/statuses are
recomputed from current anchors.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import PatientGraphClient
from libs.pipeline_graph.subgraphs.anchor import _load_registry
from libs.pipeline_graph.subgraphs.staging_enrichment import enrich_staging
from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors
from services.analysis_worker.app.analyzers.episode_builder import build_episodes

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

_START_DATE = "2010-01-01"
_END_DATE = "2030-12-31"

_Q_PATIENTS = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id IS NOT NULL
RETURN DISTINCT toString(ep.patient_id) AS patient_id
ORDER BY patient_id
"""

_Q_DELETE_PATIENT_EPISODES = """
MATCH (ep:EpisodeOfCare {patient_id: $patient_id})
DETACH DELETE ep
"""


async def _run_patient(
    patient_id: str,
    domain_id: str,
    registry,
    patient_client: PatientGraphClient,
    clear_existing: bool,
) -> tuple[int, int, int]:
    if clear_existing:
        patient_client.run(_Q_DELETE_PATIENT_EPISODES, patient_id=patient_id)
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
    staging_state = enrich_staging(
        {
            "patient_id": patient_id,
            "episode_ids": result.episode_ids,
            "errors": [],
        }
    )
    staging_errors = len(staging_state.get("errors") or [])
    return result.episodes_created, len(result.errors), staging_errors


async def main(domain_id: str, limit: int | None, clear_existing: bool) -> None:
    client = PatientGraphClient()
    try:
        rows = client.run(_Q_PATIENTS) or []
        patient_ids = [str(r.get("patient_id") or "") for r in rows if r.get("patient_id")]
        if limit is not None:
            patient_ids = patient_ids[:limit]
        print(f"Loaded {len(patient_ids)} patients with existing episodes")
        print(f"Domain: {domain_id}")

        registry = _load_registry(domain_id)
        created_total = 0
        error_patients = 0
        staging_error_patients = 0
        for i, pid in enumerate(patient_ids, 1):
            created, err_count, staging_err_count = await _run_patient(
                pid, domain_id, registry, client, clear_existing
            )
            created_total += created
            if err_count:
                error_patients += 1
            if staging_err_count:
                staging_error_patients += 1
            if i % 25 == 0 or i == len(patient_ids):
                print(
                    f"  processed {i}/{len(patient_ids)} "
                    f"(episodes_written={created_total}, "
                    f"patient_errors={error_patients}, "
                    f"staging_error_patients={staging_error_patients})"
                )

        print("Done.")
        print(f"  patients_processed: {len(patient_ids)}")
        print(f"  episodes_written: {created_total}")
        print(f"  patients_with_errors: {error_patients}")
        print(f"  patients_with_staging_errors: {staging_error_patients}")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rebuild episodes for patients that already have EpisodeOfCare rows",
    )
    parser.add_argument(
        "--domain-id",
        default="cancer_audit",
        help="Domain ID to load from ValueSet registry",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for smoke-run testing",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not delete existing episodes before rebuild.",
    )
    args = parser.parse_args()
    asyncio.run(main(args.domain_id, args.limit, not args.keep_existing))

