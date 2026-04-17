"""Rebuild EpisodeOfCare nodes for all patients using the text-only anchor path.

Used after deleting DOCUMENTS and HAS_<semantic_tag> relationships to
establish a clean text-only baseline before the NLP recoding pipeline runs.

Usage
-----
    python scripts/rebuild_episodes_text_path.py              # dry run
    python scripts/rebuild_episodes_text_path.py --apply      # write to Neo4j
    python scripts/rebuild_episodes_text_path.py --apply --patient 4802241127
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("rebuild_episodes")

_Q_ALL_PATIENTS = """
MATCH (p:Patient)
RETURN DISTINCT toString(p.id) AS patient_id
ORDER BY patient_id
"""


async def _run_patient(patient_id: str, domain_id: str, dry_run: bool) -> dict:
    from libs.domain_config.registry import DomainRegistry
    from libs.neo4j_client.client import PatientGraphClient
    from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors
    from services.analysis_worker.app.analyzers.episode_builder import build_episodes

    client = PatientGraphClient()
    try:
        anchors = detect_anchors(
            patient_id=patient_id,
            start_date="2000-01-01",
            end_date="2030-12-31",
            patient_client=client,
            registry=DomainRegistry.from_defaults(),
        )
        anchor_counts = {
            "referrals": len(anchors.referral_anchors),
            "diagnoses": len(anchors.diagnosis_anchors),
            "first_seen": len(anchors.first_seen_anchors),
            "treatments": len(anchors.treatment_anchors),
            "benign_closures": len(anchors.benign_closure_anchors),
        }
        if dry_run:
            return {"status": "dry_run", "anchors": anchor_counts}

        result = await build_episodes(
            patient_id=patient_id,
            anchors=anchors,
            patient_client=client,
            domain_id=domain_id,
        )
        return {
            "status": "ok",
            "episodes_created": result.episodes_created,
            "errors": result.errors or [],
            "anchors": anchor_counts,
        }
    except Exception as exc:
        log.exception("Failed for patient %s", patient_id)
        return {"status": "error", "error": str(exc)}
    finally:
        client.close()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild episodes from text-only anchor detection"
    )
    parser.add_argument("--apply", action="store_true", help="Write to Neo4j")
    parser.add_argument("--patient", metavar="ID", help="Single patient only")
    parser.add_argument(
        "--domain-id",
        default=os.getenv("ANALYSIS_DOMAIN_ID", "cancer_audit"),
        help="Domain registry ID (default: cancer_audit)",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    if args.patient:
        patient_ids = [args.patient]
    else:
        rows = client.run(_Q_ALL_PATIENTS)
        patient_ids = [r["patient_id"] for r in rows]
    client.close()

    log.info(
        "%s mode -- %d patient(s)",
        "DRY RUN" if dry_run else "APPLY",
        len(patient_ids),
    )

    totals: dict[str, int] = defaultdict(int)
    errors: list[str] = []

    for i, pid in enumerate(patient_ids, 1):
        res = await _run_patient(pid, args.domain_id, dry_run)
        totals["processed"] += 1
        if res["status"] == "ok":
            totals["episodes_created"] += res.get("episodes_created", 0)
            if res.get("errors"):
                errors.append(f"{pid}: {res['errors']}")
        elif res["status"] == "error":
            totals["failed"] += 1
            errors.append(f"{pid}: {res['error']}")
        elif res["status"] == "dry_run":
            anc = res.get("anchors", {})
            if any(anc.values()):
                log.info(
                    "  [%s] anchors: ref=%d diag=%d seen=%d treat=%d benign=%d",
                    pid,
                    anc.get("referrals", 0),
                    anc.get("diagnoses", 0),
                    anc.get("first_seen", 0),
                    anc.get("treatments", 0),
                    anc.get("benign_closures", 0),
                )

        if i % 20 == 0:
            log.info("Progress: %d / %d patients", i, len(patient_ids))

    sep = "=" * 70
    print(sep)
    print("REBUILD COMPLETE" if not dry_run else "DRY RUN COMPLETE")
    print(sep)
    for k, v in sorted(totals.items()):
        print(f"  {k:<25} {v}")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for e in errors[:20]:
            print(f"  {e}")
    print(sep)

    if dry_run:
        print("\nRe-run with --apply to write episodes to Neo4j.")


if __name__ == "__main__":
    asyncio.run(main())
