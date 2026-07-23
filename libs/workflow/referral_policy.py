"""Versioned referral clinical policy schema (M2.2).

Atlas trace:
  DO: DO-E89DE9EE
  DI: DI-090D4939, DI-29BF950F, DI-33376FBB, DI-8788B246, DI-9EE8D65E, DI-AB1C442D, DI-CB01B8A6
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-E89DE9EE")

Embedded in PlanDefinition snapshots as ``_referralPolicy``. Invalid or
out-of-bound values fail plan publication; production never falls back to
hidden Python defaults for referral assessment runs.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

SCHEMA_VERSION = "1.0"

_REQUIRED_PROMPT_KEYS = ("situation", "background", "recommendation", "recall")
_REQUIRED_LLM_STAGES = ("situation", "background", "recommendation")

DEFAULT_REFERRAL_POLICY: dict[str, Any] = {
    "schemaVersion": SCHEMA_VERSION,
    "extraction": {
        "windowSize": 10,
        "windowOverlap": 1,
    },
    "salvage": {
        "maxSentences": 50,
        "includeQualifiers": True,
    },
    "evidence": {
        "maxCodesPerChunk": 200,
        "maxEvidenceChars": 8000,
    },
    "alerts": {
        "twowDetectorVersion": "1.0",
    },
    "recall": {
        "maxChunkFetches": 5,
        "maxLlmCalls": 2,
        "maxTokens": 50000,
    },
    "llm": {
        "situation": {"temperature": 0.0, "maxTokens": 512},
        "background": {"temperature": 0.0, "maxTokens": 1024},
        "recommendation": {"temperature": 0.0, "maxTokens": 1024},
        "runTokenBudget": 200000,
    },
    "prompts": {
        "situation": {"name": "sbar_situation", "version": 2},
        "background": {"name": "sbar_background", "version": 2},
        "recommendation": {"name": "sbar_recommendation", "version": 2},
        "recall": {"name": "sbar_recall", "version": 1},
    },
    "models": {
        "provider": "aws",
        "tier": "big",
    },
    "failureBehaviour": "fail_closed",
}


def referral_policy_requires_validation(plan_resource: dict[str, Any]) -> bool:
    plan_id = str(plan_resource.get("id") or "")
    workflow_mode = str(
        plan_resource.get("_workflowMode") or plan_resource.get("workflowMode") or ""
    )
    if plan_resource.get("_referralPolicy") is not None:
        return True
    return workflow_mode == "durable_pubsub" and plan_id == "pd-referral-assessment"


def parse_referral_policy(plan_resource: dict[str, Any]) -> dict[str, Any]:
    """Merge plan snapshot policy with factory defaults."""
    raw = plan_resource.get("_referralPolicy")
    if not isinstance(raw, dict):
        return deepcopy(DEFAULT_REFERRAL_POLICY)
    return _deep_merge(deepcopy(DEFAULT_REFERRAL_POLICY), raw)


def validate_referral_policy(policy: dict[str, Any]) -> list[str]:
    """Return validation errors; empty list means publish may proceed."""
    errors: list[str] = []
    if not isinstance(policy, dict):
        return ["referral policy must be an object"]

    schema = str(policy.get("schemaVersion") or "")
    if schema != SCHEMA_VERSION:
        errors.append(f"referral policy schemaVersion must be {SCHEMA_VERSION!r}")

    extraction = policy.get("extraction") or {}
    window_size = _int_field(extraction, "windowSize")
    window_overlap = _int_field(extraction, "windowOverlap")
    if window_size is None or window_size < 1 or window_size > 50:
        errors.append("extraction.windowSize must be between 1 and 50")
    if window_overlap is None or window_overlap < 0:
        errors.append("extraction.windowOverlap must be >= 0")
    if (
        window_size is not None
        and window_overlap is not None
        and window_overlap >= window_size
    ):
        errors.append("extraction.windowOverlap must be less than windowSize")

    salvage = policy.get("salvage") or {}
    max_sentences = _int_field(salvage, "maxSentences")
    if max_sentences is None or max_sentences < 0 or max_sentences > 500:
        errors.append("salvage.maxSentences must be between 0 and 500")

    evidence = policy.get("evidence") or {}
    max_codes = _int_field(evidence, "maxCodesPerChunk")
    max_chars = _int_field(evidence, "maxEvidenceChars")
    if max_codes is None or max_codes < 1 or max_codes > 2000:
        errors.append("evidence.maxCodesPerChunk must be between 1 and 2000")
    if max_chars is None or max_chars < 500 or max_chars > 50000:
        errors.append("evidence.maxEvidenceChars must be between 500 and 50000")

    recall = policy.get("recall") or {}
    for field, upper in (
        ("maxChunkFetches", 20),
        ("maxLlmCalls", 10),
        ("maxTokens", 1_000_000),
    ):
        value = _int_field(recall, field)
        if value is None or value < 0 or value > upper:
            errors.append(f"recall.{field} must be between 0 and {upper}")

    llm = policy.get("llm") or {}
    run_budget = _int_field(llm, "runTokenBudget")
    if run_budget is None or run_budget < 1000 or run_budget > 2_000_000:
        errors.append("llm.runTokenBudget must be between 1000 and 2000000")
    for stage in _REQUIRED_LLM_STAGES:
        stage_cfg = llm.get(stage)
        if not isinstance(stage_cfg, dict):
            errors.append(f"llm.{stage} must be an object")
            continue
        temp = stage_cfg.get("temperature")
        if not isinstance(temp, (int, float)) or temp < 0 or temp > 1:
            errors.append(f"llm.{stage}.temperature must be between 0 and 1")
        max_tokens = _int_field(stage_cfg, "maxTokens")
        if max_tokens is None or max_tokens < 64 or max_tokens > 8192:
            errors.append(f"llm.{stage}.maxTokens must be between 64 and 8192")

    prompts = policy.get("prompts") or {}
    if not isinstance(prompts, dict):
        errors.append("prompts must be an object")
    else:
        for key in _REQUIRED_PROMPT_KEYS:
            pin = prompts.get(key)
            if not isinstance(pin, dict):
                errors.append(f"prompts.{key} must be an object")
                continue
            name = str(pin.get("name") or "").strip()
            version = _int_field(pin, "version")
            if not name:
                errors.append(f"prompts.{key}.name is required")
            if version is None or version < 1 or version > 99:
                errors.append(f"prompts.{key}.version must be between 1 and 99")

    models = policy.get("models") or {}
    provider = str(models.get("provider") or "").strip().lower()
    tier = str(models.get("tier") or "").strip().lower()
    if provider not in {"aws", "azure"}:
        errors.append("models.provider must be aws or azure")
    if tier not in {"small", "big", "max"}:
        errors.append("models.tier must be small, big, or max")

    behaviour = str(policy.get("failureBehaviour") or "").strip()
    if behaviour not in {"fail_closed", "continue_with_flags"}:
        errors.append("failureBehaviour must be fail_closed or continue_with_flags")

    return errors


def _int_field(raw: dict[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
