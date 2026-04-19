"""VT-LEO-AI-181: deterministic Assessment formatter for SBAR.

Verifies DI-LEO-AI-189 acceptance criteria:
- Empty matched_rules produce a 'no matches' fallback narrative
- Rules are sorted by priority (2WW first), then confidence
- The 2WW heading is rendered when any 2WW rule fires
- Pathway hints (stt / rtr / alternative_pathway) are derived
  deterministically from the rules without LLM calls
"""

from __future__ import annotations

from libs.sbar.assessment_formatter import format_assessment


def _rule(rid: str, *, priority: str, due_days: int | None = None,
          name: str = "Rule", strength: str = "strong",
          guideline_id: str = "G-1") -> dict:
    return {
        "rule_id": rid,
        "name": name,
        "strength": strength,
        "guideline_id": guideline_id,
        "guideline_title": "Test guideline",
        "chapter_title": "Ch1",
        "recommendation_verbatim": "Refer urgently to specialist",
        "action": {
            "priority": priority,
            "due_days": due_days,
            "name": "Specialist referral",
        },
        "confidence": 1.0,
    }


def test_empty_match_yields_no_match_narrative() -> None:
    out = format_assessment(matched_rules=[], patient_codes=["123", "456"])
    assert "No matching guideline rules" in out.markdown
    assert out.rules == []
    assert out.codes == ["123", "456"]
    assert out.pathway_hints["rtr"] == "no"
    assert out.pathway_hints["stt"] is None


def test_2ww_rule_fires_pathway_hints_and_heading() -> None:
    rules = [
        _rule("R-2WW", priority="2ww", due_days=14, name="2WW lung"),
        _rule("R-ROUTINE", priority="routine", name="Routine FBC"),
    ]
    out = format_assessment(matched_rules=rules, patient_codes=["123"])

    assert "Two week wait" in out.markdown
    assert "R-2WW" in out.markdown
    assert "Within 14 days (two-week wait)" == out.pathway_hints["stt"]
    assert "R-2WW" in (out.pathway_hints["stt_evidence"] or "")
    assert out.pathway_hints["rtr"] == "yes"
    assert "R-2WW" in out.pathway_hints["rtr_evidence"]
    assert out.pathway_hints["alternative_pathway"] is not None


def test_only_routine_rule_keeps_rtr_no() -> None:
    rules = [_rule("R-ROUTINE", priority="routine", name="Routine review")]
    out = format_assessment(matched_rules=rules, patient_codes=["1"])

    assert out.pathway_hints["rtr"] == "no"
    assert "routine" in (out.pathway_hints["rtr_evidence"] or "").lower()
    assert out.pathway_hints["alternative_pathway"] is not None


def test_rules_are_priority_sorted() -> None:
    rules = [
        _rule("R-ROUTINE", priority="routine", name="Routine"),
        _rule("R-URGENT", priority="urgent", name="Urgent"),
        _rule("R-2WW", priority="2ww", due_days=14, name="2WW"),
    ]
    out = format_assessment(matched_rules=rules, patient_codes=["1"])
    md = out.markdown
    assert md.find("R-2WW") < md.find("R-URGENT") < md.find("R-ROUTINE")


def test_rule_snapshot_is_trimmed_and_serialisable() -> None:
    rules = [_rule("R-1", priority="urgent")]
    out = format_assessment(matched_rules=rules, patient_codes=["1"])
    assert len(out.rules) == 1
    snap = out.rules[0]
    assert snap["rule_id"] == "R-1"
    assert "recommendation_verbatim" in snap
    assert snap["action"]["priority"] == "urgent"


# -- Synonym set: matched_via rendering (UN-LEO-AI-093 / DI-LEO-AI-510) ------


def test_matched_via_renders_specific_seed_in_markdown() -> None:
    """Markdown bullet names the descendant code that fired the rule."""
    rule = _rule("R-1", priority="urgent", name="Smoker rule")
    rule["matched_via"] = [
        {
            "node_id": "n1",
            "primary_concept_id": "1",
            "preferred_term": "Smoker",
            "matched_concept_ids": ["2"],
        }
    ]
    out = format_assessment(matched_rules=[rule], patient_codes=["2"])
    assert "Matched on" in out.markdown
    assert "Smoker" in out.markdown
    assert "kind of Smoker" in out.markdown
    assert "`2`" in out.markdown


def test_matched_via_renders_primary_only_when_primary_id_hits() -> None:
    """When only the primary id hit, the rendered text is just the chip label."""
    rule = _rule("R-1", priority="urgent", name="Smoker rule")
    rule["matched_via"] = [
        {
            "node_id": "n1",
            "primary_concept_id": "1",
            "preferred_term": "Smoker",
            "matched_concept_ids": ["1"],
        }
    ]
    out = format_assessment(matched_rules=[rule], patient_codes=["1"])
    assert "Matched on: Smoker" in out.markdown
    assert "kind of" not in out.markdown


def test_matched_via_preserved_in_rule_snapshot() -> None:
    """matched_via survives into the JSON snapshot the LLM prompt consumes."""
    rule = _rule("R-1", priority="urgent")
    rule["matched_via"] = [
        {
            "node_id": "n1",
            "primary_concept_id": "1",
            "preferred_term": "Smoker",
            "matched_concept_ids": ["2"],
        }
    ]
    out = format_assessment(matched_rules=[rule], patient_codes=["2"])
    assert "matched_via" in out.rules[0]
    assert out.rules[0]["matched_via"][0]["matched_concept_ids"] == ["2"]


def test_no_matched_via_keeps_legacy_markdown_behaviour() -> None:
    """Rules without matched_via render exactly as before (back-compat)."""
    rule = _rule("R-1", priority="urgent")
    out = format_assessment(matched_rules=[rule], patient_codes=["1"])
    assert "Matched on" not in out.markdown
    assert "matched_via" not in out.rules[0]
