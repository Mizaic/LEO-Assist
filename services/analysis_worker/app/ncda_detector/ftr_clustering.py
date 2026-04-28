"""FTR clustering: collapse same-referral duplicates before pair generation.

When a Fast Track Referral is entered into the EMR it often appears across
several encounters in quick succession:
  - GP consultation note (2WW decision made)
  - Admin booking record (referral sent)
  - Electronic referral acknowledgement / letter stored

These all mention "Fast Track Referral" or equivalent and can span the same
day or up to 3 calendar days.  Emitting one RoleScore per encounter creates a
false many-to-many FTR explosion in the pair generator.

This module collapses co-incident FTR candidates into a single representative
encounter (the one with the highest FTR role probability) before the pair
generator runs.

Two FTR encounters belong to the same cluster when:
  1. Their dates are within CLUSTER_WINDOW_DAYS of each other (transitively
     chained: A clusters with B and B clusters with C => A,B,C one cluster).
  2. They share a compatible cancer-site signal: either both unknown, or both
     resolve to the same coarse site bucket (e.g. "breast" / "prostate").
     Encounters with conflicting site signals are kept as separate clusters
     and propagate as distinct FTR candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from services.analysis_worker.app.ncda_detector.pair_generator import RoleScore

CLUSTER_WINDOW_DAYS: int = 3

# Coarse site buckets: map of site-name -> list of text tokens that imply it.
_SITE_SIGNALS: dict[str, tuple[str, ...]] = {
    "prostate": (
        "prostate", "urolog", "psa", "urology",
        "bladder", "haematuria",
    ),
    "breast": (
        "breast", "mammogram", "mammography", "mastectomy",
    ),
    "lung": (
        "lung", "chest x-ray", "cxr", "respiratory", "thoracic",
    ),
    "colorectal": (
        "colorectal", "bowel", "rectal", "rectum", "colon",
        "colonoscopy", "flexible sigmoidoscopy",
    ),
    "skin": (
        "melanoma", "skin", "dermoscopy", "dermatol", "nevus",
    ),
    "haematology": (
        "lymphoma", "haematol", "lymph node", "leukaemia", "leukemia",
        "myeloma",
    ),
    "gynaecology": (
        "cervic", "uterus", "uterine", "ovarian", "endometrial",
        "gynaecol", "gynecol",
    ),
    "upper_gi": (
        "oesophag", "esophag", "gastric", "stomach", "upper gi",
    ),
    "head_neck": (
        "head and neck", "larynx", "pharynx", "thyroid",
    ),
    "urology_other": (
        "testicular", "testis", "renal", "kidney",
    ),
}


def site_signal(text: str) -> str | None:
    """Return the coarse site bucket for a piece of encounter text, or None."""
    lower = (text or "").lower()
    for site, tokens in _SITE_SIGNALS.items():
        if any(tok in lower for tok in tokens):
            return site
    return None


def _to_date(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _sites_compatible(a: str | None, b: str | None) -> bool:
    """Two site signals are compatible when either is unknown or they match."""
    if a is None or b is None:
        return True
    return a == b


@dataclass
class FtrCluster:
    """One logical Fast Track Referral event with its member encounters."""

    representative: RoleScore
    members: list[RoleScore]
    site: str | None


def cluster_ftrs(
    scores: Sequence[RoleScore],
    *,
    ftr_threshold: float = 0.5,
    window_days: int = CLUSTER_WINDOW_DAYS,
) -> list[RoleScore]:
    """Return scores with FTR candidates collapsed to one per logical referral.

    Non-FTR scores pass through unchanged.  FTR candidates within
    ``window_days`` of each other that share a compatible cancer-site signal
    are merged; the member with the highest FTR probability becomes the
    representative.
    """
    non_ftrs = [s for s in scores if s.role_probabilities.get("ftr", 0.0) < ftr_threshold]
    ftrs = [s for s in scores if s.role_probabilities.get("ftr", 0.0) >= ftr_threshold]

    if not ftrs:
        return list(scores)

    clusters = _build_clusters(ftrs, window_days=window_days)
    representatives = [c.representative for c in clusters]
    return non_ftrs + representatives


def build_ftr_clusters(
    scores: Sequence[RoleScore],
    *,
    ftr_threshold: float = 0.5,
    window_days: int = CLUSTER_WINDOW_DAYS,
) -> list[FtrCluster]:
    """Return the raw cluster objects (useful for diagnostics / audit)."""
    ftrs = [s for s in scores if s.role_probabilities.get("ftr", 0.0) >= ftr_threshold]
    return _build_clusters(ftrs, window_days=window_days)


def _build_clusters(
    ftrs: list[RoleScore],
    window_days: int,
) -> list[FtrCluster]:
    """Single-linkage clustering on date proximity + site compatibility."""
    if not ftrs:
        return []

    sorted_ftrs = sorted(ftrs, key=lambda s: s.encounter_date or "")
    assigned: list[int | None] = [None] * len(sorted_ftrs)
    cluster_sites: list[str | None] = []
    clusters: list[list[int]] = []

    for i, score in enumerate(sorted_ftrs):
        d_i = _to_date(score.encounter_date)
        site_i = site_signal(score.text or "")

        best_cluster: int | None = None
        for cid in range(len(clusters) - 1, -1, -1):
            last_idx = clusters[cid][-1]
            last_score = sorted_ftrs[last_idx]
            d_last = _to_date(last_score.encounter_date)
            if d_i and d_last and (d_i - d_last).days > window_days:
                break  # scores are sorted; no earlier cluster can match either
            if not _sites_compatible(site_i, cluster_sites[cid]):
                continue
            best_cluster = cid
            break

        if best_cluster is not None:
            clusters[best_cluster].append(i)
            # Widen the cluster's site if we now know it
            if cluster_sites[best_cluster] is None:
                cluster_sites[best_cluster] = site_i
            assigned[i] = best_cluster
        else:
            assigned[i] = len(clusters)
            clusters.append([i])
            cluster_sites.append(site_i)

    result: list[FtrCluster] = []
    for cid, member_indices in enumerate(clusters):
        members = [sorted_ftrs[j] for j in member_indices]
        best = max(members, key=lambda s: s.role_probabilities.get("ftr", 0.0))
        result.append(FtrCluster(representative=best, members=members, site=cluster_sites[cid]))
    return result
