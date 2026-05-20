from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

from libs.workflow.validation_workflows import (
    REFERRAL_TRIAGE_PLAN_DEFINITION,
    VALIDATION_WORKFLOW_SPECS,
    all_validation_plan_definitions,
)
from scripts.seed_plan_definitions import ACTIVITY_DEFINITIONS, PLAN_DEFINITIONS
from services.api.app.services import validation_workflow_runner
from services.api.app.routers import extraction_scenarios

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ENGINE = ROOT / "libs/workflow/engine.py"

EXPECTED_SUBGRAPHS = {
    "pd-val-key-fact-extraction": [
        "extraction",
        "post_processing",
        "relation_linking",
        "extraction_check",
    ],
    "pd-val-pathway-criteria": [
        "extraction",
        "post_processing",
        "relation_linking",
        "extraction_check",
        "terminology",
        "compliance",
    ],
    "pd-val-triage-completeness": [
        "extraction",
        "post_processing",
        "relation_linking",
        "extraction_check",
        "quality_check",
    ],
    "pd-val-terminology-mapping": [
        "extraction",
        "post_processing",
        "relation_linking",
        "extraction_check",
        "terminology",
        "surface_form_validation",
    ],
    "pd-val-sbar-summary": [
        "extraction",
        "post_processing",
        "relation_linking",
        "extraction_check",
        "terminology",
        "sbar",
    ],
    "pd-referral-triage-e2e": [
        "extraction",
        "post_processing",
        "relation_linking",
        "extraction_check",
        "terminology",
        "compliance",
        "quality_check",
        "sbar",
        "human_review_gate",
    ],
}


def _seed_plan(plan_id: str) -> dict:
    return next(plan for plan in PLAN_DEFINITIONS if plan["id"] == plan_id)


def _subgraphs(plan: dict) -> list[str]:
    return [action["_subgraphId"] for action in plan["action"]]


def test_seed_includes_un_scoped_validation_plan_definitions():
    for plan_id, expected in EXPECTED_SUBGRAPHS.items():
        assert _subgraphs(_seed_plan(plan_id)) == expected


def test_validation_specs_map_un_to_plan_val_metric_and_contract():
    spec = VALIDATION_WORKFLOW_SPECS["UN-89E2AE36"]

    assert spec.val_id == "VAL-87173594"
    assert spec.plan_definition_id == "pd-val-key-fact-extraction"
    assert spec.metric == "phrase_level_f1"
    assert "terms[].text" in spec.output_contract


def test_e2e_referral_triage_composes_un_scoped_stages():
    action_ids = [item["id"] for item in REFERRAL_TRIAGE_PLAN_DEFINITION["action"]]

    assert action_ids == [
        "act-triage-extract",
        "act-triage-post",
        "act-triage-relation-link",
        "act-triage-extraction-check",
        "act-triage-terminology",
        "act-triage-criteria",
        "act-triage-completeness",
        "act-triage-sbar",
        "act-triage-review",
    ]
    assert any(item["id"] == "ad-human-review-gate" for item in ACTIVITY_DEFINITIONS)


@pytest.mark.asyncio
async def test_runner_maps_un_to_expected_plan_and_actions(monkeypatch):
    captured = {}

    async def fake_run_actions(engine, actions, initial_state):
        captured["actions"] = actions
        captured["state"] = initial_state
        return {"status": "completed", "steps": [], "final_state": {"entities": []}}

    monkeypatch.setattr(validation_workflow_runner, "_run_actions", fake_run_actions)

    result = await validation_workflow_runner.execute_validation_workflow(
        un_id="UN-89E2AE36",
        initial_state={"case_id": "case-1", "encounter_text": "weight loss"},
    )

    assert result["val_id"] == "VAL-87173594"
    assert result["plan_definition_id"] == "pd-val-key-fact-extraction"
    assert [action.subgraph_id for action in captured["actions"]] == [
        "extraction",
        "post_processing",
        "relation_linking",
        "extraction_check",
    ]
    assert captured["state"]["case_id"] == "case-1"


def test_catalog_exposes_all_un_scoped_validation_workflows():
    catalog = validation_workflow_runner.validation_workflow_catalog()
    ids = {item["un_id"] for item in catalog}

    assert ids == set(VALIDATION_WORKFLOW_SPECS)
    assert len(all_validation_plan_definitions()) == 6


def test_extraction_scenario_scorer_uses_validation_workflow(monkeypatch):
    calls = []

    def fake_execute_validation_workflow_sync(*, un_id, initial_state, engine=None):
        calls.append((un_id, initial_state, engine))
        return {
            "status": "completed",
            "final_state": {
                "entities": [
                    {"text": "weight loss"},
                    {"surface_form": "abdominal pain"},
                ]
            },
        }

    monkeypatch.setattr(
        "app.services.validation_workflow_runner.execute_validation_workflow_sync",
        fake_execute_validation_workflow_sync,
    )

    case = {
        "case_id": "case-1",
        "markdown_body": "Referral text with weight loss and abdominal pain.",
        "expected_strings": ["weight loss", "abdominal pain"],
    }

    score = extraction_scenarios._score_case_from_node(case)

    assert calls[0][0] == "UN-89E2AE36"
    assert calls[0][1]["encounter_text"] == case["markdown_body"]
    assert score["f1"] == 1.0


