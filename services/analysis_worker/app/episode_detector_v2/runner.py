"""Episode Detector v2 runner.

Atlas trace:
  DI: DI-8A5FCF4F
  DO: (will be created in Phase 1 once tests are recorded)

Provides ``build_episodes`` with the same signature the legacy
episode_builder exposed, so ``libs/pipeline_graph/subgraphs/episode.py``
can call either implementation behind the ``episode_pipeline`` feature
flag (see libs/feature_flags.py).

Pipeline order matches the 12-component defence-in-depth design:

    normalise -> 5 signal extractors -> referral/seen/diagnosis candidate anchors
      -> evidence aggregator -> conflict resolver -> boundary detector
      -> generator-consensus voting -> coverage check -> confidence tier
      -> persist (default: auto-tier only) -> persist provenance
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from libs.episodes.lifecycle import (
    canonical_status_from_v2_boundary,
)
from libs.episodes.status import EpisodeStatus
from libs.oncology.cancer_types import normalise_cancer_type

from .aggregator import aggregate_evidence
from .boundary import detect_boundary
from .coverage import check_coverage
from .generators import (
    generate_diagnosis_anchored,
    generate_referral_anchored,
)
from .milestone_inference import (
    add_same_day_referral_sent_encounter_ids,
    infer_benign_presentation_encounter_ids,
    infer_contextual_encounter_ids,
    infer_milestone_links,
    infer_walkback_encounter_ids,
    prune_duplicate_same_day_referral_encounter_ids,
    prune_weak_breast_context_encounter_ids,
    prune_weak_haematology_context_encounter_ids,
)
from .normaliser import load_timeline
from .provenance import persist_provenance
from .reviewed_replay import load_reviewed_episode_replay
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
    Signal,
    TimelineEvent,
)
from .voting import assign_confidence_tier, vote_for_candidates

logger = logging.getLogger(__name__)


def _episode_id(patient_id: str, site_key: str, anchor_iso: str) -> str:
    raw = f"{patient_id}|{site_key.lower()}|{anchor_iso}|v2"
    return f"ep-v2-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _context_signal_eligible_for_membership(
    signal: Signal,
    *,
    event_by_id: dict[str, TimelineEvent],
) -> bool:
    """Whether a context_milestone may tie an in-window encounter to membership.

    Including every context hit in the referral window over-links generic
    primary-care rows (routine FBC/bloods). Gate ``primary_care_investigations``
    and ``referral_admin`` with short urology/oncology pathway cues; keep
    specialist-facing tags that already encode staging intent.
    """
    if signal.role != "context_milestone":
        return False
    tag = signal.context_tag or ""
    event = event_by_id.get(signal.encounter_id)
    text = (event.text_snippet if event else "") or ""
    lower = text.lower()
    if tag == "referral_sent":
        # Rulebook referral_sent lines are already USC/2WW-heavy; keep them.
        return True
    if tag == "related_gp_visit":
        # The prostate rulebook also lists plain "GP consultation" lines; those
        # must not pull every primary-care contact into a cancer episode.
        return any(
            x in lower
            for x in (
                "firmagon",
                "degarelix",
                "psd",
                "patient specific direction",
                "drug injection",
            )
        ) or (
            "authori" in lower
            and ("firmagon" in lower or "degarelix" in lower)
        )
    if tag == "specialist_diagnostics":
        return any(
            x in lower
            for x in (
                "prostate",
                "urology",
                "urological",
                "psa",
                "trus",
                "mri prostate",
                "mp-mri",
                "mp mri",
                "template biopsy",
                "transperineal",
                "bone scan",
                "spect",
                "transrectal",
                "cystoscopy",
            )
        )
    if tag == "related_specialist_visit":
        return any(
            x in lower
            for x in (
                "prostate",
                "urology",
                "urological",
                "psa",
                "oncology",
                "biopsy",
                "mdt",
                "2ww",
                "2 ww",
                "suspected cancer",
                "care navigation",
                "follow-up after biopsy",
                "follow up after biopsy",
            )
        )
    if tag == "related_correspondence":
        return any(
            x in lower
            for x in (
                "prostate",
                "urology",
                "urological",
                "psa",
                "oncology",
                "mdt",
                "biopsy",
                "2ww",
                "2 ww",
                "two week",
            )
        )
    if tag == "referral_admin":
        return any(
            x in lower
            for x in (
                "oncology",
                "urology",
                "urological",
                "2ww",
                "2 ww",
                "two week",
                "fast track",
                "suspected cancer",
                "usc",
                "mdt",
            )
        )
    if tag == "primary_care_investigations":
        return any(
            x in lower
            for x in (
                "pathology",
                "psa",
                "urea",
                " u & e",
                "u & e",
                "u&e",
                "electrolyte",
                "prostate",
                "urology",
                "biopsy",
                "mp-mri",
                "mri prostate",
                "trus",
                "cystoscopy",
                "luts",
                "haematuria",
                "2ww",
                "2 ww",
            )
        )
    return False


_PROSTATE_MEMBERSHIP_ANCHOR_TERMS: frozenset[str] = frozenset(
    {
        "prostate",
        "urology",
        "urological",
        "psa",
        "firmagon",
        "degarelix",
        "decapeptyl",
        "triptorelin",
        "gnrh",
        "2ww",
        "two week",
        "biopsy",
        "mdt",
        "injection",
        "recall",
        "suspected cancer",
        "fast track",
        "usc",
        "haematuria",
        "luts",
        "template biopsy",
        "mri prostate",
        "mp-mri",
        "mp mri",
        "trus",
        "cystoscopy",
        "prostatectomy",
        "radiotherapy",
        "hormone therapy",
        "brachytherapy",
        "adt",
        "zoladex",
        "eligard",
    }
)


def _prostate_pathway_anchor_in_text(lower: str) -> bool:
    return any(term in lower for term in _PROSTATE_MEMBERSHIP_ANCHOR_TERMS)


def _prostate_encounter_is_membership_noise(lower: str) -> bool:
    """True when free text suggests primary care / admin / other-pathway work."""
    if not lower.strip():
        return False
    pathway = _prostate_pathway_anchor_in_text(lower)

    if "minor injur" in lower:
        return True
    if "behind on accurx" in lower:
        return True
    if "nhs health check" in lower:
        return True
    # Drop weak case-management MDT rows (significant-event triage) but keep
    # staging/diagnosis-led reviews that name prostate cancer in the note.
    if (
        "case management" in lower
        and "mdt" in lower
        and "significant event" in lower
        and not any(
            x in lower
            for x in (
                "t4",
                "t3",
                "t2",
                "t1",
                "n1",
                "m1",
                "metasta",
                "ca prostate",
                "prostate cancer",
                "carcinoma of prostate",
            )
        )
    ):
        return True
    if ("h pylori" in lower or "helicobacter" in lower) and not pathway:
        return True
    if "clinical supervision" in lower and "patient present: no" in lower:
        return True
    if "continence service" in lower or "llr continence" in lower:
        if pathway:
            return False
        if any(
            x in lower
            for x in (
                "bypassing catheter",
                "bypassing urethral",
                "urethral catheter",
                "catheter",
                "twoc",
                "t.w.o.c",
            )
        ):
            return False
        return True
    # Balanitis / SGLT2 foreskin bleed without urgent suspected-cancer context.
    if "foreskin" in lower and ("dapaglif" in lower or "dapagli" in lower):
        if not any(
            x in lower
            for x in (
                "2ww",
                "two week",
                "suspected urological",
                "fast track referral for suspected",
            )
        ):
            return True
    # Cardiac SPECT / coronary work triggered by chest pain -- keep out of
    # prostate episode even when the note also lists prostate cancer history.
    if "chest pain" in lower and "spect" in lower:
        if "coronary" in lower or "calcified" in lower:
            return True
    if "chest pain" in lower and not pathway:
        return True
    if "foreskin" in lower and not pathway:
        return True
    # Auto-filed U&E tied to CKD monitoring: curators tag 2WW bloods explicitly;
    # routine renal panels without that hook are usually not episode members.
    if "auto-filed" in lower:
        if "psa" not in lower and "prostate-specific antigen" not in lower:
            if "serum urea level" in lower or "urea and electrolytes" in lower:
                if "2ww" not in lower and "two week" not in lower:
                    if not pathway:
                        return True
    if "phlebotomy" in lower and "routine" in lower and "psa" not in lower:
        if not pathway:
            return True
    if "short message service" in lower and not pathway:
        if "catheter" not in lower:
            return True
    return False


def _drop_prostate_low_value_encounters(
    encounter_ids: list[str],
    timeline: list[TimelineEvent],
    *,
    anchor_event_id: str,
) -> list[str]:
    """Strip admin / other-service encounters curators usually omit.

    Text-only heuristics: coded-only rows with an empty snippet are kept.
    The referral anchor is never removed.
    """
    by_id = {e.encounter_id: e for e in timeline}
    anchor = (anchor_event_id or "").strip()
    out: list[str] = []
    for eid in encounter_ids:
        if eid == anchor:
            out.append(eid)
            continue
        ev = by_id.get(eid)
        lower = ((ev.text_snippet if ev else "") or "").lower()
        if _prostate_encounter_is_membership_noise(lower):
            continue
        out.append(eid)
    return out


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
        # Benign closure is a hard boundary for suspected pathways: once a
        # rule-out result lands, later symptom recurrences need a fresh anchor.
        if boundary_status == "benign_closure":
            self.intent = boundary_intent
            self.status = boundary_status
            self.end_date = boundary_end
        elif boundary_end is not None and (
            self.end_date is None or boundary_end > self.end_date
        ):
            # Boundary widens: pick the latest end_date, never clip back.
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
        self.provenance_rows.append((generator, "", evidence_weight, signals))

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
            generators = sorted({row[0] for row in self.provenance_rows})
            score = max((row[2] for row in self.provenance_rows), default=0.0)
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


def _encounter_dates(timeline: list[Any]) -> dict[str, date]:
    return {event.encounter_id: event.occurred_on for event in timeline}


def _filter_to_boundary(
    encounter_ids: list[str],
    *,
    event_dates: dict[str, date],
    start: date | None,
    end: date | None,
) -> list[str]:
    out: list[str] = []
    for enc_id in encounter_ids:
        occurred_on = event_dates.get(enc_id)
        if occurred_on is None:
            continue
        if start is not None and occurred_on < start:
            continue
        if end is not None and occurred_on > end:
            continue
        out.append(enc_id)
    return out


def _earliest_encounter_date(
    encounter_ids: list[str],
    *,
    event_dates: dict[str, date],
) -> date | None:
    dates = [event_dates[enc_id] for enc_id in encounter_ids if enc_id in event_dates]
    return min(dates) if dates else None


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
    e.cancer_type = coalesce(e.cancer_type, ep.cancer_type),
    e.condition_type = coalesce(e.condition_type, ep.cancer_type),
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
UNWIND ep.milestone_links AS link
MATCH (enc:Encounter {id: link.encounter_id})
MERGE (enc)-[r:IS_PART_OF {milestone_type: link.milestone_type}]->(e)
SET r.linked_by = 'episode_detector_v2',
    r.linked_at = datetime(),
    r.evidence_quote = link.evidence_quote,
    r.confidence = link.confidence,
    r.treatment_type = link.treatment_type
WITH e
OPTIONAL MATCH (slot_enc:Encounter)-[slot_rel:IS_PART_OF]->(e)
WHERE slot_rel.milestone_type IS NOT NULL
  AND slot_enc.date IS NOT NULL
WITH e, collect({
    mt: slot_rel.milestone_type,
    d: toString(slot_enc.date)
}) AS slots
WITH e,
     [s IN slots WHERE s.mt IN [
        'referral', 'referral_sent', 'first_presentation'
     ] | s.d] AS referral_dates,
     [s IN slots WHERE s.mt IN [
        'first_presentation', 'presentation'
     ] | s.d] AS presentation_dates,
     [s IN slots WHERE s.mt IN [
        'diagnosis', 'diagnosis_confirmed'
     ] | s.d] AS diagnosis_dates,
     [s IN slots WHERE s.mt = 'benign_closure' | s.d] AS benign_dates,
     [s IN slots WHERE s.mt IN [
        'treatment', 'treatment_started', 'treatment_completed',
        'first_treatment', 'treatment_decision'
     ] | s.d] AS treatment_dates
WITH e,
     CASE WHEN size(referral_dates) > 0
          THEN reduce(best = referral_dates[0], d IN referral_dates |
              CASE WHEN d < best THEN d ELSE best END)
          ELSE null END AS referral_date,
     CASE WHEN size(presentation_dates) > 0
          THEN reduce(best = presentation_dates[0], d IN presentation_dates |
              CASE WHEN d < best THEN d ELSE best END)
          ELSE null END AS presentation_date,
     CASE WHEN size(diagnosis_dates) > 0
          THEN reduce(best = diagnosis_dates[0], d IN diagnosis_dates |
              CASE WHEN d < best THEN d ELSE best END)
          ELSE null END AS diagnosis_date,
     CASE WHEN size(benign_dates) > 0
          THEN reduce(best = benign_dates[0], d IN benign_dates |
              CASE WHEN d < best THEN d ELSE best END)
          ELSE null END AS benign_closure_date,
     CASE WHEN size(treatment_dates) > 0
          THEN reduce(best = treatment_dates[0], d IN treatment_dates |
              CASE WHEN d > best THEN d ELSE best END)
          ELSE null END AS treatment_end_date
SET e.referral_date = referral_date,
    e.benign_closure_date = benign_closure_date,
    e.end_date = coalesce(benign_closure_date, treatment_end_date),
    e.diagnostic_interval_days =
        CASE WHEN referral_date IS NOT NULL AND diagnosis_date IS NOT NULL
             THEN duration.inDays(date(referral_date), date(diagnosis_date)).days
             ELSE null END,
    e.benign_interval_days =
        CASE WHEN referral_date IS NOT NULL AND benign_closure_date IS NOT NULL
             THEN duration.inDays(date(referral_date), date(benign_closure_date)).days
             ELSE null END,
    e.primary_care_interval_days =
        CASE WHEN presentation_date IS NOT NULL AND referral_date IS NOT NULL
             THEN duration.inDays(date(presentation_date), date(referral_date)).days
             ELSE null END,
    e.dates_updated_at = datetime()
"""


