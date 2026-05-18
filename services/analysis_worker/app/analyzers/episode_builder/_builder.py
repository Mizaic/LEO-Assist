"""Top-level episode building orchestrator.

Atlas trace:
  DO: DO-0C7A443A
  Also implements: DO-3BA98649, DO-6C398363, DO-8CCC6230
  DI: DI-080A2454, DI-6C5D77CA, DI-EE4E6477, DI-FC264BBF, DI-FF9C74E2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0C7A443A")
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult
from services.analysis_worker.app.analyzers.kpi_calculator import calculate_kpis

from . import _config as cfg
from ._auto_close import _apply_auto_close_rules, _apply_outcome_inference
from ._first_presentation import (
    _anchor_is_complaint,
    _first_presentation_from_anchors,
    _first_presentation_from_referral_context,
)
from ._grouping import (
    _build_diagnosis_led_groups,
    _claim_specialists_for_episodes,
    _detect_phantom_sites,
)
from ._lock_guard import (
    filter_link_groups,
    is_episode_fully_locked,
    load_lock_state,
)
from ._milestone_dedup import collapse_same_day_referrals
from ._persistence import (
    _benign_closure_for_episode,
    _benign_qualifier_closure_for_episode,
    _link_encounters_to_episode,
    _write_episode,
)
from ._site_resolution import (
    _extract_condition_key_from_anchor,
    _referral_route_from_concept,
    _site_keys_compatible,
)
from ._status import (
    _cancer_diag_anchors,
    _determine_episode_status,
    _has_confirmed_diagnosis,
    _has_possible_only_diagnosis,
    _infer_completed_from_specialist_letter,
)
from ._types import (
    BuildContext,
    EpisodeBuildResult,
    WriteEpisodeParams,
    _EpisodeSpec,
    _SpecialistClaim,
    _episode_id,
    _parse_date,
)


def _first_presentation_link_anchors(
    fp_anchors: list[dict[str, Any]],
    fp_date: str | None,
) -> list[dict[str, Any]]:
    """Return anchors for one selected first-presentation encounter."""
    if not fp_date:
        return []
    day = str(fp_date)[:10]
    on_day = [
        anchor
        for anchor in fp_anchors
        if str(anchor.get("encounter_date") or "").startswith(day)
        and str(anchor.get("encounter_id") or "")
    ]
    if not on_day:
        return []

    complaint_ids = [
        str(anchor.get("encounter_id") or "")
        for anchor in on_day
        if _anchor_is_complaint(anchor)
    ]
    target_id = (
        complaint_ids[0] if complaint_ids else str(on_day[0].get("encounter_id"))
    )
    if not target_id:
        return []
    return [
        anchor
        for anchor in on_day
        if str(anchor.get("encounter_id") or "") == target_id
    ]


def _episode_treatment_anchors(
    treatment_anchors: list[dict[str, Any]],
    ref_date: date | None,
    site_key: str,
) -> list[dict[str, Any]]:
    """Filter treatment anchors to those plausibly belonging to one episode."""
    out: list[dict[str, Any]] = []
    for anchor in treatment_anchors:
        t_date = _parse_date(anchor.get("encounter_date"))
        if ref_date and t_date and t_date < ref_date:
            continue
        t_key = _extract_condition_key_from_anchor(anchor)
        if t_key not in ("unknown", "non_site_specific") and not _site_keys_compatible(
            site_key, t_key
        ):
            continue
        out.append(anchor)
    out.sort(key=lambda a: str(a.get("encounter_date") or ""))
    return out


def _treatment_started_link_anchors(
    treatment_anchors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a single earliest encounter for treatment_started milestone."""
    if not treatment_anchors:
        return []
    for anchor in treatment_anchors:
        if str(anchor.get("encounter_id") or ""):
            return [anchor]
    return []


