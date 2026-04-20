"""Plain-English rule labels in scaffolded test patient descriptions.

Reviewers must NEVER see a raw rule_id like
``rule:NG12:v1:CH002:SEC000:R004:6d4e9c13:edit:dd11e8d3:edit:a0b74f59``
in a description (per .cursor/rules/health-literacy.mdc -- UK
reading age 11). The scaffolder picks the friendliest label
available from the rule payload before persisting the patient.

These tests pin the fall-through chain:

  1. ``rule_name``                  -- preferred
  2. first line of ``recommendation_text`` (trimmed, ~120 chars)
  3. ``rule_id``                    -- last resort
"""

from __future__ import annotations

from app.services.test_patient_scaffolder import _friendly_rule_label


def _make_rule(**overrides):
    base = {
        "rule_id": (
            "rule:NG12:v1:CH002:SEC000:R004:6d4e9c13"
            ":edit:dd11e8d3:edit:a0b74f59"
        ),
        "rule_name": "",
        "recommendation_text": "",
        "guideline_title": "Suspected cancer: recognition and referral",
    }
    base.update(overrides)
    return base


class TestFriendlyRuleLabel:
    def test_prefers_curated_rule_name_when_present(self):
        rule = _make_rule(rule_name="Suspected mesothelioma -- urgent X-ray")
        assert (
            _friendly_rule_label(rule)
            == '"Suspected mesothelioma -- urgent X-ray"'
        )

    def test_falls_back_to_recommendation_text_first_line(self):
        rule = _make_rule(
            rule_name="",
            recommendation_text=(
                "Offer an urgent chest X-ray (to be done within 2 weeks) "
                "to assess for mesothelioma in people aged 40 and over.\n"
                "Second line should be ignored."
            ),
        )
        label = _friendly_rule_label(rule)
        assert label.startswith('"Offer an urgent chest X-ray')
        assert "Second line" not in label

    def test_truncates_long_recommendation_text_with_ellipsis(self):
        long_text = "A" * 300
        rule = _make_rule(rule_name="", recommendation_text=long_text)
        label = _friendly_rule_label(rule)
        assert label.endswith('..."')
        # Strip the surrounding quotes and the ellipsis when sizing.
        body = label[1:-1]
        assert len(body) <= 120

    def test_strips_trailing_colon_from_recommendation(self):
        rule = _make_rule(
            rule_name="",
            recommendation_text="Refer using a suspected cancer pathway:",
        )
        assert (
            _friendly_rule_label(rule)
            == '"Refer using a suspected cancer pathway"'
        )

    def test_falls_back_to_rule_id_only_when_nothing_else_set(self):
        rule = _make_rule(rule_name="", recommendation_text="")
        assert _friendly_rule_label(rule) == rule["rule_id"]

    def test_blank_strings_are_treated_as_empty(self):
        rule = _make_rule(rule_name="   ", recommendation_text="\n  \n")
        assert _friendly_rule_label(rule) == rule["rule_id"]