async def build_episodes(
    *,
    patient_id: str,
    anchors: Any = None,  # parity arg, ignored by v2
    patient_client: Any,
    domain_id: str = "",
    persist_confidence_tiers: Collection[str] | None = None,
) -> EpisodeBuildResultV2:
    """Run the v2 detector and return an EpisodeBuildResultV2.

    ``persist_confidence_tiers`` defaults to ``{\"auto\"}`` only. Pass
    e.g. ``{\"auto\", \"suggest\"}`` to MERGE suggest-tier proposals so
    curators can review them in Mission Control.
    """
    _ = (anchors, domain_id)
    persist_tiers = (
        frozenset(persist_confidence_tiers)
        if persist_confidence_tiers is not None
        else frozenset({"auto"})
    )
    errors: list[str] = []
    if not patient_id:
        return EpisodeBuildResultV2(
            patient_id=patient_id, errors=["missing_patient_id"]
        )

    timeline = await load_timeline(patient_id, patient_client)
    if not timeline:
        logger.info("v2 detector: no timeline events for patient %s", patient_id)
        return EpisodeBuildResultV2(patient_id=patient_id)

    reviewed_episodes = load_reviewed_episode_replay(
        patient_client, patient_id=patient_id
    )
    if reviewed_episodes:
        return EpisodeBuildResultV2(
            patient_id=patient_id,
            episodes_created=0,
            episodes_completed=0,
            encounters_linked=sum(len(ep.encounter_ids) for ep in reviewed_episodes),
            coverage_report=check_coverage(timeline, [], reviewed_episodes),
            resolved_episodes=reviewed_episodes,
        )

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
    )

    aggregated = aggregate_evidence(candidates, signals)
    resolved_aggs = resolve_conflicts(aggregated)
    consensus_map = vote_for_candidates(aggregated)

    # Build one ResolvedEpisode per unique episode_id, merging multiple
    # aggregated-candidate rows that derive the same id (the resolver
    # groups by (site_key, anchor); _episode_id collapses by start_date,
    # so we de-duplicate here before persistence).
    by_episode_id: dict[str, _EpisodeAccumulator] = {}
    event_dates = _encounter_dates(timeline)
    event_by_id = {evt.encounter_id: evt for evt in timeline}
    for agg in resolved_aggs:
        cand = agg.candidate
        boundary = detect_boundary(agg, timeline)
        consensus = (
            list(agg.consensus_generators)
            if agg.consensus_generators is not None
            else consensus_map.get(
                f"{cand.site_key}|{cand.anchor_event_id}", [cand.generator]
            )
        )
        tier, reasons = assign_confidence_tier(agg, consensus)
        all_signals = [s for sl in agg.signals_by_channel.values() for s in sl]
        non_context_encounter_ids = {
            s.encounter_id
            for s in all_signals
            if getattr(s, "role", "") != "context_milestone"
        }
        # Context milestones (rulebook context_role_catalogue) are site-
        # specific and must count toward membership when the encounter is
        # already inside the generator window. Otherwise pathway-windowed
        # admin/lab text that only fires context_milestone -- common for
        # prostate U&E requests, letter routing, PSD injections -- is
        # dropped; infer_contextual_encounter_ids only expands breast/skin.
        # Generic primary-care context (routine FBC) is gated on text so
        # the episode does not absorb every chronic-disease blood test.
        candidate_id_set = frozenset(cand.encounter_ids)
        context_window_encounter_ids = {
            s.encounter_id
            for s in all_signals
            if isinstance(s, Signal)
            and s.site_key == cand.site_key
            and s.encounter_id in candidate_id_set
            and _context_signal_eligible_for_membership(s, event_by_id=event_by_id)
        }
        signal_encounter_ids = non_context_encounter_ids | context_window_encounter_ids
        # Restrict encounter membership to those with at least one
        # supporting signal for this candidate's site. The window in
        # the generator was for *search*; final membership is signal-
        # backed.
        scoped_encounters = [
            enc_id for enc_id in cand.encounter_ids if enc_id in signal_encounter_ids
        ]
        contextual_encounters = infer_contextual_encounter_ids(
            site_key=cand.site_key,
            candidate_encounter_ids=cand.encounter_ids,
            timeline=timeline,
        )
        walkback_encounters = infer_walkback_encounter_ids(
            site_key=cand.site_key,
            anchor_event_id=cand.anchor_event_id,
            generator=cand.generator,
            intent=boundary.intent,
            timeline=timeline,
        )
        benign_presentation_encounters = infer_benign_presentation_encounter_ids(
            site_key=cand.site_key,
            candidate_encounter_ids=cand.encounter_ids,
            intent=boundary.intent,
            boundary_end=boundary.end_date,
            timeline=timeline,
        )
        contextual_encounters = _filter_to_boundary(
            contextual_encounters,
            event_dates=event_dates,
            start=boundary.start_date,
            end=boundary.end_date,
        )
        effective_start = boundary.start_date
        walkback_start = _earliest_encounter_date(
            walkback_encounters + benign_presentation_encounters,
            event_dates=event_dates,
        )
        if walkback_start is not None and (
            effective_start is None or walkback_start < effective_start
        ):
            effective_start = walkback_start
        anchor_iso = (
            effective_start.isoformat() if effective_start is not None else "unknown"
        )
        episode_id = _episode_id(patient_id, cand.site_key, anchor_iso)
        scoped_encounters = list(
            dict.fromkeys(
                scoped_encounters
                + contextual_encounters
                + walkback_encounters
                + benign_presentation_encounters
            )
        )
        scoped_encounters = add_same_day_referral_sent_encounter_ids(
            site_key=cand.site_key,
            candidate_encounter_ids=scoped_encounters,
            timeline=timeline,
        )
        scoped_encounters = prune_duplicate_same_day_referral_encounter_ids(
            site_key=cand.site_key,
            candidate_encounter_ids=scoped_encounters,
            timeline=timeline,
        )
        scoped_encounters = prune_weak_breast_context_encounter_ids(
            site_key=cand.site_key,
            candidate_encounter_ids=scoped_encounters,
            timeline=timeline,
        )
        scoped_encounters = prune_weak_haematology_context_encounter_ids(
            site_key=cand.site_key,
            candidate_encounter_ids=scoped_encounters,
            timeline=timeline,
        )
        if cand.site_key == "prostate_urological":
            scoped_encounters = _drop_prostate_low_value_encounters(
                scoped_encounters,
                timeline,
                anchor_event_id=cand.anchor_event_id or "",
            )
        if boundary.status == "benign_closure":
            scoped_encounters = _filter_to_boundary(
                scoped_encounters,
                event_dates=event_dates,
                start=effective_start,
                end=boundary.end_date,
            )
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
                start_date=effective_start,
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

    episodes_to_persist = [
        ep for ep in resolved_episodes if ep.confidence_tier in persist_tiers
    ]
    persisted_ids: list[str] = []
    if episodes_to_persist and patient_client is not None:
        milestone_links_by_episode = {
            ep.episode_id: infer_milestone_links(ep, timeline)
            for ep in episodes_to_persist
        }
        rows = [
            {
                "episode_id": ep.episode_id,
                "site_key": ep.site_key,
                "cancer_type": normalise_cancer_type(ep.site_key),
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
                "milestone_links": [
                    {
                        "encounter_id": link.encounter_id,
                        "milestone_type": link.milestone_type,
                        "evidence_quote": link.evidence_quote,
                        "confidence": link.confidence,
                        "treatment_type": link.treatment_type,
                    }
                    for link in milestone_links_by_episode[ep.episode_id]
                ],
            }
            for ep in episodes_to_persist
        ]
        try:
            patient_client.run(_EPISODE_MERGE, patient_id=patient_id, episodes=rows)
            persisted_ids = [ep.episode_id for ep in episodes_to_persist]
        except Exception:
            logger.exception(
                "v2 detector: failed to persist %d episodes for %s",
                len(episodes_to_persist),
                patient_id,
            )
            errors.append("persist_auto_failed")

    if persisted_ids:
        persisted_set = set(persisted_ids)
        prov_filtered = [r for r in provenance_records if r.episode_id in persisted_set]
        persist_provenance(patient_client, records=prov_filtered)

    encounters_linked = sum(len(ep.encounter_ids) for ep in episodes_to_persist)
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
        for ep in episodes_to_persist
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
        resolved_episodes=list(resolved_episodes),
    )
