"""Compare domain-driven episode config vs hardcoded concept sets.

Loads the cancer_audit AuditDomain from the Knowledge Graph, reads the
SNOMED concept IDs stored in each subdomain ValueSet (referral, diagnosis,
seen_by_specialist), expands each via IS_A hierarchy (matching what
_load_registry() does at runtime), then runs the same patient-graph queries
that audit_cancer_status.py uses and prints a side-by-side comparison.

Usage
-----
    python scripts/investigations/_compare_domain_vs_hardcoded.py
    python scripts/investigations/_compare_domain_vs_hardcoded.py --domain cancer_audit
    python scripts/investigations/_compare_domain_vs_hardcoded.py --show-diffs
    python scripts/investigations/_compare_domain_vs_hardcoded.py --depth 5
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.domains.ncda_concept_sets import (  # noqa: E402
    CANCER_TYPE_IDS,
    FAST_TRACK_REFERRAL_IDS,
    SEEN_BY_SPECIALIST_IDS,
)
from libs.neo4j_client.client import (  # noqa: E402
    KnowledgeGraphClient,
    PatientGraphClient,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("compare_domain")


# ---------------------------------------------------------------------------
# KG queries
# ---------------------------------------------------------------------------

_Q_DOMAIN_VALUESETS = """
MATCH (d:AuditDomain {id: $domain_id})-[:HAS_SUBDOMAIN]->(v:ValueSet)
RETURN
    v.id           AS vs_id,
    v.rawJson      AS raw_json,
    coalesce(v.milestoneType, '') AS milestone_type,
    coalesce(v.assertionFilter, []) AS assertion_filter
ORDER BY vs_id
"""

_Q_ALL_DOMAINS = """
MATCH (d:AuditDomain)
RETURN d.id AS domain_id, d.title AS title,
       coalesce(d.episodeDetector, false) AS episode_detector
ORDER BY d.id
"""

_Q_ISA_DESCENDANTS = (
    "MATCH (ancestor:Concept)<-[:IS_A*1..{depth}]-(d:Concept) "
    "WHERE ancestor.id IN $ids AND d.active = true "
    "RETURN ancestor.id AS parent_id, d.id AS child_id"
)


def _extract_concept_ids(raw_json: str | dict) -> list[int]:
    """Pull SNOMED concept IDs out of a FHIR ValueSet rawJson blob."""
    try:
        vs = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except Exception:
        return []
    ids: list[int] = []
    for include in (vs.get("compose") or {}).get("include") or []:
        for concept in include.get("concept") or []:
            code = concept.get("code", "")
            try:
                ids.append(int(code))
            except (ValueError, TypeError):
                pass
    return ids


def _expand_with_isa(
    kg,
    parent_ids: list[int],
    depth: int = 5,
) -> list[int]:
    """Return parent_ids plus all IS_A descendants from the KG."""
    if not parent_ids:
        return parent_ids
    str_ids = [str(c) for c in parent_ids]
    try:
        rows = kg.run(
            _Q_ISA_DESCENDANTS.format(depth=depth),
            ids=str_ids,
        )
    except Exception as exc:
        logger.warning("IS_A expansion failed: %s", exc)
        return parent_ids
    descendants = [int(r["child_id"]) for r in (rows or []) if r.get("child_id")]
    total = len(descendants)
    logger.info(
        "  IS_A expanded %d parent(s) -> %d descendants", len(parent_ids), total
    )
    return list(set(parent_ids) | set(descendants))


# ---------------------------------------------------------------------------
# Patient graph queries
# ---------------------------------------------------------------------------

_Q_PATIENTS_WITH_CONCEPTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(d)
WHERE d.conceptId IN $concept_ids
RETURN
    toString(p.id)              AS patient_id,
    collect(DISTINCT toString(d.conceptId))  AS matched_concepts,
    count(DISTINCT e)           AS encounter_count
ORDER BY patient_id
"""

_Q_PATIENTS_WITH_CONCEPTS_AND_ASSERTION = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(d)
WHERE d.conceptId IN $concept_ids
  AND coalesce(r.assertion, 'present') IN $assertions
RETURN
    toString(p.id)              AS patient_id,
    collect(DISTINCT toString(d.conceptId))  AS matched_concepts,
    count(DISTINCT e)           AS encounter_count
