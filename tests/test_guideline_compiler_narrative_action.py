"""Compiler narrative action shape -- static source + helper coverage."""

from __future__ import annotations

from pathlib import Path

from libs.guidance.narrative_actions import procedure_compliance_actions
from libs.terminology.local_concepts import validate_action_kind

_COMPILER = (
    Path(__file__).resolve().parents[1]
    / "services/terminology_api/app/services/guideline_compiler.py"
)


class TestCompilerSourceCarriesNarrativeFields:
    def test_fetch_actions_selects_action_kind_and_text(self):
        src = _COMPILER.read_text(encoding="utf-8")
        assert "ha.actionKind" in src or "action_kind" in src
        assert "ha.actionText" in src or "action_text" in src
        assert "validate_action_kind" in src


class TestActionKindHelpers:
    def test_validate_defaults(self):
        assert validate_action_kind(None) == "snomed_procedure"
        assert validate_action_kind("narrative") == "narrative"

    def test_compliance_filter_drops_narrative(self):
        kept = procedure_compliance_actions(
            [
                {"concept_id": "LEO-ACT-ADVISE", "action_kind": "narrative"},
                {"concept_id": "1", "action_kind": "snomed_procedure"},
            ]
        )
        assert len(kept) == 1
        assert kept[0]["concept_id"] == "1"
