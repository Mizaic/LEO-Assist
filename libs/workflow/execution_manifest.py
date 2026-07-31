"""Pinned execution manifest snapshot for PipelineRun admission (M2.5).

Atlas trace:
  DO: DO-04CEDFB1
  DI: DI-090D4939, DI-29BF950F, DI-33376FBB, DI-8788B246, DI-9EE8D65E, DI-AB1C442D, DI-CB01B8A6
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-04CEDFB1")

Captures clinical policy, prompt pins, model config and LLM parameters so a
run can answer what exact settings were used without reading live graph state.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from libs.workflow.plan_manifest import PlanManifest
from libs.workflow.referral_policy import DEFAULT_REFERRAL_POLICY

MANIFEST_SCHEMA_VERSION = "1.0"


def build_execution_manifest(
    manifest: PlanManifest,
    *,
    prompt_hashes: dict[str, str],
    model_config: dict[str, Any],
) -> dict[str, Any]:
    """Build the immutable manifest persisted on PipelineRun at admission."""
    policy = manifest.referral_policy or dict(DEFAULT_REFERRAL_POLICY)
    prompts = policy.get("prompts") or {}
    pinned_prompts: dict[str, Any] = {}
    for stage in ("situation", "background", "recommendation", "recall"):
        pin = dict(prompts.get(stage) or {})
        pin["content_hash"] = str(prompt_hashes.get(stage) or "")
        pinned_prompts[stage] = pin
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "plan_id": manifest.plan_id,
        "plan_version_id": manifest.version_node_id,
        "policy_version": manifest.policy_version,
        "workflow_mode": manifest.workflow_mode,
        "referral_policy": policy,
        "prompts": pinned_prompts,
        "model": dict(model_config),
        "llm": dict(policy.get("llm") or {}),
        "extraction": dict(policy.get("extraction") or {}),
        "salvage": dict(policy.get("salvage") or {}),
        "evidence": dict(policy.get("evidence") or {}),
        "alerts": dict(policy.get("alerts") or {}),
        "recall": dict(policy.get("recall") or {}),
        "failure_behaviour": str(policy.get("failureBehaviour") or "fail_closed"),
        "snapshotted_at": datetime.now(timezone.utc).isoformat(),
    }


def manifest_from_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def prompt_content_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def resolve_prompt_hashes(policy: dict[str, Any]) -> dict[str, str]:
    """Resolve prompt content hashes from Neo4j PromptConfig nodes."""
    from libs.prompts.registry import get_prompt

    prompts = policy.get("prompts") or {}
    out: dict[str, str] = {}
    for stage in ("situation", "background", "recommendation", "recall"):
        pin = prompts.get(stage) or {}
        name = str(pin.get("name") or "")
        version = int(pin.get("version") or 1)
        if not name:
            out[stage] = ""
            continue
        try:
            text = get_prompt(name, version=version)
        except RuntimeError:
            out[stage] = ""
            continue
        out[stage] = prompt_content_hash(text)
    return out


def resolve_model_config(policy: dict[str, Any]) -> dict[str, Any]:
    """Resolve immutable ModelConfig fields from the pinned provider/tier."""
    models = policy.get("models") or {}
    provider = str(models.get("provider") or "azure").strip().lower()
    tier = str(models.get("tier") or "big").strip().lower()
    key = f"{provider}:{tier}"
    row: dict[str, Any] = {
        "key": key,
        "provider": provider,
        "tier": tier,
        "modelId": "",
        "displayName": "",
    }
    try:
        from libs.cypher.model_config_queries import GET_MODEL_CONFIG
        from libs.neo4j_client.client import KnowledgeGraphClient

        client = KnowledgeGraphClient()
        try:
            with client.session() as session:
                mc = session.run(GET_MODEL_CONFIG, key=key).single()
            if mc:
                row["modelId"] = str(mc.get("modelId") or "")
                row["displayName"] = str(mc.get("displayName") or "")
        finally:
            client.close()
    except Exception:
        pass
    if not row["modelId"]:
        from libs.llm_client.factory import create_llm

        try:
            llm = create_llm(provider=provider, tier=tier)
            row["modelId"] = str(getattr(llm, "model_id", "") or "")
        except Exception:
            row["modelId"] = ""
    return row


def build_manifest_for_plan(manifest: PlanManifest) -> dict[str, Any]:
    """Build a full execution manifest, resolving live prompt/model pins."""
    policy = manifest.referral_policy or dict(DEFAULT_REFERRAL_POLICY)
    return build_execution_manifest(
        manifest,
        prompt_hashes=resolve_prompt_hashes(policy),
        model_config=resolve_model_config(policy),
    )
