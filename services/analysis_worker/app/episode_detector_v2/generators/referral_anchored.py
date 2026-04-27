"""Referral-anchored candidate generator.

Atlas trace:
  DI: DI-8A5FCF4F

REAL implementation. Walks the pathway-channel signals and emits one
candidate per (site_key, referral) pair.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..types import CandidateEpisode, Signal, TimelineEvent
from ._window import candidate_id, encounters_in_window

_REPEAT_REFERRAL_GAP_DAYS = 120
_REPEAT_REFERRAL_LOOKBACK_DAYS = 30


def generate_referral_anchored(
    *,
    patient_id: str,
    events: Sequence[TimelineEvent],
    signals: Sequence[Signal],
) -> list[CandidateEpisode]:
    candidates: list[CandidateEpisode] = []
    events_list = list(events)
    event_by_id = {evt.encounter_id: evt for evt in events_list}
    anchor_signals = [
        s
        for s in signals
        if (
            (s.role == "referral" and s.intent == "suspected")
            or (s.channel == "pathway" and s.role == "first_seen")
        )
    ]
    referral_events_by_site: dict[str, list[TimelineEvent]] = {}
    for signal in anchor_signals:
        if signal.role != "referral":
            continue
        event = event_by_id.get(signal.encounter_id)
        if event is None:
            continue
        referral_events_by_site.setdefault(signal.site_key, []).append(event)
    for site_events in referral_events_by_site.values():
        site_events.sort(key=lambda evt: (evt.occurred_on, evt.encounter_id))
    seen: set[tuple[str, str, str]] = set()
    for signal in anchor_signals:
        anchor_event = event_by_id.get(signal.encounter_id)
        if anchor_event is None:
            continue
        key = (signal.site_key, anchor_event.encounter_id, signal.role)
        if key in seen:
            continue
        seen.add(key)
        lookback_days, lookahead_days = _repeat_referral_window(
            anchor_event=anchor_event,
            site_events=referral_events_by_site.get(signal.site_key, []),
        )
        cand = CandidateEpisode(
            candidate_id=candidate_id(
                patient_id=patient_id,
                site_key=signal.site_key,
                generator="referral_anchored",
                anchor_date=anchor_event.occurred_on,
            ),
            site_key=signal.site_key,
            generator="referral_anchored",
            encounter_ids=encounters_in_window(
                events_list,
                anchor_date=anchor_event.occurred_on,
                site_key=signal.site_key,
                lookback_days=lookback_days,
                lookahead_days=lookahead_days,
            ),
            anchor_event_id=anchor_event.encounter_id,
            anchor_date=anchor_event.occurred_on,
            role_hint=signal.role,
            intent_hint=signal.intent,
            raw_score=signal.confidence,
            supporting_signals=[signal],
        )
        candidates.append(cand)
    return candidates


def _repeat_referral_window(
    *,
    anchor_event: TimelineEvent,
    site_events: list[TimelineEvent],
) -> tuple[int | None, int | None]:
    previous_dates = [
        event.occurred_on
        for event in site_events
        if (anchor_event.occurred_on - event.occurred_on).days > 0
    ]
    next_dates = [
        event.occurred_on
        for event in site_events
        if (event.occurred_on - anchor_event.occurred_on).days > 0
    ]
    lookback_days: int | None = None
    lookahead_days: int | None = None
    if previous_dates:
        days_since_previous = (anchor_event.occurred_on - max(previous_dates)).days
        if days_since_previous > _REPEAT_REFERRAL_GAP_DAYS:
            lookback_days = _REPEAT_REFERRAL_LOOKBACK_DAYS
    if next_dates:
        days_until_next = (min(next_dates) - anchor_event.occurred_on).days
        if days_until_next > _REPEAT_REFERRAL_GAP_DAYS:
            lookahead_days = max(days_until_next - 1, 0)
    return lookback_days, lookahead_days
