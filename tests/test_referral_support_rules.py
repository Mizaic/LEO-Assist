"""2WW support rules stay; primary-care test rules do not claim support.

When a two-week-wait rule has already fired, ultrasound or CA125
rules must not be listed as why the referral is supported.

Atlas:
  DO: DO-B226E498
  VT: VT-LEO-AI-181
"""

from __future__ import annotations

from libs.sbar.assessment_formatter import format_assessment
from libs.sbar.prompt_calls import build_referral_justification_bullet
from libs.sbar.referral_support import support_rules_for_referral


def _rule(rid: str, *, priority: str, name: str) -> dict:
    return {
        "rule_id": rid,
        "name": name,
        "strength": "offer",
        "guideline_id": "NG12",
        "guideline_title": "Suspected cancer: recognition and referral",
        "actions": [{"priority": priority, "name": name, "due_days": 14}],
        "action": {"priority": priority, "name": name, "due_days": 14},
    }


def test_support_rules_keep_2ww_and_drop_primary_care_tests() -> None:
    rules = [
        _rule("1.5.14", priority="2ww", name="1.5.14"),
        _rule("1.5.2", priority="urgent", name="Rule: 1.5.2"),
        _rule("1.5.3", priority="routine", name="Rule: 1.5.3"),
    ]

    support = support_rules_for_referral(rules)
    ids = {str(rule.get("rule_id")) for rule in support}

    assert ids == {"1.5.14"}


def test_support_rules_empty_when_no_time_critical_rule() -> None:
    rules = [
        _rule("1.5.2", priority="urgent", name="Rule: 1.5.2"),
        _rule("1.5.3", priority="routine", name="Rule: 1.5.3"),
    ]

    support = support_rules_for_referral(rules)
    ids = {str(rule.get("rule_id")) for rule in support}

    assert ids == set()


def test_spoa_primary_matches_omit_primary_care_tests_when_2ww_fired() -> None:
    rules = [
        _rule("1.5.14", priority="2ww", name="1.5.14"),
        _rule("1.5.2", priority="urgent", name="Rule: 1.5.2"),
        _rule("1.5.3", priority="routine", name="Rule: 1.5.3"),
    ]
    out = format_assessment(
        matched_rules=rules,
        patient_codes=["76742009"],
        compliance_context={
            "primary": {
                "service_name": "Sherwood 2WW Gynaecology",
                "service_specialty": "2WW Gynaecology",
                "guideline_ids": ["NG12"],
                "supported": True,
                "matched_rules": rules,
            },
            "alternatives": {"matched_rules": []},
        },
    )

    assert "Primary matches" in out.markdown
    assert "1.5.14" in out.markdown
    assert "Rule: 1.5.2" in out.markdown
    assert "Rule: 1.5.3" in out.markdown
    primary = out.markdown.split("**Other guidelines")[0]
    assert "1.5.14" in primary
    assert "Rule: 1.5.2" not in primary
    assert "Rule: 1.5.3" not in primary
    assert "Other guidelines that would support this request" in out.markdown


def test_offer_only_rules_do_not_claim_receiving_service_support() -> None:
    rules = [_rule("1.10.4", priority="routine", name="Rule: 1.10.4")]
    out = format_assessment(
        matched_rules=rules,
        patient_codes=["66308002"],
        compliance_context={
            "primary": {
                "service_name": "Breast Clinic",
                "service_specialty": "2WW Breast",
                "guideline_ids": ["NG12"],
                "supported": True,
                "matched_rules": rules,
            },
            "alternatives": {"matched_rules": []},
        },
    )

    assert "**Supported by receiving service?** no." in out.markdown
    assert "Rule: 1.10.4" in out.markdown
    assert "Other guidelines that would support this request" in out.markdown


def test_justification_bullet_cites_2ww_not_primary_care_tests() -> None:
    rules = [
        _rule("1.5.14", priority="2ww", name="1.5.14"),
        _rule("1.5.2", priority="urgent", name="Rule: 1.5.2"),
        _rule("1.5.3", priority="routine", name="Rule: 1.5.3"),
    ]

    bullet = build_referral_justification_bullet(rules)

    assert "1.5.14" in bullet
    assert "1.5.2" not in bullet
    assert "1.5.3" not in bullet
