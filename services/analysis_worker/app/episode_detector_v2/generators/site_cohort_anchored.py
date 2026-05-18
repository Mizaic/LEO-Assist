"""Site-cohort anchored candidate generator.

Atlas trace:
  DI: DI-8A5FCF4F

REAL for breast: collects every event whose result-channel signals are
breast-specific (mammography / biopsy results) and emits one candidate
per cluster.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..types import CandidateEpisode, Signal, TimelineEvent
from ._window import candidate_id, encounters_in_window


def generate_site_cohort_anchored(
    *,
    patient_id: str,
    events: Sequence[TimelineEvent],
    signals: Sequence[Signal],
) -> list[CandidateEpisode]:
    candidates: list[CandidateEpisode] = []
    events_list = list(events)
    event_by_id = {evt.encounter_id: evt for evt in events_list}
    result_signals = [s for s in signals if s.channel == "result"]
    seen: set[tuple[str, str]] = set()
    for signal in result_signals:
        anchor = event_by_id.get(signal.encounter_id)
        if anchor is None:
            continue
        key = (signal.site_key, anchor.encounter_id)
        if key in seen:
            continue
        seen.add(key)
        cand = CandidateEpisode(
            candidate_id=candidate_id(
                patient_id=patient_id,
                site_key=signal.site_key,
                generator="site_cohort_anchored",
                anchor_date=anchor.occurred_on,
            ),
            site_key=signal.site_key,
            generator="site_cohort_anchored",
            encounter_ids=encounters_in_window(
                events_list,
                anchor_date=anchor.occurred_on,
                site_key=signal.site_key,
            ),
            anchor_event_id=anchor.encounter_id,
            anchor_date=anchor.occurred_on,
            role_hint="result",
            intent_hint=signal.intent,
            raw_score=signal.confidence * 0.9,
            supporting_signals=[signal],
        )
        candidates.append(cand)
    return candidates
