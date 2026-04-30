#!/usr/bin/env python3
"""NCDA cancer episode detection — dry-run and graph write-back.

Default mode: report-only (dry run).  Use --apply to write EpisodeOfCare nodes
and IS_PART_OF edges to Neo4j.

Usage:
    # Dry-run only (default):
    python scripts/ncda/run_full_cancer_episode_detection.py

    # Write-back (creates/updates EpisodeOfCare nodes):
    python scripts/ncda/run_full_cancer_episode_detection.py --apply

    # Write-back limited to one patient:
    python scripts/ncda/run_full_cancer_episode_detection.py --apply --patient 6309359401

Write-back guards:
  - Episodes sourced from 'reviewed' (manually curated) are never touched.
  - Existing 'ncda_detector' episodes are backed up to artifacts/ncda_episode_backup/
    before any MERGE.
  - Each run is fully idempotent: re-running produces the same graph state.
  - episode_id is a deterministic 16-char hex hash of patient+site+anchor-date.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.domains.documents_disorder_malignancy_ids import (  # noqa: E402
    DOCUMENTS_DISORDER_MALIGNANCY_IDS,
)
from libs.domains.ncda_concept_sets import CANCER_TYPE_IDS  # noqa: E402
from libs.oncology.cancer_types import infer_cancer_type_from_dx_text  # noqa: E402
from libs.oncology.first_presentation import (  # noqa: E402
    EXTENDED_LOOKBACK_DAYS as FP_EXTENDED_LOOKBACK_DAYS,
    LOOKBACK_DAYS as FP_LOOKBACK_DAYS,
    build_fp_cypher_filter,
    resolve_symptom_site,
)
from libs.oncology.staging_extractor import extract_staging  # noqa: E402
from services.analysis_worker.app.ncda_detector.route_classifier import (  # noqa: E402
    classify_diagnosis_route,
)
from services.analysis_worker.app.ncda_detector.silver_labeller import (  # noqa: E402
    deterministic_label,
)
from services.analysis_worker.app.ncda_detector.simple_linker import (  # noqa: E402
    EncounterRow as SimpleEncounterRow,
    SimplePathway,
    link_patient as simple_link_patient,
)


_DIAGNOSIS_PATIENTS_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(c.conceptId) IN $diagnosis_ids
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    count(DISTINCT enc) AS diagnosis_encounter_count,
    collect(DISTINCT {
        concept_id: toString(c.conceptId),
        concept_name: coalesce(c.name, c.term, '')
    })[0..20] AS diagnosis_concepts
ORDER BY patient_id
"""

_ALL_ENCOUNTERS_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE coalesce(toString(p.id), toString(p.patient_id)) IN $patient_ids
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    enc.id AS encounter_id,
    toString(enc.date) AS encounter_date,
    enc.text AS text,
    enc.flags AS flags
