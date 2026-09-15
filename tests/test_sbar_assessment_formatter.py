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


def _rule(
    rid: str,
    *,
    priority: str,
    due_days: int | None = None,
    name: str = "Rule",
    strength: str = "strong",
    guideline_id: str = "G-1",
) -> dict:
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
    assert "2WW lung" in out.markdown
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
    # Markdown bullets cite the rule name, not rule_id.
    assert md.find("**2WW**") < md.find("**Urgent**") < md.find("**Routine**")


def test_very_urgent_outranks_2ww_and_urgent() -> None:
    """NICE very-urgent (48h) must bucket above 2WW and plain urgent."""
    rules = [
        _rule("R-URGENT", priority="urgent", due_days=7, name="Urgent arm"),
        _rule("R-2WW", priority="2ww", due_days=14, name="2WW arm"),
        _rule(
            "R-VU",
            priority="very_urgent",
            due_days=2,
            name="Very urgent arm",
        ),
    ]
    out = format_assessment(matched_rules=rules, patient_codes=["1"])
    md = out.markdown
    assert "### Very urgent (within 48 hours)" in md
    assert md.find("Very urgent arm") < md.find("2WW arm") < md.find("Urgent arm")
    assert out.pathway_hints["stt"] == "Within 2 days (very urgent)"
    assert out.pathway_hints["rtr"] == "yes"
    assert "R-VU" in (out.pathway_hints["rtr_evidence"] or "")


def test_rule_snapshot_is_trimmed_and_serialisable() -> None:
    rules = [_rule("R-1", priority="urgent")]
    out = format_assessment(matched_rules=rules, patient_codes=["1"])
    assert len(out.rules) == 1
    snap = out.rules[0]
    assert snap["rule_id"] == "R-1"
    # Verbatim recommendation text is intentionally excluded from the
    # trimmed snapshot (keeps the recommendation LLM from anchoring).
    assert "recommendation_verbatim" not in snap
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
    assert "**Matched on:**" in out.markdown
    assert "Smoker (related finding)" in out.markdown


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
    assert "**Matched on:** Smoker" in out.markdown
    assert "related finding" not in out.markdown


def test_matched_via_renders_age_and_gender() -> None:
    rule = _rule("R-1", priority="2ww", name="Breast rule")
    rule["matched_via"] = [
        {
            "kind": "DEMOGRAPHIC",
            "field": "age",
            "operator": ">=",
            "value": 50,
            "patient_value": 71,
        },
        {
            "kind": "DEMOGRAPHIC",
            "field": "sex",
            "operator": "=",
            "value": "female",
            "patient_value": "female",
        },
        {
            "primary_concept_id": "162164007",
            "preferred_term": "Nipple discharge symptom (finding)",
            "matched_concept_ids": ["162164007"],
        },
    ]
    out = format_assessment(matched_rules=[rule], patient_codes=["162164007"])
    assert (
        "**Matched on:** Age 71 years (50 or over); Gender recorded as female; "
        "Nipple discharge symptom" in out.markdown
    )


def test_matched_via_renders_multiple_related_leaves_without_repeated_clause() -> None:
    """Several descendant hits under different leaves stay easy to scan.

    Each leaf gets its own trailing "(related finding)" qualifier
    instead of every fragment repeating a leading "a related coded
    finding for ..." clause, which reads clunky once several leaves
    are joined with "; " in one Matched on line.
    """
    rule = _rule("R-1", priority="urgent", name="Lung rule")
    rule["matched_via"] = [
        {
            "node_id": "n1",
            "primary_concept_id": "1",
            "preferred_term": "Finding of tobacco smoking consumption",
            "matched_concept_ids": ["2"],
        },
        {
            "node_id": "n2",
            "primary_concept_id": "3",
            "preferred_term": "Weight decreased",
            "matched_concept_ids": ["4"],
        },
    ]
    out = format_assessment(matched_rules=[rule], patient_codes=["2", "4"])
    assert (
        "**Matched on:** Finding of tobacco smoking consumption "
        "(related finding); Weight decreased (related finding)" in out.markdown
    )
    assert "a related coded finding for" not in out.markdown


