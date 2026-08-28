"""Prod Bicep must match the live leo-ai-prod / mizaic-cds-oai deploy.

Snapshot taken 2026-08-25 from:
  - Container Apps in leo-ai-prod
  - Cognitive Services deployments on mizaic-cds-oai in leo-prod-rg
"""

from __future__ import annotations

from pathlib import Path

INFRA_DIR = Path(__file__).parent.parent / "infra" / "bicep"
PROD_PARAMS = INFRA_DIR / "parameters" / "prod.bicepparam"
CONTAINER_APPS = INFRA_DIR / "modules" / "container-apps.bicep"
OPENAI_MODULE = INFRA_DIR / "modules" / "openai.bicep"
MAIN_BICEP = INFRA_DIR / "main.bicep"


def _param(source: str, name: str) -> str:
    prefix = f"param {name} ="
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped.split("=", 1)[1].strip().strip("'")
    raise AssertionError(f"param {name} missing")


def test_prod_params_match_live_container_apps() -> None:
    source = PROD_PARAMS.read_text()
    assert _param(source, "azureOpenAiBigModel") == "gpt-5.2-chat"
    assert _param(source, "azureOpenAiSmallModel") == "gpt-5.4-mini"
    assert _param(source, "azureOpenAiApiVersion") == "2024-12-01-preview"
    assert _param(source, "pipelineModelProvider") == "aws"
    assert _param(source, "azureOpenAiWorkerBigModel") == "gpt-5.4"
    assert _param(source, "azureOpenAiWorkerSmallModel") == "gpt-5.4-mini"
    assert _param(source, "azureUseReasoningSmall") == "true"
    assert _param(source, "azureUseReasoningBig") == "false"
    assert _param(source, "azureReasoningEffortSmall") == "low"


def test_container_apps_wires_provider_and_worker_overrides() -> None:
    source = CONTAINER_APPS.read_text()
    assert "param pipelineModelProvider string" in source
    assert "param azureOpenAiWorkerBigModel string" in source
    assert "param azureOpenAiWorkerSmallModel string" in source
    assert "PIPELINE_MODEL_PROVIDER', value: pipelineModelProvider" in source
    assert "name: 'pipeline-worker'" in source
    assert "AZURE_OPENAI_WORKER" not in source
    assert "azureOpenAiWorkerBigModel" in source
    assert "azureOpenAiWorkerSmallModel" in source


def test_main_bicep_forwards_prod_openai_params() -> None:
    source = MAIN_BICEP.read_text()
    assert "param pipelineModelProvider string" in source
    assert "param azureOpenAiWorkerBigModel string" in source
    assert "param azureOpenAiWorkerSmallModel string" in source
    assert "pipelineModelProvider: pipelineModelProvider" in source
    assert "azureOpenAiWorkerBigModel: azureOpenAiWorkerBigModel" in source
    assert "azureOpenAiWorkerSmallModel: azureOpenAiWorkerSmallModel" in source


def test_openai_module_declares_live_account_deployments() -> None:
    source = OPENAI_MODULE.read_text()
    for name in ("gpt-5.4", "gpt-5-mini", "gpt-5.4-mini", "gpt-5.4-nano"):
        assert f"name: '{name}'" in source
    assert "2026-03-05" in source
    assert "2025-08-07" in source
    assert "2026-03-17" in source
