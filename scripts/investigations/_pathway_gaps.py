"""Cancer pathway gap analysis using domain-driven IS_A-expanded concept sets.

Reports:
  1. Which hardcoded concept IDs are NOT covered by the domain's IS_A expansion
     (so the user can add them as parent concepts to the domain).
  2. Patients with a fast-track referral but no diagnosis and not excluded.
  3. Patients with a diagnosis but no prior fast-track referral.

Usage
-----
    python scripts/investigations/_pathway_gaps.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.domains.ncda_concept_sets import (
    CANCER_TYPE_IDS,
    CANCER_EXCLUSION_IDS,
    FAST_TRACK_REFERRAL_IDS,
    SEEN_BY_SPECIALIST_IDS,
)
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("pathway_gaps")

DOMAIN_ID = "cancer_audit"
ISA_DEPTH = 5

_Q_DOMAIN_VALUESETS = (
    "MATCH (d:AuditDomain {id: $domain_id})-[:HAS_SUBDOMAIN]->(v:ValueSet) "
    "RETURN v.id AS vs_id, v.rawJson AS raw_json, "
    "       coalesce(v.milestoneType, '') AS milestone_type"
)

_Q_ISA = (
    "MATCH (ancestor:Concept)<-[:IS_A*1..{depth}]-(d:Concept) "
    "WHERE ancestor.id IN $ids AND d.active = true "
    "RETURN ancestor.id AS parent_id, d.id AS child_id"
)

_Q_CONCEPT_NAMES = (
    "MATCH (c) WHERE c.conceptId IN $ids "
    "RETURN c.conceptId AS id, c.name AS name LIMIT 200"
)

_Q_PATIENTS_WITH = (
    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(c) "
    "WHERE c.conceptId IN $ids "
    "RETURN DISTINCT toString(p.id) AS patient_id"
)

_Q_PATIENTS_WITH_ASSERTION = (
    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c) "
    "WHERE c.conceptId IN $ids "
    "  AND coalesce(r.assertion, 'present') IN $assertions "
    "RETURN DISTINCT toString(p.id) AS patient_id"
)


def _extract_ids(raw_json) -> list[int]:
    try:
        vs = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except Exception:
        return []
    return [
        int(c.get("code", 0))
        for inc in (vs.get("compose") or {}).get("include") or []
        for c in inc.get("concept") or []
        if c.get("code")
    ]


def _isa_expand(kg, parent_ids: list[int]) -> set[int]:
    if not parent_ids:
        return set()
    rows = kg.run(
        _Q_ISA.format(depth=ISA_DEPTH),
        ids=[str(c) for c in parent_ids],
    )
    return set(parent_ids) | {
        int(r["child_id"]) for r in (rows or []) if r.get("child_id")
    }


def _patient_set(
    pg, concept_ids: set[int], assertions: list[str] | None = None
) -> set[str]:
    if not concept_ids:
        return set()
    str_ids = [str(c) for c in concept_ids]
    if assertions:
        rows = pg.run(_Q_PATIENTS_WITH_ASSERTION, ids=str_ids, assertions=assertions)
    else:
        rows = pg.run(_Q_PATIENTS_WITH, ids=str_ids)
    return {r["patient_id"] for r in rows}


def main() -> None:
    # -- Load and expand domain concept IDs from KG --
    logger.info("Loading domain '%s' from Knowledge Graph...", DOMAIN_ID)
    kg = KnowledgeGraphClient()
    try:
        rows = kg.run(_Q_DOMAIN_VALUESETS, domain_id=DOMAIN_ID)
        domain_by_milestone: dict[str, list[int]] = {}
        for row in rows:
            m = row["milestone_type"] or "unknown"
            parent_ids = _extract_ids(row["raw_json"])
            domain_by_milestone.setdefault(m, []).extend(parent_ids)

        logger.info("Expanding IS_A (depth=%d)...", ISA_DEPTH)
        expanded: dict[str, set[int]] = {}
        for m, ids in domain_by_milestone.items():
            expanded[m] = _isa_expand(kg, ids)
            logger.info(
                "  %-20s  %d parent(s) -> %d after IS_A", m, len(ids), len(expanded[m])
            )
    finally:
        kg.close()

    referral_ids = expanded.get("referral", set())
    diagnosis_ids = expanded.get("diagnosis", set())
    specialist_ids = expanded.get("specialist_visit", set())

    # -- Find hardcoded IDs not covered by domain IS_A expansion --
    missing_referral = FAST_TRACK_REFERRAL_IDS - referral_ids
    missing_diagnosis = CANCER_TYPE_IDS - diagnosis_ids
    missing_specialist = SEEN_BY_SPECIALIST_IDS - specialist_ids

    logger.info("")
    logger.info("=" * 65)
    logger.info("HARDCODED CONCEPT IDs NOT COVERED BY DOMAIN IS_A EXPANSION")
    logger.info("=" * 65)

    pg = PatientGraphClient()
    try:
        for label, missing in [
            ("referral", missing_referral),
            ("diagnosis", missing_diagnosis),
            ("specialist_visit", missing_specialist),
        ]:
            if not missing:
                logger.info("  %-16s  all covered", label)
                continue
            name_rows = pg.run(_Q_CONCEPT_NAMES, ids=[str(c) for c in missing])
            names = {r["id"]: r["name"] for r in name_rows}
            logger.info("  %s  -- %d NOT COVERED:", label, len(missing))
            for cid in sorted(missing):
                logger.info(
                    "    %s  %s", cid, names.get(str(cid), "(not in patient graph)")
                )

        # -- Pathway gap analysis --
        all_patients = {
            r["patient_id"]
            for r in pg.run("MATCH (p:Patient) RETURN toString(p.id) AS patient_id")
        }
        total = len(all_patients)

        with_referral = _patient_set(pg, referral_ids)
        with_diagnosis = _patient_set(pg, diagnosis_ids)
        with_exclusion = _patient_set(pg, CANCER_EXCLUSION_IDS)
        with_specialist = _patient_set(pg, specialist_ids)

        # Referral with no diagnosis AND no exclusion
        referral_no_outcome = with_referral - with_diagnosis - with_exclusion
        # Diagnosis with no prior referral recorded
        diagnosis_no_referral = with_diagnosis - with_referral
        # Referred and then saw specialist but still no diagnosis/exclusion
        specialist_no_outcome = with_specialist - with_diagnosis - with_exclusion

        logger.info("")
        logger.info("=" * 65)
        logger.info("PATHWAY GAP ANALYSIS  (total patients: %d)", total)
        logger.info("=" * 65)
        logger.info(
            "  With referral:                     %3d  (%d%%)",
            len(with_referral),
            100 * len(with_referral) // total,
        )
        logger.info(
            "  With diagnosis (incl. exclusion):  %3d  (%d%%)",
            len(with_diagnosis),
            100 * len(with_diagnosis) // total,
        )
        logger.info(
            "  With exclusion only:               %3d",
            len(with_exclusion - with_diagnosis),
        )
        logger.info(
            "  Saw specialist:                    %3d",
            len(with_specialist),
        )
        logger.info("")
        logger.info(
            "  REFERRAL but NO diagnosis & NOT excluded:  %3d  <-- safety net",
            len(referral_no_outcome),
        )
        logger.info(
            "  DIAGNOSIS but NO referral recorded:        %3d  <-- late/direct presentation",
            len(diagnosis_no_referral),
        )
        logger.info(
            "  Saw SPECIALIST but still no outcome:       %3d",
            len(specialist_no_outcome),
        )

        if referral_no_outcome:
            logger.info("\n  Patients with referral but no outcome:")
            for pid in sorted(referral_no_outcome):
                logger.info("    %s", pid)

        if diagnosis_no_referral:
            logger.info("\n  Patients with diagnosis but no referral:")
            for pid in sorted(diagnosis_no_referral):
                logger.info("    %s", pid)

    finally:
        pg.close()

    logger.info("=" * 65)


if __name__ == "__main__":
    main()
