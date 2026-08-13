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


def test_default_referral_policy_pins_small_tier() -> None:
    assert DEFAULT_REFERRAL_POLICY["models"]["tier"] == "small"
    assert DEFAULT_REFERRAL_POLICY["models"]["provider"] == "azure"


def test_big_and_max_model_pins_remain_valid() -> None:
    for tier in ("big", "max"):
        policy = {
            **DEFAULT_REFERRAL_POLICY,
            "models": {"provider": "azure", "tier": tier},
        }
        assert validate_referral_policy(policy) == []


def test_rejects_window_overlap_gte_window_size() -> None:
    bad = {
        **DEFAULT_REFERRAL_POLICY,
        "extraction": {
            **DEFAULT_REFERRAL_POLICY["extraction"],
            "windowSize": 5,
            "windowOverlap": 5,
        },
    }
    errors = validate_referral_policy(bad)
    assert any("windowOverlap" in err for err in errors)


def test_default_extraction_context_mode_and_token_budget() -> None:
    parsed = parse_referral_policy({})
    assert parsed["extraction"]["contextMode"] == "window_local"
    assert parsed["extraction"]["maxWindowInputTokens"] == 16000
    assert parsed["llm"]["situation"]["maxTokens"] == 2048
    assert parsed["llm"]["background"]["maxTokens"] == 4096
    assert parsed["llm"]["recommendation"]["maxTokens"] == 4096
    assert validate_referral_policy(parsed) == []


def test_accepts_high_window_and_stage_token_budgets() -> None:
    policy = {
        **DEFAULT_REFERRAL_POLICY,
        "extraction": {
            **DEFAULT_REFERRAL_POLICY["extraction"],
            "maxWindowInputTokens": 128000,
        },
        "llm": {
            **DEFAULT_REFERRAL_POLICY["llm"],
            "situation": {"temperature": 0.0, "maxTokens": 16384},
        },
    }
    assert validate_referral_policy(policy) == []


def test_rejects_invalid_context_mode_and_token_budget() -> None:
    bad_mode = {
        **DEFAULT_REFERRAL_POLICY,
        "extraction": {
            **DEFAULT_REFERRAL_POLICY["extraction"],
            "contextMode": "banana",
        },
    }
    errors = validate_referral_policy(bad_mode)
    assert any("contextMode" in err for err in errors)

    bad_tokens = {
        **DEFAULT_REFERRAL_POLICY,
        "extraction": {
            **DEFAULT_REFERRAL_POLICY["extraction"],
            "maxWindowInputTokens": 100,
        },
    }
    errors = validate_referral_policy(bad_tokens)
    assert any("maxWindowInputTokens" in err for err in errors)


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