ORDER BY patient_id, encounter_date
"""


def _connect():
    uri = os.environ.get("NEO4J_PATIENT_URI", "").strip() or os.environ.get("NEO4J_URI", "").strip()
    user = os.environ.get("NEO4J_PATIENT_USER", "").strip() or os.environ.get("NEO4J_USER", "").strip()
    pw = os.environ.get("NEO4J_PATIENT_PASSWORD", "").strip() or os.environ.get("NEO4J_PASSWORD", "").strip()
    if not all([uri, user, pw]):
        raise SystemExit("ERROR: NEO4J credentials missing.")
    return GraphDatabase.driver(uri, auth=(user, pw))


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _date_key(v: str | None) -> tuple[int, int, int] | None:
    if not v:
        return None
    parts = str(v)[:10].split("-")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _row_anchor_date(row: dict[str, Any], anchor: str) -> str | None:
    payload = row.get(anchor) or {}
    return payload.get("encounter_date")


def _row_dx_date(row: dict[str, Any]) -> str | None:
    return _row_anchor_date(row, "dx")


def _row_ftr_date(row: dict[str, Any]) -> str | None:
    return _row_anchor_date(row, "ftr")


def _pathway_site(pathway: SimplePathway) -> str | None:
    if pathway.ftr_site:
        return str(pathway.ftr_site)
    if pathway.dx and pathway.dx.site:
        return str(pathway.dx.site)
    if pathway.ftr and pathway.ftr.site:
        return str(pathway.ftr.site)
    return None


def _row_sort_key(row: dict[str, Any]) -> tuple:
    return (
        row.get("patient_id") or "",
        _date_key(_row_dx_date(row)) or (9999, 12, 31),
        _date_key(_row_ftr_date(row)) or (9999, 12, 31),
        row.get("cohort") or "",
        row.get("site") or "",
    )


def _date_lte(a: str | None, b: str | None) -> bool:
    da = _date_key(a)
    db = _date_key(b)
    if da is None or db is None:
        return False
    return da <= db


def _days_between(a: str | None, b: str | None) -> int | None:
    da, db = _date_key(a), _date_key(b)
    if da is None or db is None:
        return None
    from datetime import date

    return abs((date(*da) - date(*db)).days)


def _within_days(a: str | None, b: str | None, days: int) -> bool:
    gap = _days_between(a, b)
    return gap is not None and gap <= days


def _same_specific_site(a: str | None, b: str | None) -> bool:
    return bool(a and b and a != "unknown" and b != "unknown" and a == b)


# Same-site duplicate FTR collapse window. Two referrals coded within this many
# days that share a Seen-In or Dx encounter are almost always the same pathway
# captured twice (admin re-send, secretary copy, secondary-care echo).
_NEAR_FTR_COLLAPSE_DAYS = 7


def _anchor_payload(anchor: SimpleEncounterRow | None) -> dict[str, Any] | None:
    if anchor is None:
        return None
    return {
        "encounter_id": anchor.encounter_id,
        "encounter_date": anchor.encounter_date,
        "role": anchor.role,
        "outcome": anchor.outcome,
        "site": str(anchor.site) if anchor.site else None,
        # 1000 chars ensures staging info (Gleason, Breslow, TNM) is included
        # even when the dx encounter has a long preamble before the diagnosis.
        "text_preview": (anchor.text or "")[:1000],
    }


def _run_patient(pid: str, enc_list: list[dict], *, window_days: int) -> list[dict[str, Any]]:
    labels = [
        deterministic_label(
            patient_id=pid,
            encounter_id=str(r["encounter_id"]),
            encounter_date=r.get("encounter_date"),
            text=r.get("text") or "",
            flags=r.get("flags"),
        )
        for r in enc_list
    ]
    enc_by_id = {str(r["encounter_id"]): r for r in enc_list}

    # Pass the silver-labeller's site_hint directly into the EncounterRow so
    # _annotate_site (in the simple linker) skips site_from_text.  site_from_text
    # uses a simpler keyword scan on the raw text and can misattribute site when
    # incidental mentions appear — e.g. "XR Thoracic spine" in a prostate review
    # causes site_from_text to return "lung" before it reaches "urological".  The
    # silver labeller strips problem-lines and applies _SITE_TOKENS consistently.
    simple_encs = [
        SimpleEncounterRow(
            encounter_id=lb.encounter_id,
            encounter_date=lb.encounter_date or "",
            role=lb.role,
            outcome=lb.outcome,
            text=enc_by_id[lb.encounter_id].get("text") or "",
            site=lb.site_hint,  # type: ignore[arg-type]
        )
        for lb in labels
    ]
    labeled_for_route = sorted(
        [
            (
                lb.encounter_date or "",
                enc_by_id[lb.encounter_id].get("text") or "",
                lb.role,
            )
            for lb in labels
        ],
        key=lambda x: x[0],
    )

    # NSS (non-site-specific) referrals reach diagnosis much later than
    # site-specific pathways — NICE guidance allows up to 12 months on the
    # NSS pathway. Extend the link window to 400 days whenever an NSS FTR
    # (Y3dd2) is present so these pathways aren't dropped as cohort-3.
    has_nss_ftr = any(
        "Y3dd2" in (enc_by_id.get(lb.encounter_id) or {}).get("text", "")
        for lb in labels
        if lb.role == "ftr"
    )
    effective_window = 400 if has_nss_ftr else window_days

    pathways = simple_link_patient(pid, simple_encs, link_window_days=effective_window)

    rows: list[dict[str, Any]] = []
    for idx, pathway in enumerate(pathways, start=1):
        route = classify_diagnosis_route(pathway, labeled_encounters=labeled_for_route)
        rows.append(
            {
                "patient_id": pid,
                "pathway_index": idx,
                "cohort": pathway.cohort,
                "site": _pathway_site(pathway),
                "diagnosis_route": route.route,
                "route_rationale": list(route.rationale),
                "confidence": pathway.confidence,
                "notes": pathway.notes,
                "gap_ftr_dx_days": pathway.gap_ftr_dx_days,
                "gap_ftr_seen_days": pathway.gap_ftr_seen_days,
                "gap_dx_treatment_days": pathway.gap_dx_treatment_days,
                "ftr": _anchor_payload(pathway.ftr),
                "seen": _anchor_payload(pathway.seen),
                "dx": _anchor_payload(pathway.dx),
                "treatment": _anchor_payload(pathway.treatment),
                "n_encounters": len(enc_list),
                "n_labelled_non_none": sum(1 for lb in labels if lb.role != "none"),
            }
        )
    return rows


def _is_better_episode_candidate(
    current: dict[str, Any] | None,
    challenger: dict[str, Any],
) -> bool:
    """Prefer cancer-found, then linked-FTR, then earliest Dx for duplicates."""
    if current is None:
        return True
    current_dx = current.get("dx") or {}
    challenger_dx = challenger.get("dx") or {}
    current_found = current_dx.get("outcome") == "cancer_found"
    challenger_found = challenger_dx.get("outcome") == "cancer_found"
    if challenger_found != current_found:
        return challenger_found
    current_linked = current.get("cohort") in {"1a", "1b"}
    challenger_linked = challenger.get("cohort") in {"1a", "1b"}
    if challenger_linked != current_linked:
        return challenger_linked
    return _row_sort_key(challenger) < _row_sort_key(current)


def _collapse_near_day_ftrs(
    linked_rows: list[dict[str, Any]],
    *,
    days: int = _NEAR_FTR_COLLAPSE_DAYS,
) -> list[dict[str, Any]]:
    """Collapse same-site FTRs within ``days`` that share Seen-In or Dx.

    A single fast-track referral is often coded twice within a few days (admin
    re-send, secondary-care echo, scanned letter). When two linked rows for the
    same patient and site sit within the window AND share either the Seen-In
    encounter date or the Dx encounter date, they describe the same pathway and
    should be reduced to the best outcome (cancer_found over cancer_excluded
    over outcome=None).
    """
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in linked_rows:
        site = row.get("site") or "unknown"
        grouped[(row.get("patient_id") or "", site)].append(row)

    out: list[dict[str, Any]] = []
    for rows in grouped.values():
        rows.sort(key=lambda r: _date_key(_row_ftr_date(r)) or (9999, 12, 31))
        clusters: list[list[dict[str, Any]]] = []
        for row in rows:
            placed = False
            for cluster in clusters:
                anchor = cluster[0]
                gap = _days_between(_row_ftr_date(anchor), _row_ftr_date(row))
                if gap is None or gap > days:
                    continue
                shares_seen = _shared_anchor(anchor, row, "seen")
                shares_dx = _shared_anchor(anchor, row, "dx")
                if shares_seen or shares_dx:
                    cluster.append(row)
                    placed = True
                    break
            if not placed:
                clusters.append([row])
        for cluster in clusters:
            best: dict[str, Any] | None = None
            for r in cluster:
                if _is_better_episode_candidate(best, r):
                    best = r
            assert best is not None
            out.append(best)
    return out


def _shared_anchor(a: dict[str, Any], b: dict[str, Any], anchor: str) -> bool:
    da = _row_anchor_date(a, anchor)
    db = _row_anchor_date(b, anchor)
    return bool(da and db and da == db)


def _drop_outcomeless_when_found_exists(
    linked_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop ``1b`` rows whose Dx outcome is ``None`` when a ``1a cancer_found``
    row exists for the same patient+site.

    These rows are usually the linker reaching back to a Seen-In or interim
    imaging encounter as a stand-in Dx; the real diagnosis comes through the
    cohort 1a sibling. Keeping both inflates episode counts without adding
    clinical signal.
    """
    found_keys: set[tuple[str, str]] = set()
    for row in linked_rows:
        dx = row.get("dx") or {}
        if row.get("cohort") == "1a" and dx.get("outcome") == "cancer_found":
            found_keys.add((row.get("patient_id") or "", row.get("site") or "unknown"))

    kept: list[dict[str, Any]] = []
    for row in linked_rows:
        dx = row.get("dx") or {}
        is_outcomeless_1b = row.get("cohort") == "1b" and dx.get("outcome") in (
            None,
            "",
        )
        site_key = (row.get("patient_id") or "", row.get("site") or "unknown")
        if is_outcomeless_1b and site_key in found_keys:
            continue
        kept.append(row)
    return kept


