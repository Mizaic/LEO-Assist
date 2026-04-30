"""Reviewed-guard and anchor-stability helpers for the NCDA detector.

Two transforms are applied to ``episode_candidates`` before they are written
to the JSON / CSV / graph:

1. **Reviewed-guard (wide)** -- if a patient already has a ``reviewed``
   ``EpisodeOfCare`` whose canonical site overlaps a candidate's window,
   suppress the candidate (and record why).  The detector is not allowed to
   re-emit episodes that a human curator has already triaged.

2. **Anchor stability** -- if an existing ``ncda_detector`` episode for the
   same patient/site sits within +-N days of the candidate's anchor, reuse
   that ``episode_id`` instead of computing a fresh deterministic hash.
   This stops 1-day FTR-collapse drift from forcing DELETE+RECREATE churn
   on already-stable episodes.

Both transforms are pure: they do not write to the graph.  Callers can run
them in dry-run mode (the suppressed list is reported in the JSON output)
or in apply mode (where suppressed candidates simply are not MERGE'd).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from libs.oncology.cancer_types import cancer_type_to_detector_site


# Window inside which a reviewed episode is considered to "cover" a
# detector candidate for the same canonical site.  +-180 days from any
# date the reviewed episode carries (referral_date or end_date).
REVIEWED_GUARD_WINDOW_DAYS = 180

# Window for swapping an existing ncda_detector episode_id when the new
# candidate's anchor has drifted.  Tight: only treat <= 14 day drifts as
# "the same logical episode".
ANCHOR_REUSE_WINDOW_DAYS = 14


def _to_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _compatible_site(detector_site: str | None, reviewed_site_key: str) -> bool:
    """True when a detector ``site`` overlaps a reviewed episode's site key.

    Both inputs are detector-site keys (e.g. ``"breast"``, ``"urological"``).
    Reviewed episodes whose cancer_type maps to ``"unknown"`` (Other /
    Unknown Primary / No Information) match anything: a curator marked the
    pathway as benign or completed without a specific site, and a detector
    candidate that picks a specific site for the same patient/window is
    almost certainly the same clinical reality the curator already saw.
    """
    if not detector_site or not reviewed_site_key:
        return False
    if reviewed_site_key == "unknown":
        return True
    if detector_site == "unknown":
        # A cohort-3 unknown-site candidate against a reviewed specific site
        # for the same patient is very likely a metastasis recap; treat as
        # covered.
        return True
    return detector_site == reviewed_site_key


def _episodes_overlap(
    candidate_anchor: str | None,
    candidate_end: str | None,
    reviewed_ref: str | None,
    reviewed_end: str | None,
    *,
    window_days: int,
) -> bool:
    """True when the candidate window touches the reviewed window +- buffer."""
    cand_dates = [d for d in (_to_date(candidate_anchor), _to_date(candidate_end)) if d]
    rev_dates = [d for d in (_to_date(reviewed_ref), _to_date(reviewed_end)) if d]
    if not cand_dates or not rev_dates:
        # Reviewed episode has no usable dates -> trust same-site as cover.
        return True
    cand_lo, cand_hi = min(cand_dates), max(cand_dates)
    rev_lo, rev_hi = min(rev_dates), max(rev_dates)
    rev_lo = rev_lo - timedelta(days=window_days)
    rev_hi = rev_hi + timedelta(days=window_days)
    return not (cand_hi < rev_lo or cand_lo > rev_hi)


def apply_reviewed_guard(
    candidates: list[dict[str, Any]],
    existing_episodes: Iterable[dict[str, Any]],
    *,
    window_days: int = REVIEWED_GUARD_WINDOW_DAYS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop candidates that overlap a reviewed episode for the same patient.

    Args:
        candidates: ``episode_candidates`` from ``reduce_episode_candidates``.
        existing_episodes: Iterable of ``EpisodeOfCare`` rows fetched from
            Neo4j for the same patient cohort.  Each row must contain at
            least ``patient_id``, ``source``, ``cancer_type``,
            ``referral_date``, ``end_date``.

    Returns:
        ``(kept, suppressed)`` -- ``suppressed`` rows have a
        ``_suppressed_by`` field added describing which reviewed episode
        covered them.
    """
    reviewed_by_pid: dict[str, list[dict[str, Any]]] = {}
    for ep in existing_episodes:
        if (ep.get("source") or "").lower() == "ncda_detector":
            continue
        pid = str(ep.get("patient_id") or ep.get("pid") or "")
        if not pid:
            continue
        reviewed_by_pid.setdefault(pid, []).append(ep)

    kept: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for cand in candidates:
        pid = str(cand.get("patient_id") or "")
        cand_site = (cand.get("site") or "unknown") or "unknown"
        ftr_date = (cand.get("ftr") or {}).get("encounter_date") or ""
        dx_date = (cand.get("dx") or {}).get("encounter_date") or ""
        anchor = ftr_date or dx_date
        end = dx_date or ftr_date

        cover: dict[str, Any] | None = None
        for ep in reviewed_by_pid.get(pid, []):
            rev_site_key = cancer_type_to_detector_site(ep.get("cancer_type"))
            if not _compatible_site(cand_site, rev_site_key):
                continue
            if not _episodes_overlap(
                anchor,
                end,
                ep.get("referral_date"),
                ep.get("end_date"),
                window_days=window_days,
            ):
                continue
            cover = ep
            break

        if cover is not None:
            suppressed.append(
                {
                    **cand,
                    "_suppressed_by": {
                        "reason": "reviewed_episode_covers_window",
                        "reviewed_episode_id": cover.get("episode_id"),
                        "reviewed_cancer_type": cover.get("cancer_type"),
                        "reviewed_verdict": cover.get("review_verdict"),
                        "reviewed_referral_date": cover.get("referral_date"),
                        "reviewed_end_date": cover.get("end_date"),
                    },
                }
            )
        else:
            kept.append(cand)
    return kept, suppressed


