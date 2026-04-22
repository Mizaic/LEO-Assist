"""Episode Detector v2 runner.

Atlas trace:
  DI: DI-8A5FCF4F
  DO: (will be created in Phase 1 once tests are recorded)

Provides ``build_episodes`` with the same signature the legacy
episode_builder exposed, so ``libs/pipeline_graph/subgraphs/episode.py``
can call either implementation behind the ``episode_pipeline`` feature
flag (see libs/feature_flags.py).

Pipeline order matches the 12-component defence-in-depth design:

    normalise -> 5 signal extractors -> 5 candidate generators
      -> evidence aggregator -> conflict resolver -> boundary detector
      -> generator-consensus voting -> coverage check -> confidence tier
      -> persist (only auto-tier) -> persist provenance
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from libs.episodes.lifecycle import (
    canonical_status_from_v2_boundary,
)
from libs.episodes.status import EpisodeStatus

from .aggregator import aggregate_evidence
from .boundary import detect_boundary
from .coverage import check_coverage
from .generators import (
    generate_diagnosis_anchored,
    generate_referral_anchored,
    generate_site_cohort_anchored,
    generate_symptom_cluster_anchored,
    generate_treatment_anchored,
)
from .normaliser import load_timeline
from .provenance import persist_provenance
from .resolver import resolve_conflicts
from .signals import (
    extract_code_signals,
    extract_pathway_signals,
    extract_result_signals,
    extract_text_signals,
    extract_treatment_signals,
)
from .types import (
    EpisodeBuildResultV2,
    EpisodeProvenance,
    ResolvedEpisode,
)
from .voting import assign_confidence_tier, vote_for_candidates

logger = logging.getLogger(__name__)


def _episode_id(patient_id: str, site_key: str, anchor_iso: str) -> str:
    raw = f"{patient_id}|{site_key.lower()}|{anchor_iso}|v2"
    return f"ep-v2-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


# Strict ordering of confidence tiers -- higher index wins when two
# rows for the same episode_id disagree.
_TIER_PRIORITY = {"review": 0, "suggest": 1, "auto": 2}


@dataclass
class _EpisodeAccumulator:
    """Merges multiple aggregated-candidate rows that resolve to the
    same episode_id into a single ResolvedEpisode + per-encounter
    provenance bundle.
    """

    episode_id: str
    site_key: str
    role_hint: str
    tier: str
    reasons: list[str]
    start_date: date | None
    end_date: date | None
    intent: str
    status: str
    consensus: list[str]
    encounter_ids: list[str] = field(default_factory=list)
    signals: list[Any] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    provenance_rows: list[tuple[str, str, float, list[Any]]] = field(
        default_factory=list
    )

    def merge(
        self,
        *,
        scoped_encounters: list[str],
        signals: list[Any],
        consensus: list[str],
        alternatives: list[str],
        tier: str,
        reasons: list[str],
        boundary_status: str,
        boundary_end: date | None,
        boundary_intent: str,
        generator: str,
        evidence_weight: float,
    ) -> None:
        existing = set(self.encounter_ids)
        for enc in scoped_encounters:
            if enc not in existing:
                self.encounter_ids.append(enc)
                existing.add(enc)
        seen_signals = {
            (s.channel, s.encounter_id, s.site_key, s.intent) for s in self.signals
        }
        for sig in signals:
            key = (sig.channel, sig.encounter_id, sig.site_key, sig.intent)
            if key in seen_signals:
                continue
            seen_signals.add(key)
            self.signals.append(sig)
        for gen in consensus:
            if gen not in self.consensus:
                self.consensus.append(gen)
        for alt in alternatives:
            if alt not in self.alternatives:
                self.alternatives.append(alt)
        # Highest-priority tier wins -- e.g. an auto vote upgrades a
        # row that the resolver originally tagged review.
        if _TIER_PRIORITY.get(tier, -1) > _TIER_PRIORITY.get(self.tier, -1):
            self.tier = tier
            self.reasons = list(reasons)
        elif tier == self.tier:
            for r in reasons:
                if r not in self.reasons:
                    self.reasons.append(r)
        # Boundary widens: pick the latest end_date, never clip back.
        if boundary_end is not None and (
            self.end_date is None or boundary_end > self.end_date
        ):
            self.end_date = boundary_end
        # Promote intent: confirmed > suspected > ruled_out collapse to
        # the most clinically significant signal observed.
        intent_priority = {"ruled_out": 0, "suspected": 1, "confirmed": 2}
        if intent_priority.get(boundary_intent, -1) > intent_priority.get(
            self.intent, -1
        ):
            self.intent = boundary_intent
            self.status = boundary_status
        # Per-encounter provenance is appended for every contributing
        # generator -- the persister deduplicates downstream.
        self.provenance_rows.append(
            (generator, "", evidence_weight, signals)
        )

    def to_resolved_episode(self) -> ResolvedEpisode:
        return ResolvedEpisode(
            episode_id=self.episode_id,
            site_key=self.site_key,
            encounter_ids=list(self.encounter_ids),
            start_date=self.start_date,
            end_date=self.end_date,
            suspected_site=self.site_key,
            role=self.role_hint,
            intent=self.intent,
            status=self.status,
            confidence_tier=self.tier,
            needs_human_review=self.tier != "auto",
            review_reasons=list(self.reasons),
            vote_count=len(self.consensus),
            supporting_signals=list(self.signals),
            alternatives_considered=list(self.alternatives),
            generator_consensus=list(self.consensus),
        )

    def provenance_records(self) -> list[EpisodeProvenance]:
        records: list[EpisodeProvenance] = []
        for enc_id in self.encounter_ids:
            enc_signals = [s for s in self.signals if s.encounter_id == enc_id]
            generators = sorted(
                {row[0] for row in self.provenance_rows}
            )
            score = max(
                (row[2] for row in self.provenance_rows), default=0.0
            )
            records.append(
                EpisodeProvenance(
                    episode_id=self.episode_id,
                    encounter_id=enc_id,
                    generator=",".join(generators),
                    score=score,
                    supporting_signals=[
                        {
                            "channel": s.channel,
                            "intent": s.intent,
                            "confidence": s.confidence,
                            "citation": s.citation,
                        }
                        for s in enc_signals
                    ],
                    alternatives_considered=[],
                )
            )
        return records


# Persist Cypher (DI-C4CEFA32, R-2AA626E7).
#
# Two SET clauses to keep curator-signed verdicts intact:
#   1. The first SET writes everything EXCEPT status / needs_human_review /
#      intent. These are detector-derived fields the curator does not
#      manage, so they refresh every run.
#   2. The second SET only fires when reviewed_at IS NULL (no curator
#      sign-off yet). Once a curator has clicked "Mark reviewed" the
#      status, intent, and review-flag fields are FROZEN so the
#      detector cannot silently flip them back on a subsequent run.
#
# Status values written here come from canonical_status_from_v2_boundary
# in libs/episodes/lifecycle.py and are guaranteed to be members of
# ENGINE_OUTPUT_STATUSES (active / review / completed / closed_benign).
_EPISODE_MERGE = """
UNWIND $episodes AS ep
MATCH (p:Patient {id: $patient_id})
MERGE (e:EpisodeOfCare {episode_id: ep.episode_id})
SET e.suspected_site = ep.suspected_site,
    e.cancer_type = coalesce(e.cancer_type, ep.suspected_site),
    e.site_key = ep.site_key,
    e.start_date = ep.start_date,
    e.end_date = ep.end_date,
    e.confidence_tier = ep.confidence_tier,
    e.review_reasons = ep.review_reasons,
    e.engine_version = 'episode-detector-v2',
    e.detector_version = 'v2',
    e.last_updated = datetime()
