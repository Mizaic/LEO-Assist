"""Top-level episode building orchestrator."""

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
        str(ref_anchors[0].get("encounter_date") or "") or None
        if ref_anchors
        else None
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
        has_diag, diag_anchors, None, None, episode_treatments, ref_date, is_phantom
    )

    if status == "completed" and site_key == "unknown" and not hitl_flag:
        hitl_flag = True
        hitl_reason = (
            "Completed: cancer type could not be determined from diagnosis coding. "
            "SNOMED concept name is unresolved in the graph. "
            "Confirm cancer site from records."
        )

    end_date = max(all_dates_str) if all_dates_str else None
    ref_concept = str(ref_anchors[0].get("concept_name") or "") if ref_anchors else ""

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
    _link_encounters_to_episode(
        ctx.patient_client,
        ep_id,
        [
            (ref_anchors, "referral"),
            (diag_anchors, diag_milestone),
            (treatment_link_anchors, "treatment_started"),
            (fp_link_anchors, "first_presentation"),
        ],
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
        ),
        ctx.result,
        ctx.episode_ids,
    )

    fp_anchors = ctx.anchors.first_presentation_anchors if ctx.anchors else []
    fp_link_anchors = _first_presentation_link_anchors(fp_anchors, fp_date)
    _link_encounters_to_episode(
        ctx.patient_client,
        ep_id,
        [
            (group, "referral"),
            (fp_link_anchors, "first_presentation"),
        ],
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
    ctx = BuildContext(
        patient_id=patient_id,
        anchors=anchors,
        patient_client=patient_client,
        domain_id=domain_id,
        result=result,
        episode_ids=episode_ids,
        phantom_sites=phantom_sites,
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
        _build_open_episode(ctx, site_key, group, claims[ep_id])

    _apply_auto_close_rules(patient_id, episode_ids, patient_client)
    _apply_outcome_inference(patient_id, episode_ids, patient_client)
    # DI-LEO-AI-125: persist NCDA interval KPIs as named properties on each
    # EpisodeOfCare so downstream dashboards all read the same numbers.
    calculate_kpis(patient_id, episode_ids, patient_client)
    return result
