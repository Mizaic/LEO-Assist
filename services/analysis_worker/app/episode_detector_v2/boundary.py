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
  the manually-reviewed breast episode for patient 9990001004.

- benign_closure: True iff a result-channel signal with intent
  ``ruled_out`` is present and there is no later confirmed signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from ._rulebook_adapter import (
    benign_closure_no_confirmed_days,
    completed_closure_tokens,
    completed_quiet_window_days,
)
from .aggregator import AggregatedCandidate
from .site_keys import BREAST_SNOMED_CONFIRMED, SITE_BREAST
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


def _is_boundary_signal(sig: Signal) -> bool:
    """Return True for signals allowed to define episode boundaries."""
    if sig.role == "context_milestone":
        return False
    return sig.channel in {"code", "pathway", "result", "treatment"}


def _is_explicit_closure(sig: Signal) -> bool:
    if sig.intent in _EXPLICIT_CLOSURE_INTENTS:
        return True
    return False


def _completed_snomed_for(site_key: str) -> frozenset[str]:
    """Extract the SNOMED concept ids referenced by the site's
    ``closure.completed.requires_any_of`` rule. Tokens shaped as
    ``snomed:<id>`` are promoted to the id set; non-SNOMED tokens are
    dropped (they'd only fire via other branches of the boundary).
    """
    ids: set[str] = set()
    for token in completed_closure_tokens(site_key):
        if not isinstance(token, str):
            continue
        t = token.strip()
        if t.startswith("snomed:"):
            ids.add(t[len("snomed:"):])
    return frozenset(ids)


def _dates_with_completed_snomed(
    site_key: str,
    events: Iterable[TimelineEvent],
    target_events: set[str],
) -> list[date]:
    """Return the dates of the encounters in ``target_events`` that
    carry at least one SNOMED listed in the site's completed-closure
    rule. Used to detect explicit completion (e.g. "discharged from
    oncology with remission") that does not flow through a ruled_out
    signal.
    """
    completed_codes = _completed_snomed_for(site_key)
    if not completed_codes:
        return []
    found: list[date] = []
    for evt in events:
        if evt.encounter_id not in target_events:
            continue
        for code in evt.coded_entities:
            cid = str(code.get("concept_id") or "").strip()
            if cid and cid in completed_codes:
                found.append(evt.occurred_on)
                break
    return found


def _has_post_benign_cancer_mention(
    *,
    site_key: str,
    events: Iterable[TimelineEvent],
    after: date,
) -> bool:
    """Return True if the later record contradicts a benign closure."""
    if site_key != SITE_BREAST:
        return False
    for evt in events:
        if evt.occurred_on <= after:
            continue
        if _has_confirmed_breast_code(evt) or _has_breast_cancer_history_text(evt):
            return True
    return False


def _has_confirmed_breast_code(event: TimelineEvent) -> bool:
    for code in event.coded_entities:
        concept_id = str(code.get("concept_id") or "").strip()
        if concept_id in BREAST_SNOMED_CONFIRMED:
            return True
    return False


def _has_breast_cancer_history_text(event: TimelineEvent) -> bool:
    text = " ".join((event.text_snippet or "").lower().split())
    if not text:
        return False
    if "family history" in text or "fhx" in text or "no history of breast cancer" in text:
        return False
    cancer_terms = (
        "breast cancer",
        "breast ca",
        "carcinoma of breast",
        "invasive carcinoma of breast",
        "infiltrating duct carcinoma",
        "malignant neoplasm of breast",
        "malignant tumour of breast",
    )
    context_terms = (
        "problem:",
        "major:",
        "history of",
        "past medical history",
        "pmh",
        "following treatment for",
        "diagnosed with",
    )
    return any(term in text for term in cancer_terms) and any(
        term in text for term in context_terms
    )


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
            if not _is_boundary_signal(sig):
                continue
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

    # Augment explicit-closure dates with completed-closure SNOMEDs
    # from the site's rulebook (e.g. "in remission", "discharged from
    # oncology"). These do not always flow through a ruled_out signal
    # because they are not benign investigation results.
    scoped_events = {
        sig.encounter_id
        for sig_list in aggregated.signals_by_channel.values()
        for sig in sig_list
        if _is_boundary_signal(sig)
    }
    completed_dates = _dates_with_completed_snomed(
        cand.site_key, events, scoped_events
    )
    explicit_closure_dates.extend(completed_dates)
    # A completed-closure code is also an "intent=ruled_out-equivalent"
    # outcome for boundary purposes when no confirmed signal survives
    # it. We count those dates as ruled_out so suspected-only episodes
    # without any confirmation flip to benign_closure correctly.
    if completed_dates:
        ruled_out_dates.extend(completed_dates)

    start = min(relevant_dates) if relevant_dates else cand.anchor_date

    intent = cand.intent_hint or "suspected"
    if confirmed_dates:
        intent = "confirmed"
    elif ruled_out_dates and not confirmed_dates:
        intent = "ruled_out"

    if intent == "ruled_out":
        # Benign closure -- but the rulebook can require a quiet
        # window after the benign signal during which no confirmed
        # signal may appear. If a confirmed arrives inside that
        # window the closure is invalidated (fail-safe: the episode
        # reopens).
        status = "benign_closure"
        end = max(ruled_out_dates) if ruled_out_dates else None
        quiet_days = benign_closure_no_confirmed_days(
            cand.site_key, fallback=0
        )
        if end is not None and quiet_days > 0 and confirmed_dates:
            horizon = end + timedelta(days=quiet_days)
            if any(end < c <= horizon for c in confirmed_dates):
                # A confirmed signal arrived inside the quiet window --
                # revert to an open confirmed episode so a curator can
                # re-triage. The coverage check will pick this up.
                intent = "confirmed"
                status = "open"
                end = None
        if end is not None and _has_post_benign_cancer_mention(
            site_key=cand.site_key,
            events=events,
            after=end,
        ):
            intent = "confirmed"
            status = "open"
            end = None
    elif confirmed_dates:
        # Confirmed cancer episode -- close only if an explicit
        # closure signal arrived after the latest confirmed signal
        # AND the rulebook's quiet window has elapsed (or is zero,
        # which is the v0 behaviour).
        last_confirmed = max(confirmed_dates)
        post_closure = [
            d for d in explicit_closure_dates if d >= last_confirmed
        ]
        quiet_days = completed_quiet_window_days(cand.site_key, fallback=0)
        if post_closure:
            closure_date = max(post_closure)
            horizon = closure_date + timedelta(days=quiet_days)
            # If another confirmed signal lands inside the quiet
            # window after the closure event, keep the episode open --
            # a clinician would.
            reopened = any(
                closure_date < c <= horizon for c in confirmed_dates
            )
            if reopened:
                status = "open"
                end = None
            else:
                status = "closed"
                end = closure_date
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