ORDER BY patient_id
"""


def _query_patient_ids(
    patient_client: PatientGraphClient,
    concept_ids: list[int],
    assertion_filter: list[str] | None = None,
) -> set[str]:
    if not concept_ids:
        return set()
    str_ids = [str(c) for c in concept_ids]
    if assertion_filter:
        rows = patient_client.run(
            _Q_PATIENTS_WITH_CONCEPTS_AND_ASSERTION,
            concept_ids=str_ids,
            assertions=assertion_filter,
        )
    else:
        rows = patient_client.run(
            _Q_PATIENTS_WITH_CONCEPTS,
            concept_ids=str_ids,
        )
    return {r["patient_id"] for r in rows}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pct(a: int, b: int) -> str:
    if b == 0:
        return "n/a"
    return f"{100 * a / b:.1f}%"


def _set_diff_summary(
    label: str,
    domain_ids: set[str],
    hardcoded_ids: set[str],
    show_diffs: bool,
) -> None:
    only_domain = domain_ids - hardcoded_ids
    only_hard = hardcoded_ids - domain_ids
    both = domain_ids & hardcoded_ids
    logger.info(
        "  %s: domain=%d  hardcoded=%d  both=%d  only-domain=%d  only-hardcoded=%d",
        label,
        len(domain_ids),
        len(hardcoded_ids),
        len(both),
        len(only_domain),
        len(only_hard),
    )
    if show_diffs and only_domain:
        logger.info("    Patients only in DOMAIN:     %s", sorted(only_domain)[:20])
    if show_diffs and only_hard:
        logger.info("    Patients only in HARDCODED:  %s", sorted(only_hard)[:20])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare domain-driven concept IDs (with IS_A expansion) vs hardcoded sets"
    )
    parser.add_argument("--domain", default="cancer_audit")
    parser.add_argument("--show-diffs", action="store_true")
    parser.add_argument(
        "--depth",
        type=int,
        default=5,
        help="IS_A traversal depth (default 5)",
    )
    args = parser.parse_args()

    # -- Step 1: load domain ValueSets and expand IS_A in one KG session --
    logger.info("Connecting to Knowledge Graph...")
    kg = KnowledgeGraphClient()
    try:
        rows = kg.run(_Q_DOMAIN_VALUESETS, domain_id=args.domain)
        if not rows:
            logger.error("Domain '%s' not found or has no subdomains.", args.domain)
            sys.exit(1)

        logger.info(
            "Loaded %d ValueSet subdomains for domain '%s':", len(rows), args.domain
        )

        domain_by_milestone: dict[str, dict] = {}
        for row in rows:
            milestone = row["milestone_type"] or "unknown"
            assertion_filter = list(row["assertion_filter"] or [])
            parent_ids = _extract_concept_ids(row["raw_json"])
            logger.info(
                "  %-40s  milestone=%-20s  parent_concepts=%d",
                row["vs_id"],
                milestone,
                len(parent_ids),
            )
            domain_by_milestone.setdefault(
                milestone,
                {
                    "concept_ids": [],
                    "assertion_filter": assertion_filter,
                },
            )
            domain_by_milestone[milestone]["concept_ids"].extend(parent_ids)

        # Expand each milestone's concept IDs via IS_A while KG is open
        logger.info("\nExpanding IS_A descendants (depth=%d)...", args.depth)
        for milestone, cfg in domain_by_milestone.items():
            if cfg["concept_ids"]:
                logger.info("  %s:", milestone)
                cfg["concept_ids"] = _expand_with_isa(
                    kg, cfg["concept_ids"], depth=args.depth
                )
    finally:
        kg.close()

    # -- Step 2: query patient graph --
    logger.info("\nConnecting to Patient Graph...")
    pg = PatientGraphClient()
    try:
        total = pg.run("MATCH (p:Patient) RETURN count(p) AS n")[0]["n"]
        logger.info("Total patients: %d", total)

        def _get(milestone: str) -> set[str]:
            cfg = domain_by_milestone.get(milestone, {})
            return _query_patient_ids(
                pg,
                cfg.get("concept_ids", []),
                cfg.get("assertion_filter") or None,
            )

        domain_referral = _get("referral")
        domain_diagnosis = _get("diagnosis")
        domain_specialist = _get("specialist_visit")

        hard_referral = _query_patient_ids(pg, list(FAST_TRACK_REFERRAL_IDS))
        hard_diagnosis = _query_patient_ids(pg, list(CANCER_TYPE_IDS))
        hard_specialist = _query_patient_ids(pg, list(SEEN_BY_SPECIALIST_IDS))
    finally:
        pg.close()

    # -- Step 3: print comparison --
    logger.info("")
    logger.info("=" * 70)
    logger.info(
        "COMPARISON (with IS_A expansion, depth=%d): domain '%s' vs hardcoded",
        args.depth,
        args.domain,
    )
    logger.info("=" * 70)
    _set_diff_summary("referral  ", domain_referral, hard_referral, args.show_diffs)
    _set_diff_summary("diagnosis ", domain_diagnosis, hard_diagnosis, args.show_diffs)
    _set_diff_summary("specialist", domain_specialist, hard_specialist, args.show_diffs)

    logger.info("")
    logger.info("DOMAIN CONCEPT COUNTS AFTER IS_A EXPANSION:")
    for milestone, cfg in sorted(domain_by_milestone.items()):
        ids = set(cfg["concept_ids"])
        if milestone == "referral":
            hard = FAST_TRACK_REFERRAL_IDS
        elif milestone == "diagnosis":
            hard = CANCER_TYPE_IDS
        elif milestone == "specialist_visit":
            hard = SEEN_BY_SPECIALIST_IDS
        else:
            logger.info("  %-20s  %d concepts (not a milestone)", milestone, len(ids))
            continue
        overlap = ids & hard
        logger.info(
            "  %-20s  domain=%d  hardcoded=%d  overlap=%d  "
            "only-domain=%d  only-hardcoded=%d",
            milestone,
            len(ids),
            len(hard),
            len(overlap),
            len(ids - hard),
            len(hard - ids),
        )
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
