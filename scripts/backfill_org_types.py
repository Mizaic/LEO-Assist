#!/usr/bin/env python3
"""Idempotent backfill of :GPPractice and :ServiceProvider org labels.

Dry-run by default. Pass --apply to write labels.

GP candidates: Organization with incoming HAS_GENERAL_PRACTITIONER and
no :GPPractice label yet.
SP candidates: Organization with incoming PROVIDES_SERVICE from a Service
and no :ServiceProvider label yet.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_org_types")

CYPHER_FIND_GP_CANDIDATES = """
MATCH (o:Organization)<-[:HAS_GENERAL_PRACTITIONER]-(:Patient)
WHERE NOT o:GPPractice
RETURN DISTINCT o.id AS id, o.name AS name
ORDER BY o.id
"""

CYPHER_FIND_SP_CANDIDATES = """
MATCH (o:Organization)<-[:PROVIDES_SERVICE]-(:Service)
WHERE NOT o:ServiceProvider
RETURN DISTINCT o.id AS id, o.name AS name
ORDER BY o.id
"""

CYPHER_RELABEL_GP = """
MATCH (o:Organization {id: $org_id})
SET o:GPPractice
RETURN o.id AS id
"""

CYPHER_RELABEL_SP = """
MATCH (o:Organization {id: $org_id})
SET o:ServiceProvider
RETURN o.id AS id
"""


def plan_relabels(
    gp_rows: list[dict[str, Any]], sp_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build a dry-run plan from candidate query rows."""
    gp_ids = [r["id"] for r in gp_rows if r.get("id")]
    sp_ids = [r["id"] for r in sp_rows if r.get("id")]
    return {
        "gp": gp_ids,
        "service_provider": sp_ids,
        "counts": {"gp": len(gp_ids), "service_provider": len(sp_ids)},
    }


def run_backfill(*, apply: bool) -> dict[str, Any]:
    """Query candidates and optionally apply relabels."""
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    try:
        gp_rows = client.run(CYPHER_FIND_GP_CANDIDATES)
        sp_rows = client.run(CYPHER_FIND_SP_CANDIDATES)
        plan = plan_relabels(gp_rows, sp_rows)
        logger.info(
            "Candidates: gp=%s service_provider=%s (apply=%s)",
            plan["counts"]["gp"],
            plan["counts"]["service_provider"],
            apply,
        )
        if not apply:
            for oid in plan["gp"]:
                logger.info("DRY-RUN would SET :GPPractice on %s", oid)
            for oid in plan["service_provider"]:
                logger.info("DRY-RUN would SET :ServiceProvider on %s", oid)
            return plan

        for oid in plan["gp"]:
            client.run(CYPHER_RELABEL_GP, org_id=oid)
            logger.info("SET :GPPractice on %s", oid)
        for oid in plan["service_provider"]:
            client.run(CYPHER_RELABEL_SP, org_id=oid)
            logger.info("SET :ServiceProvider on %s", oid)
        return plan
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write labels (default is dry-run)",
    )
    args = parser.parse_args(argv)
    run_backfill(apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