def test_extraction_run_uses_production_pipeline_queue() -> None:
    source = Path(extraction_scenarios.__file__).read_text(encoding="utf-8")
    run_scoring = source[
        source.index("def _run_scoring") : source.index("def _score_case_from_node")
    ]
    publish_jobs = source[
        source.index(
            "async def _publish_production_validation_jobs_async"
        ) : source.index("def _refresh_production_run")
    ]

    assert "execute_validation_workflow_sync" not in run_scoring
    assert "await bus.send(" in source
    assert '"event_type": "validation-run-requested"' in source
    assert '"plan_definition_id": _PRODUCTION_PLAN_ID' in source
    assert '"source_node_type": "ExtractionScenario"' in source
    assert '"source_node_id": case_id' in source
    assert '"source_text_property": "markdown_body"' in source
    assert '"encounter_text": text' not in publish_jobs
    assert '"capture_validation_output": True' in source
    assert "correlation_id=child_run_id" in source


def test_extraction_scenario_list_uses_lightweight_rows(monkeypatch):
    class FakeClient:
        def run(self, query, **params):
            if "count(" in query:
                return [{"total": 1, "approved": 1, "draft": 0}]
            return [
                {
                    "case_id": "case-1",
                    "site": "lung",
                    "expected_strings": '["weight loss"]',
                }
            ]

        def close(self):
            return None

    monkeypatch.setattr(extraction_scenarios, "_coding_client", lambda: FakeClient())

    result = extraction_scenarios.list_scenarios()

    assert result["total"] == 1
    assert result["cases"][0]["case_id"] == "case-1"
    assert "markdown_body" not in result["cases"][0]


def test_production_run_refresh_scores_worker_audit_output(monkeypatch):
    run_id = "run-1"
    case = {
        "case_id": "case-1",
        "expected_strings": ["weight loss", "abdominal pain"],
    }
    job = {
        "status": "running",
        "triggered_at": "2026-05-19T00:00:00+00:00",
        "cases": [case],
        "child_runs": {"case-1": "run-1:case-1"},
    }
    captured = {}

    def fake_read_validation_audit_rows(child_run_ids):
        assert child_run_ids == ["run-1:case-1"]
        return [
            {
                "run_id": "run-1:case-1",
                "status": "completed",
                "validation_output": {
                    "terms": [
                        {"text": "weight loss"},
                        {"text": "abdominal pain"},
                    ]
                },
                "extraction_provider": "aws",
                "extraction_model_tier": "small",
                "extraction_prompt_hash": "hash-1",
            }
        ]

    def fake_finalise(run_id_arg, per_case, total, cases, triggered_at):
        captured["run_id"] = run_id_arg
        captured["per_case"] = per_case
        captured["total"] = total
        captured["cases"] = cases
        captured["triggered_at"] = triggered_at

    monkeypatch.setattr(
        extraction_scenarios,
        "_read_validation_audit_rows",
        fake_read_validation_audit_rows,
    )
    monkeypatch.setattr(extraction_scenarios, "_finalise_run", fake_finalise)

    extraction_scenarios._refresh_production_run(run_id, job)

    assert captured["run_id"] == run_id
    assert captured["total"] == 1
    assert captured["per_case"][0]["f1"] == 1.0
    assert captured["per_case"][0]["model_provider"] == "aws"
    assert captured["per_case"][0]["model_tier"] == "small"


def test_validation_output_normalises_value_unit_terms_before_scoring():
    case = {
        "case_id": "case-1",
        "expected_strings": ["Alb", "CRP", "weight loss"],
        "expected_observables": [
            {"test_name": "Albumin", "display_name": "Alb"},
            {"test_name": "C reactive protein", "display_name": "CRP"},
        ],
    }
    row = {
        "validation_output": {
            "terms": [
                {"text": "Albumin 43.9 g/L"},
                {"text": "C reactive protein 7 mg/L"},
                {"text": "weight loss"},
                {"text": "Referral criteria and clinical information"},
                {"text": "11.2 g/L"},
            ]
        }
    }

    terms = extraction_scenarios._terms_from_validation_output(row, case)
    score = extraction_scenarios._score_case_from_terms(case, terms)

    assert terms == ["Alb", "CRP", "weight loss"]
    assert score["f1"] == 1.0
    assert score["false_positive"] == 0


def test_worker_audit_captures_validation_terms_only_when_requested():
    engine = WORKFLOW_ENGINE.read_text(encoding="utf-8")

    assert 'pipeline_state.get("capture_validation_output")' in engine
    assert 'audit["validation_output"]' in engine
    assert '"terms": [' in engine
    assert '"case_id": pipeline_state.get("case_id", "")' in engine


def test_extraction_source_node_allowlist_supports_chunk_and_scenario():
    extraction = (ROOT / "libs/pipeline_graph/subgraphs/extraction.py").read_text(
        encoding="utf-8"
    )

    assert '"Chunk": {' in extraction
    assert '"DocumentReference": {' in extraction
    assert '"ExtractionScenario": {' in extraction
    assert '"graph": "knowledge"' in extraction
    assert (
        '"text_properties": ("markdown_body", "source_template_markdown")' in extraction
    )
    assert '"text_properties": ("text",)' in extraction
