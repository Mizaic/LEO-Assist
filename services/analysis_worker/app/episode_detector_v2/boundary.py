"""Boundary detector with benign-closure port.

Atlas trace:
  DI: DI-8A5FCF4F
  Closes the gap that R-D4BE025E (benign-closure regression) covers.

Determines start_date, end_date, status (open / closed / benign_closure)
for each candidate based on:

- start_date: earliest encounter with a same-site supporting signal,
  OR the anchor date (whichever is earlier).
- end_date / status: defaults to ``status="open"`` and ``end_date=None``
  for confirmed-intent episodes -- a confirmed cancer episode is never
  "closed" by silence; closure requires an explicit signal:
    * ruled_out signal -> ``benign_closure``
    * explicit closure SNOMED (discharge from oncology, remission,
      death) recognised through the closure-signal predicate -> ``closed``

  This mirrors how a clinician keeps a cancer episode active through
  routine follow-up. Earlier behaviour clipped end_date to the last
  same-site signal, which silently dropped follow-up encounters from
  the manually-reviewed breast episode for patient 4920262426.

- benign_closure: True iff a result-channel signal with intent
  ``ruled_out`` is present and there is no later confirmed signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .aggregator import AggregatedCandidate
from .types import Signal, TimelineEvent


@dataclass
class EpisodeBoundary:
    start_date: date | None
    end_date: date | None
    status: str  # "open" | "closed" | "benign_closure"
    intent: str  # "suspected" | "confirmed" | "ruled_out"


# Roles that explicitly close an episode when emitted as a signal.
# Today only "outcome" signals close (the lab/imaging interpretation
# layer), but additional explicit closure SNOMEDs (discharge from
# clinic, remission, death) can be added here without touching the
# runner.
_EXPLICIT_CLOSURE_INTENTS = {"ruled_out"}


def _is_explicit_closure(sig: Signal) -> bool:
    if sig.intent in _EXPLICIT_CLOSURE_INTENTS:
        return True
    return False


def detect_boundary(
    aggregated: AggregatedCandidate,
    events: list[TimelineEvent],
) -> EpisodeBoundary:
    cand = aggregated.candidate
    event_by_id = {evt.encounter_id: evt for evt in events}
    relevant_dates: list[date] = []
    confirmed_dates: list[date] = []
    ruled_out_dates: list[date] = []
    explicit_closure_dates: list[date] = []

    for sig_list in aggregated.signals_by_channel.values():
        for sig in sig_list:
            evt = event_by_id.get(sig.encounter_id)
            if evt is None:
                continue
            relevant_dates.append(evt.occurred_on)
            if sig.intent == "confirmed":
                confirmed_dates.append(evt.occurred_on)
            elif sig.intent == "ruled_out":
                ruled_out_dates.append(evt.occurred_on)
            if _is_explicit_closure(sig):
                explicit_closure_dates.append(evt.occurred_on)

    start = min(relevant_dates) if relevant_dates else cand.anchor_date

    intent = cand.intent_hint or "suspected"
    if confirmed_dates:
        intent = "confirmed"
    elif ruled_out_dates and not confirmed_dates:
        intent = "ruled_out"

    if intent == "ruled_out":
        # benign closure: episode terminates at the ruled_out date.
        status = "benign_closure"
        end = max(ruled_out_dates) if ruled_out_dates else None
    elif confirmed_dates:
        # confirmed cancer episode -- only close if we observed an
        # explicit closure signal AFTER the latest confirmed signal.
        last_confirmed = max(confirmed_dates)
        post_closure = [
            d for d in explicit_closure_dates if d >= last_confirmed
        ]
        if post_closure:
            status = "closed"
            end = max(post_closure)
        else:
            status = "open"
            end = None
    else:
        # suspected only -- stay open; the curator will close it.
        status = "open"
        end = None

    return EpisodeBoundary(
        start_date=start,
        end_date=end,
        status=status,
        intent=intent,
    )
