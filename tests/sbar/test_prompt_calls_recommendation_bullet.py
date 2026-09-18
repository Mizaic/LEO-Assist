"""Deterministic SBAR recommendation bullet-1 coverage for multi-rule fires."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from libs.sbar.prompt_calls import (
    _apply_referral_justification_bullet,
    build_referral_justification_bullet,
    call_recommendation,
)


def _ng12_rule(
    *,
    rule_id: str,
    name: str,
    matched_label: str,
) -> dict:
    """A fired NG12 refer rule, shaped as the graph actually holds one.

    Priority is owned by Neo4j on ``(:ActionGroup)-[:HAS_ACTION]->()``.
    NG12 1.2.1 and 1.2.7 are stored there as ``priority='2ww'`` with
    ``dueDays=14``. Only 2WW-or-higher rules claim receiving-service
    support (``libs/sbar/referral_support.py``), so a fixture saying
    ``routine`` describes a rule that does not exist and would never
    reach bullet 1.
    """
    return {
        "rule_id": rule_id,
        "name": name,
        "strength": "refer",
        "guideline_id": "NG12",
        "guideline_title": "Suspected cancer: recognition and referral",
        "action": {"priority": "2ww", "due_days": 14},
        "matched_via": [
            {
                "preferred_term": matched_label,
                "primary_concept_id": "123",
                "matched_concept_ids": ["123"],
            }
        ],
    }


def test_build_referral_justification_bullet_lists_every_fired_rule() -> None:
    rules = [
        _ng12_rule(
            rule_id="rule-121",
            name="Rule: 1.2.1",
            matched_label="Difficulty swallowing",
        ),
        _ng12_rule(
            rule_id="rule-127",
            name="Rule: 1.2.7",
            matched_label="Difficulty swallowing",
        ),
    ]

    bullet = build_referral_justification_bullet(rules)

    assert "Rule: 1.2.1 and Rule: 1.2.7" in bullet
    assert "Suspected cancer: recognition and referral" in bullet
    assert "difficulty swallowing" in bullet


def test_no_support_bullet_for_a_rule_below_two_week_wait() -> None:
    """A routine or urgent rule is not why a referral is supported.

    An empty bullet here is correct, not a defect. Rules that only offer
    a primary-care test stay visible as other matches; claiming they
    support the referral would overstate the case to the receiving
    service. See ``libs/sbar/referral_support.py``.
    """
    rule = _ng12_rule(
        rule_id="rule-152",
        name="Rule: 1.5.2",
        matched_label="Abdominal pain",
    )
    rule["strength"] = "offer"
    rule["action"] = {"priority": "urgent", "due_days": 14}

    assert build_referral_justification_bullet([rule]) == ""


def test_apply_referral_justification_bullet_replaces_primary_only_output() -> None:
    rules = [
        _ng12_rule(
            rule_id="rule-121",
            name="Rule: 1.2.1",
            matched_label="Difficulty swallowing",
        ),
        _ng12_rule(
            rule_id="rule-127",
            name="Rule: 1.2.7",
            matched_label="Difficulty swallowing",
        ),
    ]
    llm_md = (
        "- Referral is supported by Rule: 1.2.1 -- Suspected cancer: "
        "recognition and referral (difficulty swallowing).\n"
        "- Suspected cancer: recognition and referral signals noted -- "
        "routine (no specified timeframe).\n"
        "- Acute onset dysphagia noted for clinical consideration."
    )

    merged = _apply_referral_justification_bullet(llm_md, rules)

    assert "Rule: 1.2.1 and Rule: 1.2.7" in merged
    assert "signals noted" not in merged
    assert "Acute onset dysphagia noted for clinical consideration." in merged


@pytest.mark.asyncio
async def test_call_recommendation_enforces_multi_rule_bullet_one() -> None:
    rules = [
        _ng12_rule(
            rule_id="rule-121",
            name="Rule: 1.2.1",
            matched_label="Difficulty swallowing",
        ),
        _ng12_rule(
            rule_id="rule-127",
            name="Rule: 1.2.7",
            matched_label="Difficulty swallowing",
        ),
    ]
    invoker = AsyncMock(
        return_value={
            "recommendation_markdown": (
                "- Referral is supported by Rule: 1.2.1 -- Suspected cancer: "
                "recognition and referral (difficulty swallowing).\n"
                "- Suspected cancer: recognition and referral signals noted -- "
                "routine (no specified timeframe)."
            ),
            "actions": [],
        }
    )

    result = await call_recommendation(
        situation_md="Dysphagia referral.",
        background_md="Background details.",
        assessment_md="Two rules fired.",
        assessment_rules=rules,
        guideline_titles=["Suspected cancer: recognition and referral"],
        guidelines=["NG12"],
        invoker=invoker,
        prompt_fetcher=lambda _name: "stub",
    )

    assert result["error"] is None
    assert "Rule: 1.2.1 and Rule: 1.2.7" in result["markdown"]
