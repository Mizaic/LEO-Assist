"""Per-site rulebook retrainer seeded by CorrectionEvent rows.

Atlas trace:
  DI: DI-D983C6EE (per-site rulebook retrain from correction events)
  Mitigates: R-94D0D086 (rulebook drift regressing episode accuracy)

Pipeline::

  CorrectionEvent stream  ->  pattern_miner.propose_candidate()
                             (per-site, PII-safe, produces SiteRulebook)
                             ->  registry.register()
                             ->  promote_to_champion (gold-gated)

Design notes
------------

The miner never auto-promotes. Its output is a candidate rulebook in
state REGISTERED. Promotion is gated by the per-site gold VT pass
(see ``libs/episode_detector/registry.py``).

The miner is pure on its inputs so it can be unit-tested without
touching Neo4j or Atlas. It calls ``validate_no_pii`` on every
candidate before returning, so any 7+ digit string that looks like
an NHS number is rejected defensively (belt-and-braces -- the audit
capture layer already de-ids but we double-check here).

This first-pass miner handles three correction shapes:

  1. **attach with new suspected/confirmed SNOMED** -> add to
     ``anchors.suspected_snomed`` or ``anchors.confirmed_snomed``.
  2. **attach with new referral SNOMED** -> add to
     ``anchors.referral_snomed``.
  3. **detach with SNOMED removed** -> add to ``cross_site_guard``.

Finer-grained learning (regex, thresholds, windows) is deferred
until we have more than three gold patients. The output already
tracks counts and sources so the next iteration can expand without
changing the contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from libs.episode_detector.rulebook import (
    SiteRulebook,
    validate_no_pii,
)
from libs.episode_learning.correction_capture import CorrectionEvent

# Accepts only conservative SNOMED shapes (6-18 digits) so we do not
# accidentally absorb a 10-digit NHS number. The PII validator then
# runs as the final gate before emission.
_SNOMED_RE = re.compile(r"^\d{6,18}$")

# Correction targets that plausibly carry code-level information.
_CODE_TARGETS = frozenset(
    {"detector_boundary", "coding_decision", "canonical_code"}
)

# Event types that count as "attach" vs "detach" for the miner.
_ATTACH_TYPES = frozenset(
    {"episodemanualattach", "episode_manual_attach"}
)
_DETACH_TYPES = frozenset(
    {"episodemanualdetach", "episode_manual_detach"}
)


@dataclass(frozen=True)
class MinerResult:
    """Outcome of a per-site mining run.

    ``candidate_rulebook`` is None when the events yielded no
    actionable signal (for example all events were ``other`` target,
    or the site had zero events). ``reason`` explains that outcome
    in UK-English plain language so the CLI / ops can surface it
    directly.
    """

    site_key: str
    candidate_rulebook: SiteRulebook | None
    added_suspected: tuple[str, ...] = ()
    added_referral: tuple[str, ...] = ()
    added_confirmed: tuple[str, ...] = ()
    added_cross_site_guard: tuple[str, ...] = ()
    events_considered: int = 0
    events_with_signal: int = 0
    reason: str = ""
    source_audit_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class _Buckets:
    """Accumulators for the per-site mining pass."""

    suspected: set[str] = field(default_factory=set)
    referral: set[str] = field(default_factory=set)
    confirmed: set[str] = field(default_factory=set)
    cross_site_guard: set[str] = field(default_factory=set)
    audit_ids: list[str] = field(default_factory=list)


def propose_candidate(
    events: Iterable[CorrectionEvent],
    *,
    baseline: SiteRulebook,
    next_version: str,
    site_key: str | None = None,
) -> MinerResult:
    """Propose a candidate SiteRulebook from correction events.

    The baseline is the current champion (or a v0/v1 rulebook during
    bootstrap). The site_key argument lets callers pass it explicitly;
    if omitted we take it from the baseline.

    The returned candidate always has ``rulebook_version=next_version``
    so the registry can tell iterations apart. Every candidate is
    re-validated for PII before it leaves this function.
    """

    resolved_site = (site_key or baseline.site_key).strip().lower()
    scope_events = [e for e in events if e.site_key == resolved_site]
    if not scope_events:
        return MinerResult(
            site_key=resolved_site,
            candidate_rulebook=None,
            reason=f"no correction events for site {resolved_site!r}",
        )

    buckets = _collect_buckets(scope_events, baseline)
    any_signal = (
        buckets.suspected
        or buckets.referral
        or buckets.confirmed
        or buckets.cross_site_guard
    )
    if not any_signal:
        return MinerResult(
            site_key=resolved_site,
            candidate_rulebook=None,
            events_considered=len(scope_events),
            events_with_signal=0,
            reason=(
                "correction events had no new SNOMEDs over the baseline; "
                "nothing to mine"
            ),
        )

    candidate = _apply_buckets(baseline, buckets, next_version)
    validate_no_pii(candidate)
    return MinerResult(
        site_key=resolved_site,
        candidate_rulebook=candidate,
        added_suspected=tuple(sorted(buckets.suspected)),
        added_referral=tuple(sorted(buckets.referral)),
        added_confirmed=tuple(sorted(buckets.confirmed)),
        added_cross_site_guard=tuple(sorted(buckets.cross_site_guard)),
        events_considered=len(scope_events),
        events_with_signal=len(buckets.audit_ids),
        reason=(
            f"mined {len(buckets.audit_ids)} events; "
            f"added suspected={len(buckets.suspected)}, "
            f"referral={len(buckets.referral)}, "
            f"confirmed={len(buckets.confirmed)}, "
            f"guards={len(buckets.cross_site_guard)}"
        ),
        source_audit_ids=tuple(buckets.audit_ids),
    )


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _collect_buckets(
    events: list[CorrectionEvent], baseline: SiteRulebook
) -> _Buckets:
    buckets = _Buckets()
    known_anchors = _baseline_anchor_codes(baseline)
    known_guards = set(baseline.cross_site_guard)

    for event in events:
        if event.label != 1:
            continue
        event_type = event.event_type.strip().lower()
        is_attach = event_type in _ATTACH_TYPES
        is_detach = event_type in _DETACH_TYPES
        if not (is_attach or is_detach):
            continue

        category = _infer_category(event)

        if is_attach and event.correction_target not in _CODE_TARGETS:
            continue
        if is_detach and event.correction_target not in _CODE_TARGETS:
            continue

        after = event.context.get("after", {}) or {}
        before = event.context.get("before", {}) or {}

        if is_attach:
            added_any = _absorb_attach(
                after, before, category, buckets, known_anchors
            )
            if added_any:
                buckets.audit_ids.append(event.audit_id)
        elif is_detach:
            added_any = _absorb_detach(
                before, after, buckets, known_guards
            )
            if added_any:
                buckets.audit_ids.append(event.audit_id)

    return buckets


def _baseline_anchor_codes(baseline: SiteRulebook) -> set[str]:
    a = baseline.anchors
    return (
        set(a.referral_snomed)
        | set(a.clinic_seen_snomed)
        | set(a.suspected_snomed)
        | set(a.confirmed_snomed)
    )


def _infer_category(event: CorrectionEvent) -> str:
    """Map a correction's target + context hints to a bucket.

    ``coding_decision`` events with a ``primary_code_kind == "confirmed"``
    land in the confirmed bucket; ``canonical_code`` events with a
    ``code_kind == "referral"`` land in referral; everything else in
    that family lands in suspected. This stays conservative: anything
    ambiguous goes to suspected, where the worst case is a slightly
    fuzzier anchor rather than a false-positive confirmed diagnosis.
    """
    after = event.context.get("after", {}) or {}
    kind = str(
        after.get("code_kind")
        or after.get("primary_code_kind")
        or ""
    ).strip().lower()
    if kind == "confirmed":
        return "confirmed"
    if kind == "referral":
        return "referral"
    return "suspected"


def _absorb_attach(
    after: Mapping[str, object],
    before: Mapping[str, object],
    category: str,
    buckets: _Buckets,
    known_anchors: set[str],
) -> bool:
    codes = _extract_snomed_codes(after) - _extract_snomed_codes(before)
    new_codes = {c for c in codes if c not in known_anchors}
    if not new_codes:
        return False
    target = {
        "confirmed": buckets.confirmed,
        "referral": buckets.referral,
        "suspected": buckets.suspected,
    }[category]
    target.update(new_codes)
    return True


def _absorb_detach(
    before: Mapping[str, object],
    after: Mapping[str, object],
    buckets: _Buckets,
    known_guards: set[str],
) -> bool:
    removed = _extract_snomed_codes(before) - _extract_snomed_codes(after)
    new_guards = {c for c in removed if c not in known_guards}
    if not new_guards:
        return False
    buckets.cross_site_guard.update(new_guards)
    return True


def _extract_snomed_codes(snapshot: Mapping[str, object]) -> set[str]:
    """Pull SNOMED-shaped codes out of an audit snapshot.

    Only known keys are read -- we never scan free-text. Anything that
    is not a pure digit string of plausible SNOMED length is dropped.
    """
    keys = (
        "snomed_codes",
        "encounter_codes",
        "primary_code",
        "codes",
    )
    found: set[str] = set()
    for key in keys:
        value = snapshot.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            if _SNOMED_RE.match(value):
                found.add(value)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                if isinstance(item, str) and _SNOMED_RE.match(item):
                    found.add(item)
    return found


def _apply_buckets(
    baseline: SiteRulebook, buckets: _Buckets, next_version: str
) -> SiteRulebook:
    from dataclasses import replace

    anchors = replace(
        baseline.anchors,
        referral_snomed=_extend(
            baseline.anchors.referral_snomed, buckets.referral
        ),
        suspected_snomed=_extend(
            baseline.anchors.suspected_snomed, buckets.suspected
        ),
        confirmed_snomed=_extend(
            baseline.anchors.confirmed_snomed, buckets.confirmed
        ),
    )
    new_guard = _extend(baseline.cross_site_guard, buckets.cross_site_guard)
    return replace(
        baseline,
        rulebook_version=next_version,
        anchors=anchors,
        cross_site_guard=new_guard,
    )


def _extend(existing: tuple[str, ...], additions: set[str]) -> tuple[str, ...]:
    """Deterministic, de-duplicated merge preserving baseline order."""
    out: list[str] = list(existing)
    seen = set(existing)
    for code in sorted(additions):
        if code not in seen:
            out.append(code)
            seen.add(code)
    return tuple(out)