def stabilise_anchor_eids(
    candidates: list[dict[str, Any]],
    existing_episodes: Iterable[dict[str, Any]],
    *,
    window_days: int = ANCHOR_REUSE_WINDOW_DAYS,
    eid_for_candidate=None,
) -> list[dict[str, Any]]:
    """Re-use existing ncda_detector eids when the candidate's anchor drifted.

    For each candidate we compute the deterministic eid; if it matches an
    existing detector eid for the patient -> no change.  Otherwise, if an
    existing detector episode for the same patient and SAME site has its
    referral_date / end_date within +- ``window_days`` of the candidate's
    anchor, we attach the existing eid to the candidate via ``_stable_eid``
    so the writer can re-use it instead of MERGEing a fresh node.

    Args:
        candidates: ``episode_candidates`` (already filtered by
            ``apply_reviewed_guard``).
        existing_episodes: ``EpisodeOfCare`` rows from Neo4j.
        window_days: Anchor drift tolerance.
        eid_for_candidate: Callable (patient_id, site, anchor) -> str that
            computes the deterministic eid.  Required.
    """
    if eid_for_candidate is None:
        raise ValueError("eid_for_candidate callable is required")

    detector_by_pid_site: dict[tuple[str, str], list[dict[str, Any]]] = {}
    detector_eids_by_pid: dict[str, set[str]] = {}
    for ep in existing_episodes:
        if (ep.get("source") or "").lower() != "ncda_detector":
            continue
        pid = str(ep.get("patient_id") or ep.get("pid") or "")
        if not pid:
            continue
        site = (ep.get("site") or "unknown") or "unknown"
        detector_by_pid_site.setdefault((pid, site), []).append(ep)
        detector_eids_by_pid.setdefault(pid, set()).add(ep.get("episode_id"))

    for cand in candidates:
        pid = str(cand.get("patient_id") or "")
        site = (cand.get("site") or "unknown") or "unknown"
        ftr_date = (cand.get("ftr") or {}).get("encounter_date") or ""
        dx_date = (cand.get("dx") or {}).get("encounter_date") or ""
        anchor = ftr_date or dx_date
        if not anchor:
            continue

        new_eid = eid_for_candidate(pid, site, anchor)
        if new_eid in detector_eids_by_pid.get(pid, set()):
            continue  # exact match; no swap needed

        anchor_d = _to_date(anchor)
        if anchor_d is None:
            continue
        for ep in detector_by_pid_site.get((pid, site), []):
            ep_dates = [
                d for d in (_to_date(ep.get("referral_date")), _to_date(ep.get("end_date")))
                if d is not None
            ]
            if not ep_dates:
                continue
            drift = min(abs((d - anchor_d).days) for d in ep_dates)
            if drift <= window_days:
                cand["_stable_eid"] = ep.get("episode_id")
                cand["_stable_eid_drift_days"] = drift
                break
    return candidates


def fetch_existing_episodes(driver, patient_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch every EpisodeOfCare for the given patient cohort.

    All date-shaped values are coerced to ISO date strings so the result is
    JSON-serialisable.
    """
    query = """
    MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE|HAS_EPISODE]->(e:EpisodeOfCare)
    WHERE coalesce(toString(p.id), toString(p.patient_id)) IN $pids
    RETURN
      coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
      e.episode_id            AS episode_id,
      coalesce(e.source,'')   AS source,
      coalesce(e.cancer_type,'') AS cancer_type,
      coalesce(e.site,'')     AS site,
      coalesce(e.cohort,'')   AS cohort,
      toString(e.referral_date) AS referral_date,
      toString(e.end_date)      AS end_date,
      coalesce(e.review_verdict,'') AS review_verdict
    """
    with driver.session() as s:
        return [dict(r) for r in s.run(query, pids=patient_ids)]


def episode_id_hash(patient_id: str, site: str, anchor_date: str) -> str:
    """Deterministic 16-char hex episode_id (mirrors detector hash)."""
    raw = f"{patient_id}|{site}|{anchor_date}|ncda"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
