"""Referral episode timeline analysis.

For every patient with a fast-track (2WW) cancer referral, this script:

  1. Loads all coded milestones in chronological order:
       referrals (tumour-site specific), specialist clinic visits,
       cancer diagnoses, and referral outcomes (exclusion / benign / NAD)

  2. Clusters referrals into episodes using two rules:
       CLUSTER_GAP_DAYS (default 90)  -- referrals within this window
                                          belong to the same episode
       NEW_EPISODE_GAP_DAYS (default 365) -- gap larger than this always
                                              creates a new episode

  3. For each episode, scans the window between the last referral in the
     cluster and the next referral cluster (or look_ahead_days later) for:
       - A cancer diagnosis                     -> outcome: confirmed_cancer
       - An exclusion / normal outcome concept  -> outcome: cancer_excluded
       - A specialist clinic visit              -> specialist_seen: true
       - Nothing                                -> outcome: pending

  4. Flags complex cases that need human review:
       MULTI_SITE  -- referrals to >1 tumour site in the same cluster
       DIAG_BEFORE_REFERRAL -- diagnosis date before first referral
       NO_SPECIALIST -- referred but never seen in specialist clinic
       MULTI_EPISODE -- patient has >1 episode (second primary or recurrence)
       DIAGNOSIS_AMBIGUOUS -- diagnosis found but site does not match referral

Output
------
  Console: summary + one row per episode needing attention
  CSV     : full episode table (--output PATH)

Usage
-----
    python scripts/analyse_referral_episodes.py
    python scripts/analyse_referral_episodes.py --output referral_episodes.csv
    python scripts/analyse_referral_episodes.py --cluster-days 90 --new-episode-days 365
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("referral_episodes")

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
CLUSTER_GAP_DAYS = 90  # referrals <= this apart = same episode
NEW_EPISODE_GAP_DAYS = 365  # gap >= this = definitely a new episode
LOOK_AHEAD_DAYS = 180  # scan this far after last referral if no next

# ------------------------------------------------------------------
# Site-specific referral concept IDs (from fast_track_referrals JSON)
# ------------------------------------------------------------------
REFERRAL_SITE: dict[str, str] = {
    "276581000000102": "brain",
    "276341000000100": "breast",
    "1556551000000104": "non_site_specific",
    "276371000000106": "childrens_tumour",
    "276401000000108": "colorectal",
    "892201000000106": "lower_gi",
    "276311000000101": "gynaecological",
    "276461000000107": "haematology",
    "280521000000108": "head_and_neck",
    "276491000000101": "lung",
    "276521000000103": "sarcoma",
    "276281000000104": "skin",
    "276551000000108": "upper_gi",
    "276431000000102": "urological",
}

# Specialist clinic visit concept IDs (from seen_by_specialist JSON)
SPECIALIST_SITE: dict[str, str] = {
    "382361000000100": "sarcoma",
    "382711000000103": "skin",
    "382681000000102": "lung",
    "382401000000109": "brain",
    "382431000000103": "breast",
    "383201000000101": "childrens_tumour",
    "382651000000108": "colorectal",
    "382841000000109": "urological",
    "382621000000103": "head_and_neck",
    "382511000000105": "gynaecological",
    "382581000000103": "haematology",
    "382811000000108": "upper_gi",
}

# Outcome concepts that mean cancer was EXCLUDED
# (from referral_outcomes_mapping.json + ncda_concept_sets.py)
EXCLUSION_CONCEPT_IDS: frozenset[str] = frozenset(
    [
        "395100000",  # No evidence of cancer found (situation)
        "414861001",  # No evidence of recurrence of cancer
        # 415068001 REMOVED: this is "Exposure to ultraviolet radiation (event)" in SNOMED,
        #   not a cancer exclusion concept. Confirmed via patient graph 2026-04-06.
        "1090791000000103",  # No evidence of malignancy (UK extension)
        "281900007",  # No abnormality detected (NAD)
        "165324008",  # Biopsy result normal
        "171175005",  # Breast neoplasm screening normal
        "168749009",  # Mammography normal
        "169064005",  # Computed tomography normal
        "923501000000103",  # Referral cancelled by patient
        "20376005",  # Benign neoplastic disease
    ]
)

# Cancer diagnosis concept IDs (from ncda_concept_sets.py CANCER_TYPE_IDS)
# Loaded dynamically below to stay in sync
from libs.domains.ncda_concept_sets import (  # noqa: E402
    CANCER_TYPE_IDS,
    CANCER_HISTORY_IDS,
)

DIAGNOSIS_IDS: frozenset[str] = frozenset(
    str(c) for c in CANCER_TYPE_IDS | CANCER_HISTORY_IDS
)
REFERRAL_IDS: frozenset[str] = frozenset(REFERRAL_SITE.keys())
SPECIALIST_IDS: frozenset[str] = frozenset(SPECIALIST_SITE.keys())


# ------------------------------------------------------------------
# Cypher
# ------------------------------------------------------------------

_Q_PATIENTS_WITH_REFERRALS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(d)
WHERE toString(d.conceptId) IN $referral_ids
RETURN DISTINCT toString(p.id) AS patient_id
ORDER BY patient_id
"""

