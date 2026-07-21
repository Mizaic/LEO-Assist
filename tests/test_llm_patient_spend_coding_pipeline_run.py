"""Regression tests for the Phase A coding-PipelineRun UNION arm added to
GET_PATIENT_LLM_SPEND (2026-07 CTO peer-review item 3: LLM telemetry
end-to-end population).

Atlas trace: covered by existing DI-LEO-AI-506/517/518 family (query
extension only, no new write path or entity shape -- see plan item 3,
Phase A). Look up via search_design_controls(query="LLM patient spend").

Why these tests are query-text + logic-simulation, not a live-Neo4j
integration test: this repo's test suite mocks Neo4j sessions everywhere
(tests/conftest.py `mock_patient_graph` / `mock_knowledge_graph`); there is
no live-Cypher test harness or Neo4j test container wired into `pytest`
here, and no local Docker daemon is available in this environment to add
one for a single query change. Instead, this module:

1. Asserts the query TEXT has exactly the UNION arm structure expected,
   so a future edit cannot silently drop the double-count guard or the
   new `source` discriminator (`test_query_text_*`).
2. Re-implements the WHERE-clause arm-selection logic the query encodes
   for `AuditEvent {type:'PipelineRun'}` rows as a small, exhaustively
   tested pure-Python classifier, and cross-checks that classifier's
   subtype exclusion list against the *actual* query text via regex, so
   the two cannot silently drift apart (`test_classifier_matches_query_*`,
   `_arm_for_subtype`).
3. Uses that classifier to assert row-count / total non-duplication
   across a representative subtype matrix, satisfying the plan's "row
   count and total assertions, not just 'some row exists'" requirement
   at the logic level.

If/when a live-Neo4j integration harness is added to this repo, this
module should be supplemented (not replaced) with a real end-to-end test
that seeds AuditEvent nodes and calls `GET_PATIENT_LLM_SPEND` directly.
"""

from __future__ import annotations

import re

from libs.cypher.model_config_queries import GET_PATIENT_LLM_SPEND

_EPISODE_ENGINE_SUBTYPE = "episode_engine"
_GUIDANCE_SUBTYPES = {"guidance_rule_extraction", "guidance_rule_dry_run"}


def _new_arm_excluded_subtypes() -> set[str]:
    """Extract the subtype exclusion list for the new coding-pipeline-run
    arm directly from the query text, so this test fails loudly if the
    guard clause is edited without updating this test."""
    match = re.search(
        r"AuditEvent rows written by WorkflowEngine.*?NOT IN\s*\n?\s*\[(.*?)\]",
        GET_PATIENT_LLM_SPEND,
        re.DOTALL,
    )
    assert match, "could not find the new arm's exclusion list in the query text"
    return {s.strip().strip("'\"") for s in match.group(1).split(",")}


def _arm_for_subtype(subtype: str | None) -> str:
    """Pure-Python mirror of which UNION arm an AuditEvent{type:'PipelineRun'}
    row lands in, given its `subtype`. Mirrors the WHERE clauses in
    GET_PATIENT_LLM_SPEND for the three AuditEvent-based arms."""
    if subtype == _EPISODE_ENGINE_SUBTYPE:
        return "episode_engine"
    if subtype in _GUIDANCE_SUBTYPES:
        return subtype  # coalesce(ae.subtype, 'guidance') -- subtype is set here
    excluded = {_EPISODE_ENGINE_SUBTYPE, *_GUIDANCE_SUBTYPES}
    if subtype is None or subtype not in excluded:
        return "coding_pipeline_run"
    raise AssertionError(f"subtype {subtype!r} matched no arm -- gap in classifier")


def test_query_text_has_exactly_five_union_arms():
    # coding_extraction, sbar_assessment, episode_engine, guidance*,
    # coding_pipeline_run (new) -- 5 arms joined by 4 UNION keywords.
    assert GET_PATIENT_LLM_SPEND.count("UNION") == 4


