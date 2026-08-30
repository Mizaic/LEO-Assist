"""Dry-run applies the same read-only enrichment as a writeback run.

Atlas: Class A tooling. Search 'in-process referral dry-run enrichment'.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from libs.pipeline_graph.subgraphs.compliance import evaluate_compliance
from libs.pipeline_graph.subgraphs.quality_check import run_quality_checks
from libs.clinical_scoping.healthcare_service import apply_healthcare_service_scope
from libs.referral_quality.dry_run_enrichment import enrich_dry_run_state
from libs.referral_quality.inprocess_dry_run import (
    build_dry_run_state,
    is_write_cypher,
    run_dry_pipeline,
)
from libs.workflow.step_state_loader import enrich_patient_demographics


def _thin_state() -> dict:
    return build_dry_run_state(
        referral_id="000481914514",
        patient_id="p-1",
        encounter_id="000481914514:referral-assessment",
        document_reference_id="doc-1",
        chunk_ids=["c-1"],
        run_id="run-1",
    )


def _service_row() -> dict:
    return {
        "id": "117038",
        "name": "Breast 2WW",
        "specialty": "2WW",
        "guideline_ids_prop": "NG12",
        "guidance_ids": ["NG12"],
        "completeness_domain": "cancer",
        "completeness_subdomain": "breast",
        "spoa_id": None,
        "organization_id": "RK5",
        "organization_name": "Sherwood Forest Hospitals",
        "ers_service_id": "117038",
    }


def _client_with_scope() -> MagicMock:
    client = MagicMock()

    def _run(query: str, **_params: object) -> list[dict]:
        assert not is_write_cypher(query)
        if "birthDate" in query or "birth_date" in query:
            return [
                {
                    "birth_date": "1968-03-01",
                    "gender": "female",
                    "source": "",
                }
            ]
        if "HAS_GENERAL_PRACTITIONER" in query:
            return [{"org_id": "RK5"}]
        if "FOR_SERVICE" in query or "completeness_domain" in query:
            return [_service_row()]
        return []

    client.run.side_effect = _run
    return client


def test_dry_run_enrichment_sets_completeness_domain_from_service() -> None:
    state = _thin_state()
    enrich_dry_run_state(_client_with_scope(), state)
    assert state["completeness_domain"] == "cancer"
    assert state["completeness_subdomain"] == "breast"
    assert state["healthcare_service_id"] == "117038"
    assert state["primary_guideline_ids"] == ["NG12"]


def test_dry_run_enrichment_sets_patient_age_and_sex() -> None:
    state = _thin_state()
    enrich_dry_run_state(_client_with_scope(), state)
    expected_age = float(date.today().year - 1968)
    if (date.today().month, date.today().day) < (3, 1):
        expected_age -= 1
    assert state["patient_age"] == expected_age
    assert state["patient_sex"] == "female"


def test_quality_check_skips_completeness_on_thin_dry_run_state() -> None:
    with patch(
        "libs.pipeline_graph.subgraphs.quality_check._global_quality_report",
        return_value={"issues": []},
    ):
        out = run_quality_checks({**_thin_state(), "entities": [], "episodes": []})
    assert "completeness_result" not in out


def test_quality_check_produces_completeness_after_enrichment() -> None:
    state = _thin_state()
    enrich_dry_run_state(_client_with_scope(), state)
    schema = [{"id": "g1", "name": "History", "concept_ids": [123]}]
    with (
        patch(
            "libs.pipeline_graph.subgraphs.quality_check._load_completeness_schema",
            return_value=schema,
        ),
        patch(
            "libs.pipeline_graph.subgraphs.quality_check._load_isa_expansion",
            return_value={},
        ),
        patch(
            "libs.pipeline_graph.subgraphs.quality_check._global_quality_report",
            return_value={"issues": []},
        ),
    ):
        out = run_quality_checks(
            {
                **state,
                "entities": [
                    {"concept_id": "123", "assertion": "present", "text": "lump"}
                ],
                "episodes": [{"id": "e-1"}],
            }
        )
    result = out["completeness_result"]
    assert result["domain"] == "cancer"
    assert result["subdomain"] == "breast"
    assert result["configured"] is True


@patch("services.terminology_api.app.services.guideline_evaluator.GuidelineEvaluator")
def test_unenriched_compliance_falls_to_global(mock_cls: MagicMock) -> None:
    evaluator = MagicMock()
    mock_cls.return_value = evaluator
    captured: list[dict] = []

    def _evaluate(_codes: list, **kwargs: object) -> dict:
        captured.append(dict(kwargs))
        return {"matched_rules": []}

    evaluator.evaluate_patient.side_effect = _evaluate
    evaluate_compliance({**_thin_state(), "entities": []})
    assert captured
    assert captured[0].get("scope_type") == "global"
    assert captured[0].get("scope_id") is None


@patch("services.terminology_api.app.services.guideline_evaluator.GuidelineEvaluator")
def test_enriched_compliance_uses_receiving_service_ng12(mock_cls: MagicMock) -> None:
    state = _thin_state()
    enrich_dry_run_state(_client_with_scope(), state)
    evaluator = MagicMock()
    mock_cls.return_value = evaluator
    captured: list[dict] = []

    def _evaluate(_codes: list, **kwargs: object) -> dict:
        captured.append(dict(kwargs))
        return {"matched_rules": []}

    evaluator.evaluate_patient.side_effect = _evaluate
    evaluate_compliance({**state, "entities": []})
    assert captured
    first = captured[0]
    assert first.get("scope_type") == "guideline"
    assert first.get("scope_id") == "NG12"
    assert first.get("patient_age") == state["patient_age"]
    assert first.get("patient_sex") == "female"


def test_enrichment_reuses_production_helpers() -> None:
    state = _thin_state()
    client = _client_with_scope()
    with (
        patch(
            "libs.workflow.step_state_loader.enrich_patient_demographics",
            wraps=enrich_patient_demographics,
        ) as demo,
        patch(
            "libs.clinical_scoping.healthcare_service.apply_healthcare_service_scope",
            wraps=apply_healthcare_service_scope,
        ) as apply_scope,
    ):
        enrich_dry_run_state(client, state)
    assert demo.called
    assert apply_scope.called


@pytest.mark.asyncio
async def test_run_dry_pipeline_enriches_before_trace(tmp_path: Path) -> None:
    target = MagicMock()
    target.patient_id = "p-1"
    target.document_reference_id = "doc-1"

    async def _trace(_actions: object, state: dict) -> dict:
        return {"status": "completed", "final_state": state}

    engine = MagicMock()
    engine.trace_run = _trace
    with (
        patch(
            "libs.referral_quality.inprocess_dry_run.resolve_existing_chunks",
            return_value={"target": target, "chunk_ids": ["c-1"]},
        ),
        patch(
            "libs.referral_quality.inprocess_dry_run.read_run_context",
            return_value={},
        ),
        patch("libs.referral_quality.inprocess_dry_run.enrich_dry_run_state") as enrich,
        patch(
            "libs.referral_quality.inprocess_dry_run.load_plan_manifest",
            return_value=MagicMock(actions=[]),
        ),
        patch(
            "libs.referral_quality.inprocess_dry_run.WorkflowEngine",
            return_value=engine,
        ),
    ):
        await run_dry_pipeline(MagicMock(), "000481914514", report_dir=tmp_path)
    assert enrich.called