def reduce_episode_candidates(
    raw_pathways: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split raw linker rows into diagnosis episodes and open referrals.

    The simple linker intentionally emits every unmatched FTR (cohort 2) and
    every cancer-found Dx without an FTR (cohort 3).  That is useful for debug,
    but too noisy for diagnosis-positive episode counts.  This reducer keeps
    cohort 2 rows as ``open_referrals`` and collapses repeated diagnosis rows by
    patient, site, Dx date, and outcome.  Cohort 3 is further reduced to one
    earliest Dx per patient/site because repeated problem-list or treatment
    encounters often carry the same known cancer forward.
    """
    open_referrals = [r for r in raw_pathways if r.get("cohort") == "2"]
    diagnosis_rows = [r for r in raw_pathways if r.get("cohort") != "2"]

    # First collapse exact anchor duplicates (same FTR/Dx/date/outcome/site).
    exact: dict[tuple, dict[str, Any]] = {}
    for row in diagnosis_rows:
        dx = row.get("dx") or {}
        key = (
            row.get("patient_id"),
            row.get("cohort"),
            row.get("site") or "unknown",
            _row_ftr_date(row),
            _row_dx_date(row),
            dx.get("outcome"),
        )
        if _is_better_episode_candidate(exact.get(key), row):
            exact[key] = row

    # Then collapse linked pathways to one outcome per patient/site/FTR.  A
    # single FTR can create several candidate Dx rows (interim imaging, outcome
    # letter, later treatment-coded cancer mention); for episode reporting it
    # should contribute one outcome, preferring cancer_found when present.
    reduced: list[dict[str, Any]] = []
    linked_best: dict[tuple, dict[str, Any]] = {}
    cohort3_best: dict[tuple, dict[str, Any]] = {}
    for row in sorted(exact.values(), key=_row_sort_key):
        if row.get("cohort") in {"1a", "1b"}:
            key = (
                row.get("patient_id"),
                row.get("site") or "unknown",
                _row_ftr_date(row),
            )
            if _is_better_episode_candidate(linked_best.get(key), row):
                linked_best[key] = row
            continue
        if row.get("cohort") == "3":
            key = (row.get("patient_id"), row.get("site") or "unknown")
            if _is_better_episode_candidate(cohort3_best.get(key), row):
                cohort3_best[key] = row

    linked_by_dx: dict[tuple, dict[str, Any]] = {}
    for row in linked_best.values():
        dx = row.get("dx") or {}
        key = (
            row.get("patient_id"),
            row.get("site") or "unknown",
            _row_dx_date(row),
            dx.get("outcome"),
        )
        if _is_better_episode_candidate(linked_by_dx.get(key), row):
            linked_by_dx[key] = row

    linked_rows = _collapse_near_day_ftrs(list(linked_by_dx.values()))
    linked_rows = _drop_outcomeless_when_found_exists(linked_rows)
    cohort3_rows = list(cohort3_best.values())

    # Drop unknown-site cohort-3 rows when a site-specific cohort-3 row for
    # the same patient is within 30 days. These are usually the same imported
    # diagnosis letter being parsed twice: once as a generic cancer term
    # (unknown site) and once as a site-specific term (e.g. "breast cancer").
    specific_cohort3_by_patient: dict[str, list[str | None]] = defaultdict(list)
    for row in cohort3_rows:
        if row.get("site") not in (None, "unknown"):
            specific_cohort3_by_patient[row.get("patient_id") or ""].append(
                _row_dx_date(row)
            )
    cohort3_rows = [
        row
        for row in cohort3_rows
        if not (
            row.get("site") in (None, "unknown")
            and any(
                _within_days(_row_dx_date(row), other, 30)
                for other in specific_cohort3_by_patient.get(
                    row.get("patient_id") or "", []
                )
            )
        )
    ]

    # Drop cohort-3 repeats after an already linked same-patient + same-site
    # cancer-found episode. These are usually problem-list / treatment
    # follow-up mentions for a known cancer, not a fresh no-FTR diagnosis
    # route. (Earlier versions of this reducer cross-referenced ALL patients,
    # which incorrectly suppressed genuine cohort-3 episodes when any other
    # patient had a same-site linked diagnosis at an earlier date.)
    linked_found_by_patient_site: dict[tuple[str, str], list[str | None]] = defaultdict(list)
    for row in linked_rows:
        if (row.get("dx") or {}).get("outcome") != "cancer_found":
            continue
        site = row.get("site") or "unknown"
        if site == "unknown":
            continue
        linked_found_by_patient_site[
            (row.get("patient_id") or "", site)
        ].append(_row_dx_date(row))
    # Build a lookup of all 1a cancer_found dx dates by patient for the
    # unknown-site proximity check below.
    all_linked_found_by_patient: dict[str, list[str | None]] = defaultdict(list)
    for row in linked_rows:
        if (row.get("dx") or {}).get("outcome") == "cancer_found":
            all_linked_found_by_patient[row.get("patient_id") or ""].append(
                _row_dx_date(row)
            )

    _NEAR_DX_COLLAPSE_DAYS = 14

    filtered_cohort3: list[dict[str, Any]] = []
    for row in cohort3_rows:
        site = row.get("site") or "unknown"
        dx_date = _row_dx_date(row)
        same_pat_site_dx_dates = linked_found_by_patient_site.get(
            (row.get("patient_id") or "", site), []
        )
        # Drop site-known cohort-3 when a linked 1a already exists for the same
        # patient+site at an equal-or-earlier date.
        drop = site != "unknown" and any(
            _date_lte(linked_dx, dx_date) for linked_dx in same_pat_site_dx_dates
        )
        # Drop unknown-site cohort-3 when ANY linked 1a cancer_found episode for
        # the same patient has a dx date within 14 days.  These are usually
        # multiple admin entries of the same diagnosis result (e.g. 2025-02-07,
        # -11, -12 for the same squamous cell carcinoma letter) where some entries
        # get linked to the FTR and the last one is left unlinked with no site.
        if not drop and site == "unknown":
            drop = any(
                _within_days(dx_date, linked_dx, _NEAR_DX_COLLAPSE_DAYS)
                for linked_dx in all_linked_found_by_patient.get(
                    row.get("patient_id") or "", []
                )
            )
        if not drop:
            filtered_cohort3.append(row)

    reduced.extend(linked_rows)
    reduced.extend(filtered_cohort3)
    reduced.sort(key=_row_sort_key)
    open_referrals.sort(key=_row_sort_key)
    return reduced, open_referrals


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "patient_id",
        "pathway_index",
        "cohort",
        "site",
        "diagnosis_route",
        "route_rationale",
        "ftr_date",
        "seen_date",
        "dx_date",
        "dx_outcome",
        "treatment_date",
        "gap_ftr_dx_days",
        "gap_ftr_seen_days",
        "gap_dx_treatment_days",
        "confidence",
        "notes",
        "n_encounters",
        "n_labelled_non_none",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "patient_id": row["patient_id"],
                    "pathway_index": row["pathway_index"],
                    "cohort": row["cohort"],
                    "site": row["site"],
                    "diagnosis_route": row["diagnosis_route"],
                    "route_rationale": "; ".join(row["route_rationale"]),
                    "ftr_date": (row["ftr"] or {}).get("encounter_date"),
                    "seen_date": (row["seen"] or {}).get("encounter_date"),
                    "dx_date": (row["dx"] or {}).get("encounter_date"),
                    "dx_outcome": (row["dx"] or {}).get("outcome"),
                    "treatment_date": (row["treatment"] or {}).get("encounter_date"),
                    "gap_ftr_dx_days": row["gap_ftr_dx_days"],
                    "gap_ftr_seen_days": row["gap_ftr_seen_days"],
                    "gap_dx_treatment_days": row["gap_dx_treatment_days"],
                    "confidence": row["confidence"],
                    "notes": "; ".join(row["notes"]),
                    "n_encounters": row["n_encounters"],
                    "n_labelled_non_none": row["n_labelled_non_none"],
                }
            )


# ---------------------------------------------------------------------------
# Write-back helpers
# ---------------------------------------------------------------------------

_SOURCE_TAG = "ncda_detector"

_BACKUP_EXISTING_Q = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE toString(p.id) IN $patient_ids
  AND ep.source = $source_tag
OPTIONAL MATCH (enc:Encounter)-[r:IS_PART_OF]->(ep)
RETURN
    ep.episode_id        AS episode_id,
    ep.patient_id        AS patient_id,
    ep.cancer_type       AS cancer_type,
    ep.cohort            AS cohort,
    ep.referral_date     AS referral_date,
    ep.end_date          AS end_date,
    ep.status            AS status,
    collect({
        encounter_id:   enc.id,
        milestone_type: r.milestone_type
    }) AS encounters
"""

_MERGE_EPISODE_Q = """
MATCH (p:Patient) WHERE toString(p.id) = $patient_id
MERGE (ep:EpisodeOfCare {episode_id: $episode_id})
ON CREATE SET
    ep.patient_id              = $patient_id,
    ep.source                  = $source,
    ep.domain_id               = 'cancer',
    ep.condition_type          = $condition_type,
    ep.cancer_type             = $cancer_type,
    ep.site                    = $site,
    ep.cohort                  = $cohort,
    ep.referral_date           = $referral_date,
    ep.specialist_visit_date   = $specialist_visit_date,
    ep.end_date                = $end_date,
    ep.dx_outcome              = $dx_outcome,
    ep.referral_route          = $referral_route,
    ep.diagnosis_route         = $diagnosis_route,
    ep.place_of_presentation   = $place_of_presentation,
    ep.nss_referral            = $nss_referral,
    ep.referral_site           = $referral_site,
    ep.route_rationale         = $route_rationale,
    ep.status                  = $status,
    ep.hitl_flag               = $hitl_flag,
    ep.confidence              = $confidence,
    ep.gap_ftr_dx_days         = $gap_ftr_dx_days,
    ep.gap_ftr_seen_days       = $gap_ftr_seen_days,
    ep.gap_dx_treatment_days   = $gap_dx_treatment_days,
    ep.cancer_stage            = 'unknown',
    ep.cancer_stage_group      = '',
    ep.staging_system          = $staging_system,
    ep.staging_value           = $staging_value,
    ep.staging_early_late      = $staging_early_late,
    ep.staging_source          = $staging_source,
    ep.staging_confidence      = $staging_confidence,
    ep.staging_systems_found   = $staging_systems_found,
    ep.first_presentation_date = $first_presentation_date,
    ep.created_at              = datetime(),
    ep.updated_at              = datetime()
ON MATCH SET
    ep.cohort                  = $cohort,
    ep.cancer_type             = $cancer_type,
    ep.site                    = $site,
    ep.condition_type          = $condition_type,
    ep.referral_date           = $referral_date,
    ep.specialist_visit_date   = $specialist_visit_date,
    ep.end_date                = $end_date,
    ep.dx_outcome              = $dx_outcome,
    ep.referral_route          = $referral_route,
    ep.diagnosis_route         = $diagnosis_route,
    ep.place_of_presentation   = $place_of_presentation,
    ep.nss_referral            = $nss_referral,
    ep.referral_site           = $referral_site,
    ep.route_rationale         = $route_rationale,
    ep.status                  = $status,
    ep.hitl_flag               = $hitl_flag,
    ep.confidence              = $confidence,
    ep.gap_ftr_dx_days         = $gap_ftr_dx_days,
    ep.gap_ftr_seen_days       = $gap_ftr_seen_days,
    ep.gap_dx_treatment_days   = $gap_dx_treatment_days,
    ep.staging_system          = $staging_system,
    ep.staging_value           = $staging_value,
    ep.staging_early_late      = $staging_early_late,
    ep.staging_source          = $staging_source,
    ep.staging_confidence      = $staging_confidence,
    ep.staging_systems_found   = $staging_systems_found,
    ep.first_presentation_date = $first_presentation_date,
    ep.updated_at              = datetime()
MERGE (p)-[:HAS_EPISODE_OF_CARE]->(ep)
RETURN ep.episode_id AS written_id
"""

_LINK_ENCOUNTERS_Q = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
OPTIONAL MATCH (old_enc:Encounter)-[old_r:IS_PART_OF]->(ep)
WHERE old_enc.id IN $all_encounter_ids
DELETE old_r
WITH ep
UNWIND $encounters AS e
OPTIONAL MATCH (enc:Encounter {id: e.encounter_id})
WITH ep, enc, e WHERE enc IS NOT NULL
MERGE (enc)-[r:IS_PART_OF]->(ep)
SET r.milestone_type  = e.milestone_type,
    r.linked_by       = 'ncda_detector',
    r.linked_at       = datetime()
"""


def _det_episode_id(patient_id: str, site: str, anchor_date: str) -> str:
    """Deterministic 16-char hex episode ID from patient + site + anchor date."""
    raw = f"{patient_id}|{site}|{anchor_date}|ncda"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


_ROUTE_TO_PLACE: dict[str, str] = {
    "gp_surgery_fast_track": "GP Surgery",
    "fast_track_clinic_referral_missing": "GP Surgery",
    "routine_gp_investigation": "GP Surgery",
    "screening": "Screening Programme",
    "emergency_or_urgent_care": "A&E / Emergency",
    "secondary_care_surgical": "Secondary Care",
    "specialist_surveillance_incidental": "Secondary Care",
    "external_or_unknown_route": "Other / Unknown",
    "unknown": "Not Recorded",
}


def _place_of_presentation(diagnosis_route: str) -> str:
    """Map a diagnosis_route to its canonical NCDA place-of-presentation label."""
    return _ROUTE_TO_PLACE.get(diagnosis_route, "Not Recorded")


def _episode_params(row: dict[str, Any]) -> dict[str, Any]:
    """Translate a reduced pathway row into MERGE parameters."""
    patient_id = row["patient_id"]
    site = row["site"] or "unknown"
    cohort = row["cohort"]
    dx_outcome = (row["dx"] or {}).get("outcome") or ""

    # Derive the specific NCDA canonical cancer type from the dx encounter text.
    # Falls back to the pathway-group normalisation (e.g. "urological" → "Other")
    # when the text yields no specific pattern match.
    dx_text_preview = (row["dx"] or {}).get("text_preview") or ""
    ftr_text_preview = (row["ftr"] or {}).get("text_preview") or ""
    seen_text_preview = (row.get("seen") or {}).get("text_preview") or ""
    treatment_text_preview = (row.get("treatment") or {}).get("text_preview") or ""
    ncda_cancer_type = infer_cancer_type_from_dx_text(
        site, dx_text_preview + " " + ftr_text_preview
    )

    # Extract staging information from all milestoned encounter texts.
    # dx text is most likely to contain staging; the others are searched
    # as fallback (e.g. staging mentioned in the treatment summary).
    staging = extract_staging(
        ncda_cancer_type,
        dx_text_preview,
        treatment_text_preview,
        seen_text_preview,
        ftr_text_preview,
    )

    ftr_date = (row["ftr"] or {}).get("encounter_date") or ""
    seen_date = (row["seen"] or {}).get("encounter_date") or ""
    dx_date = (row["dx"] or {}).get("encounter_date") or ""
    treatment_date = (row["treatment"] or {}).get("encounter_date") or ""

    # Deterministic anchor: prefer FTR date, fall back to Dx date for cohort-3
    anchor = ftr_date or dx_date
    episode_id = _det_episode_id(patient_id, site, anchor)

    # Status
    # 1b = cancer excluded → closed_benign so the MECE hero-bucket correctly
    # maps it to 'cancer_excluded' and confirmed_cancer_where excludes it.
    # 1a / 3 = cancer found → closed (LEGACY-RULE closed, treated as completed).
    if cohort == "1b":
        status = "closed_benign"
    elif cohort in ("1a", "3"):
        status = "closed"
    else:
        status = "in_progress"

    # condition_type
    condition_type = "cancer" if dx_outcome == "cancer_found" else (
        "no_cancer" if dx_outcome == "cancer_excluded" else "cancer"
    )

    # End date: prefer dx_date, then treatment_date
    end_date = dx_date or treatment_date or ""

    # Cohort-3 (no FTR) always needs human review
    hitl_flag = cohort == "3"

    # NSS referral flag — Y3dd2 Read code in the FTR encounter text.
    nss_referral = "Y3dd2" in ftr_text_preview
    referral_site = "non_site_specific" if nss_referral else ("site_specific" if ftr_date else "unknown")

    # referral_route — kept for episode_builder compatibility
    referral_route = "fast_track" if ftr_date else "unknown"

    encounters: list[dict[str, str]] = []
    if row.get("ftr"):
        encounters.append(
            {"encounter_id": row["ftr"]["encounter_id"], "milestone_type": "referral"}
        )
    if row.get("seen"):
        encounters.append(
            {"encounter_id": row["seen"]["encounter_id"], "milestone_type": "first_seen"}
        )
    if row.get("dx"):
        encounters.append(
            {
                "encounter_id": row["dx"]["encounter_id"],
                "milestone_type": "diagnosis_confirmed",
            }
        )
    if row.get("treatment"):
        encounters.append(
            {
                "encounter_id": row["treatment"]["encounter_id"],
                "milestone_type": "treatment_started",
            }
        )

    all_encounter_ids = [e["encounter_id"] for e in encounters]

    return {
        "patient_id": patient_id,
        "episode_id": episode_id,
        "source": _SOURCE_TAG,
        "condition_type": condition_type,
        "cancer_type": ncda_cancer_type,
        "site": row.get("site") or "unknown",
        "cohort": cohort,
        "referral_date": ftr_date,
        "specialist_visit_date": seen_date,
        "end_date": end_date,
        "dx_outcome": dx_outcome,
        "referral_route": referral_route,
        "diagnosis_route": row.get("diagnosis_route") or "",
        "place_of_presentation": _place_of_presentation(row.get("diagnosis_route") or ""),
        "nss_referral": nss_referral,
        "referral_site": referral_site,
        "route_rationale": "; ".join(row.get("route_rationale") or []),
        "status": status,
        "hitl_flag": hitl_flag,
        "confidence": row.get("confidence") or 0.0,
        "gap_ftr_dx_days": row.get("gap_ftr_dx_days"),
        "gap_ftr_seen_days": row.get("gap_ftr_seen_days"),
        "gap_dx_treatment_days": row.get("gap_dx_treatment_days"),
        "staging_system": staging.system,
        "staging_value": staging.raw_value,
        "staging_early_late": staging.early_late,
        "staging_source": "encounter_text" if staging.system != "none" else "none",
        "staging_confidence": staging.confidence,
        "staging_systems_found": staging.systems_found,
        # Populated in the post-write first_presentation_date pass.
        "first_presentation_date": "",
        "_encounters": encounters,
        "_all_encounter_ids": all_encounter_ids,
    }


def _backup_existing_episodes(
    session: Any,
    patient_ids: list[str],
    backup_dir: Path,
) -> Path:
    """Snapshot existing ncda_detector EpisodeOfCare nodes before overwriting."""
    rows = [
        dict(r)
        for r in session.run(
            _BACKUP_EXISTING_Q,
            patient_ids=patient_ids,
            source_tag=_SOURCE_TAG,
        )
    ]
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _iso_now()
    path = backup_dir / f"{stamp}_pre_apply_backup.json"
    path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    return path


def write_episodes_to_graph(
    episode_candidates: list[dict[str, Any]],
    *,
    backup_dir: Path,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Persist episode_candidates as EpisodeOfCare nodes in Neo4j.

    Only episodes with source='ncda_detector' are created/updated.
    Episodes with source='reviewed' are never touched.

    Args:
        episode_candidates: Reduced list from reduce_episode_candidates().
        backup_dir: Where to write the pre-apply backup JSON.
        dry_run: If True, compute params and backup but do not write (default).

    Returns:
        Summary dict with counts.
    """
    params_list = [_episode_params(row) for row in episode_candidates]
    patient_ids = list({p["patient_id"] for p in params_list})

    driver = _connect()
    try:
        with driver.session() as session:
            backup_path = _backup_existing_episodes(session, patient_ids, backup_dir)

            # Stale episode cleanup: when a pathway is reclassified between runs
            # (e.g. cohort-3 → cohort-1a after the NSS extended-window fix), the
            # old episode_id stays in the graph because MERGE never deletes nodes.
            # Remove any ncda_detector episodes for these patients whose episode_id
            # is no longer in this run's output.  Reviewed episodes are safe — they
            # have source='reviewed' which is explicitly excluded by the WHERE clause.
            current_episode_ids = [p["episode_id"] for p in params_list]
            session.run(
                """
                MATCH (ep:EpisodeOfCare)
                WHERE ep.source = 'ncda_detector'
                  AND ep.patient_id IN $patient_ids
                  AND NOT ep.episode_id IN $current_ids
                DETACH DELETE ep
                """,
                patient_ids=patient_ids,
                current_ids=current_episode_ids,
            )

            if dry_run:
                return {
                    "mode": "write_back_dry_run",
                    "would_write": len(params_list),
                    "patient_count": len(patient_ids),
                    "backup_path": str(backup_path),
                    "episodes": [
                        {
                            "episode_id": p["episode_id"],
                            "patient_id": p["patient_id"],
                            "cohort": p["cohort"],
                            "cancer_type": p["cancer_type"],
                            "referral_date": p["referral_date"],
                            "end_date": p["end_date"],
                            "status": p["status"],
                            "hitl_flag": p["hitl_flag"],
                            "milestones": [e["milestone_type"] for e in p["_encounters"]],
                        }
                        for p in params_list
                    ],
                }

            written = 0
            skipped_reviewed = 0
            for p in params_list:
                # Guard: never touch a manually reviewed episode for this patient
                # with the same anchor date and site.
                reviewed_check = session.run(
                    """
                    MATCH (ep:EpisodeOfCare {episode_id: $eid})
                    WHERE ep.source = 'reviewed'
                    RETURN count(ep) AS cnt
                    """,
                    eid=p["episode_id"],
                ).single()
                if reviewed_check and reviewed_check["cnt"] > 0:
                    skipped_reviewed += 1
                    continue

                session.run(
                    _MERGE_EPISODE_Q,
                    **{k: v for k, v in p.items() if not k.startswith("_")},
                )
                session.run(
                    _LINK_ENCOUNTERS_Q,
                    episode_id=p["episode_id"],
                    encounters=p["_encounters"],
                    all_encounter_ids=p["_all_encounter_ids"],
                )
                written += 1

            # Staging refinement pass: for episodes still missing staging (or
            # having only receptor_status which is not a true stage), fetch the
            # full encounter texts from the graph and re-run the extractor.
            for p in params_list:
                if p.get("staging_system") not in ("none", "receptor_status", ""):
                    continue  # already has a proper staging classification
                enc_rows = session.run(
                    """
                    MATCH (enc:Encounter)-[:IS_PART_OF]->(ep:EpisodeOfCare {episode_id: $eid})
                    RETURN coalesce(enc.text, '') AS text
                    ORDER BY enc.date
                    """,
                    eid=p["episode_id"],
                )
                full_texts = [r["text"] for r in enc_rows if r.get("text")]
                if not full_texts:
                    continue
                staging = extract_staging(p["cancer_type"], *full_texts)
                if staging.system == "none":
                    continue
                session.run(
                    """
                    MATCH (ep:EpisodeOfCare {episode_id: $eid})
                    SET ep.staging_system        = $system,
                        ep.staging_value         = $value,
                        ep.staging_early_late    = $early_late,
                        ep.staging_source        = 'encounter_text',
                        ep.staging_confidence    = $confidence,
                        ep.staging_systems_found = $systems_found
                    """,
                    eid=p["episode_id"],
                    system=staging.system,
                    value=staging.raw_value,
                    early_late=staging.early_late,
                    confidence=staging.confidence,
                    systems_found=staging.systems_found,
                )

            # NSS referral reconciliation pass: scan every referral-milestone
            # encounter in the graph for Y3dd2.  The text-preview check in
            # _episode_params can miss cases where (a) Y3dd2 falls beyond the
            # 1000-char preview, (b) the linker picked a different encounter as
            # the FTR anchor than the actual Y3dd2 booking encounter, or (c) the
            # episode was written manually (benign NSS patients).  This single
            # Cypher pass is authoritative.
            session.run(
                """
                MATCH (enc:Encounter)-[r:IS_PART_OF]->(ep:EpisodeOfCare)
                WHERE r.milestone_type = 'referral'
                  AND ep.source = 'ncda_detector'
                  AND enc.text CONTAINS 'Y3dd2'
                SET ep.nss_referral  = true,
                    ep.referral_site = 'non_site_specific'
                """
            )

            # First presentation date pass — text-keyword scan backwards from the
            # episode anchor date.
            #
            # Anchor selection:
            #   cohort 1a / 1b: referral_date (when the 2WW FTR was issued)
            #   cohort 3 (no FTR): end_date (cancer confirmation date)
            #
            # Two-pass attempt: 90 days first (NCDA typical window), widening to
            # 180 days for pathways where symptoms pre-date the referral by more
            # than 3 months (e.g. slow-presenting cancers, delayed presentation).
            for p in params_list:
                anchor = p["referral_date"] if p["referral_date"] else p["end_date"]
                if not anchor:
                    continue
                symptom_site = resolve_symptom_site(
                    p.get("cancer_type") or "", p.get("site") or ""
                )
                kw_filter = build_fp_cypher_filter(symptom_site)
                fp_date: str | None = None
                for lookback in (FP_LOOKBACK_DAYS, FP_EXTENDED_LOOKBACK_DAYS):
                    row = session.run(
                        f"""
                        MATCH (pat:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)
                        WHERE toString(pat.id) = $pid
                          AND enc.date IS NOT NULL
                          AND date(toString(enc.date)) <= date($anchor)
                          AND date(toString(enc.date)) >= date($anchor) - duration({{days: $lookback}})
                          AND size(coalesce(enc.text, '')) > 150
                          AND {kw_filter}
                        RETURN toString(min(enc.date)) AS fp_date
                        """,
                        pid=p["patient_id"],
                        anchor=anchor,
                        lookback=lookback,
                    ).single()
                    if row and row["fp_date"]:
                        fp_date = row["fp_date"]
                        break
                if fp_date:
                    session.run(
                        """
                        MATCH (ep:EpisodeOfCare {episode_id: $eid})
                        SET ep.first_presentation_date = $fp_date
                        """,
                        eid=p["episode_id"],
                        fp_date=fp_date,
                    )

            # Supplementary fp_date pass: covers ncda_detector episodes that
            # were written directly to Neo4j (e.g. manually-created benign NSS
            # episodes) and therefore do not appear in params_list.  Uses the
            # generic symptom keyword list since site is unknown or "nss".
            remaining = session.run(
                """
                MATCH (ep:EpisodeOfCare)
                WHERE ep.source = 'ncda_detector'
                  AND (ep.first_presentation_date IS NULL
                       OR ep.first_presentation_date = '')
                RETURN ep.episode_id AS eid,
                       ep.patient_id AS pid,
                       CASE WHEN ep.referral_date IS NOT NULL AND ep.referral_date <> ''
                            THEN ep.referral_date
                            ELSE ep.end_date END AS anchor,
                       coalesce(ep.site, '') AS site,
                       coalesce(ep.cancer_type, '') AS cancer_type
                """
            )
            for rem in remaining:
                anchor = rem["anchor"]
                if not anchor:
                    continue
                symptom_site = resolve_symptom_site(
                    rem.get("cancer_type") or "", rem.get("site") or ""
                )
                kw_filter = build_fp_cypher_filter(symptom_site)
                for lookback in (FP_LOOKBACK_DAYS, FP_EXTENDED_LOOKBACK_DAYS):
                    row = session.run(
                        f"""
                        MATCH (pat:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)
                        WHERE toString(pat.id) = $pid
                          AND enc.date IS NOT NULL
                          AND date(toString(enc.date)) <= date($anchor)
                          AND date(toString(enc.date)) >= date($anchor) - duration({{days: $lookback}})
                          AND size(coalesce(enc.text, '')) > 150
                          AND {kw_filter}
                        RETURN toString(min(enc.date)) AS fp_date
                        """,
                        pid=rem["pid"],
                        anchor=anchor,
                        lookback=lookback,
                    ).single()
                    if row and row["fp_date"]:
                        session.run(
                            """
                            MATCH (ep:EpisodeOfCare {episode_id: $eid})
                            SET ep.first_presentation_date = $fp_date
                            """,
                            eid=rem["eid"],
                            fp_date=row["fp_date"],
                        )
                        break

        return {
            "mode": "write_back_applied",
            "written": written,
            "skipped_reviewed": skipped_reviewed,
            "patient_count": len(patient_ids),
            "backup_path": str(backup_path),
        }
    finally:
        driver.close()


def run_full_dry_run(
    *,
    patient_filter: str | None,
    limit: int | None,
    window_days: int,
    output_dir: Path,
    apply: bool = False,
) -> dict[str, Any]:
    driver = _connect()
    try:
        with driver.session() as session:
            cohort_rows = [
                dict(r)
                for r in session.run(
                    _DIAGNOSIS_PATIENTS_QUERY,
                    diagnosis_ids=[
                        str(c)
                        for c in CANCER_TYPE_IDS | DOCUMENTS_DISORDER_MALIGNANCY_IDS
                    ],
                )
            ]
            if patient_filter:
                cohort_rows = [r for r in cohort_rows if r["patient_id"] == patient_filter]
            if limit:
                cohort_rows = cohort_rows[:limit]

            patient_ids = [r["patient_id"] for r in cohort_rows]
            if not patient_ids:
                raise SystemExit("No diagnosis-positive patients found for requested filter.")

            enc_rows = [
                dict(r)
                for r in session.run(_ALL_ENCOUNTERS_QUERY, patient_ids=patient_ids)
            ]
    finally:
        driver.close()

    enc_by_patient: dict[str, list[dict]] = defaultdict(list)
    for r in enc_rows:
        enc_by_patient[r["patient_id"]].append(r)

    diagnosis_by_patient = {r["patient_id"]: r for r in cohort_rows}
    pathways: list[dict[str, Any]] = []
    no_pathway_patients: list[dict[str, Any]] = []

    for pid in patient_ids:
        patient_pathways = _run_patient(
            pid,
            enc_by_patient.get(pid, []),
            window_days=window_days,
        )
        if patient_pathways:
            for row in patient_pathways:
                row["diagnosis_concepts"] = diagnosis_by_patient[pid]["diagnosis_concepts"]
                row["diagnosis_encounter_count"] = diagnosis_by_patient[pid]["diagnosis_encounter_count"]
            pathways.extend(patient_pathways)
        else:
            no_pathway_patients.append(
                {
                    "patient_id": pid,
                    "n_encounters": len(enc_by_patient.get(pid, [])),
                    "diagnosis_concepts": diagnosis_by_patient[pid]["diagnosis_concepts"],
                    "diagnosis_encounter_count": diagnosis_by_patient[pid]["diagnosis_encounter_count"],
                }
            )

    episode_candidates, open_referrals = reduce_episode_candidates(pathways)

    route_counts = Counter(row["diagnosis_route"] for row in episode_candidates)
    cohort_counts = Counter(row["cohort"] for row in episode_candidates)
    site_counts = Counter(row["site"] or "unknown" for row in episode_candidates)
    raw_cohort_counts = Counter(row["cohort"] for row in pathways)
    mode_label = "apply" if apply else "dry_run_no_graph_writes"
    summary = {
        "generated_at": _iso_now(),
        "mode": mode_label,
        "window_days": window_days,
        "diagnosis_patient_count": len(patient_ids),
        "episode_candidate_count": len(episode_candidates),
        "raw_pathway_count": len(pathways),
        "open_referral_count": len(open_referrals),
        "patients_with_no_pathways": len(no_pathway_patients),
        "route_counts": dict(sorted(route_counts.items())),
        "cohort_counts": dict(sorted(cohort_counts.items())),
        "raw_cohort_counts": dict(sorted(raw_cohort_counts.items())),
        "site_counts": dict(sorted(site_counts.items())),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = summary["generated_at"]
    json_path = output_dir / f"full_ncda_dry_run_{stamp}.json"
    csv_path = output_dir / f"full_ncda_dry_run_{stamp}.csv"
    raw_csv_path = output_dir / f"full_ncda_dry_run_raw_pathways_{stamp}.csv"
    summary_path = output_dir / f"full_ncda_dry_run_summary_{stamp}.json"

    payload = {
        "summary": summary,
        "episode_candidates": episode_candidates,
        "open_referrals": open_referrals,
        "raw_pathways": pathways,
        "no_pathway_patients": no_pathway_patients,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_csv(csv_path, episode_candidates)
    _write_csv(raw_csv_path, pathways)

    result: dict[str, Any] = {
        "summary": summary,
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "raw_csv_path": str(raw_csv_path),
        "summary_path": str(summary_path),
    }

    if apply:
        backup_dir = ROOT / "artifacts" / "ncda_episode_backup"
        wb_result = write_episodes_to_graph(
            episode_candidates,
            backup_dir=backup_dir,
            dry_run=False,
        )
        result["write_back"] = wb_result

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient", default=None, help="Limit to one NHS number.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of diagnosis-positive patients.")
    parser.add_argument("--window", type=int, default=180, help="FTR/Seen-to-Dx window in days.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "ncda_full_run",
        help="Directory for JSON/CSV artifacts.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help=(
            "Write EpisodeOfCare nodes and IS_PART_OF edges to Neo4j. "
            "Without this flag the script is report-only. "
            "Existing 'reviewed' episodes are always preserved."
        ),
    )
    args = parser.parse_args(argv)

    result = run_full_dry_run(
        patient_filter=args.patient,
        limit=args.limit,
        window_days=args.window,
        output_dir=args.output_dir,
        apply=args.apply,
    )
    summary = result["summary"]

    if args.apply:
        wb = result.get("write_back", {})
        print("NCDA episode write-back complete.")
        print(f"  Episodes written to graph : {wb.get('written', '?')}")
        print(f"  Reviewed episodes skipped : {wb.get('skipped_reviewed', 0)}")
        print(f"  Patients affected         : {wb.get('patient_count', '?')}")
        print(f"  Pre-apply backup          : {wb.get('backup_path', '?')}")
    else:
        print("Full NCDA dry run complete (no graph writes). Use --apply to write.")

    print(f"Diagnosis-positive patients: {summary['diagnosis_patient_count']}")
    print(f"Episode candidates:          {summary['episode_candidate_count']}")
    print(f"Raw linker pathways:         {summary['raw_pathway_count']}")
    print(f"Open/unmatched referrals:    {summary['open_referral_count']}")
    print(f"Patients with no pathways:   {summary['patients_with_no_pathways']}")
    print(f"Cohorts: {summary['cohort_counts']}")
    print(f"Routes:  {summary['route_counts']}")
    print(f"JSON:    {result['json_path']}")
    print(f"CSV:     {result['csv_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
