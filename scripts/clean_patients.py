"""Reset patient data before a gold pipeline run.

Removes DOCUMENTS links, EncounterCandidates, ReviewTasks, Approvals, Changes,
SafetyNetAlerts, and EpisodeOfCare nodes for the specified patients.

Usage:
    python scripts/clean_patients.py --patients P1,P2,...
    python scripts/clean_patients.py --all --confirm
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env")

from libs.cypher.cleanup_queries import (
    RESET_PATIENT_ALERTS,
    RESET_PATIENT_DOCUMENTS,
    RESET_PATIENT_DIRECT_SEMANTIC,
    RESET_PATIENT_EPISODES,
    RESET_PATIENT_LEGACY_ALERTS,
    RESET_PATIENT_LEGACY_EPISODES,
    RESET_PATIENT_REVIEW_QUEUE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("clean_patients")


def clean_patient(session, patient_id: str) -> dict[str, int]:
    """Remove all pipeline artefacts for a single patient."""
    totals: dict[str, int] = {}

    r = session.run(RESET_PATIENT_REVIEW_QUEUE, patient_id=patient_id).single()
    totals["review_queue"] = r["deleted"] if r else 0

    r = session.run(RESET_PATIENT_DOCUMENTS, patient_id=patient_id).single()
    totals["documents"] = r["links_deleted"] if r else 0

    r = session.run(RESET_PATIENT_DIRECT_SEMANTIC, patient_id=patient_id).single()
    totals["direct_semantic"] = r["direct_deleted"] if r else 0

    r = session.run(RESET_PATIENT_ALERTS, patient_id=patient_id).single()
    totals["alerts"] = r["deleted"] if r else 0

    r = session.run(RESET_PATIENT_EPISODES, patient_id=patient_id).single()
    totals["episodes"] = r["deleted"] if r else 0

    r = session.run(RESET_PATIENT_LEGACY_ALERTS, patient_id=patient_id).single()
    totals["legacy_alerts"] = r["deleted"] if r else 0

    r = session.run(RESET_PATIENT_LEGACY_EPISODES, patient_id=patient_id).single()
    totals["legacy_episodes"] = r["deleted"] if r else 0

    return totals


def get_all_patient_ids(driver) -> list[str]:
    with driver.session() as session:
        result = session.run(
            "MATCH (p:Patient) RETURN toString(p.id) AS pid ORDER BY pid"
        )
        return [row["pid"] for row in result]


def main():
    parser = argparse.ArgumentParser(description="Clean patient data before gold run")
    parser.add_argument("--patients", type=str, help="Comma-separated patient IDs")
    parser.add_argument("--all", action="store_true", help="Clean ALL patients")
    parser.add_argument("--confirm", action="store_true", help="Required with --all")
    args = parser.parse_args()

    from neo4j import GraphDatabase

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    if args.all:
        if not args.confirm:
            print("ERROR: --all requires --confirm flag")
            sys.exit(1)
        patient_ids = get_all_patient_ids(driver)
    elif args.patients:
        patient_ids = [p.strip() for p in args.patients.split(",")]
    else:
        print("ERROR: Provide --patients or --all --confirm")
        sys.exit(1)

    logger.info("Cleaning %d patients", len(patient_ids))

    grand_totals: dict[str, int] = {}
    with driver.session() as session:
        for pid in patient_ids:
            totals = clean_patient(session, pid)
            logger.info("Patient %s: %s", pid, totals)
            for k, v in totals.items():
                grand_totals[k] = grand_totals.get(k, 0) + v

    logger.info("Grand totals: %s", grand_totals)
    driver.close()


if __name__ == "__main__":
    main()
