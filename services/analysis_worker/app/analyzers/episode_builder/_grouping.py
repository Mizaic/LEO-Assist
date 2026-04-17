"""Grouping algorithms: diagnosis-led grouping, specialist claiming, phantom detection."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from . import _config as cfg
from ._types import _EpisodeSpec, _SpecialistClaim, _parse_date
from ._site_resolution import _extract_condition_key_from_anchor, _site_keys_compatible


def _group_referrals_by_time(
    anchors: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Split same-site referral anchors (sorted by date) into time-window groups."""
    if not anchors:
        return []
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = [anchors[0]]
    prev_date = _parse_date(anchors[0].get("encounter_date"))

    for anchor in anchors[1:]:
        this_date = _parse_date(anchor.get("encounter_date"))
        if this_date and prev_date:
            gap = (this_date - prev_date).days
            if gap > cfg.SAME_EPISODE_DAYS:
                groups.append(current)
                current = []
        current.append(anchor)
        if this_date:
            prev_date = this_date

    groups.append(current)
    return groups


def _claim_specialists_for_episodes(
    specialist_anchors: list[dict[str, Any]],
    specs: list[_EpisodeSpec],
) -> dict[str, _SpecialistClaim]:
    """Claim each specialist visit for at most one episode.

    Each visit goes to the earliest-referral episode whose site key
    is compatible and whose window contains the visit date.
    """
    claims: dict[str, _SpecialistClaim] = {s.ep_id: _SpecialistClaim() for s in specs}
    if not specialist_anchors or not specs:
        return claims

    sorted_visits = sorted(
        specialist_anchors,
        key=lambda a: str(a.get("encounter_date") or ""),
    )
    claimed: set[int] = set()
    ordered_specs = sorted(specs, key=lambda s: s.ref_date or date.min)

    for spec in ordered_specs:
        if spec.ref_date is None:
            continue
        for idx, visit in enumerate(sorted_visits):
            if idx in claimed:
                continue
            v_date = _parse_date(visit.get("encounter_date"))
            if not v_date:
                continue
            if v_date < spec.ref_date or v_date > spec.window_end:
                continue
            v_key = _extract_condition_key_from_anchor(visit)
            if not _site_keys_compatible(spec.site_key, v_key):
                continue
            claimed.add(idx)
            claims[spec.ep_id] = _SpecialistClaim(
                specialist_seen=True,
                specialist_visit_date=str(visit.get("encounter_date") or "") or None,
                referral_site_name=str(visit.get("concept_name") or ""),
            )
            break

    return claims


def _find_best_referral(
    diag_date: date,
    diag_key: str,
    sorted_ref: list[dict[str, Any]],
    claimed: set[int],
) -> tuple[int, date] | None:
    """Return (index, ref_date) of the closest unclaimed same-site referral."""
    best_idx: int | None = None
    best_gap = timedelta(days=cfg.DIAG_LOOKBACK_DAYS + 1)
    best_date: date | None = None
    for idx, ref in enumerate(sorted_ref):
        if idx in claimed:
            continue
        r_date = _parse_date(ref.get("encounter_date"))
        if not r_date:
            continue
        gap = diag_date - r_date
        if gap < timedelta(0) or gap > timedelta(days=cfg.DIAG_LOOKBACK_DAYS):
            continue
        # DI-LEO-AI-124: require a minimum plausible gap so diagnosis-
        # encounter text containing fast-track language is not picked
        # up as a fresh referral. Candidates inside the gap are
        # skipped; diagnosis-led grouping then looks further back.
        if gap < timedelta(days=cfg.MIN_REFERRAL_TO_DIAG_DAYS):
            continue
        ref_key = _extract_condition_key_from_anchor(ref)
        if (
            diag_key not in ("unknown",)
            and ref_key != diag_key
            and ref_key != "non_site_specific"
        ):
            continue
        if gap < best_gap:
            best_gap = gap
            best_idx = idx
            best_date = r_date
    if best_idx is None or best_date is None:
        return None
    return best_idx, best_date


def _claim_window_referrals(
    sorted_ref: list[dict[str, Any]],
    claimed: set[int],
    diag_key: str,
    diag_date: date,
    primary_idx: int,
) -> list[dict[str, Any]]:
    """Collect the primary referral plus any other unclaimed same-site referrals
    that fall within the lookback window of this diagnosis."""
    claimed.add(primary_idx)
    result = [sorted_ref[primary_idx]]
    for idx, ref in enumerate(sorted_ref):
        if idx == primary_idx or idx in claimed:
            continue
        r_date = _parse_date(ref.get("encounter_date"))
        if not r_date:
            continue
        ref_key = _extract_condition_key_from_anchor(ref)
        site_match = (
            diag_key == "unknown"
            or ref_key == diag_key
            or ref_key == "non_site_specific"
        )
        if not site_match:
            continue
        gap = diag_date - r_date
        if timedelta(0) <= gap <= timedelta(days=cfg.DIAG_LOOKBACK_DAYS):
            result.append(ref)
            claimed.add(idx)
    result.sort(key=lambda a: str(a.get("encounter_date") or ""))
    return result