def test_matched_via_dedupes_identical_leaf_labels() -> None:
    """Repeated CONCEPT leaves with the same label render once in Matched on."""
    rule = _rule("R-1", priority="routine", name="FIT rule")
    rule["matched_via"] = [
        {
            "node_id": "n1",
            "primary_concept_id": "262285001",
            "preferred_term": "Weight decreased (finding)",
            "matched_concept_ids": ["262285001"],
        },
        {
            "node_id": "n2",
            "primary_concept_id": "262285001",
            "preferred_term": "Weight decreased (finding)",
            "matched_concept_ids": ["262285001"],
        },
        {
            "node_id": "n3",
            "primary_concept_id": "448765001",
            "preferred_term": "Weight decreased (finding)",
            "matched_concept_ids": ["448765001"],
        },
    ]
    out = format_assessment(matched_rules=[rule], patient_codes=["262285001"])
    assert "**Matched on:** Weight decreased" in out.markdown
    assert out.markdown.count("Weight decreased") == 1
    # Audit snapshot still keeps every leaf that fired.
    assert len(out.rules[0]["matched_via"]) == 3


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


def test_excluded_present_preserved_in_rule_snapshot() -> None:
    rule = _rule("R-1", priority="urgent")
    rule["excluded_present"] = ["65576009"]
    out = format_assessment(matched_rules=[rule], patient_codes=["74285003"])
    assert out.rules[0]["excluded_present"] == ["65576009"]


def test_no_matched_via_keeps_legacy_markdown_behaviour() -> None:
    """Rules without matched_via omit the Matched on landmark (back-compat)."""
    rule = _rule("R-1", priority="urgent")
    out = format_assessment(matched_rules=[rule], patient_codes=["1"])
    assert "Matched on" not in out.markdown
    assert "matched_via" not in out.rules[0]


def test_assessment_landmarks_are_bold_and_guideline_includes_code() -> None:
    """Assessment landmarks render as bold Markdown; Guideline shows title + code."""
    rule = _rule("R-1", priority="urgent", guideline_id="NG12")
    rule["guideline_title"] = "Suspected cancer: recognition and referral"
    out = format_assessment(matched_rules=[rule], patient_codes=["1"])
    assert "**Recommendation:**" in out.markdown
    assert "**Action:**" in out.markdown
    assert (
        "**Guideline:** NICE Suspected cancer: recognition and referral (`NG12`)"
        in out.markdown
    )


# -- Multi-action (Phase 4b: multiple recommended procedures per rule) ------


def _rule_with_actions(
    rid: str,
    *,
    priority: str,
    actions: list[dict],
    due_days: int | None = None,
    name: str = "Rule",
    strength: str = "strong",
    guideline_id: str = "G-1",
) -> dict:
    """Build a rule using the new evaluator ``actions`` list shape.

    Mirrors ``_format_match``'s output: ``actions`` is the source of truth
    and ``action`` (singular) is the back-compat shim equal to actions[0].
    """
    return {
        "rule_id": rid,
        "name": name,
        "strength": strength,
        "guideline_id": guideline_id,
        "guideline_title": "Test guideline",
        "chapter_title": "Ch1",
        "recommendation_verbatim": "Refer urgently to specialist",
        "actions": actions,
        "action": actions[0] if actions else None,
        "confidence": 1.0,
    }


def test_single_action_via_actions_list_is_byte_identical_to_legacy_action() -> None:
    """CRITICAL REGRESSION GUARD: a rule with exactly one action, expressed
    via the new ``actions`` list, must produce byte-identical markdown and
    an identical rule snapshot to the legacy singular ``action`` shape."""
    legacy_rule = _rule("R-1", priority="urgent", due_days=7)
    new_rule = _rule_with_actions(
        "R-1",
        priority="urgent",
        due_days=7,
        actions=[{"priority": "urgent", "due_days": 7, "name": "Specialist referral"}],
    )

    legacy_out = format_assessment(matched_rules=[legacy_rule], patient_codes=["1"])
    new_out = format_assessment(matched_rules=[new_rule], patient_codes=["1"])

    assert new_out.markdown == legacy_out.markdown
    assert new_out.pathway_hints == legacy_out.pathway_hints
    # Snapshots differ only in the extra "actions" key the new shape adds;
    # every pre-existing key/value must be unchanged.
    legacy_snap = legacy_out.rules[0]
    new_snap = new_out.rules[0]
    for key, value in legacy_snap.items():
        assert new_snap[key] == value


