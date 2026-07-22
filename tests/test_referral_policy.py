"""Tests for referral policy schema and publish validation (M2.2)."""

from __future__ import annotations

from libs.workflow.referral_policy import (
    DEFAULT_REFERRAL_POLICY,
    parse_referral_policy,
    referral_policy_requires_validation,
    validate_referral_policy,
)


def test_default_referral_policy_is_valid() -> None:
    errors = validate_referral_policy(DEFAULT_REFERRAL_POLICY)
    assert errors == []


def test_rejects_window_overlap_gte_window_size() -> None:
    bad = {
        **DEFAULT_REFERRAL_POLICY,
        "extraction": {"windowSize": 5, "windowOverlap": 5},
    }
    errors = validate_referral_policy(bad)
    assert any("windowOverlap" in err for err in errors)


def test_rejects_negative_recall_budgets() -> None:
    bad = {
        **DEFAULT_REFERRAL_POLICY,
        "recall": {**DEFAULT_REFERRAL_POLICY["recall"], "maxChunkFetches": -1},
    }
    errors = validate_referral_policy(bad)
    assert any("maxChunkFetches" in err for err in errors)


def test_rejects_missing_sbar_prompt_pins() -> None:
    bad = {
        **DEFAULT_REFERRAL_POLICY,
        "prompts": {
            "situation": {"name": "sbar_situation", "version": 2},
        },
    }
    errors = validate_referral_policy(bad)
    assert any("prompts" in err for err in errors)


def test_parse_referral_policy_returns_defaults_when_absent() -> None:
    parsed = parse_referral_policy({})
    assert parsed["extraction"]["windowSize"] == 10
    assert parsed["prompts"]["situation"]["version"] == 2


def test_referral_assessment_plan_requires_policy() -> None:
    assert referral_policy_requires_validation(
        {"id": "pd-referral-assessment", "_workflowMode": "durable_pubsub"}
    )


def test_gp_plan_does_not_require_referral_policy() -> None:
    assert not referral_policy_requires_validation(
        {"id": "pd-gp-encounter-coding", "_workflowMode": "durable_pubsub"}
    )
