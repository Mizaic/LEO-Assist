"""Evidence-wins duplicate-episode resolution.

Design controls: DI-LEO-AI-137, DO-LEO-AI-133, R-LEO-AI-097, VT-LEO-AI-138.

Two-stage algorithm:

1. ``cluster_episodes`` -- group episodes on the same patient whose
   referral_date (or end_date when referral_date is NULL) fall within
   ``SAME_EPISODE_DAYS``. NSS and floating episodes are included -- they
   were previously skipped by the legacy same-site merger, which is how
   a single clinical pathway got split into multiple EpisodeOfCare
   nodes.

2. ``pick_evidence_winner`` -- within a cluster, choose the primary
   episode by re-extracting the dominant cancer type from the
   ``diagnosis_confirmed`` encounter text via ``SPECIALTY_MARKERS``,
   and preferring the episode whose persisted ``cancer_type`` matches
   that evidence. Ties are broken by (a) presence of a
   ``treatment_started`` milestone, (b) earliest referral_date (nulls
   last), and (c) episode_id string order for determinism.

The caller is responsible for actually moving IS_PART_OF edges (via
``MOVE_LINKS_Q``) and marking duplicates with ``MARK_MERGED_Q``. This
module is pure logic -- no Neo4j driver dependencies -- so it is fully
unit-testable.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable

from libs.clinical_scoping.specialty_markers import SPECIALTY_MARKERS

logger = logging.getLogger(__name__)


@dataclass
class EpisodeRecord:
    """Minimal episode description consumed by the resolver."""

    episode_id: str
    cancer_type: str
    referral_date: date | None
    end_date: date | None
    status: str
    diagnosis_texts: list[str] = field(default_factory=list)
    treatment_count: int = 0
    match_method: str = "strict_site"


@dataclass
class MergeDecision:
    """Result of resolving one cluster."""

    primary_id: str
    duplicates: list[str]
    evidence_cancer_type: str
    reasoning: str


def _parse_iso(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _anchor_date(record: EpisodeRecord) -> date | None:
    """Return the anchor date used for clustering. Prefer referral_date;
    fall back to end_date so floating diagnosis-only episodes still
    cluster with a matched referral episode whose referral_date is in a
    plausible window."""
    return record.referral_date or record.end_date


def cluster_episodes(
    episodes: Iterable[EpisodeRecord],
    same_episode_days: int,
) -> list[list[EpisodeRecord]]:
    """Group episodes whose anchor dates fall within ``same_episode_days``.

    Episodes without any anchor date are each placed in a singleton
    cluster -- the resolver cannot safely infer whether they belong to
    another cluster without additional evidence. Non-singleton clusters
    drive the evidence-wins merge; singletons are returned as-is so the
    caller can skip them.
    """
    records = list(episodes)
    dated = [r for r in records if _anchor_date(r) is not None]
    undated = [r for r in records if _anchor_date(r) is None]

    dated.sort(key=lambda r: (_anchor_date(r), r.episode_id))
    clusters: list[list[EpisodeRecord]] = []
    current: list[EpisodeRecord] = []
    cluster_min: date | None = None
    for record in dated:
        anchor = _anchor_date(record)
        if anchor is None:
            continue
        if not current or cluster_min is None:
            current = [record]
            cluster_min = anchor
            continue
        if (anchor - cluster_min) <= timedelta(days=same_episode_days):
            current.append(record)
            continue
        clusters.append(current)
        current = [record]
        cluster_min = anchor
    if current:
        clusters.append(current)
    clusters.extend([[r] for r in undated])
    return clusters


def evidence_cancer_type(texts: Iterable[str]) -> str:
    """Infer the dominant cancer type from diagnosis encounter text.

    Returns ``'unknown'`` when no specialty marker matches, or when the
    top match is ambiguous (two or more markers tied on hit count).
    Ambiguity is deliberately surfaced so the caller can skip the
    cluster rather than collapse two genuine primaries.
    """
    counts: Counter[str] = Counter()
    for text in texts:
        if not text:
            continue
        for site, pattern in SPECIALTY_MARKERS.items():
            if site == "non_site_specific":
                continue
            if pattern.search(text):
                counts[site] += 1
    if not counts:
        return "unknown"
    most = counts.most_common()
    if len(most) >= 2 and most[0][1] == most[1][1]:
        return "unknown"
    return most[0][0]


def _rank_key(record: EpisodeRecord, evidence_type: str) -> tuple:
    """Sort key -- lower is better. Prefer (a) match with evidence,
    (b) has treatment, (c) earliest referral, (d) episode_id order."""
    matches_evidence = 0 if record.cancer_type == evidence_type else 1
    has_treatment = 0 if record.treatment_count > 0 else 1
    ref = record.referral_date or date.max
    return (matches_evidence, has_treatment, ref, record.episode_id)


def pick_evidence_winner(cluster: list[EpisodeRecord]) -> MergeDecision | None:
    """Return the merge decision for a cluster, or None if no merge.

    Clusters of size 1 are skipped. Clusters are also skipped when:

    * The evidence cancer_type is ``'unknown'`` AND no episode has a
      recognised cancer_type -- there is no signal to pick a primary
      and collapsing would risk merging genuine multi-primary cases.

    * The cluster contains two or more distinct, non-NSS cancer_types
      (e.g. ``breast`` + ``melanoma``) AND the diagnosis text does not
      uniquely corroborate one of them. Per DI-LEO-AI-137 acceptance
      criterion ("When no deterministic winner exists, the merge is
      skipped; logger.warning records the patient_id and cluster
      members for human review; no destructive write occurs"), we must
      not fall back to alphabetical or any other arbitrary ordering --
      a same-day breast and skin 2WW pair are two real pathways, not a
      duplicate. (R-LEO-AI-097 covers this safety branch.)
    """
    if len(cluster) < 2:
        return None
    texts: list[str] = []
    for record in cluster:
        texts.extend(record.diagnosis_texts or [])
    evidence_type = evidence_cancer_type(texts)
    known_types = {
        r.cancer_type
        for r in cluster
        if r.cancer_type and r.cancer_type not in ("unknown", "non_site_specific")
    }
    if evidence_type == "unknown" and not known_types:
        logger.debug(
            "Cluster of %d episodes has no resolvable cancer type; skipping merge",
            len(cluster),
        )
        return None
    # DI-LEO-AI-137 / R-LEO-AI-097 -- multi-distinct-type guard.
    # If two or more episodes carry distinct, recognised cancer types,
    # only proceed when the diagnosis text uniquely names one of them.
    # Otherwise the cluster is preserved for human review.
    if len(known_types) >= 2 and (
        evidence_type == "unknown" or evidence_type not in known_types
    ):
        logger.warning(
            "Skipping merge: cluster has %d distinct known cancer_types %s "
            "with no deterministic text evidence (evidence_type=%r). "
            "Episode IDs: %s",
            len(known_types),
            sorted(known_types),
            evidence_type,
            [r.episode_id for r in cluster],
        )
        return None
    if evidence_type == "unknown" and known_types:
        # Single known type and no text evidence -- safe to keep the
        # NSS/unknown shadows merging into the only known primary.
        evidence_type = next(iter(known_types))
    ranked = sorted(cluster, key=lambda r: _rank_key(r, evidence_type))
    primary = ranked[0]
    duplicates = [r.episode_id for r in ranked[1:]]
    reasoning = _merge_reasoning(primary, duplicates, evidence_type, len(cluster))
    return MergeDecision(
        primary_id=primary.episode_id,
        duplicates=duplicates,
        evidence_cancer_type=evidence_type,
        reasoning=reasoning,
    )


def _merge_reasoning(
    primary: EpisodeRecord,
    duplicates: list[str],
    evidence_type: str,
    cluster_size: int,
) -> str:
    """Compose the audit-trail string persisted on merged episodes."""
    ref = (
        primary.referral_date.isoformat() if primary.referral_date else "(no referral)"
    )
    return (
        "Evidence-wins merge (DI-LEO-AI-137). "
        f"Cluster size {cluster_size}. "
        f"Evidence cancer_type='{evidence_type}'. "
        f"Primary={primary.episode_id} ref={ref} "
        f"treatments={primary.treatment_count}. "
        f"Duplicates merged: {', '.join(duplicates)}."
    )
