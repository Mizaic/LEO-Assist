"""Narrative action filtering -- happy and non-happy paths."""

from __future__ import annotations

from libs.guidance.narrative_actions import (
    display_action_label,
    procedure_compliance_actions,
    strike_completed_action,
)


class TestProcedureComplianceFilter:
    def test_keeps_snomed_procedures(self):
        actions = [
            {
                "concept_id": "183851006",
                "name": "Referral to dermatology",
                "action_kind": "snomed_procedure",
            }
        ]
        assert len(procedure_compliance_actions(actions)) == 1

    def test_drops_narrative_actions(self):
        actions = [
            {
                "concept_id": "LEO-ACT-ADVISE",
                "name": "Advise",
                "action_kind": "narrative",
                "action_text": "Advise non-alkaline cleanser",
            },
            {
                "concept_id": "183851006",
                "name": "Referral",
                "action_kind": "snomed_procedure",
            },
        ]
        kept = procedure_compliance_actions(actions)
        assert len(kept) == 1
        assert kept[0]["concept_id"] == "183851006"

    def test_empty_and_none_safe(self):
        assert procedure_compliance_actions(None) == []
        assert procedure_compliance_actions([]) == []


class TestDisplayLabel:
    def test_narrative_prefers_action_text(self):
        assert (
            display_action_label(
                {
                    "action_kind": "narrative",
                    "name": "Advise",
                    "action_text": "Use a syndet cleanser",
                }
            )
            == "Use a syndet cleanser"
        )

    def test_procedure_uses_name(self):
        assert (
            display_action_label(
                {"action_kind": "snomed_procedure", "name": "Urgent referral"}
            )
            == "Urgent referral"
        )

    def test_completed_action_is_struck_through(self):
        assert (
            display_action_label(
                {
                    "action_kind": "snomed_procedure",
                    "name": "Ultrasound scan of abdomen and pelvis",
                    "already_done": True,
                }
            )
            == "~~Ultrasound scan of abdomen and pelvis~~ (already done)"
        )

    def test_outstanding_action_is_not_struck_through(self):
        assert (
            display_action_label(
                {
                    "action_kind": "snomed_procedure",
                    "name": "Ultrasound scan of abdomen and pelvis",
                    "already_done": False,
                }
            )
            == "Ultrasound scan of abdomen and pelvis"
        )


class TestStrikeCompletedAction:
    def test_wraps_label_in_markdown_strike(self):
        assert (
            strike_completed_action("Ultrasound scan of abdomen and pelvis")
            == "~~Ultrasound scan of abdomen and pelvis~~ (already done)"
        )

    def test_empty_label_stays_empty(self):
        assert strike_completed_action("") == ""
        assert strike_completed_action("   ") == ""