# DI-LEO-AI-171: silent-closure provenance fix. When the episode builder
# resolves an open episode to status='closed_benign' (whether via a
# benign_closure anchor, a benign-qualifier closure, or a letter-inferred
# benign), we MUST persist a benign_closure IS_PART_OF edge so the
# downstream traceability matrix and the canonical confirmed-cancer
# cohort query can distinguish 'no diagnosis recorded' from 'clinically
# resolved as not-cancer'. The earlier behaviour wrote the status
# silently and left no audit trail, producing the 77 closed_benign
# episodes with zero benign_closure milestones discovered in the
# 2026-04-17 audit.
def _benign_closure_link_anchors(
    benign_closure_anchors: list[dict[str, Any]],
    benign_date: date | None,
    ref_date: date | None,
) -> list[dict[str, Any]]:
    """Return a single earliest in-window encounter for benign_closure."""
    if not benign_closure_anchors or not benign_date:
        return []
    window_start = ref_date or date.min
    in_window: list[dict[str, Any]] = []
    for anchor in benign_closure_anchors:
        encounter_id = str(anchor.get("encounter_id") or "")
        if not encounter_id:
            continue
        a_date = _parse_date(str(anchor.get("encounter_date") or ""))
        if a_date is None:
            continue
        if window_start <= a_date <= benign_date:
            in_window.append(anchor)
    if not in_window:
        return []
    in_window.sort(key=lambda a: str(a.get("encounter_date") or ""))
    return [in_window[0]]


