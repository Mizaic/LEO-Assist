"""Core dataclasses for Episode Detector v2.

Atlas trace:
  DI: DI-8A5FCF4F
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-8A5FCF4F")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


# -- 1. Normalised event ----------------------------------------------------


@dataclass(frozen=True)
class TimelineEvent:
    """Site-agnostic, deterministic representation of a single
    encounter / document / coded entity in the patient timeline.

    Produced by :mod:`normaliser`. Consumed by signal extractors,
    candidate generators, and the boundary detector. Immutable so
    multiple downstream components can hold references safely.
    """

    encounter_id: str
    occurred_on: date
    event_kind: str  # "encounter" | "document" | "coded_entity"
    text_snippet: str = ""
    coded_entities: tuple[dict[str, Any], ...] = ()
    referral_form: dict[str, Any] | None = None
    observation_results: tuple[dict[str, Any], ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


# -- 2. Signals --------------------------------------------------------------


@dataclass(frozen=True)
class Signal:
    """A piece of evidence emitted by one signal extractor for one event.

    The combination of (channel, encounter_id) is the join key used by
    the evidence aggregator.
    """

    channel: str  # "code" | "text" | "pathway" | "result" | "treatment"
    encounter_id: str
    site_key: str  # canonical site like "breast", "upper_gi", "lung"
    role: str  # "referral" | "diagnosis" | "investigation" | "treatment" | "outcome"
    intent: str  # "suspected" | "confirmed" | "ruled_out" | "unspecified"
    confidence: float  # 0.0-1.0
    citation: str = ""  # short human-readable provenance


# -- 3. Candidate episode ---------------------------------------------------


@dataclass
class CandidateEpisode:
    """A proposed episode emitted by a candidate generator.

    Multiple generators may emit overlapping candidates for the same
    site/window. The conflict resolver decides which (if any) survive.
    """

    candidate_id: str
    site_key: str
    generator: str  # "referral_anchored" | "diagnosis_anchored" | etc
    encounter_ids: list[str] = field(default_factory=list)
    anchor_event_id: str = ""
    anchor_date: date | None = None
    role_hint: str = ""
    intent_hint: str = ""
    raw_score: float = 0.0
    supporting_signals: list[Signal] = field(default_factory=list)


# -- 4. Resolved episode ----------------------------------------------------


@dataclass
class ResolvedEpisode:
    """The output of the conflict resolver + boundary detector + arbitration."""

    episode_id: str
    site_key: str
    encounter_ids: list[str]
    start_date: date | None
    end_date: date | None
    suspected_site: str
    role: str
    intent: str  # "suspected" | "confirmed" | "ruled_out"
    status: str  # "open" | "closed" | "benign_closure"
    confidence_tier: str  # "auto" | "suggest" | "review"
    needs_human_review: bool
    review_reasons: list[str]
    vote_count: int
    supporting_signals: list[Signal]
    alternatives_considered: list[str]
    generator_consensus: list[str]


# -- 5. Coverage check ------------------------------------------------------


@dataclass
class CoverageReport:
    """Result of the coverage check -- the fail-safe that catches
    silent drops.

    Bucket semantics::

        encounter_ids_total
            -- everything the normaliser saw.
        encounter_ids_in_episodes
            -- linked to a resolved auto/suggest episode.
        encounter_ids_adjacent_to_active_episode
            -- no signal of their own but within +/- 90 days of an
               in-episode encounter for an active confirmed episode.
               These are the routine follow-up encounters that a
               clinician implicitly attaches to an open cancer
               episode (chemo cycles, scans, clinic reviews).
        encounter_ids_no_signal
            -- no signal AND not adjacent to any active episode.
               Genuinely off-pathway from the v2 detector's view.
        encounter_ids_unaccounted
            -- had a signal but no episode survived the resolver.
               This is the silent-drop fail-safe; non-empty means
               human review is required.
    """

    encounter_ids_total: list[str]
    encounter_ids_in_episodes: list[str]
    encounter_ids_no_signal: list[str]
    encounter_ids_unaccounted: list[str]
    encounter_ids_adjacent_to_active_episode: list[str] = field(
        default_factory=list
    )

    # Backwards-compatible alias for the old field name. Kept so a
    # downstream consumer that still reads
    # ``encounter_ids_explicitly_off_pathway`` keeps working until it
    # migrates to the new name.
    @property
    def encounter_ids_explicitly_off_pathway(self) -> list[str]:
        return self.encounter_ids_no_signal

    @property
    def is_complete(self) -> bool:
        return not self.encounter_ids_unaccounted


# -- 6. Provenance ---------------------------------------------------------


@dataclass
class EpisodeProvenance:
    """One record per (resolved_episode, encounter) link.

    Serialised to ``EpisodeProvenance`` graph nodes by the persister.
    Lets us reconstruct, audit, and learn from every assignment.
    """

    episode_id: str
    encounter_id: str
    generator: str
    score: float
    supporting_signals: list[dict[str, Any]]
    alternatives_considered: list[dict[str, Any]]
    detector_version: str = "v2"


# -- 7. Build result -------------------------------------------------------


@dataclass
class EpisodeBuildResultV2:
    """Compatible with EpisodeBuildResult (used by subgraphs/episode.py)."""

    patient_id: str
    episodes_created: int = 0
    episodes_completed: int = 0
    episodes_merged: int = 0
    encounters_linked: int = 0
    episode_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    coverage_report: CoverageReport | None = None
    review_count: int = 0
    # All resolved episodes before the auto-only persist filter. Populated
    # for dry-run / parity tooling so a caller can inspect review- and
    # suggest-tier proposals that never reach Neo4j. Left empty in the
    # hot path: the production runner only sets this when called by a
    # debug harness.
    resolved_episodes: list[ResolvedEpisode] = field(default_factory=list)
