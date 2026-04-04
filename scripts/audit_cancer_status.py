"""Cancer diagnosis and exclusion data quality audit.

Finds all patients and reports whether each one has a cancer diagnosis,
a cancer exclusion, or neither -- and flags inconsistencies that may
indicate data quality problems.

Issues detected
---------------
DQ-1  Patient has a fast-track referral but no diagnosis AND no exclusion
      (stuck mid-pathway; exclusion detector may not have run)
DQ-2  Cancer coded as 'present' in DOCUMENTS but no EpisodeOfCare exists
      (episode builder may not have run for this patient)
DQ-3  EpisodeOfCare exists but lacks exclusion_outcome
      (exclusion detector did not complete)
DQ-4  Both a confirmed cancer DOCUMENTS link AND a cancer-excluded episode
      exist for the same patient (contradictory state)
DQ-5  Legacy CancerEpisode node but no modern EpisodeOfCare
      (migration from the old schema is incomplete)
DQ-6  Cancer concept coded with 'present' assertion AND separately with
      'refuted'/'absent' assertion on the same patient
      (conflicting assertions; pipeline may have seen the same text twice)

Usage
-----
    python scripts/audit_cancer_status.py
    python scripts/audit_cancer_status.py --output cancer_audit.csv
    python scripts/audit_cancer_status.py --fix-dry-run
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402
from libs.domains.ncda_concept_sets import (  # noqa: E402
    CANCER_EXCLUSION_IDS,
    CANCER_HISTORY_IDS,
    CANCER_SUSPECTED_IDS,
    CANCER_TYPE_IDS,
    FAST_TRACK_REFERRAL_IDS,
)
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

# Local dev: .env.config sets AZURE_KEYVAULT_URL; secrets/.env is the
# fallback for offline use (populated by sync-secrets-local.ps1).
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("audit_cancer")

_CANCER_IDS_STR = [str(c) for c in CANCER_TYPE_IDS]
_REFERRAL_IDS_STR = [str(c) for c in FAST_TRACK_REFERRAL_IDS]
_EXCLUSION_IDS_STR = [str(c) for c in CANCER_EXCLUSION_IDS]
_HISTORY_IDS_STR = [str(c) for c in CANCER_HISTORY_IDS]
_SUSPECTED_IDS_STR = [str(c) for c in CANCER_SUSPECTED_IDS]

# Assertions that mean "cancer is present / confirmed"
_PRESENT_ASSERTIONS = {"present", "historical"}
# Assertions that mean "cancer was excluded / ruled out"
_EXCLUDED_ASSERTIONS = {"absent", "refuted"}


# ------------------------------------------------------------------
# Cypher queries
# ------------------------------------------------------------------

_Q_ALL_PATIENTS = """
MATCH (p:Patient)
RETURN toString(p.id) AS patient_id
ORDER BY patient_id
"""

_Q_CANCER_DOCUMENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(d)
WHERE d.conceptId IN $concept_ids
RETURN
    toString(p.id)            AS patient_id,
    d.conceptId               AS concept_id,
    d.name                    AS concept_name,
    coalesce(
        r.context,
        '{}'
    )                         AS context_json,
    toString(e.date)          AS encounter_date
ORDER BY patient_id, encounter_date
"""

_Q_REFERRAL_DOCUMENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(d)
WHERE d.conceptId IN $concept_ids
RETURN
    toString(p.id)  AS patient_id,
    d.conceptId     AS concept_id,
    d.name          AS concept_name,
    toString(e.date) AS encounter_date
ORDER BY patient_id, encounter_date
"""

_Q_EPISODES = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
RETURN
    toString(p.id)              AS patient_id,
    ep.episode_id               AS episode_id,
    ep.exclusion_outcome        AS exclusion_outcome,
    ep.exclusion_confidence     AS exclusion_confidence,
    ep.exclusion_method         AS exclusion_method,
    ep.status                   AS status,
    toString(ep.updated_at)     AS updated_at
ORDER BY patient_id, episode_id
"""

_Q_LEGACY_EPISODES = """
MATCH (p:Patient)-[:HAS_EPISODE]->(ep:CancerEpisode)
RETURN toString(p.id) AS patient_id, ep.episode_id AS legacy_episode_id
ORDER BY patient_id
"""

