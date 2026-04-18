"""Same-day same-event milestone collapse (Pattern N2).

DI-LEO-AI-403 / DO-LEO-AI-403 / R-LEO-AI-403 / VT-LEO-AI-403.

A single referral decision can leave multiple Encounter records on the
same date inside a single EpisodeOfCare:

    - the GP's clinical encounter that documents the decision
      ("Refer 2ww breast for further investigation"); subtype
      ``text_generic``
    - the structured PRISM 2WW questionnaire completed at the same
      time by the same GP ("PRISM 2WW Breast Female questionnaire
      ... Fast track referral for suspected breast cancer (XaMeC)");
      subtype ``prism``
    - a back-dated medical-secretary admin record tracking the
      referral booking ("Fast track referral for suspected breast
      cancer (XaMeC) ... Patient awaiting OPD appt."); subtype
      ``text_generic``

Patient 4802892365 had three such referral anchors on 2025-03-26
attached to the real breast-cancer episode 1ecfb55618c2a6d2 -- one
``prism`` and two ``text_generic``. The episode timeline therefore
showed three "referral" milestones on a single day, all describing
the same single 2WW decision. This inflates referral-count
analytics, confuses pathway-explorer investigations, and erodes
reviewer trust.

Pattern N2 collapses these by selecting ONE representative anchor
per (episode, milestone_type, encounter_date) tuple. Selection
priority is by ``referral_subtype`` (highest fidelity first):

    1. ``prism``        -- structured 2WW form, machine-coded fields
    2. ``form_field``   -- generic structured proforma
    3. ``text_generic`` -- free-text mention only
    4. anything else / missing subtype

Within the same tier the anchor with the earliest ``created_at`` is
kept; ties are broken by stable input order.

Safety design
-------------
- The collapse is intentionally narrow: it only acts WITHIN a
  single episode's link-group list, and only on milestone_types
  that we have explicitly opted in (currently ``referral`` only).
- Genuine multi-referral episodes (e.g. a GP refers to dermatology
  AND a separate breast clinic on the same day) are unaffected --
  those anchors live in DIFFERENT site_keys and therefore in
  different episodes' link-group lists.
- A genuine SAME-SITE same-day re-referral (rare: e.g. emergency
  hospital re-issues the same 2WW after a GP referral that morning)
  is collapsed -- the patient's pathway sees one logical "first
  referral" event regardless. This is the intended behaviour: the
  duplicate is operational noise, not a clinical signal.
- Dropped anchors lose only the IS_PART_OF "referral" edge; the
  underlying Encounter node is unaffected and remains visible in
  the patient's encounter list. Search, coding, and other downstream
  consumers see all encounters; only the EpisodeOfCare timeline is
  cleaned up.
"""

from __future__ import annotations

from typing import Any, Iterable

# DI-LEO-AI-403 (Pattern N2): referral subtype priority order. Lower
# index == higher fidelity == kept when collapsing. Subtypes not in
# this list (or missing) fall to the lowest priority and are dropped
# in favour of any listed subtype on the same date.
REFERRAL_SUBTYPE_PRIORITY: tuple[str, ...] = (
    "prism",
    "form_field",
    "text_generic",
)

_DEFAULT_COLLAPSE_MILESTONE_TYPES: frozenset[str] = frozenset({"referral"})


def _referral_subtype_rank(subtype: str | None) -> int:
    """Return priority rank for a referral subtype.

    Lower number == higher fidelity (kept). Unknown / empty subtypes
    return one past the end of the priority list so they always
    lose to any listed subtype.
    """
    if not subtype:
        return len(REFERRAL_SUBTYPE_PRIORITY)
    try:
        return REFERRAL_SUBTYPE_PRIORITY.index(subtype)
    except ValueError:
        return len(REFERRAL_SUBTYPE_PRIORITY)


def _anchor_date_key(anchor: dict[str, Any]) -> str:
    """Stable string key for an anchor's encounter date."""
    return str(anchor.get("encounter_date") or "")


def _anchor_created_at(anchor: dict[str, Any]) -> str:
    """Stable string key for an anchor's created_at timestamp.

    Empty string sorts first so anchors without a timestamp do not
    accidentally lose to ones that have one.
    """
    return str(anchor.get("created_at") or "")


def _select_representative(
    candidates: list[tuple[int, dict[str, Any]]],
) -> dict[str, Any]:
    """Select the highest-fidelity anchor from a candidate group.

    Each candidate is a ``(input_index, anchor)`` tuple. Sort key:
    ``(subtype_rank, created_at, input_index)``. The first entry
    after sorting is the representative.
    """
    candidates.sort(
        key=lambda item: (
            _referral_subtype_rank(item[1].get("referral_subtype")),
            _anchor_created_at(item[1]),
            item[0],
        )
    )
    return candidates[0][1]


def collapse_same_day_referrals(
    link_groups: list[tuple[list[dict[str, Any]], str]],
    *,
    milestone_types: Iterable[str] = _DEFAULT_COLLAPSE_MILESTONE_TYPES,
) -> list[tuple[list[dict[str, Any]], str]]:
    """Collapse same-date anchors per opted-in milestone type.

    For each ``(anchors, milestone_type)`` group whose
    ``milestone_type`` is in ``milestone_types``, keep at most one
    representative anchor per ``encounter_date``. Anchors with no
    ``encounter_date`` are passed through untouched (we never
    silently drop a dateless anchor -- safer to leave it for
    downstream visibility).

    Groups whose milestone_type is NOT in ``milestone_types`` are
    returned unchanged. The function is pure and does not mutate
    the input list or its anchor dicts.

    Args:
        link_groups: list of ``(anchors, milestone_type)`` tuples
            as produced by ``_filter_unclaimed_link_groups`` in the
            episode builder.
        milestone_types: collection of milestone_type strings to
            opt into. Default: ``{"referral"}``.

    Returns:
        New list of ``(anchors, milestone_type)`` tuples with same-
        day duplicates collapsed for the opted-in milestone types.
    """
    target = frozenset(milestone_types)
    out: list[tuple[list[dict[str, Any]], str]] = []
    for anchor_list, milestone_type in link_groups:
        if milestone_type not in target:
            out.append((anchor_list, milestone_type))
            continue

        if not anchor_list:
            out.append((anchor_list, milestone_type))
            continue

        by_date: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        no_date: list[dict[str, Any]] = []
        for idx, anchor in enumerate(anchor_list):
            date_key = _anchor_date_key(anchor)
            if not date_key:
                no_date.append(anchor)
                continue
            by_date.setdefault(date_key, []).append((idx, anchor))

        kept: list[dict[str, Any]] = []
        for date_key in sorted(by_date.keys()):
            kept.append(_select_representative(by_date[date_key]))
        kept.extend(no_date)

        out.append((kept, milestone_type))

    return out


__all__ = [
    "REFERRAL_SUBTYPE_PRIORITY",
    "collapse_same_day_referrals",
]
