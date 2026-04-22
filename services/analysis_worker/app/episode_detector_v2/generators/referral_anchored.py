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


def generate_referral_anchored(
    *,
    patient_id: str,
    events: Sequence[TimelineEvent],
    signals: Sequence[Signal],
) -> list[CandidateEpisode]:
    candidates: list[CandidateEpisode] = []
    events_list = list(events)
    event_by_id = {evt.encounter_id: evt for evt in events_list}
    pathway_signals = [s for s in signals if s.channel == "pathway"]
    seen: set[tuple[str, str, str]] = set()
    for signal in pathway_signals:
        anchor_event = event_by_id.get(signal.encounter_id)
        if anchor_event is None:
            continue
        key = (signal.site_key, anchor_event.encounter_id, signal.role)
        if key in seen:
            continue
        seen.add(key)
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
                events_list, anchor_date=anchor_event.occurred_on
            ),
            anchor_event_id=anchor_event.encounter_id,
            anchor_date=anchor_event.occurred_on,
            role_hint="referral",
            intent_hint=signal.intent,
            raw_score=signal.confidence,
            supporting_signals=[signal],
        )
        candidates.append(cand)
    return candidates
