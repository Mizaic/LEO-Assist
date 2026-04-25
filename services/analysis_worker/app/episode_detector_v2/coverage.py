"""Coverage check -- the silent-drop fail-safe.

Atlas trace:
  DI: DI-8A5FCF4F
  Mitigates: R-1276F86C (silent drop)

Every encounter the normaliser saw must end up in one of four buckets
(see :class:`CoverageReport` for the full semantics):

1. ``encounter_ids_in_episodes``                  -- linked to an episode.
2. ``encounter_ids_adjacent_to_active_episode``    -- no own signal but
   within +/- 90 days of an in-episode encounter for an active
   confirmed episode (routine follow-up).
3. ``encounter_ids_no_signal``                    -- genuinely off-pathway.
4. ``encounter_ids_unaccounted``                  -- had a signal but no
   episode survived. Non-empty => human review required.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from .types import CoverageReport, ResolvedEpisode, Signal, TimelineEvent

# How wide the "adjacent" window is around in-episode encounters.
# 90 days picks up routine follow-up cycles for active cancer episodes
# without spuriously claiming unrelated encounters six months away.
_ADJACENCY_WINDOW = timedelta(days=90)


def check_coverage(
    events: Sequence[TimelineEvent],
    signals: Sequence[Signal],
    resolved: Sequence[ResolvedEpisode],
) -> CoverageReport:
    """Return a CoverageReport across the four buckets."""
    all_ids = [evt.encounter_id for evt in events]
    event_by_id = {evt.encounter_id: evt for evt in events}

    in_episodes: set[str] = set()
    active_anchor_dates: list = []
    for ep in resolved:
        in_episodes.update(ep.encounter_ids)
        if ep.intent != "ruled_out":
            for enc_id in ep.encounter_ids:
                evt = event_by_id.get(enc_id)
                if evt is not None:
                    active_anchor_dates.append(evt.occurred_on)

    encounters_with_signal = {
        sig.encounter_id
        for sig in signals
        if getattr(sig, "role", "") != "context_milestone"
    }

    adjacent: list[str] = []
    no_signal: list[str] = []
    unaccounted: list[str] = []
    for enc_id in all_ids:
        if enc_id in in_episodes:
            continue
        evt = event_by_id.get(enc_id)
        if enc_id in encounters_with_signal:
            unaccounted.append(enc_id)
            continue
        if evt is not None and any(
            abs((evt.occurred_on - anchor).days) <= _ADJACENCY_WINDOW.days
            for anchor in active_anchor_dates
        ):
            adjacent.append(enc_id)
            continue
        no_signal.append(enc_id)

    return CoverageReport(
        encounter_ids_total=all_ids,
        encounter_ids_in_episodes=sorted(in_episodes),
        encounter_ids_no_signal=no_signal,
        encounter_ids_unaccounted=unaccounted,
        encounter_ids_adjacent_to_active_episode=adjacent,
    )