def _first_seen_link_anchors(
    first_seen_anchors: list[dict[str, Any]],
    ref_date: date | None,
    end_date: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """DI-LEO-AI-145: Claim first_seen anchors within episode window.

    Returns (anchors_to_link, first_seen_date_str).  An anchor is
    claimed when its date falls on or after ref_date (or any date when
    no referral) and on or before end_date + 90 days.
    """
    if not first_seen_anchors:
        return [], None
    window_start = ref_date or date.min
    try:
        window_end = (
            _parse_date(end_date) + timedelta(days=90) if end_date else date.max
        )
    except Exception:  # noqa: BLE001
        window_end = date.max
    claimed = [
        a
        for a in first_seen_anchors
        if _parse_date(str(a.get("encounter_date") or ""))
        and window_start
        <= _parse_date(str(a.get("encounter_date") or ""))  # type: ignore[operator]
        <= window_end
        and str(a.get("encounter_id") or "")
    ]
    if not claimed:
        return [], None
    first_date = min(str(a.get("encounter_date") or "")[:10] for a in claimed)
    return claimed, first_date


def _filter_unclaimed_link_groups(
    link_groups: list[tuple[list[dict[str, Any]], str]],
    claimed: set[str],
    protected_milestones: tuple[str, ...] = ("referral",),
) -> list[tuple[list[dict[str, Any]], str]]:
    """DI-LEO-AI-205 (Pattern F): drop already-claimed encounters from
    each link group. Encounters tagged with a milestone in
    ``protected_milestones`` are always kept -- the referral encounter
    is the episode's identity, not a transferable signal. Adds new
    encounter ids to the shared ``claimed`` set in place so subsequent
    episodes within the same build see them as taken.
    """
    out: list[tuple[list[dict[str, Any]], str]] = []
    for anchor_list, milestone_type in link_groups:
        kept: list[dict[str, Any]] = []
        for anchor in anchor_list:
            eid = str(anchor.get("encounter_id") or "")
            if not eid:
                kept.append(anchor)
                continue
            if eid in claimed and milestone_type not in protected_milestones:
                continue
            claimed.add(eid)
            kept.append(anchor)
        if kept:
            out.append((kept, milestone_type))
    return out


def _care_obstruction_link_anchors(
    care_obstruction_anchors: list[dict[str, Any]],
    ref_date: date | None,
    end_date: str | None,
) -> list[dict[str, Any]]:
    """DI-LEO-AI-204 (Pattern G): claim care_obstruction anchors that fall
    within an episode window so the QA UI can surface blocked pathways.

    Returns at most one anchor per encounter id (anchor-detector
    already de-duplicates) within ``[ref_date, end_date + 90 days]``.
    """
    if not care_obstruction_anchors:
        return []
    window_start = ref_date or date.min
    try:
        window_end = (
            _parse_date(end_date) + timedelta(days=90) if end_date else date.max
        )
    except Exception:  # noqa: BLE001
        window_end = date.max
    claimed: list[dict[str, Any]] = []
    for anchor in care_obstruction_anchors:
        eid = str(anchor.get("encounter_id") or "")
        if not eid:
            continue
        a_date = _parse_date(str(anchor.get("encounter_date") or ""))
        if not a_date:
            continue
        if window_start <= a_date <= window_end:
            claimed.append(anchor)
    claimed.sort(key=lambda a: str(a.get("encounter_date") or ""))
    return claimed


def _care_obstruction_hitl(
    care_links: list[dict[str, Any]],
    existing_reason: str | None,
) -> tuple[bool, str | None]:
    """DI-LEO-AI-204 (Pattern G): combine HITL flag/reason for the
    parent episode when one or more care_obstruction anchors are linked.
    Preserves any existing HITL reason from prior status logic.
    """
    if not care_links:
        return False, existing_reason
    sample_text = ""
    for anchor in care_links:
        evidence = str(anchor.get("evidence") or "")
        if evidence:
            sample_text = evidence[:80].replace("\n", " ").strip()
            break
    suffix = (
        f"Care obstruction signal on {care_links[0].get('encounter_date')}: "
        f"{sample_text or 'see encounter'}. Review pathway block."
    )
    if existing_reason:
        return True, f"{existing_reason} | {suffix}"
    return True, suffix


def _has_competing_confirmed_diagnosis(
    ref_date: date | None,
    diagnosis_anchors: list[dict[str, Any]],
) -> bool:
    """True when any confirmed cancer diagnosis exists in the 90-day window."""
    if not ref_date:
        return False
    window_end = ref_date + timedelta(days=cfg.BENIGN_QUALIFIER_WINDOW_DAYS)
    for anchor in diagnosis_anchors:
        if anchor.get("is_pathway_completion"):
            continue
        assertion = str(anchor.get("assertion", "present") or "present")
        if assertion not in ("present", ""):
            continue
        d = _parse_date(anchor.get("encounter_date"))
        if not d or d < ref_date or d > window_end:
            continue
        return True
    return False


def _rescue_diagnosis_for_open_episode(
    diagnosis_anchors: list[dict[str, Any]],
    site_key: str,
    ref_date: date | None,
) -> tuple[date, list[dict[str, Any]]] | None:
    """DI-LEO-AI-150: find unmatched diagnosis anchors in the open-episode
    window so the episode can be promoted to 'completed' instead of being
    auto-closed as stale.

    Returns ``(earliest_diag_date, anchors_on_that_date)`` when at least
    one site-compatible confirmed diagnosis anchor falls in
    ``[ref_date, ref_date + STALE_HARD_DAYS]``; ``None`` otherwise.

    Site compatibility uses the same _site_keys_compatible helper as the
    rest of the builder, so an unknown / non_site_specific diagnosis is
    eligible for any site, and a specific-site diagnosis must match the
    referral's site key.
    """
    if not diagnosis_anchors or ref_date is None:
        return None
    window_end = ref_date + timedelta(days=cfg.STALE_HARD_DAYS)

    eligible: list[tuple[date, dict[str, Any]]] = []
    for anchor in diagnosis_anchors:
        if anchor.get("is_pathway_completion"):
            continue
        assertion = str(anchor.get("assertion", "present") or "present")
        if assertion not in ("present", ""):
            continue
        d = _parse_date(anchor.get("encounter_date"))
        if d is None or d < ref_date or d > window_end:
            continue
        anchor_key = _extract_condition_key_from_anchor(anchor)
        # 'unknown' / 'non_site_specific' diagnoses match any site --
        # they may legitimately belong to this referral and the upstream
        # _build_diagnosis_led_groups already failed to pair them.
        if anchor_key not in ("unknown", "non_site_specific"):
            if not _site_keys_compatible(site_key, anchor_key):
                continue
        eligible.append((d, anchor))

    if not eligible:
        return None
    earliest = min(d for d, _ in eligible)
    same_day = [a for d, a in eligible if d == earliest and a.get("encounter_id")]
    return earliest, same_day


def _closed_episode_spec(
    patient_id: str,
    site_key: str,
    ref_anchors: list[dict[str, Any]],
    diag_anchors: list[dict[str, Any]],
) -> _EpisodeSpec:
    all_anchors = ref_anchors + diag_anchors
    all_dates = [
        str(a.get("encounter_date") or "")
        for a in all_anchors
        if a.get("encounter_date")
    ]
    earliest = min(all_dates) if all_dates else ""
    latest = max(all_dates) if all_dates else ""
    ref_str = (
        str(ref_anchors[0].get("encounter_date") or earliest)
        if ref_anchors
        else earliest
    )
    ref_date = _parse_date(ref_str)
    window_end = _parse_date(latest) or (
        (ref_date + timedelta(days=cfg.DIAG_LOOKBACK_DAYS))
        if ref_date
        else date.today()
    )
    return _EpisodeSpec(
        ep_id=_episode_id(patient_id, site_key, earliest),
        site_key=site_key,
        ref_date=ref_date,
        window_end=window_end,
    )


def _open_episode_spec(
    patient_id: str,
    site_key: str,
    group: list[dict[str, Any]],
) -> _EpisodeSpec:
    earliest = str(group[0].get("encounter_date") or "")
    ref_date = _parse_date(group[0].get("encounter_date"))
    window_end = (
        (ref_date + timedelta(days=cfg.STALE_HARD_DAYS)) if ref_date else date.today()
    )
    return _EpisodeSpec(
        ep_id=_episode_id(patient_id, site_key, earliest),
        site_key=site_key,
        ref_date=ref_date,
        window_end=window_end,
    )


def _build_closed_episode(
    ctx: BuildContext,
    site_key: str,
    ref_anchors: list[dict[str, Any]],
    diag_anchors: list[dict[str, Any]],
    claim: _SpecialistClaim,
    referral_match_method: str = "strict_site",
) -> None:
    """Write one diagnosis-led (completed) episode."""
    all_anchors = ref_anchors + diag_anchors
    all_dates_str = [
        str(a.get("encounter_date") or "")
        for a in all_anchors
        if a.get("encounter_date")
    ]
    earliest_str = min(all_dates_str) if all_dates_str else ""
    # DI-LEO-AI-136: honest NULL semantics. When no referral anchor is
    # claimed (truly floating diagnosis-only episode), ep.referral_date
    # is persisted as NULL. The previous behaviour back-filled from the
    # diagnosis encounter date, which falsely inflated the via-2WW
    # metric because 75 of 91 confirmed-cancer episodes in 2025 had
    # referral_date synthesised from the diagnosis date.
    referral_date: str | None = (
        str(ref_anchors[0].get("encounter_date") or "") or None if ref_anchors else None
    )
    if not ref_anchors:
        referral_match_method = "none"

    if site_key in ("unknown", "non_site_specific") and ctx.anchors:
        fp_and_ref = (ctx.anchors.first_presentation_anchors or []) + ref_anchors
        for fp_anchor in fp_and_ref:
            candidate = _extract_condition_key_from_anchor(fp_anchor)
            if candidate not in ("unknown", "non_site_specific"):
                site_key = candidate
                break

    # DI-LEO-AI-173: site reconciliation. When a diagnosis anchor
    # carries an unambiguous explicit site signal (Read code or
    # malignancy term on a problem-list line) that conflicts with the
    # referral-derived site_key, prefer the diagnosis site and flag
    # the episode HITL. Surface-form heuristics on referral text are
    # unreliable; explicit problem-list codes are not.
    site_reconciliation_hitl: str | None = None
    _explicit_diag_sources = {
        "explicit_2ww_code",
        "explicit_malignancy_code",
        "malignancy_term_problem_line",
    }
    for diag_anchor in diag_anchors:
        diag_source = str(diag_anchor.get("site_source") or "")
        diag_site = str(diag_anchor.get("site_key") or "")
        if (
            diag_source in _explicit_diag_sources
            and diag_site
            and diag_site not in ("unknown", "non_site_specific")
            and diag_site != site_key
        ):
            site_reconciliation_hitl = (
                f"Site reconciled: referral suggested '{site_key}' but "
                f"diagnosis carries explicit site '{diag_site}' "
                f"(source: {diag_source}). Confirm cancer site."
            )
            site_key = diag_site
            break

    ep_id = _episode_id(ctx.patient_id, site_key, earliest_str)
    ctx.result.episode_ids.append(ep_id)
    ctx.result.episodes_created += 1
    ctx.result.encounters_linked += len(
        {str(a.get("encounter_id") or "") for a in all_anchors if a.get("encounter_id")}
    )

    cancer_diags = _cancer_diag_anchors(diag_anchors)
    has_diag = _has_confirmed_diagnosis(diag_anchors) or bool(
        cancer_diags and not _has_possible_only_diagnosis(diag_anchors)
    )

    ref_dates = [
        d
        for d in (_parse_date(str(a.get("encounter_date") or "")) for a in ref_anchors)
        if d is not None
    ]
    ref_date = _parse_date(referral_date)
    fp_date, complaint, place, aligned_ref_date = _first_presentation_from_anchors(
        ctx.anchors, ref_date, ref_dates
    )
    if aligned_ref_date:
        referral_date = aligned_ref_date
        ref_date = _parse_date(referral_date)
    if not fp_date and ref_date:
        fb_date, fb_complaint, fb_place = _first_presentation_from_referral_context(
            ctx.patient_id, ref_date, ctx.anchors, ctx.patient_client
        )
        if fb_date and fb_complaint:
            fp_date, complaint, place = fb_date, fb_complaint, (fb_place or place)

    episode_treatments = _episode_treatment_anchors(
        ctx.anchors.treatment_anchors if ctx.anchors else [],
        ref_date,
        site_key,
    )
    is_phantom = site_key in ctx.phantom_sites
    status, hitl_flag, hitl_reason = _determine_episode_status(
        has_diag,
        diag_anchors,
        None,
        None,
        episode_treatments,
        ref_date,
        is_phantom,
        ref_anchors=ref_anchors,
    )

    if status == "completed" and site_key == "unknown" and not hitl_flag:
        hitl_flag = True
        hitl_reason = (
            "Completed: cancer type could not be determined from diagnosis coding. "
            "SNOMED concept name is unresolved in the graph. "
            "Confirm cancer site from records."
        )

    # DI-LEO-AI-173: surface site-reconciliation HITL on the episode.
    if site_reconciliation_hitl:
        hitl_flag = True
        hitl_reason = (
            f"{hitl_reason} | {site_reconciliation_hitl}"
            if hitl_reason
            else site_reconciliation_hitl
        )

    end_date = max(all_dates_str) if all_dates_str else None
    ref_concept = str(ref_anchors[0].get("concept_name") or "") if ref_anchors else ""

    # DI-LEO-AI-145: claim first_seen anchors before writing episode so
    # first_seen_date can be persisted on the node in the same MERGE call.
    fs_raw = ctx.anchors.first_seen_anchors if ctx.anchors else []
    ref_d = _parse_date(referral_date)
    fs_link_anchors, fs_date = _first_seen_link_anchors(fs_raw, ref_d, end_date)

    # DI-LEO-AI-204 (Pattern G): attach care_obstruction signals.
    co_raw = (
        ctx.anchors.care_obstruction_anchors
        if ctx.anchors and hasattr(ctx.anchors, "care_obstruction_anchors")
        else []
    )
    co_link_anchors = _care_obstruction_link_anchors(co_raw, ref_d, end_date)
    if co_link_anchors:
        co_hitl_flag, co_hitl_reason = _care_obstruction_hitl(
            co_link_anchors, hitl_reason
        )
        hitl_flag = hitl_flag or co_hitl_flag
        hitl_reason = co_hitl_reason

    _write_episode(
        ctx.patient_client,
        WriteEpisodeParams(
            patient_id=ctx.patient_id,
            ep_id=ep_id,
            domain_id=ctx.domain_id,
            site_key=site_key,
            referral_date=referral_date,
            end_date=end_date,
            claim=claim,
            status=status,
            hitl_flag=hitl_flag,
            hitl_reason=hitl_reason,
            referral_route=_referral_route_from_concept(ref_concept),
            place_of_presentation=place or "GP surgery",
            first_presentation_date=fp_date,
            presenting_complaint=complaint,
            referral_match_method=referral_match_method,
            first_seen_date=fs_date,
        ),
        ctx.result,
        ctx.episode_ids,
    )

    diag_milestone = (
        "diagnosis_confirmed" if _has_confirmed_diagnosis(diag_anchors) else "diagnosis"
    )
    fp_anchors = ctx.anchors.first_presentation_anchors if ctx.anchors else []
    fp_link_anchors = _first_presentation_link_anchors(fp_anchors, fp_date)
    treatment_link_anchors = _treatment_started_link_anchors(episode_treatments)
    _closed_link_groups = _filter_unclaimed_link_groups(
        [
            (ref_anchors, "referral"),
            (diag_anchors, diag_milestone),
            (treatment_link_anchors, "treatment_started"),
            (fp_link_anchors, "first_presentation"),
            (fs_link_anchors, "first_seen"),
            (co_link_anchors, "care_obstruction"),
        ],
        ctx.claimed_encounters,
    )
    # DI-LEO-AI-403 (Pattern N2): collapse same-day referral
    # duplicates so the timeline shows ONE referral milestone per
    # day per episode (highest-fidelity subtype kept).
    _closed_link_groups = collapse_same_day_referrals(_closed_link_groups)
    # DI-C424BB44 rebuild guard: drop any (encounter, milestone) whose
    # IS_PART_OF edge is locked, then forward the lock state so the
    # LINK_ENCOUNTERS Cypher's WHERE NOT clause preserves the existing
    # locked edges.
    if ctx.lock_state is not None:
        _closed_link_groups = filter_link_groups(
            _closed_link_groups, episode_id=ep_id, lock_state=ctx.lock_state
        )
    _link_encounters_to_episode(
        ctx.patient_client,
        ep_id,
        _closed_link_groups,
        lock_state=ctx.lock_state,
    )


def _build_open_episode(
    ctx: BuildContext,
    site_key: str,
    group: list[dict[str, Any]],
    claim: _SpecialistClaim,
) -> None:
    """Write one referral-only (in_progress) episode."""
    earliest_str = str(group[0].get("encounter_date") or "")
    ep_id = _episode_id(ctx.patient_id, site_key, earliest_str)
    ctx.result.episode_ids.append(ep_id)
    ctx.result.episodes_created += 1
    ctx.result.encounters_linked += len(
        {str(r.get("encounter_id") or "") for r in group if r.get("encounter_id")}
    )

    ref_date = _parse_date(group[0].get("encounter_date"))
    ref_dates = [
        d
        for d in (_parse_date(str(a.get("encounter_date") or "")) for a in group)
        if d is not None
    ]
    fp_date, complaint, place, aligned_ref_date = _first_presentation_from_anchors(
        ctx.anchors, ref_date, ref_dates
    )
    if aligned_ref_date:
        earliest_str = aligned_ref_date
        ref_date = _parse_date(earliest_str)
    if not fp_date and ref_date:
        fb_date, fb_complaint, fb_place = _first_presentation_from_referral_context(
            ctx.patient_id, ref_date, ctx.anchors, ctx.patient_client
        )
        if fb_date and fb_complaint:
            fp_date, complaint, place = fb_date, fb_complaint, (fb_place or place)

    episode_treatments = _episode_treatment_anchors(
        ctx.anchors.treatment_anchors if ctx.anchors else [],
        ref_date,
        site_key,
    )
    is_phantom = site_key in ctx.phantom_sites
    benign_date: date | None = None
    benign_qualifier_date: date | None = None
    if not is_phantom and ref_date:
        benign_date = _benign_closure_for_episode(
            ctx.patient_id, ref_date, ctx.patient_client, ctx.anchors
        )
        has_competing_diag = _has_competing_confirmed_diagnosis(
            ref_date,
            ctx.anchors.diagnosis_anchors if ctx.anchors else [],
        )
        if not has_competing_diag:
            benign_qualifier_date = _benign_qualifier_closure_for_episode(
                ctx.patient_id, site_key, ref_date, ctx.patient_client
            )

    letter_end, letter_reason = _infer_completed_from_specialist_letter(
        claim,
        ctx.anchors.specialist_outcome_letter_anchors,
        episode_treatments,
        ref_date,
    )
    letter_inferred_benign = False
    if letter_end:
        status, hitl_flag, hitl_reason = "completed", True, letter_reason
        end_date: str | None = letter_end.isoformat()
        letter_inferred_benign = True
    else:
        status, hitl_flag, hitl_reason = _determine_episode_status(
            False,
            [],
            benign_date,
            benign_qualifier_date,
            episode_treatments,
            ref_date,
            is_phantom,
            ref_anchors=group,
        )
        if benign_date:
            end_date = benign_date.isoformat()
        elif benign_qualifier_date:
            end_date = benign_qualifier_date.isoformat()
        elif status == "closed_phantom":
            end_date = earliest_str
        else:
            end_date = None

    ref_concept = str(group[0].get("concept_name") or "") if group else ""

    # DI-LEO-AI-145 (defect fix): claim first_seen anchors BEFORE
    # _write_episode so first_seen_date is persisted on the EpisodeOfCare
    # node. The previous ordering computed _fs_date AFTER the MERGE call
    # and discarded it, leaving first_seen_date NULL on 68/79 (86%) of
    # auto-closed open episodes even though the IS_PART_OF first_seen
    # edge was still being written.
    fs_raw = ctx.anchors.first_seen_anchors if ctx.anchors else []
    fs_link_anchors, fs_date = _first_seen_link_anchors(
        fs_raw, _parse_date(earliest_str), end_date
    )

    # DI-LEO-AI-204 (Pattern G): attach care_obstruction signals.
    co_raw = (
        ctx.anchors.care_obstruction_anchors
        if ctx.anchors and hasattr(ctx.anchors, "care_obstruction_anchors")
        else []
    )
    co_link_anchors = _care_obstruction_link_anchors(
        co_raw, _parse_date(earliest_str), end_date
    )
    if co_link_anchors:
        co_hitl_flag, co_hitl_reason = _care_obstruction_hitl(
            co_link_anchors, hitl_reason
        )
        hitl_flag = hitl_flag or co_hitl_flag
        hitl_reason = co_hitl_reason

    # DI-LEO-AI-150: rescue diagnosis-aware completion. If the episode
    # would otherwise stay 'in_progress' AND a confirmed cancer diagnosis
    # anchor exists in the window, promote it to 'completed' with
    # end_date = diagnosis date instead of leaving it for the stale
    # auto-close pass to file as stale_post_specialist or
    # stale_no_diagnosis. Diagnosis text is stronger evidence than 'no
    # update for 90 days', so it must beat the stale rule.
    diag_link_anchors: list[dict[str, Any]] = []
    diag_milestone_open = "diagnosis_confirmed"
    if status == "in_progress":
        diag_rescue = _rescue_diagnosis_for_open_episode(
            ctx.anchors.diagnosis_anchors if ctx.anchors else [],
            site_key,
            _parse_date(earliest_str),
        )
        if diag_rescue is not None:
            rescue_date, rescue_anchors = diag_rescue
            status, hitl_flag = "completed", True
            hitl_reason = (
                "Auto-completed: confirmed cancer diagnosis text in episode "
                "window. Verify cancer site and pathway outcome."
            )
            end_date = rescue_date.isoformat()
            diag_link_anchors = rescue_anchors

    _write_episode(
        ctx.patient_client,
        WriteEpisodeParams(
            patient_id=ctx.patient_id,
            ep_id=ep_id,
            domain_id=ctx.domain_id,
            site_key=site_key,
            referral_date=earliest_str,
            end_date=end_date,
            claim=claim,
            status=status,
            hitl_flag=hitl_flag,
            hitl_reason=hitl_reason,
            referral_route=_referral_route_from_concept(ref_concept),
            place_of_presentation=place or "GP surgery",
            letter_inferred_benign=letter_inferred_benign,
            first_presentation_date=fp_date,
            presenting_complaint=complaint,
            first_seen_date=fs_date,
        ),
        ctx.result,
        ctx.episode_ids,
    )

    fp_anchors = ctx.anchors.first_presentation_anchors if ctx.anchors else []
    fp_link_anchors = _first_presentation_link_anchors(fp_anchors, fp_date)
    link_groups: list[tuple[list[dict[str, Any]], str]] = [
        (group, "referral"),
        (fp_link_anchors, "first_presentation"),
        (fs_link_anchors, "first_seen"),
        (co_link_anchors, "care_obstruction"),
    ]
    if diag_link_anchors:
        link_groups.append((diag_link_anchors, diag_milestone_open))
    if status == "closed_benign":
        bc_anchors = ctx.anchors.benign_closure_anchors if ctx.anchors else []
        bc_link_anchors = _benign_closure_link_anchors(
            bc_anchors, benign_date or benign_qualifier_date, ref_date
        )
        if bc_link_anchors:
            link_groups.append((bc_link_anchors, "benign_closure"))
    link_groups = _filter_unclaimed_link_groups(link_groups, ctx.claimed_encounters)
    # DI-LEO-AI-403 (Pattern N2): collapse same-day referral
    # duplicates on the open-episode path too.
    link_groups = collapse_same_day_referrals(link_groups)
    # DI-C424BB44 rebuild guard (open path) -- see closed path above.
    if ctx.lock_state is not None:
        link_groups = filter_link_groups(
            link_groups, episode_id=ep_id, lock_state=ctx.lock_state
        )
    _link_encounters_to_episode(
        ctx.patient_client,
        ep_id,
        link_groups,
        lock_state=ctx.lock_state,
    )


async def build_episodes(
    patient_id: str,
    anchors: AnchorResult,
    patient_client: Any,
    domain_id: str = "",
) -> EpisodeBuildResult:
    """Build EpisodeOfCare nodes using a diagnosis-led algorithm."""
    result = EpisodeBuildResult(patient_id=patient_id)
    if not anchors.referral_anchors and not anchors.diagnosis_anchors:
        return result

    referrals_by_site: dict[str, list[dict[str, Any]]] = {}
    for anchor in anchors.referral_anchors:
        key = _extract_condition_key_from_anchor(anchor)
        referrals_by_site.setdefault(key, []).append(anchor)
    phantom_sites = _detect_phantom_sites(referrals_by_site)

    closed_groups, open_groups = _build_diagnosis_led_groups(
        anchors.referral_anchors, anchors.diagnosis_anchors
    )

    specs: list[_EpisodeSpec] = [
        _closed_episode_spec(patient_id, site_key, ref_anchors, diag_anchors)
        for site_key, ref_anchors, diag_anchors, _method in closed_groups
    ] + [
        _open_episode_spec(patient_id, site_key, group)
        for site_key, group in open_groups
    ]

    claims = _claim_specialists_for_episodes(anchors.specialist_visit_anchors, specs)

    episode_ids: list[str] = []
    # DI-C424BB44 rebuild guard: read every VerificationLock on this
    # patient's graph neighbourhood once at the start of the build so
    # the per-episode builders can skip fully-locked episodes and
    # preserve locked IS_PART_OF edges.
    lock_state = load_lock_state(patient_id, patient_client)
    ctx = BuildContext(
        patient_id=patient_id,
        anchors=anchors,
        patient_client=patient_client,
        domain_id=domain_id,
        result=result,
        episode_ids=episode_ids,
        phantom_sites=phantom_sites,
        lock_state=lock_state,
    )

    for site_key, ref_anchors, diag_anchors, match_method in closed_groups:
        ep_id = _episode_id(
            patient_id,
            site_key,
            min(
                [
                    str(a.get("encounter_date") or "")
                    for a in ref_anchors + diag_anchors
                    if a.get("encounter_date")
                ],
                default="",
            ),
        )
        if is_episode_fully_locked(ep_id, lock_state):
            # Reviewer locked the episode end-to-end; respect their
            # decision and skip the rebuild entirely.
            result.episode_ids.append(ep_id)
            continue
        _build_closed_episode(
            ctx,
            site_key,
            ref_anchors,
            diag_anchors,
            claims[ep_id],
            match_method,
        )

    for site_key, group in open_groups:
        ep_id = _episode_id(
            patient_id, site_key, str(group[0].get("encounter_date") or "")
        )
        if is_episode_fully_locked(ep_id, lock_state):
            result.episode_ids.append(ep_id)
            continue
        _build_open_episode(ctx, site_key, group, claims[ep_id])

    _apply_auto_close_rules(patient_id, episode_ids, patient_client)
    _apply_outcome_inference(patient_id, episode_ids, patient_client)
    # DI-LEO-AI-125: persist NCDA interval KPIs as named properties on each
    # EpisodeOfCare so downstream dashboards all read the same numbers.
    calculate_kpis(patient_id, episode_ids, patient_client)
    return result
