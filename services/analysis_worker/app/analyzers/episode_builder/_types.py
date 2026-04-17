"""Shared types and pure utility functions for the episode builder."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class EpisodeBuildResult:
    patient_id: str
    episodes_created: int = 0
    episodes_completed: int = 0
    episodes_merged: int = 0
    encounters_linked: int = 0
    episode_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class _EpisodeSpec:
    """Lightweight descriptor used to match specialist visits to episodes."""

    ep_id: str
    site_key: str
    ref_date: date | None
    window_end: date
    # DI-LEO-AI-136: audit field tagging how the referral anchor was
    # claimed. 'strict_site' (same-site Pass 1), 'fallback_any_site'
    # (Pass 2 any-site within window), or 'none' (diagnosis-only
    # floating episode or referral-only open episode with no claim).
    referral_match_method: str = "strict_site"


@dataclass
class _SpecialistClaim:
    """Per-episode specialist visit outcome after claiming."""

    specialist_seen: bool = False
    specialist_visit_date: str | None = None
    referral_site_name: str = ""


@dataclass
class WriteEpisodeParams:
    """All fields needed by ``_write_episode`` to persist one episode."""

    patient_id: str
    ep_id: str
    domain_id: str
    site_key: str
    # DI-LEO-AI-136: honest semantics -- ``None`` when no referral anchor
    # exists. Previously a diagnosis-only floating episode was written
    # with the diagnosis date as a synthesised referral_date, corrupting
    # the 2WW-route NCDA metric. The builder no longer back-fills.
    referral_date: str | None
    end_date: str | None
    claim: _SpecialistClaim
    status: str
    hitl_flag: bool
    hitl_reason: str | None
    referral_route: str = "two_week_wait"
    place_of_presentation: str = "GP surgery"
    letter_inferred_benign: bool = False
    first_presentation_date: str | None = None
    presenting_complaint: str | None = None
    # DI-LEO-AI-136: how the referral was claimed. Persisted on the
    # episode so analytics and audit UI can distinguish strict from
    # fallback matches from truly-floating episodes.
    referral_match_method: str = "strict_site"
    # DI-LEO-AI-136: True when referral_date was inferred rather than
    # taken from a genuine referral anchor. Always False in the current
    # builder (honest-NULL semantics); reserved for future inference
    # paths that may choose to supply a computed date with an explicit
    # audit flag rather than persisting NULL.
    referral_inferred: bool = False
    # DI-LEO-AI-145: date of first IS_PART_OF first_seen encounter
    # claimed for this episode; None when no fast-track clinic attendance
    # was detected within the episode window.
    first_seen_date: str | None = None


@dataclass
class BuildContext:
    """Shared state threaded through ``_build_closed_episode`` /
    ``_build_open_episode`` to stay within the 6-parameter limit."""

    patient_id: str
    anchors: Any  # AnchorResult (avoid circular import)
    patient_client: Any
    domain_id: str
    result: EpisodeBuildResult
    episode_ids: list[str]
    phantom_sites: set[str]


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if hasattr(val, "year"):
        try:
            return date(val.year, val.month, val.day)
        except (ValueError, TypeError):
            return None
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _episode_id(patient_id: str, condition_key: str, earliest: str) -> str:
    raw = f"{patient_id}|{condition_key}|{earliest}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