FOREACH (_ IN CASE WHEN e.reviewed_at IS NULL THEN [1] ELSE [] END |
    SET e.status = ep.status,
        e.intent = ep.intent,
        e.needs_human_review = ep.needs_human_review,
        e.needs_review = ep.needs_human_review,
        e.status_source = 'episode_detector_v2',
        e.status_updated_at = datetime()
)
MERGE (p)-[:HAS_EPISODE_OF_CARE]->(e)
WITH e, ep
UNWIND ep.encounter_ids AS enc_id
MATCH (enc:Encounter {id: enc_id})
MERGE (enc)-[:IS_PART_OF]->(e)
"""


async def build_episodes(
    *,
    patient_id: str,
    anchors: Any = None,  # parity arg, ignored by v2
    patient_client: Any,
    domain_id: str = "",
) -> EpisodeBuildResultV2:
    """Run the v2 detector and return an EpisodeBuildResultV2."""
    _ = (anchors, domain_id)
    errors: list[str] = []
    if not patient_id:
        return EpisodeBuildResultV2(
            patient_id=patient_id, errors=["missing_patient_id"]
        )

    timeline = await load_timeline(patient_id, patient_client)
    if not timeline:
        logger.info("v2 detector: no timeline events for patient %s", patient_id)
        return EpisodeBuildResultV2(patient_id=patient_id)

    signals = (
        extract_code_signals(timeline)
        + extract_text_signals(timeline)
        + extract_pathway_signals(timeline)
        + extract_result_signals(timeline)
        + extract_treatment_signals(timeline)
    )

    candidates = (
        generate_referral_anchored(
            patient_id=patient_id, events=timeline, signals=signals
        )
        + generate_diagnosis_anchored(
            patient_id=patient_id, events=timeline, signals=signals
        )
        + generate_symptom_cluster_anchored(
            patient_id=patient_id, events=timeline, signals=signals
        )
        + generate_site_cohort_anchored(
            patient_id=patient_id, events=timeline, signals=signals
        )
        + generate_treatment_anchored(
            patient_id=patient_id, events=timeline, signals=signals
        )
    )

    aggregated = aggregate_evidence(candidates, signals)
    resolved_aggs = resolve_conflicts(aggregated)
    consensus_map = vote_for_candidates(aggregated)

    # Build one ResolvedEpisode per unique episode_id, merging multiple
    # aggregated-candidate rows that derive the same id (the resolver
    # groups by (site_key, anchor); _episode_id collapses by start_date,
    # so we de-duplicate here before persistence).
    by_episode_id: dict[str, _EpisodeAccumulator] = {}
    for agg in resolved_aggs:
        cand = agg.candidate
        boundary = detect_boundary(agg, timeline)
        consensus = consensus_map.get(
            f"{cand.site_key}|{cand.anchor_event_id}", [cand.generator]
        )
        tier, reasons = assign_confidence_tier(agg, consensus)
        anchor_iso = (
            boundary.start_date.isoformat()
            if boundary.start_date is not None
            else "unknown"
        )
        episode_id = _episode_id(patient_id, cand.site_key, anchor_iso)
        all_signals = [s for sl in agg.signals_by_channel.values() for s in sl]
        signal_encounter_ids = {s.encounter_id for s in all_signals}
        # Restrict encounter membership to those with at least one
        # supporting signal for this candidate's site. The window in
        # the generator was for *search*; final membership is signal-
        # backed.
        scoped_encounters = [
            enc_id for enc_id in cand.encounter_ids if enc_id in signal_encounter_ids
        ]
        if not scoped_encounters and cand.anchor_event_id:
            scoped_encounters = [cand.anchor_event_id]
        alternatives = [
            a.candidate.candidate_id
            for a in aggregated
            if a.candidate.site_key == cand.site_key
            and a.candidate.candidate_id != cand.candidate_id
        ]
        accumulator = by_episode_id.get(episode_id)
        if accumulator is None:
            accumulator = _EpisodeAccumulator(
                episode_id=episode_id,
                site_key=cand.site_key,
                role_hint=cand.role_hint or "diagnosis",
                tier=tier,
                reasons=list(reasons),
                start_date=boundary.start_date,
                end_date=boundary.end_date,
                intent=boundary.intent,
                status=boundary.status,
                consensus=list(consensus),
            )
            by_episode_id[episode_id] = accumulator
        accumulator.merge(
            scoped_encounters=scoped_encounters,
            signals=all_signals,
            consensus=consensus,
            alternatives=alternatives,
            tier=tier,
            reasons=reasons,
            boundary_status=boundary.status,
            boundary_end=boundary.end_date,
            boundary_intent=boundary.intent,
            generator=cand.generator,
            evidence_weight=agg.evidence_weight,
        )

    resolved_episodes: list[ResolvedEpisode] = []
    provenance_records: list[EpisodeProvenance] = []
    review_count = 0
    for accumulator in by_episode_id.values():
        ep = accumulator.to_resolved_episode()
        resolved_episodes.append(ep)
        if ep.confidence_tier != "auto":
            review_count += 1
        provenance_records.extend(accumulator.provenance_records())

    auto_only = [ep for ep in resolved_episodes if ep.confidence_tier == "auto"]
    coverage = check_coverage(timeline, signals, auto_only)
    if not coverage.is_complete:
        errors.append(
            f"coverage_incomplete:{len(coverage.encounter_ids_unaccounted)}_unaccounted"
        )

    auto_episodes = auto_only
    persisted_ids: list[str] = []
    if auto_episodes and patient_client is not None:
        rows = [
            {
                "episode_id": ep.episode_id,
                "site_key": ep.site_key,
                "suspected_site": ep.suspected_site,
                "start_date": ep.start_date.isoformat() if ep.start_date else None,
                "end_date": ep.end_date.isoformat() if ep.end_date else None,
                "intent": ep.intent,
                # Translate the v2 boundary vocabulary to the canonical
                # EpisodeStatus before persisting (DI-C4CEFA32). The
                # boundary detector emits open / closed / benign_closure
                # which are NOT valid EpisodeStatus members.
                "status": canonical_status_from_v2_boundary(
                    ep.status, ep.needs_human_review
                ),
                "confidence_tier": ep.confidence_tier,
                "needs_human_review": ep.needs_human_review,
                "review_reasons": ep.review_reasons,
                "encounter_ids": ep.encounter_ids,
            }
            for ep in auto_episodes
        ]
        try:
            patient_client.run(
                _EPISODE_MERGE, patient_id=patient_id, episodes=rows
            )
            persisted_ids = [ep.episode_id for ep in auto_episodes]
        except Exception:
            logger.exception(
                "v2 detector: failed to persist %d auto-episodes for %s",
                len(auto_episodes),
                patient_id,
            )
            errors.append("persist_auto_failed")

    if persisted_ids:
        persist_provenance(patient_client, records=provenance_records)

    encounters_linked = sum(len(ep.encounter_ids) for ep in auto_episodes)
    # Count episodes that resolved to a closed-family canonical status.
    # The v2 boundary still uses internal labels (open / closed /
    # benign_closure); we project them to canonical to compute the
    # headline so the dashboard counts agree with the persisted status.
    closed_canonical = {
        EpisodeStatus.CLOSED.value,
        EpisodeStatus.CLOSED_BENIGN.value,
        EpisodeStatus.COMPLETED.value,
    }
    completed_count = sum(
        1
        for ep in auto_episodes
        if canonical_status_from_v2_boundary(ep.status, ep.needs_human_review)
        in closed_canonical
    )
    return EpisodeBuildResultV2(
        patient_id=patient_id,
        episodes_created=len(persisted_ids),
        episodes_completed=completed_count,
        episodes_merged=0,
        encounters_linked=encounters_linked,
        episode_ids=persisted_ids,
        errors=errors,
        coverage_report=coverage,
        review_count=review_count,
    )