_Q_EXCLUSION_SITUATIONS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(d)
WHERE toString(d.conceptId) IN $concept_ids
RETURN DISTINCT toString(p.id) AS patient_id
ORDER BY patient_id
"""

_Q_HISTORY_SITUATIONS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(d)
WHERE toString(d.conceptId) IN $concept_ids
RETURN DISTINCT toString(p.id) AS patient_id
ORDER BY patient_id
"""

_Q_SUSPECTED_SITUATIONS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(d)
WHERE toString(d.conceptId) IN $concept_ids
RETURN DISTINCT toString(p.id) AS patient_id
ORDER BY patient_id
"""


# ------------------------------------------------------------------
# Data loading helpers
# ------------------------------------------------------------------

def _load_all_patients(session) -> list[str]:
    rows = session.run(_Q_ALL_PATIENTS)
    return [r["patient_id"] for r in rows]


def _load_cancer_documents(session) -> dict[str, list[dict]]:
    """Returns patient_id -> list of cancer DOCUMENTS rows."""
    result: dict[str, list[dict]] = {}
    rows = session.run(_Q_CANCER_DOCUMENTS, concept_ids=_CANCER_IDS_STR)
    for row in rows:
        pid = row["patient_id"]
        result.setdefault(pid, []).append(dict(row))
    return result


def _load_referral_documents(session) -> dict[str, list[dict]]:
    """Returns patient_id -> list of fast-track referral DOCUMENTS rows."""
    result: dict[str, list[dict]] = {}
    rows = session.run(_Q_REFERRAL_DOCUMENTS, concept_ids=_REFERRAL_IDS_STR)
    for row in rows:
        pid = row["patient_id"]
        result.setdefault(pid, []).append(dict(row))
    return result


def _load_episodes(session) -> dict[str, list[dict]]:
    """Returns patient_id -> list of EpisodeOfCare rows."""
    result: dict[str, list[dict]] = {}
    rows = session.run(_Q_EPISODES)
    for row in rows:
        pid = row["patient_id"]
        result.setdefault(pid, []).append(dict(row))
    return result


def _load_legacy_episodes(session) -> set[str]:
    """Returns set of patient_ids with legacy CancerEpisode nodes."""
    rows = session.run(_Q_LEGACY_EPISODES)
    return {r["patient_id"] for r in rows}


def _load_situation_patients(
    session, query: str, ids: list[str]
) -> set[str]:
    """Return patient IDs that have any of the given concept IDs in DOCUMENTS.

    Uses toString(d.conceptId) to handle both integer and string storage,
    since different write paths (clinical coding vs knowledge graph seeding)
    may store conceptId with different Neo4j types.
    """
    rows = session.run(query, concept_ids=ids)
    return {r["patient_id"] for r in rows}


# ------------------------------------------------------------------
# Assertion parsing
# ------------------------------------------------------------------

def _parse_assertion(context_json: str) -> str:
    """Extract assertion value from the JSON stored in r.context."""
    import json
    try:
        ctx = json.loads(context_json or "{}")
    except (ValueError, TypeError):
        return "present"
    if ctx.get("negated") or ctx.get("refuted"):
        return "absent"
    if ctx.get("uncertain"):
        return "possible"
    if ctx.get("historical"):
        return "historical"
    return ctx.get("assertion", "present")


# ------------------------------------------------------------------
# Per-patient analysis
# ------------------------------------------------------------------

def _analyse_patient(
    patient_id: str,
    cancer_docs: list[dict],
    referral_docs: list[dict],
    episodes: list[dict],
    has_legacy_episode: bool,
    has_exclusion_situation: bool,
    has_history_situation: bool,
    has_suspected_situation: bool,
) -> dict:
    """Return a summary row and a list of DQ flags for one patient."""
    issues: list[str] = []

    # -- Classify cancer document assertions --
    present_concepts: set[str] = set()
    excluded_concepts: set[str] = set()

    for doc in cancer_docs:
        assertion = _parse_assertion(doc.get("context_json", "{}"))
        cid = str(doc.get("concept_id", ""))
        if assertion in _PRESENT_ASSERTIONS:
            present_concepts.add(cid)
        elif assertion in _EXCLUDED_ASSERTIONS:
            excluded_concepts.add(cid)

    has_cancer_present = bool(present_concepts)
    # Exclusion via coded situation node OR via assertion on a cancer concept
    has_cancer_excluded_doc = bool(excluded_concepts) or has_exclusion_situation
    has_referral = bool(referral_docs)
    has_episode = bool(episodes)

    # -- Episode-level state --
    episodes_missing_status = [
        ep for ep in episodes
        if not ep.get("exclusion_outcome") and not ep.get("status")
    ]

    # -- DQ checks --
    # DQ-1: referral but no diagnosis and no exclusion at all
    if has_referral and not has_cancer_present and not has_cancer_excluded_doc:
        no_ep_exclusion = not any(
            ep.get("exclusion_outcome") == "excluded" for ep in episodes
        )
        if no_ep_exclusion:
            issues.append("DQ-1:referral_no_diagnosis_no_exclusion")

    # DQ-2: cancer present in DOCUMENTS but no EpisodeOfCare
    if has_cancer_present and not has_episode:
        issues.append("DQ-2:cancer_coded_no_episode")

    # DQ-3: EpisodeOfCare exists but lacks exclusion_outcome
    if episodes_missing_status:
        issues.append(
            f"DQ-3:episode_missing_status({len(episodes_missing_status)} ep)"
        )

    # DQ-4: confirmed cancer diagnosis AND excluded episode (contradictory)
    has_confirmed_ep = any(
        ep.get("exclusion_outcome") == "excluded" for ep in episodes
    )
    if has_cancer_present and has_confirmed_ep:
        issues.append("DQ-4:cancer_present_and_episode_excluded")

    # DQ-5: legacy CancerEpisode but no modern EpisodeOfCare
    if has_legacy_episode and not has_episode:
        issues.append("DQ-5:legacy_episode_no_modern_episode")

    # DQ-6: same concept coded both present and excluded
    overlap = present_concepts & excluded_concepts
    if overlap:
        issues.append(
            f"DQ-6:conflicting_assertions({len(overlap)} concept(s))"
        )

    # DQ-7: suspected cancer situation coded but no diagnosis and no exclusion
    # (patient is still mid-pathway with no recorded outcome)
    mid_pathway = (
        has_suspected_situation
        and not has_cancer_present
        and not has_cancer_excluded_doc
    )
    if mid_pathway:
        if not any(ep.get("exclusion_outcome") for ep in episodes):
            issues.append("DQ-7:suspected_no_outcome")

    # -- Determine top-level cancer status --
    episode_confirmed = any(
        ep.get("exclusion_outcome") not in ("excluded", None)
        or ep.get("status") == "confirmed"
        for ep in episodes
    )
    episode_excluded = any(
        ep.get("exclusion_outcome") == "excluded"
        for ep in episodes
    )

    if has_cancer_present or has_history_situation or episode_confirmed:
        cancer_status = "cancer_diagnosis"
    elif has_cancer_excluded_doc or episode_excluded:
        cancer_status = "cancer_excluded"
    elif has_suspected_situation or has_referral:
        cancer_status = "suspected_or_referral_only"
    else:
        cancer_status = "no_cancer_signal"

    return {
        "patient_id": patient_id,
        "cancer_status": cancer_status,
        "has_referral": has_referral,
        "has_cancer_present_docs": has_cancer_present,
        "has_cancer_excluded_docs": has_cancer_excluded_doc,
        "has_exclusion_situation": has_exclusion_situation,
        "has_history_situation": has_history_situation,
        "has_suspected_situation": has_suspected_situation,
        "has_episode_of_care": has_episode,
        "has_legacy_episode": has_legacy_episode,
        "episode_count": len(episodes),
        "episodes_missing_status": len(episodes_missing_status),
        "issues": "|".join(issues) if issues else "",
        "referral_count": len(referral_docs),
        "cancer_doc_count": len(cancer_docs),
    }


# ------------------------------------------------------------------
# Summary reporting
# ------------------------------------------------------------------

def _print_summary(rows: list[dict]) -> None:
    total = len(rows)
    by_status: dict[str, int] = {}
    issue_counts: dict[str, int] = {}

    for row in rows:
        status = row["cancer_status"]
        by_status[status] = by_status.get(status, 0) + 1
        for issue in (row["issues"] or "").split("|"):
            if issue:
                code = issue.split(":")[0]
                issue_counts[code] = issue_counts.get(code, 0) + 1

    logger.info("=" * 60)
    logger.info("CANCER STATUS AUDIT -- %d patients", total)
    logger.info("=" * 60)
    for status, count in sorted(by_status.items()):
        logger.info("  %-30s %d", status, count)

    logger.info("-" * 60)
    logger.info("DATA QUALITY FLAGS")
    if not issue_counts:
        logger.info("  None -- all patients look clean")
    else:
        for code, count in sorted(issue_counts.items()):
            logger.info("  %-6s %d patients", code, count)
    logger.info("=" * 60)


def _write_csv(rows: list[dict], path: str) -> None:
    if not rows:
        logger.warning("No rows to write")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Wrote %d rows to %s", len(rows), path)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit cancer diagnosis and exclusion data quality"
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default="",
        help="Write results to a CSV file at this path",
    )
    parser.add_argument(
        "--issues-only",
        action="store_true",
        help="Only include patients with at least one DQ flag in the output",
    )
    parser.add_argument(
        "--fix-dry-run",
        action="store_true",
        help="Describe fixes without applying them (not yet implemented)",
    )
    args = parser.parse_args()

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")

    if not neo4j_password:
        logger.error(
            "NEO4J_PASSWORD is not set. "
            "Make sure secrets/.env exists or AZURE_KEYVAULT_URL is configured."
        )
        sys.exit(1)

    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    logger.info("Connecting to %s", neo4j_uri)

    with driver.session() as session:
        logger.info("Loading all patients...")
        all_patients = _load_all_patients(session)
        logger.info("Found %d patients", len(all_patients))

        logger.info("Loading cancer DOCUMENTS links...")
        cancer_docs_by_patient = _load_cancer_documents(session)

        logger.info("Loading fast-track referral DOCUMENTS links...")
        referral_docs_by_patient = _load_referral_documents(session)

        logger.info("Loading EpisodeOfCare nodes...")
        episodes_by_patient = _load_episodes(session)

        logger.info("Loading legacy CancerEpisode nodes...")
        legacy_episode_patients = _load_legacy_episodes(session)

        logger.info("Loading cancer exclusion situation nodes...")
        exclusion_patients = _load_situation_patients(
            session, _Q_EXCLUSION_SITUATIONS, _EXCLUSION_IDS_STR
        )
        logger.info("Loading cancer history situation nodes...")
        history_patients = _load_situation_patients(
            session, _Q_HISTORY_SITUATIONS, _HISTORY_IDS_STR
        )
        logger.info("Loading suspected cancer situation nodes...")
        suspected_patients = _load_situation_patients(
            session, _Q_SUSPECTED_SITUATIONS, _SUSPECTED_IDS_STR
        )

    driver.close()

    logger.info("Analysing %d patients...", len(all_patients))
    results: list[dict] = []
    for pid in all_patients:
        row = _analyse_patient(
            patient_id=pid,
            cancer_docs=cancer_docs_by_patient.get(pid, []),
            referral_docs=referral_docs_by_patient.get(pid, []),
            episodes=episodes_by_patient.get(pid, []),
            has_legacy_episode=pid in legacy_episode_patients,
            has_exclusion_situation=pid in exclusion_patients,
            has_history_situation=pid in history_patients,
            has_suspected_situation=pid in suspected_patients,
        )
        results.append(row)

    if args.issues_only:
        results = [r for r in results if r["issues"]]

    _print_summary(results)

    if args.output:
        _write_csv(results, args.output)

    if args.fix_dry_run:
        logger.info(
            "--fix-dry-run: automatic remediation is not yet implemented. "
            "Review the DQ flags in the output and re-run the gold pipeline "
            "for affected patients to rebuild missing episodes."
        )

    flagged = [r for r in results if r["issues"]]
    if flagged:
        logger.warning(
            "%d patient(s) have data quality flags. "
            "Run with --output cancer_audit.csv for the full report.",
            len(flagged),
        )
        sys.exit(2)

    logger.info("Audit complete -- no data quality issues found.")


if __name__ == "__main__":
    main()
