"""Episode status determination and specialist-letter inference."""

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
    return all(
        str(a.get("assertion", "present")) == "possible" for a in cancer_diags
    )


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

    letter_deadline = spec_date + timedelta(
        days=cfg.LETTER_WITHIN_DAYS_AFTER_VISIT
    )
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
    treat_end = letter_date + timedelta(
        days=cfg.NO_TREATMENT_WINDOW_AFTER_LETTER_DAYS
    )
    if _treatment_between(treatment_anchors, letter_date, treat_end):
        return None, None

    reason = (
        "Completed: specialist outcome letter with no coded treatment "
        "within 120 days. Inferred benign pathway; confirm from records."
    )
    return letter_date, reason


def _determine_episode_status(
    has_diagnosis: bool,
    diag_anchors: list[dict[str, Any]],
    benign_date: date | None,
    treatment_anchors: list[dict[str, Any]],
    ref_date: date | None,
    is_phantom: bool,
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

    return ("in_progress", False, None)