_Q_ALL_MILESTONES = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(d)
WHERE toString(p.id) IN $patient_ids
  AND (
    toString(d.conceptId) IN $referral_ids
    OR toString(d.conceptId) IN $specialist_ids
    OR toString(d.conceptId) IN $diagnosis_ids
    OR toString(d.conceptId) IN $exclusion_ids
  )
  AND e.date IS NOT NULL
RETURN
    toString(p.id)       AS patient_id,
    toString(e.id)       AS encounter_id,
    toString(e.date)     AS encounter_date,
    toString(d.conceptId) AS concept_id,
    d.name               AS concept_name,
    r.context            AS context_json
ORDER BY patient_id, encounter_date
"""


# ------------------------------------------------------------------
# Data helpers
# ------------------------------------------------------------------


def _parse_assertion(context_json: str | None) -> str:
    try:
        ctx = json.loads(context_json or "{}")
    except (ValueError, TypeError):
        return "present"
    if ctx.get("negated") or ctx.get("refuted"):
        return "absent"
    return ctx.get("assertion", "present")


def _safe_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _load_referral_patients(session) -> list[str]:
    rows = session.run(
        _Q_PATIENTS_WITH_REFERRALS,
        referral_ids=list(REFERRAL_IDS),
    )
    return [r["patient_id"] for r in rows]


def _load_milestones(session, patient_ids: list[str]) -> dict[str, list[dict]]:
    """Return patient_id -> sorted list of milestone event dicts."""
    rows = session.run(
        _Q_ALL_MILESTONES,
        patient_ids=patient_ids,
        referral_ids=list(REFERRAL_IDS),
        specialist_ids=list(SPECIALIST_IDS),
        diagnosis_ids=list(DIAGNOSIS_IDS),
        exclusion_ids=list(EXCLUSION_CONCEPT_IDS),
    )
    result: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        cid = row["concept_id"]
        if cid in REFERRAL_IDS:
            event_type = "referral"
            site = REFERRAL_SITE.get(cid, "unknown")
        elif cid in SPECIALIST_IDS:
            event_type = "specialist"
            site = SPECIALIST_SITE.get(cid, "unknown")
        elif cid in DIAGNOSIS_IDS:
            assertion = _parse_assertion(row.get("context_json"))
            if assertion in ("absent", "refuted"):
                continue
            event_type = "diagnosis"
            site = "unknown"
        else:
            event_type = "exclusion"
            site = "unknown"

        result[row["patient_id"]].append(
            {
                "patient_id": row["patient_id"],
                "encounter_id": row["encounter_id"],
                "encounter_date": row["encounter_date"],
                "dt": _safe_date(row["encounter_date"]),
                "concept_id": cid,
                "concept_name": row["concept_name"],
                "event_type": event_type,
                "site": site,
            }
        )
    return result


# ------------------------------------------------------------------
# Episode clustering
# ------------------------------------------------------------------


def _cluster_referrals(
    referrals: list[dict],
    cluster_gap: int,
    new_episode_gap: int,
) -> list[list[dict]]:
    """Group referrals into episodes based on date gaps."""
    if not referrals:
        return []
    sorted_refs = sorted(referrals, key=lambda r: r["dt"] or date.min)
    clusters: list[list[dict]] = [[sorted_refs[0]]]
    for ref in sorted_refs[1:]:
        last = clusters[-1][-1]
        gap = (ref["dt"] - last["dt"]).days if ref["dt"] and last["dt"] else 0
        if gap > new_episode_gap:
            clusters.append([ref])
        elif gap <= cluster_gap:
            clusters[-1].append(ref)
        else:
            clusters.append([ref])
    return clusters


# ------------------------------------------------------------------
# Per-episode analysis
# ------------------------------------------------------------------


def _analyse_episode(
    patient_id: str,
    episode_idx: int,
    cluster: list[dict],
    all_events: list[dict],
    next_cluster_start: date | None,
    look_ahead: int,
) -> dict:
    """Classify one referral cluster and find diagnosis/exclusion."""
    first_ref_date = cluster[0]["dt"]
    last_ref_date = cluster[-1]["dt"]
    sites = list({r["site"] for r in cluster})

    # Search window: last referral -> next cluster start (or +look_ahead)
    window_start = last_ref_date
    window_end = (
        next_cluster_start - timedelta(days=1)
        if next_cluster_start
        else last_ref_date + timedelta(days=look_ahead)
    )

    # Also look before first referral for any prior diagnosis (up to 60 days)
    pre_window_start = first_ref_date - timedelta(days=60)

    diagnoses_in_window: list[dict] = []
    exclusions_in_window: list[dict] = []
    specialist_visits: list[dict] = []
    diagnosis_before_referral: list[dict] = []

    for ev in all_events:
        if ev["event_type"] == "referral":
            continue
        ev_dt = ev["dt"]
        if not ev_dt:
            continue
        if ev["event_type"] == "specialist":
            if first_ref_date <= ev_dt <= window_end:
                specialist_visits.append(ev)
        elif ev["event_type"] == "diagnosis":
            if ev_dt < first_ref_date and ev_dt >= pre_window_start:
                diagnosis_before_referral.append(ev)
            elif first_ref_date <= ev_dt <= window_end:
                diagnoses_in_window.append(ev)
        elif ev["event_type"] == "exclusion":
            if first_ref_date <= ev_dt <= window_end:
                exclusions_in_window.append(ev)

    # Determine outcome
    flags: list[str] = []
    if len(sites) > 1 and "non_site_specific" not in sites:
        flags.append("MULTI_SITE")
    if not specialist_visits:
        flags.append("NO_SPECIALIST")
    if diagnosis_before_referral:
        flags.append("DIAG_BEFORE_REFERRAL")

    if diagnoses_in_window and exclusions_in_window:
        outcome = "needs_review"
        flags.append("MIXED_OUTCOME")
    elif diagnoses_in_window:
        outcome = "confirmed_cancer"
    elif exclusions_in_window:
        outcome = "cancer_excluded"
    else:
        outcome = "pending"
        flags.append("NO_OUTCOME_CODED")

    def _enc_ids(evs: list[dict]) -> str:
        return "|".join(e["encounter_id"] for e in evs)

    def _dates(evs: list[dict]) -> str:
        return "|".join(e["encounter_date"] for e in evs)

    diag_ev = diagnoses_in_window[0] if diagnoses_in_window else {}
    excl_ev = exclusions_in_window[0] if exclusions_in_window else {}

    return {
        "patient_id": patient_id,
        "episode": episode_idx + 1,
        "outcome": outcome,
        "flags": "|".join(flags) if flags else "",
        "referral_site": "|".join(sorted(sites)),
        "first_referral_date": str(first_ref_date) if first_ref_date else "",
        "last_referral_date": str(last_ref_date) if last_ref_date else "",
        "referral_count": len(cluster),
        "look_window_start": str(window_start) if window_start else "",
        "look_window_end": str(window_end) if window_end else "",
        "specialist_seen": bool(specialist_visits),
        "specialist_dates": _dates(specialist_visits),
        "diagnosis_date": diag_ev.get("encounter_date", ""),
        "diagnosis_concept": diag_ev.get("concept_name", ""),
        "diagnosis_encounter_id": diag_ev.get("encounter_id", ""),
        "exclusion_date": excl_ev.get("encounter_date", ""),
        "exclusion_concept": excl_ev.get("concept_name", ""),
        "exclusion_encounter_id": excl_ev.get("encounter_id", ""),
        "referral_encounter_ids": _enc_ids(cluster),
        "pre_referral_diag": bool(diagnosis_before_referral),
        "pre_referral_diag_dates": _dates(diagnosis_before_referral),
    }


def _analyse_patient(
    patient_id: str,
    events: list[dict],
    cluster_gap: int,
    new_episode_gap: int,
    look_ahead: int,
) -> list[dict]:
    """Return one row per episode for this patient."""
    referrals = [e for e in events if e["event_type"] == "referral"]
    if not referrals:
        return []

    clusters = _cluster_referrals(referrals, cluster_gap, new_episode_gap)
    results: list[dict] = []

    for i, cluster in enumerate(clusters):
        next_start: date | None = None
        if i + 1 < len(clusters):
            next_start = clusters[i + 1][0]["dt"]

        row = _analyse_episode(
            patient_id=patient_id,
            episode_idx=i,
            cluster=cluster,
            all_events=events,
            next_cluster_start=next_start,
            look_ahead=look_ahead,
        )
        results.append(row)

    if len(results) > 1:
        for r in results:
            r["flags"] = (r["flags"] + "|MULTI_EPISODE").lstrip("|")

    return results


# ------------------------------------------------------------------
# Reporting
# ------------------------------------------------------------------


def _print_report(rows: list[dict]) -> None:
    by_outcome: dict[str, int] = defaultdict(int)
    by_flag: dict[str, int] = defaultdict(int)
    patients: set[str] = set()

    for r in rows:
        by_outcome[r["outcome"]] += 1
        patients.add(r["patient_id"])
        for flag in (r["flags"] or "").split("|"):
            if flag:
                by_flag[flag] += 1

    logger.info("=" * 68)
    logger.info(
        "REFERRAL EPISODE ANALYSIS -- %d episodes across %d patients",
        len(rows),
        len(patients),
    )
    logger.info("=" * 68)
    logger.info("Episode outcomes:")
    for outcome, cnt in sorted(by_outcome.items(), key=lambda x: -x[1]):
        logger.info("  %-28s %d", outcome, cnt)
    logger.info("")
    logger.info("Quality flags:")
    for flag, cnt in sorted(by_flag.items(), key=lambda x: -x[1]):
        logger.info("  %-28s %d episodes", flag, cnt)
    logger.info("")
    logger.info("Episodes needing attention (pending or needs_review):")
    needs_attention = [
        r
        for r in rows
        if r["outcome"] in ("pending", "needs_review")
        or "NO_OUTCOME_CODED" in r["flags"]
    ]
    for r in sorted(needs_attention, key=lambda x: x["first_referral_date"]):
        logger.info(
            "  [%s] ep%d  site=%-20s  outcome=%-20s  flags=%s",
            r["patient_id"],
            r["episode"],
            r["referral_site"][:20],
            r["outcome"],
            r["flags"],
        )
        logger.info(
            "    referral: %s -> %s  window: %s -> %s",
            r["first_referral_date"],
            r["last_referral_date"],
            r["look_window_start"],
            r["look_window_end"],
        )
        if r["referral_encounter_ids"]:
            logger.info(
                "    referral_encounter_ids: %s",
                r["referral_encounter_ids"][:120],
            )
    logger.info("=" * 68)


def _write_csv(rows: list[dict], path: str) -> None:
    if not rows:
        logger.warning("No rows to write")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Wrote %d episode rows to %s", len(rows), path)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse 2WW referral episode timelines"
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default="",
        help="Write episode table to CSV",
    )
    parser.add_argument(
        "--cluster-days",
        type=int,
        default=CLUSTER_GAP_DAYS,
        help="Referrals <= this many days apart = same episode (default 90)",
    )
    parser.add_argument(
        "--new-episode-days",
        type=int,
        default=NEW_EPISODE_GAP_DAYS,
        help="Gap >= this days always starts a new episode (default 365)",
    )
    parser.add_argument(
        "--look-ahead",
        type=int,
        default=LOOK_AHEAD_DAYS,
        help="Days after last referral to look for outcome (default 180)",
    )
    args = parser.parse_args()

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")

    if not neo4j_password:
        logger.error("NEO4J_PASSWORD not set.")
        sys.exit(1)

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    with driver.session() as session:
        logger.info("Finding patients with fast-track referrals...")
        patient_ids = _load_referral_patients(session)
        logger.info("Found %d patients", len(patient_ids))

        logger.info("Loading all milestone events...")
        milestones = _load_milestones(session, patient_ids)

    driver.close()

    logger.info("Analysing referral timelines...")
    all_episodes: list[dict] = []
    for pid in patient_ids:
        events = sorted(
            milestones.get(pid, []),
            key=lambda e: e["dt"] or date.min,
        )
        episodes = _analyse_patient(
            patient_id=pid,
            events=events,
            cluster_gap=args.cluster_days,
            new_episode_gap=args.new_episode_days,
            look_ahead=args.look_ahead,
        )
        all_episodes.extend(episodes)

    _print_report(all_episodes)

    if args.output:
        _write_csv(all_episodes, args.output)
    elif all_episodes:
        logger.info("Run with --output referral_episodes.csv for the full table.")


if __name__ == "__main__":
    main()