def test_two_actions_render_one_line_each_and_keep_rule_level_priority() -> None:
    """A rule with two recommended actions must render one 'Action:' line
    per action, while priority/due_days-based sorting and headings stay
    rule-level (unaffected by the number of actions)."""
    rule = _rule_with_actions(
        "R-2ACTIONS",
        priority="2ww",
        due_days=14,
        name="Suspected cancer",
        actions=[
            {
                "priority": "2ww",
                "due_days": 14,
                "name": "Suspected cancer pathway referral",
            },
            {
                "priority": "2ww",
                "due_days": 14,
                "name": "Full blood count",
            },
        ],
    )
    out = format_assessment(matched_rules=[rule], patient_codes=["1"])

    assert (
        "**Action:** Suspected cancer pathway referral (within 14 days)" in out.markdown
    )
    assert "**Action:** Full blood count (within 14 days)" in out.markdown
    assert out.markdown.count("**Action:**") == 2
    # Still exactly one 2WW heading -- priority stays rule-level, not per-action.
    assert out.markdown.count("### Two week wait") == 1


def test_already_actioned_rule_moves_under_already_done_heading() -> None:
    """Completed matches stay visible under Already done, not in Primary matches."""
    open_rule = _rule("R-1514", priority="2ww", due_days=1, name="1.5.14")
    done_rule = _rule_with_actions(
        "R-152",
        priority="urgent",
        due_days=14,
        name="Rule: 1.5.2",
        actions=[
            {
                "priority": "urgent",
                "due_days": 14,
                "name": "Ultrasound scan of abdomen and pelvis",
                "already_done": True,
            }
        ],
    )
    done_rule["already_actioned"] = True
    out = format_assessment(
        matched_rules=[open_rule, done_rule],
        patient_codes=["1"],
        compliance_context={
            "primary": {
                "supported": True,
                "service_name": "Sherwood gynae 2WW",
                "guideline_ids": ["NG12"],
                "matched_rules": [open_rule, done_rule],
            }
        },
    )
    done_at = out.markdown.find("### Already done (1)")
    assert done_at != -1
    assert out.markdown.find("**1.5.14**") < done_at
    assert out.markdown.find("**Rule: 1.5.2**") > done_at
    assert "Other guidelines that would support this request" not in out.markdown


def test_completed_action_renders_struck_through_not_hidden() -> None:
    """DI-B3B44F09: already-done actions stay visible and are crossed out."""
    rule = _rule_with_actions(
        "R-152",
        priority="urgent",
        due_days=14,
        name="Rule: 1.5.2",
        actions=[
            {
                "priority": "urgent",
                "due_days": 14,
                "name": "Ultrasound scan of abdomen and pelvis",
                "already_done": True,
            }
        ],
    )
    out = format_assessment(matched_rules=[rule], patient_codes=["1"])
    assert "Rule: 1.5.2" in out.markdown
    assert (
        "**Action:** ~~Ultrasound scan of abdomen and pelvis~~ (already done)"
        in out.markdown
    )
    assert "(within 14 days)" not in out.markdown


def test_rule_with_no_actions_renders_no_action_lines() -> None:
    """A rule with an empty actions list renders zero 'Action:' lines
    instead of raising, matching the legacy None-action behaviour."""
    rule = _rule_with_actions("R-NOACTION", priority="routine", actions=[])
    out = format_assessment(matched_rules=[rule], patient_codes=["1"])
    assert "**Action:**" not in out.markdown


def test_unverified_first_presentation_is_named_in_assessment() -> None:
    """DI-C93802C8: Assessment names first presentation and says it could not be confirmed."""
    rule = _rule("R-1513", priority="urgent", name="Consider ultrasound")
    rule["unverified_qualifiers"] = ["first_presentation"]
    out = format_assessment(matched_rules=[rule], patient_codes=["1"])
    md = out.markdown
    assert "first presentation" in md
    assert "could not confirm that from this letter" in md
    assert "still shown this match so a possible cancer is not missed" in md
    assert "offered the scan" not in md
    assert "check whether this is a first episode" in md
    assert "qualifier" not in md.lower()
    assert "benefit of the doubt" not in md.lower()


def test_unverified_unexplained_uses_same_pattern() -> None:
    """DI-C93802C8: unexplained uses the same everyday-English pattern."""
    rule = _rule("R-U", priority="urgent", name="Unexplained rule")
    rule["unverified_qualifiers"] = ["unexplained"]
    out = format_assessment(matched_rules=[rule], patient_codes=["1"])
    assert "unexplained" in out.markdown
    assert "could not confirm that from this letter" in out.markdown
    assert "qualifier" not in out.markdown.lower()