def _group_open_referrals(
    unclaimed: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Group unclaimed referrals into in-progress episodes by site and time."""
    by_site: dict[str, list[dict[str, Any]]] = {}
    for ref in unclaimed:
        key = _extract_condition_key_from_anchor(ref)
        by_site.setdefault(key, []).append(ref)
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for site_key, refs in by_site.items():
        refs.sort(key=lambda a: str(a.get("encounter_date") or ""))
        for group in _group_referrals_by_time(refs):
            groups.append((site_key, group))
    return groups


def _build_diagnosis_led_groups(
    referral_anchors: list[dict[str, Any]],
    diagnosis_anchors: list[dict[str, Any]],
) -> tuple[
    list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]],
    list[tuple[str, list[dict[str, Any]]]],
]:
    """Diagnosis-first grouping: each diagnosis claims its nearest preceding
    referral.  Returns (closed_groups, open_groups)."""
    sorted_diag = sorted(
        diagnosis_anchors,
        key=lambda a: (
            1 if a.get("is_pathway_completion") else 0,
            str(a.get("encounter_date") or ""),
        ),
    )
    sorted_ref = sorted(
        referral_anchors, key=lambda a: str(a.get("encounter_date") or "")
    )
    claimed: set[int] = set()
    ref_keyed: dict[str, tuple[str, list[dict[str, Any]], list[dict[str, Any]]]] = {}
    floating: dict[str, list[dict[str, Any]]] = {}

    for diag in sorted_diag:
        d_date = _parse_date(diag.get("encounter_date"))
        if not d_date:
            continue
        diag_key = _extract_condition_key_from_anchor(diag)
        match = _find_best_referral(d_date, diag_key, sorted_ref, claimed)
        if match:
            primary_idx, _ = match
            refs = _claim_window_referrals(
                sorted_ref, claimed, diag_key, d_date, primary_idx
            )
            ref_key = _extract_condition_key_from_anchor(refs[0]) if refs else "unknown"
            if diag_key not in ("unknown", "non_site_specific"):
                site_key = diag_key
            elif ref_key not in ("unknown",):
                site_key = ref_key
            else:
                site_key = diag_key

            ref_anchor_date = str(refs[0].get("encounter_date") or "")
            group_key = f"{site_key}|{ref_anchor_date}"
            if group_key in ref_keyed:
                sk, existing_refs, existing_diags = ref_keyed[group_key]
                ref_keyed[group_key] = (sk, existing_refs, existing_diags + [diag])
            else:
                ref_keyed[group_key] = (site_key, refs, [diag])
        else:
            floating.setdefault(diag_key, []).append(diag)

    floating_groups: list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]] = []
    for site_key, diags in floating.items():
        diags.sort(key=lambda a: str(a.get("encounter_date") or ""))
        for time_group in _group_referrals_by_time(diags):
            floating_groups.append((site_key, [], time_group))

    closed_groups = list(ref_keyed.values()) + floating_groups
    unclaimed = [ref for idx, ref in enumerate(sorted_ref) if idx not in claimed]
    open_groups = _group_open_referrals(unclaimed)
    return closed_groups, open_groups


def _detect_phantom_sites(
    referrals_by_site: dict[str, list[dict[str, Any]]],
) -> set[str]:
    """Return site keys whose referrals come ONLY from multi-referral encounters."""
    encounter_to_sites: dict[str, set[str]] = {}
    for site_key, anchors in referrals_by_site.items():
        for anchor in anchors:
            eid = str(anchor.get("encounter_id") or "")
            if eid:
                encounter_to_sites.setdefault(eid, set()).add(site_key)

    multi_ref_encounters = {
        eid for eid, sites in encounter_to_sites.items() if len(sites) > 1
    }
    if not multi_ref_encounters:
        return set()

    phantom_sites: set[str] = set()
    site_referral_counts = {
        sk: len(anchors) for sk, anchors in referrals_by_site.items()
    }

    for site_key, anchors in referrals_by_site.items():
        eids = {
            str(a.get("encounter_id") or "") for a in anchors if a.get("encounter_id")
        }
        if not eids or not eids.issubset(multi_ref_encounters):
            continue
        for eid in eids:
            sibling_sites = encounter_to_sites.get(eid, set()) - {site_key}
            dominant = any(
                site_referral_counts.get(s, 0) > site_referral_counts.get(site_key, 0)
                for s in sibling_sites
            )
            if dominant:
                phantom_sites.add(site_key)
                break

    return phantom_sites
