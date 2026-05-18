"""Episode status determination and specialist-letter inference.

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from . import _config as cfg
from ._types import _SpecialistClaim, _parse_date


def _cancer_diag_anchors(diag_anchors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only non-pathway-completion anchors."""
    return [a for a in diag_anchors if not a.get("is_pathway_completion")]


def _has_confirmed_diagnosis(diag_anchors: list[dict[str, Any]]) -> bool:
    """True if at least one non-pathway-completion anchor has assertion='present'."""
    return any(
        str(a.get("assertion", "present")) in ("present", "")
        for a in _cancer_diag_anchors(diag_anchors)
    )


def _has_possible_only_diagnosis(diag_anchors: list[dict[str, Any]]) -> bool:
    """True if ALL non-pathway-completion anchors are [possible]."""
    cancer_diags = _cancer_diag_anchors(diag_anchors)
    if not cancer_diags:
        return False
    return all(str(a.get("assertion", "present")) == "possible" for a in cancer_diags)


def _treatment_after_referral(
    treatment_anchors: list[dict[str, Any]], ref_date: date | None
) -> bool:
    """True if any treatment anchor occurs on or after the referral date."""
    if not ref_date or not treatment_anchors:
        return False
    return any(
        (d := _parse_date(a.get("encounter_date"))) and d >= ref_date
        for a in treatment_anchors
    )


def _treatment_between(
    treatment_anchors: list[dict[str, Any]], start: date, end: date
) -> bool:
    """True if any treatment anchor date falls in [start, end] inclusive."""
    for a in treatment_anchors:
        d = _parse_date(a.get("encounter_date"))
        if d and start <= d <= end:
            return True
    return False


def _infer_completed_from_specialist_letter(
    claim: _SpecialistClaim,
    letter_anchors: list[dict[str, Any]],
    treatment_anchors: list[dict[str, Any]],
    ref_date: date | None,
) -> tuple[date | None, str | None]:
    """If criteria met, return (episode end date, HITL reason) for inferred benign."""
    if not claim.specialist_seen or not claim.specialist_visit_date or not ref_date:
        return None, None
    spec_date = _parse_date(claim.specialist_visit_date)
    if not spec_date:
        return None, None
    today = cfg._today_for_episode_rules()
    if (today - spec_date).days <= cfg.STALE_POST_SPECIALIST_DAYS:
        return None, None

    letter_deadline = spec_date + timedelta(days=cfg.LETTER_WITHIN_DAYS_AFTER_VISIT)
    letter_dates: list[date] = []
    for a in letter_anchors:
        ld = _parse_date(a.get("encounter_date"))
        if not ld or ld < ref_date:
            continue
        if spec_date <= ld <= letter_deadline:
            letter_dates.append(ld)
    if not letter_dates:
        return None, None

    letter_date = min(letter_dates)
    treat_end = letter_date + timedelta(days=cfg.NO_TREATMENT_WINDOW_AFTER_LETTER_DAYS)
    if _treatment_between(treatment_anchors, letter_date, treat_end):
        return None, None

    reason = (
        "Completed: specialist outcome letter with no coded treatment "
        "within 120 days. Inferred benign pathway; confirm from records."
    )
    return letter_date, reason


def _has_followup_referral(
    ref_anchors: list[dict[str, Any]],
    rejection_date: date,
    followup_window_days: int = 90,
) -> bool:
    """True when a non-rejected referral exists after the rejection date.

    DI-LEO-AI-202 (Pattern A): used by the rejected_no_followup status
    rule to distinguish (i) a referral that was rejected and the
    practice resubmitted a working referral within 90 days, from
    (ii) a referral that was rejected and never followed up.
    """
    for anchor in ref_anchors:
        subtype = str(anchor.get("referral_subtype") or "")
        if subtype in ("rejected", "marked_in_error"):
            continue
        a_date = _parse_date(anchor.get("encounter_date"))
        if not a_date or a_date <= rejection_date:
            continue
        if (a_date - rejection_date).days <= followup_window_days:
            return True
    return False


def _rejection_followup_status(
    ref_anchors: list[dict[str, Any]],
    has_diagnosis: bool,
    benign_date: date | None,
) -> tuple[str, bool, str | None] | None:
    """Return (status, hitl, reason) when the open episode looks like a
    rejected-no-followup, otherwise None.

    DI-LEO-AI-202 (Pattern A): a referral marked ``rejected`` (Choose
    & Book "Return to referrer with advice", "Hospital cancelled
    referral", etc.) with NO subsequent working referral within 90
    days is a workflow-quality failure -- the patient is left in
    limbo. Prior behaviour kept these as ``in_progress`` and the
    stale-close pass eventually filed them as ``stale_no_diagnosis``
    months later. Surface them earlier so QA can act.
    """
    if has_diagnosis or benign_date:
        return None
    rejection_dates = [
        _parse_date(a.get("encounter_date"))
        for a in ref_anchors
        if str(a.get("referral_subtype") or "") in ("rejected", "marked_in_error")
    ]
    rejection_dates_clean = [d for d in rejection_dates if d]
    if not rejection_dates_clean:
        return None
    earliest_rejection = min(rejection_dates_clean)
    if _has_followup_referral(ref_anchors, earliest_rejection):
        return None
    return (
        "rejected_no_followup",
        True,
        "Referral was rejected by the receiving service and no working "
        "referral was sent in the 90 days that followed. Patient may be "
        "in pathway limbo -- review for resubmission.",
    )


def _determine_episode_status(
    has_diagnosis: bool,
    diag_anchors: list[dict[str, Any]],
    benign_date: date | None,
    benign_qualifier_date: date | None,
    treatment_anchors: list[dict[str, Any]],
    ref_date: date | None,
    is_phantom: bool,
    ref_anchors: list[dict[str, Any]] | None = None,
) -> tuple[str, bool, str | None]:
    """Return (status, hitl_flag, hitl_reason)."""
    if is_phantom:
        return (
            "closed_phantom",
            True,
            "Auto-closed: referral encounter also codes another cancer pathway. "
            "Likely a phantom episode from a multi-referral template. Review manually.",
        )

    if has_diagnosis:
        if _has_possible_only_diagnosis(diag_anchors) and _treatment_after_referral(
            treatment_anchors, ref_date
        ):
            return (
                "completed",
                True,
                "Completed: [possible] cancer diagnosis with subsequent treatment. "
                "Confirm diagnosis from clinic letter.",
            )
        return ("completed", False, None)

    if benign_date:
        return ("closed_benign", False, None)

    if benign_qualifier_date:
        return (
            "closed_benign_qualifier",
            True,
            "Auto-closed: benign/normal qualifier on site-related finding within "
            "90 days and no coded cancer diagnosis. Verify from clinical records.",
        )

    # DI-LEO-AI-202 (Pattern A): rejected-no-followup signal beats the
    # default in_progress fallback so QA can find blocked pathways.
    if ref_anchors:
        rejection_status = _rejection_followup_status(
            ref_anchors, has_diagnosis, benign_date
        )
        if rejection_status is not None:
            return rejection_status

    return ("in_progress", False, None)
