"""Stable ID helpers for simulated referrals."""

from __future__ import annotations


def scenario_patient_id(case_id: str) -> str:
    """Synthetic patient id used by AI summarisation scenario runs."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in case_id)
    return f"scenario-sbar-{safe}"


def referral_id_for_child_run(child_run_id: str) -> str:
    """ReferralRequest id correlated to a scenario child run."""
    safe = "".join(ch if ch.isalnum() or ch in "-_:" else "_" for ch in child_run_id)
    return f"{safe}:referral"


def document_reference_id(referral_id: str) -> str:
    """DocumentReference id for a referral bundle (HCCP parity)."""
    return f"{referral_id}:leo-referral-bundle"


def encounter_id_for_referral(referral_id: str) -> str:
    """Correlation encounter id; text source remains Chunks."""
    return f"{referral_id}:referral-assessment"
