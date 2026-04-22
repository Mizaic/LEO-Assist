"""Core closure rules shared across all sites.

Atlas trace:
  DI: DI-FA3CE229 (runtime loader + bundle)
  DI: DI-AC6838DD (gold regression gate depends on deterministic closure)

Some closure signals are site-agnostic (a deceased patient closes every
episode; a long period of inactivity closes every episode; an explicit
discharge from the cancer service closes every episode). Keeping those
in code rather than in each per-site rulebook means:

  1. They cannot drift between sites.
  2. They never need per-site Clinical Safety Officer sign-off.
  3. A new site rulebook inherits them automatically by setting
     ``closure.use_core_closure_set = true``.

This module is intentionally small and side-effect free. Callers pass
in the same raw encounter/event shapes the detector already uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Mapping


# Long post-referral quiet window after which an episode is considered
# stale and closed as benign if no confirmed code landed. 180 days
# matches NICE NG12's upper bound for a diagnostic pathway completing.
DEFAULT_INACTIVITY_CLOSE_DAYS = 180


# SNOMED codes that always close any cancer episode regardless of site.
# These are strictly administrative / clinical states, not site-specific
# findings. They are kept here (not per-site) so a new site rulebook
# cannot accidentally drop them.
CORE_CLOSURE_SNOMED: frozenset[str] = frozenset(
    {
        # Discharge from service
        "308283009",   # Discharged from service
        "183665008",   # Discharged from care
        # Refused / declined
        "266757004",   # Procedure declined by patient
        "416098002",   # Drug therapy declined by patient
    }
)


# SNOMED codes that indicate death. If any of these appear on an
# encounter timeline the episode closes as 'closed_deceased' regardless
# of any site-specific signals. Kept here so the rule ships with the
# detector binary and does not need per-site sign-off.
DECEASED_SNOMED: frozenset[str] = frozenset(
    {
        "419099009",   # Dead
        "397709008",   # Patient died
    }
)


@dataclass(frozen=True)
class CoreClosureDecision:
    """The outcome of running the core (site-agnostic) closure check."""

    should_close: bool
    status: str | None  # 'closed_deceased' | 'closed_discharged' | 'closed_inactive' | None
    reason: str | None
    closure_at: datetime | None


def evaluate_core_closure(
    *,
    encounters: Iterable[Mapping[str, object]],
    now: datetime,
    inactivity_days: int = DEFAULT_INACTIVITY_CLOSE_DAYS,
) -> CoreClosureDecision:
    """Return the site-agnostic closure decision for an episode.

    The caller passes a flat iterable of encounter dicts, each with
    ``encounter_date`` (datetime) and ``coded_snomed`` (iterable of
    concept ids). ``now`` is the reference datetime used for the
    inactivity window; tests pass a fixed value so the function is
    hermetic.
    """

    # Materialise once so we can make multiple passes (deceased beats
    # discharge beats inactivity, and any of them beats "still open").
    encs = list(encounters)

    deceased_hit = _first_coded_match(encs, DECEASED_SNOMED)
    if deceased_hit is not None:
        return CoreClosureDecision(
            should_close=True,
            status="closed_deceased",
            reason="Deceased patient SNOMED on timeline",
            closure_at=_coerce_datetime(deceased_hit.get("encounter_date")),
        )

    discharge_hit = _first_coded_match(encs, CORE_CLOSURE_SNOMED)
    if discharge_hit is not None:
        return CoreClosureDecision(
            should_close=True,
            status="closed_discharged",
            reason="Core discharge / decline SNOMED on timeline",
            closure_at=_coerce_datetime(discharge_hit.get("encounter_date")),
        )

    last_seen: datetime | None = None
    for enc in encs:
        enc_dt = _coerce_datetime(enc.get("encounter_date"))
        if enc_dt is not None and (last_seen is None or enc_dt > last_seen):
            last_seen = enc_dt

    if last_seen is not None and now - last_seen > timedelta(days=inactivity_days):
        return CoreClosureDecision(
            should_close=True,
            status="closed_inactive",
            reason=(
                f"No activity for >{inactivity_days} days "
                f"(last seen {last_seen.date().isoformat()})"
            ),
            closure_at=last_seen,
        )

    return CoreClosureDecision(
        should_close=False,
        status=None,
        reason=None,
        closure_at=None,
    )


def _first_coded_match(
    encounters: Iterable[Mapping[str, object]],
    target: frozenset[str],
) -> Mapping[str, object] | None:
    for enc in encounters:
        for cid in enc.get("coded_snomed") or ():
            if str(cid) in target:
                return enc
    return None


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None
