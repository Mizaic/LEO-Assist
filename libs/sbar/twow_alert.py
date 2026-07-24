"""2WW mismatch alert evaluation and persistence shape (B3.3).

Atlas trace:
  DO: DO-79266FAB
  DI: DI-C31E59C4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-79266FAB")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from libs.sbar.twow_detector import (
    DETECTOR_VERSION,
    TwowMention,
    detect_active_twow_mentions,
)

_ALERT_TYPE = "twow_priority_mismatch"


@dataclass(frozen=True)
class TwowMismatchAlert:
    alert_type: str
    detector_version: str
    structured_priority: str
    letter_evidence: str
    message: str
    alert_key: str


def evaluate_twow_mismatch(
    *,
    structured_priority: str | None,
    letter_text: str,
    referral_id: str,
    run_id: str,
) -> TwowMismatchAlert | None:
    """Alert when structured priority is blank/non-2WW but letter asserts 2WW."""
    priority = str(structured_priority or "").strip().lower()
    if priority in {"2ww", "two_week_wait", "fast_track", "faster_diagnosis"}:
        return None
    mentions = detect_active_twow_mentions(letter_text)
    if not mentions:
        return None
    evidence = mentions[0].line.strip()
    alert_key = (
        f"{run_id}:{referral_id}:{_ALERT_TYPE}:{mentions[0].matched_text.lower()}"
    )
    if not priority:
        message = (
            "Structured referral priority is missing but the letter mentions "
            "an active two-week-wait or Faster Diagnosis referral."
        )
    else:
        message = (
            f"Structured referral priority is {priority!r} but the letter "
            "mentions an active two-week-wait or Faster Diagnosis referral."
        )
    return TwowMismatchAlert(
        alert_type=_ALERT_TYPE,
        detector_version=DETECTOR_VERSION,
        structured_priority=priority,
        letter_evidence=evidence,
        message=message,
        alert_key=alert_key,
    )


def alert_to_dict(alert: TwowMismatchAlert) -> dict[str, Any]:
    return {
        "alert_type": alert.alert_type,
        "detector_version": alert.detector_version,
        "structured_priority": alert.structured_priority,
        "letter_evidence": alert.letter_evidence,
        "message": alert.message,
        "alert_key": alert.alert_key,
    }


def merge_letter_mentions(mentions: list[TwowMention]) -> str:
    return "\n".join(m.line for m in mentions if m.line)
