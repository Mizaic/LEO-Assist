"""VT -- SBAR reason and status stay honest.

Atlas:
  DI: DI-979BDE66
  DO: DO-E2BF30E7
  VT: VT-D9EC5652
  Risk: R-A6FDB3CD
"""

from __future__ import annotations

from libs.cypher.sbar_assessment_queries import (
    FINALISE_ASSESSMENT,
    SET_ASSESSMENT_NARRATIVE,
    SET_BACKGROUND,
    SET_RECOMMENDATION,
    SET_SITUATION,
)
from libs.pipeline_graph.subgraphs.referral_reason import _REASON_PATTERNS
from libs.pipeline_graph.subgraphs.sbar import _partition_pipeline_messages
from libs.sbar.referral_reason_match import (
    extract_form_clinical_section,
    text_matches_reason_header,
)
from libs.sbar.section_status import integrity_status_for, section_status
from libs.sbar.situation_source import build_structured_situation


def test_table_cell_reason_header_matches() -> None:
    table = (
        "| Field | Value |\n"
        "| --- | --- |\n"
        "| Reason for referral | New lump left breast |\n"
    )
    assert text_matches_reason_header(table) is True
    joined = table.lower()
    assert any(pattern in joined for pattern in _REASON_PATTERNS)


def test_cis_layout_reason_header_matches() -> None:
    cis = (
        "Clinical Information Summary\n"
        "Reason for referral\n"
        "Patchy erythematous rash on the left breast.\n"
    )
    assert text_matches_reason_header(cis) is True


def test_missing_header_uses_taught_clinical_section_not_letter_prefix() -> None:
    letter = (
        "NHS Confidential cover page and clinic address.\n"
        "Please include duration and site\n"
        "6 week left breast lump, no skin change.\n"
        "Guidance: mastalgia is managed in primary care.\n"
    )
    sections = [
        {
            "section_id": "admin_header",
            "section_type": "admin",
            "label": "Header",
            "start_pattern": "NHS Confidential",
        },
        {
            "section_id": "details_narrative",
            "section_type": "free_text",
            "label": "Details",
            "start_pattern": "Please include duration and site",
        },
        {
            "section_id": "mastalgia_guidance",
            "section_type": "template_noise",
            "label": "Guidance",
            "start_pattern": "mastalgia is managed",
        },
    ]
    section = extract_form_clinical_section(letter, sections)
    assert section is not None
    assert "6 week left breast lump" in section
    assert "NHS Confidential" not in section

    result = build_structured_situation(
        referral_request=None,
        referral_reason=None,
        trigger_scoped_letter=letter,
        form_sections=sections,
    )
    assert result.source_precedence == ["form_clinical_section"]
    assert "6 week left breast lump" in result.headline
    assert not result.headline.startswith("NHS Confidential")
    assert "1800" not in result.headline


def test_audit_blockers_stay_errors_and_statuses_match_outcome() -> None:
    errors, warnings = _partition_pipeline_messages(
        [
            "situation:LLM timeout",
            "audit:execution_manifest_missing, audit_link_missing",
            "audit_link_missing",
            "prompt_hash_missing:situation",
        ]
    )
    assert "situation:LLM timeout" in errors
    assert any("audit" in item or "prompt_hash_missing" in item for item in errors)
    assert warnings == []
    assert section_status(text="", error="situation:LLM timeout") == "failed"
    assert section_status(text="Headline.", error=None) == "completed"
    assert section_status(text="", error=None) == "skipped"
    assert integrity_status_for(audit_blockers=["audit_link_missing"]) == "failed"
    assert "$situation_status" in SET_SITUATION
    assert "situation_status = 'completed'" not in SET_SITUATION
    assert "$background_status" in SET_BACKGROUND
    assert "$assessment_status" in SET_ASSESSMENT_NARRATIVE
    assert "$recommendation_status" in SET_RECOMMENDATION
    assert "$context_integrity_status" in FINALISE_ASSESSMENT