def test_query_text_declares_coding_pipeline_run_source():
    assert "'coding_pipeline_run'   AS source" in GET_PATIENT_LLM_SPEND


def test_query_text_new_arm_excludes_episode_engine_and_guidance_subtypes():
    excluded = _new_arm_excluded_subtypes()
    assert excluded == {_EPISODE_ENGINE_SUBTYPE, *_GUIDANCE_SUBTYPES}


def test_query_text_new_arm_filters_on_patient_and_token_presence():
    # The new arm must reuse the same patient/date/non-null-tokens guards
    # as the other three arms -- otherwise it could leak cross-patient
    # rows or platform-level (patient_id IS NULL) runs into a patient view.
    new_arm_start = GET_PATIENT_LLM_SPEND.index("coding_pipeline_run")
    new_arm_text = GET_PATIENT_LLM_SPEND[
        GET_PATIENT_LLM_SPEND.rindex("MATCH", 0, new_arm_start) : new_arm_start
    ]
    assert "ae.patient_id = $patient_id" in new_arm_text
    assert "ae.llm_input_tokens IS NOT NULL" in new_arm_text


def test_classifier_matches_query_exclusion_list():
    """The hand-maintained classifier's exclusion set must equal what the
    query text actually excludes -- catches drift if either changes."""
    assert _new_arm_excluded_subtypes() == {
        _EPISODE_ENGINE_SUBTYPE,
        *_GUIDANCE_SUBTYPES,
    }


def test_workflow_engine_row_with_no_subtype_lands_in_new_arm():
    """A WorkflowEngine._write_audit_event row (libs/workflow/engine.py)
    never sets `subtype`, so it must be classified as coding_pipeline_run."""
    assert _arm_for_subtype(None) == "coding_pipeline_run"


def test_episode_engine_row_is_not_double_counted_by_new_arm():
    assert _arm_for_subtype("episode_engine") == "episode_engine"


def test_guidance_rows_are_not_double_counted_by_new_arm():
    assert _arm_for_subtype("guidance_rule_extraction") == "guidance_rule_extraction"
    assert _arm_for_subtype("guidance_rule_dry_run") == "guidance_rule_dry_run"


def test_unknown_future_subtype_falls_back_to_coding_pipeline_run():
    """Any subtype not already claimed by an existing arm should still
    surface (fail-open, not fail-closed) rather than silently disappear
    from the per-patient view."""
    assert _arm_for_subtype("some_new_pipeline_kind") == "coding_pipeline_run"


def test_mixed_batch_row_counts_and_totals_are_not_double_counted():
    """Simulates a realistic mixed batch of AuditEvent{type:'PipelineRun'}
    rows for one patient and asserts each row is claimed by exactly one
    arm, with per-arm totals matching expectations (row-count + totals,
    not just 'a row exists')."""
    rows = [
        {"subtype": None, "llm_input_tokens": 100},
        {"subtype": None, "llm_input_tokens": 50},
        {"subtype": "episode_engine", "llm_input_tokens": 200},
        {"subtype": "guidance_rule_extraction", "llm_input_tokens": 30},
        {"subtype": "guidance_rule_dry_run", "llm_input_tokens": 10},
    ]

    arms: dict[str, list[dict]] = {}
    for row in rows:
        arm = _arm_for_subtype(row["subtype"])
        arms.setdefault(arm, []).append(row)

    assert len(arms["coding_pipeline_run"]) == 2
    assert sum(r["llm_input_tokens"] for r in arms["coding_pipeline_run"]) == 150

    assert len(arms["episode_engine"]) == 1
    assert sum(r["llm_input_tokens"] for r in arms["episode_engine"]) == 200

    assert len(arms["guidance_rule_extraction"]) == 1
    assert len(arms["guidance_rule_dry_run"]) == 1

    total_rows_claimed = sum(len(v) for v in arms.values())
    assert total_rows_claimed == len(
        rows
    ), "every row must be claimed by exactly one arm"
