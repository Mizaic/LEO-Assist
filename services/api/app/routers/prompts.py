"""Prompt Config CRUD router.

Atlas trace:
  DO: DO-83EBEE2C
  DI: DI-B954388C
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-83EBEE2C")

Manages PromptConfig nodes in Neo4j — the single source of truth for
all LLM system prompts, output schemas, and few-shot examples.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.neo4j_client import CodingGraphClient
from app.deps import require_admin
from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.cypher.prompt_config_queries import (
    CREATE_PROMPT,
    DELETE_PROMPT,
    GET_PROMPT,
    LIST_PROMPTS,
    UPDATE_PROMPT,
)
from libs.llm_usage import LLMCostConfig, LLMUsage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["prompts"])


class FewShotExample(BaseModel):
    id: str
    input: str
    output: str
    deidentified: bool = False
    category: str = ""  # e.g. "assertion:absent", "observable", "staging"
    model_scope: str = "any"  # "any" | "extraction" | "extraction:llm" | "verification"
    description: str = ""  # short human label shown in the example library
    core: bool = False


class PromptCreateRequest(BaseModel):
    name: str
    description: str = ""
    systemPrompt: str
    outputSchema: str = "{}"
    verification: bool = False
    fewShotExamples: list[FewShotExample] = []
    maxFewShot: int = 20


class PromptUpdateRequest(BaseModel):
    name: str
    description: str = ""
    systemPrompt: str
    outputSchema: str = "{}"
    verification: bool = False
    fewShotExamples: list[FewShotExample] = []
    maxFewShot: int = 20


class ImproveRequest(BaseModel):
    currentPrompt: str
    outputSchema: str = "{}"


class SimulateRequest(BaseModel):
    encounterText: str
    presetId: str | None = None  # preferred — derives provider/tier from preset
    provider: str = "azure"  # fallback if no presetId
    tier: str = "small"  # fallback if no presetId
    dryRun: bool = True  # False = actually call the LLM


# ── Cost table helpers ────────────────────────────────────────────────────────

_COST_ENV_PREFIXES: dict[str, dict[str, str]] = {
    "aws": {
        "small": "AWS_BEDROCK_MODEL_SMALL_MODEL",
        "big": "AWS_BEDROCK_MODEL_BIG_MODEL",
        "max": "AWS_BEDROCK_MODEL_MAX_MODEL",
    },
    "azure": {
        "small": "AZURE_OPENAI_SMALL_MODEL",
        "big": "AZURE_OPENAI_BIG_MODEL",
        "max": "AZURE_OPENAI_BIG_MODEL",  # max == big for Azure
    },
}

_MODEL_ID_ENVS: dict[str, dict[str, str]] = {
    "aws": {
        "small": "AWS_SMALL_MODEL",
        "big": "AWS_BIG_MODEL",
        "max": "AWS_MAX_MODEL",
    },
    "azure": {
        "small": "AZURE_OPENAI_SMALL_MODEL",
        "big": "AZURE_OPENAI_BIG_MODEL",
        "max": "AZURE_OPENAI_BIG_MODEL",
    },
}

_MODEL_ID_DEFAULTS: dict[str, dict[str, str]] = {
    "aws": {
        "small": "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        "big": "eu.anthropic.claude-sonnet-4-6",
        "max": "eu.anthropic.claude-opus-4-6-v1",
    },
    "azure": {
        "small": "gpt-5.4-nano",
        "big": "gpt-5.4",
        "max": "gpt-5.4",
    },
}

_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    "aws": {
        "small": "Claude Haiku (AWS Bedrock)",
        "big": "Claude Sonnet (AWS Bedrock)",
        "max": "Claude Opus (AWS Bedrock)",
    },
    "azure": {
        "small": "GPT-5.4 nano (Azure OpenAI)",
        "big": "GPT-5.4 (Azure OpenAI)",
        "max": "GPT-5.4 (Azure OpenAI)",
    },
}


import os as _os


def _model_cost_entry(provider: str, tier: str) -> dict[str, Any]:
    prefix = _COST_ENV_PREFIXES.get(provider, {}).get(tier, "")
    model_id_env = _MODEL_ID_ENVS.get(provider, {}).get(tier, "")
    model_id = _os.getenv(
        model_id_env, _MODEL_ID_DEFAULTS.get(provider, {}).get(tier, "")
    )
    return {
        "provider": provider,
        "tier": tier,
        "key": f"{provider}:{tier}",
        "modelId": model_id,
        "displayName": _DISPLAY_NAMES.get(provider, {}).get(tier, f"{provider}:{tier}"),
        "costPer1mInput": float(_os.getenv(f"{prefix}_COST_PER_1M_INPUT_TOKEN", "0")),
        "costPer1mCachedInput": float(
            _os.getenv(f"{prefix}_COST_PER_1M_CACHED_INPUT_TOKEN", "0")
        ),
        "costPer1mOutput": float(_os.getenv(f"{prefix}_COST_PER_1M_OUTPUT_TOKEN", "0")),
    }


def _estimate_cost(
    cost_entry: dict[str, Any],
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    *,
    cache_write_tokens: int = 0,
    input_excludes_cache: bool = False,
) -> float:
    """Estimate USD cost using provider-aware token semantics.

    Bedrock: ``input_tokens`` is non-cached only (do not subtract cache).
    Azure: ``input_tokens`` includes cached; subtract before full-rate billing.
    """
    usage = LLMUsage(
        input_tokens=int(input_tokens or 0),
        output_tokens=int(output_tokens or 0),
        cached_input_tokens=int(cached_tokens or 0),
        cache_creation_input_tokens=int(cache_write_tokens or 0),
        input_excludes_cache=bool(input_excludes_cache),
    )
    cfg = LLMCostConfig(
        cost_per_1m_input=float(cost_entry.get("costPer1mInput") or 0),
        cost_per_1m_cached_input=float(cost_entry.get("costPer1mCachedInput") or 0),
        cost_per_1m_output=float(cost_entry.get("costPer1mOutput") or 0),
        cost_per_1m_cache_write=float(cost_entry.get("costPer1mCacheWrite") or 0),
    )
    return round(usage.cost_usd(cfg), 6)


def _count_few_shot(raw: str | None) -> int:
    if not raw:
        return 0
    try:
        return len(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        return 0


@router.get("/model-costs")
def get_model_costs(scope: CallerScope = Depends(get_caller_scope)):
    """Return cost rates — Neo4j first, env-var fallback per model."""
    try:
        from libs.cypher.model_config_queries import LIST_MODEL_CONFIGS

        client = CodingGraphClient()
        try:
            with client.session() as session:
                rows = session.run(LIST_MODEL_CONFIGS).data()
        finally:
            client.close()
        if rows:
            return {
                "modelCosts": [
                    {
                        "key": r.get("key"),
                        "provider": r.get("provider"),
                        "tier": r.get("tier"),
                        "modelId": r.get("modelId"),
                        "displayName": r.get("displayName"),
                        "costPer1mInput": float(r.get("costPer1mInput") or 0),
                        "costPer1mCachedInput": float(
                            r.get("costPer1mCachedInput") or 0
                        ),
                        "costPer1mCacheWrite": float(r.get("costPer1mCacheWrite") or 0),
                        "costPer1mOutput": float(r.get("costPer1mOutput") or 0),
                    }
                    for r in rows
                ]
            }
    except Exception as exc:
        logger.debug("Neo4j model-costs unavailable, falling back to env: %s", exc)

    entries = []
    for provider in ("aws", "azure"):
        for tier in ("small", "big", "max"):
            entries.append(_model_cost_entry(provider, tier))
    return {"modelCosts": entries}


@router.get("")
def list_prompts(scope: CallerScope = Depends(get_caller_scope)):
    client = CodingGraphClient()
    try:
        with client.session() as session:
            rows = [dict(r) for r in session.run(LIST_PROMPTS)]
        prompts = []
        for row in rows:
            prompts.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "description": row.get("description") or "",
                    "version": row.get("version", 1),
                    "verification": bool(row.get("verification")),
                    "fewShotCount": 1 if row.get("hasFewShot") else 0,
                    "updatedAt": str(
                        row.get("updatedAt") or row.get("createdAt") or ""
                    ),
                }
            )
        return {"prompts": prompts}
    finally:
        client.close()


@router.get("/{prompt_id}")
def get_prompt(prompt_id: str, scope: CallerScope = Depends(get_caller_scope)):
    client = CodingGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_PROMPT, id=prompt_id).single()
        if not row:
            raise HTTPException(404, f"PromptConfig {prompt_id} not found")
        few_shot_raw = row.get("fewShotExamples") or "[]"
        try:
            few_shot = (
                json.loads(few_shot_raw)
                if isinstance(few_shot_raw, str)
                else few_shot_raw
            )
        except (json.JSONDecodeError, TypeError):
            few_shot = []
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row.get("description") or "",
            "version": row.get("version", 1),
            "systemPrompt": row["systemPrompt"],
            "outputSchema": row.get("outputSchema") or "{}",
            "verification": bool(row.get("verification")),
            "fewShotExamples": few_shot,
            "maxFewShot": int(row.get("maxFewShot") or 20),
        }
    finally:
        client.close()


@router.post("")
def create_prompt(
    body: PromptCreateRequest, scope: CallerScope = Depends(require_admin)
):
    prompt_id = str(uuid.uuid4())
    few_shot_json = json.dumps([e.model_dump() for e in body.fewShotExamples])
    client = CodingGraphClient()
    try:
        with client.session() as session:
            session.run(
                CREATE_PROMPT,
                id=prompt_id,
                name=body.name,
                description=body.description,
                version=1,
                system_prompt=body.systemPrompt,
                output_schema=body.outputSchema,
                verification=body.verification,
                few_shot_examples=few_shot_json,
                max_few_shot=body.maxFewShot,
                source="user",
            )
        return {"id": prompt_id}
    finally:
        client.close()


@router.put("/{prompt_id}")
def update_prompt(
    prompt_id: str,
    body: PromptUpdateRequest,
    scope: CallerScope = Depends(require_admin),
):
    few_shot_json = json.dumps([e.model_dump() for e in body.fewShotExamples])
    client = CodingGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                UPDATE_PROMPT,
                id=prompt_id,
                name=body.name,
                description=body.description,
                system_prompt=body.systemPrompt,
                output_schema=body.outputSchema,
                verification=body.verification,
                few_shot_examples=few_shot_json,
                max_few_shot=body.maxFewShot,
            ).single()
        if not row:
            raise HTTPException(404, f"PromptConfig {prompt_id} not found")
        return {"id": prompt_id, "status": "updated"}
    finally:
        client.close()


@router.delete("/{prompt_id}")
def delete_prompt(prompt_id: str, scope: CallerScope = Depends(require_admin)):
    client = CodingGraphClient()
    try:
        with client.session() as session:
            row = session.run(DELETE_PROMPT, id=prompt_id).single()
        deleted = row["deleted"] if row else 0
        if deleted == 0:
            raise HTTPException(400, "Cannot delete seed prompts or prompt not found")
        return {"status": "deleted"}
    finally:
        client.close()


def _parse_model_key(model_key: str) -> tuple[str, str]:
    """Split 'aws:small' → ('aws', 'small'). Defaults to ('aws', 'small')."""
    parts = model_key.split(":", 1)
    return (parts[0].lower(), parts[1].lower()) if len(parts) == 2 else ("aws", "small")


def _build_cost_estimate(
    cost_entry: dict[str, Any],
    system_tokens: int,
    user_tokens: int,
    est_output_tokens: int = 200,
) -> dict[str, Any]:
    """Return withoutCache + withCache cost breakdowns for a single model."""
    # Without cache: first call — full input rate on all tokens
    no_cache_total = round(
        (system_tokens + user_tokens) * cost_entry["costPer1mInput"] / 1_000_000
        + est_output_tokens * cost_entry["costPer1mOutput"] / 1_000_000,
        6,
    )
    # With cache: system tokens billed at cached rate, user tokens at full input rate
    with_cache_total = round(
        system_tokens * cost_entry["costPer1mCachedInput"] / 1_000_000
        + user_tokens * cost_entry["costPer1mInput"] / 1_000_000
        + est_output_tokens * cost_entry["costPer1mOutput"] / 1_000_000,
        6,
    )
    saving_pct = (
        round((1 - with_cache_total / no_cache_total) * 100, 1)
        if no_cache_total > 0
        else 0.0
    )
    return {
        "model": cost_entry,
        "systemTokens": system_tokens,
        "userTokens": user_tokens,
        "estOutputTokens": est_output_tokens,
        "withoutCache": {
            "inputCost": round(
                (system_tokens + user_tokens)
                * cost_entry["costPer1mInput"]
                / 1_000_000,
                6,
            ),
            "outputCost": round(
                est_output_tokens * cost_entry["costPer1mOutput"] / 1_000_000, 6
            ),
            "totalCost": no_cache_total,
        },
        "withCache": {
            "cachedInputCost": round(
                system_tokens * cost_entry["costPer1mCachedInput"] / 1_000_000, 6
            ),
            "uncachedInputCost": round(
                user_tokens * cost_entry["costPer1mInput"] / 1_000_000, 6
            ),
            "outputCost": round(
                est_output_tokens * cost_entry["costPer1mOutput"] / 1_000_000, 6
            ),
            "totalCost": with_cache_total,
        },
        "cacheSavingPct": saving_pct,
    }


@router.post("/{prompt_id}/simulate")
def simulate_prompt(
    prompt_id: str,
    body: SimulateRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Assemble and optionally run a prompt against supplied encounter text.

    When a ``presetId`` is supplied, the preset's primary_model (and
    secondary_model when consensus_mode=True) drive provider/tier selection
    and the cost estimate table shows one row per model.  Without a preset
    the legacy ``provider``/``tier`` fields are used.

    Returns assembled system prompt, RAG-selected dynamic examples, user
    message, and per-model cost breakdowns with and without Bedrock caching.
    """
    # ── Load prompt config ────────────────────────────────────────────────
    client = CodingGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_PROMPT, id=prompt_id).single()
        if not row:
            raise HTTPException(404, f"PromptConfig {prompt_id} not found")
    finally:
        client.close()

    few_shot_raw = row.get("fewShotExamples") or "[]"
    try:
        few_shot_examples: list[dict] = (
            json.loads(few_shot_raw)
            if isinstance(few_shot_raw, str)
            else list(few_shot_raw)
        )
    except (json.JSONDecodeError, TypeError):
        few_shot_examples = []

    try:
        max_few_shot = int(row.get("maxFewShot") or 20)
    except (TypeError, ValueError):
        max_few_shot = 20

    system_prompt_text: str = row.get("systemPrompt") or ""
    output_schema_json: str | None = row.get("outputSchema") or None

    # ── Resolve models from preset or fallback ────────────────────────────
    preset_name: str = ""
    consensus_mode: bool = False
    primary_key = f"{body.provider or 'azure'}:{body.tier or 'small'}"
    secondary_key: str | None = None

    if body.presetId:
        try:
            from libs.cypher.preset_queries import GET_PRESET

            preset_client = CodingGraphClient()
            try:
                with preset_client.session() as ps:
                    preset_rows = ps.run(GET_PRESET, preset_id=body.presetId).data()
            finally:
                preset_client.close()
            if preset_rows:
                p = preset_rows[0]
                preset_name = p.get("name", "")
                consensus_mode = bool(p.get("consensus_mode", False))
                primary_key = p.get("primary_model") or primary_key
                if consensus_mode:
                    secondary_key = p.get("secondary_model") or None
        except Exception as exc:
            logger.warning("Could not load preset %s: %s", body.presetId, exc)

    primary_provider, primary_tier = _parse_model_key(primary_key)

    # ── Assemble prompt for primary provider ──────────────────────────────
    from libs.pipeline_graph.subgraphs._extractor import (
        _filter_examples_for_provider,
        _split_core_dynamic,
        _build_relevant_examples_block,
        assemble_system_prompt,
    )
    from libs.prompts.few_shot_selector import FewShotSelector

    def _assemble(provider: str) -> tuple[str, str, list[dict], list[dict]]:
        applicable = _filter_examples_for_provider(few_shot_examples, provider)
        core_set, dynamic_pool = _split_core_dynamic(applicable)
        core_set = core_set[: min(len(core_set), max_few_shot)]
        budget = max(0, max_few_shot - len(core_set))
        selector = FewShotSelector(dynamic_pool=dynamic_pool)
        selector.warm()
        enc = body.encounterText.strip()
        selected_dyn: list[dict] = []
        selected_scores: list[float] = []
        if budget > 0 and enc:
            try:
                import numpy as np

                if selector._pool_embeddings is not None:
                    qv = selector._embedder.encode([enc])
                    if qv is not None:
                        scores_arr = selector._pool_embeddings @ qv[0]
                        top_idx = np.argsort(-scores_arr)[
                            : min(budget, len(dynamic_pool))
                        ]
                        selected_dyn = [dynamic_pool[int(i)] for i in top_idx]
                        selected_scores = [float(scores_arr[int(i)]) for i in top_idx]
                    else:
                        selected_dyn = selector.select(enc, budget)
                else:
                    selected_dyn = selector.select(enc, budget)
            except Exception:
                selected_dyn = selector.select(enc, budget)
        sys_prompt = assemble_system_prompt(
            instructions=system_prompt_text,
            output_schema_json=output_schema_json,
            few_shot_examples=core_set,
            provider=provider,
        )
        dyn_block = _build_relevant_examples_block(selected_dyn)
        user_parts: list[str] = []
        if dyn_block:
            user_parts.append(dyn_block)
        user_parts.append(f"Encounter text:\n{enc}")
        user_msg = "\n\n".join(user_parts)
        # Annotate scores onto dynamic examples
        out_dyn = []
        for i, ex in enumerate(selected_dyn):
            entry = dict(ex)
            if selected_scores and i < len(selected_scores):
                entry["_similarity_score"] = round(selected_scores[i], 4)
            out_dyn.append(entry)
        return sys_prompt, user_msg, core_set, out_dyn

    assembled_system, user_message, core_set, selected_dynamic = _assemble(
        primary_provider
    )

    # ── Per-model cost estimates (with & without cache) ───────────────────
    sys_tokens = len(assembled_system) // 4
    user_tokens = len(user_message) // 4
    est_output = 200  # conservative estimate for extraction responses

    primary_cost = _model_cost_entry(primary_provider, primary_tier)
    cost_estimates: list[dict[str, Any]] = [
        {
            "role": "primary",
            **_build_cost_estimate(primary_cost, sys_tokens, user_tokens, est_output),
        }
    ]

    if secondary_key:
        sec_provider, sec_tier = _parse_model_key(secondary_key)
        sec_sys, sec_user, _, _ = _assemble(sec_provider)
        sec_sys_tok = len(sec_sys) // 4
        sec_user_tok = len(sec_user) // 4
        sec_cost = _model_cost_entry(sec_provider, sec_tier)
        cost_estimates.append(
            {
                "role": "secondary",
                **_build_cost_estimate(sec_cost, sec_sys_tok, sec_user_tok, est_output),
            }
        )

    result: dict[str, Any] = {
        "presetName": preset_name,
        "consensusMode": consensus_mode,
        "systemPrompt": assembled_system,
        "coreExamples": core_set,
        "selectedDynamicExamples": selected_dynamic,
        "userMessage": user_message,
        "tokenEstimate": {
            "approxSystemTokens": sys_tokens,
            "approxUserTokens": user_tokens,
            "estOutputTokens": est_output,
        },
        "costEstimates": cost_estimates,
        "llmResponse": None,
        "llmTokenUsage": None,
        "llmActualCostUsd": None,
    }

    if not body.dryRun and body.encounterText.strip():
        try:
            from libs.llm_client.factory import create_llm

            llm = create_llm(provider=primary_provider, tier=primary_tier)
            resp = llm.converse(
                system=assembled_system,
                messages=[{"role": "user", "content": user_message}],
                max_tokens=2048,
                temperature=0.0,
                agent_task="prompt_simulator",
            )
            result["llmResponse"] = resp.text
            result["llmTokenUsage"] = {
                "inputTokens": resp.input_tokens,
                "outputTokens": resp.output_tokens,
                "cachedInputTokens": resp.cached_input_tokens,
                "cacheCreationInputTokens": getattr(
                    resp, "cache_creation_input_tokens", 0
                )
                or 0,
            }
            result["llmActualCostUsd"] = _estimate_cost(
                primary_cost,
                resp.input_tokens,
                resp.output_tokens,
                resp.cached_input_tokens,
                cache_write_tokens=int(
                    getattr(resp, "cache_creation_input_tokens", 0) or 0
                ),
                input_excludes_cache=primary_provider in ("aws", "bedrock"),
            )
        except Exception as exc:
            logger.warning("Prompt simulation LLM call failed: %s", exc)
            result["llmResponse"] = f"[LLM call failed: {exc}]"

    return result


@router.post("/improve")
async def improve_prompt(
    body: ImproveRequest,
    scope: CallerScope = Depends(require_admin),
):
    """Use the MAX model to suggest improvements to a system prompt."""
    try:
        from libs.llm_client.factory import create_llm

        llm = create_llm(tier="max")
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are an expert prompt engineer for clinical NLP systems. "
                    "The user will give you a system prompt and an output schema. "
                    "Improve the prompt for clarity, precision, and safety. "
                    "Return ONLY the improved prompt text, no explanation."
                ),
            },
            {
                "role": "user",
                "content": f"System prompt:\n{body.currentPrompt}\n\nOutput schema:\n{body.outputSchema}",
            },
        ]
        result = await llm.chat(messages=messages, max_tokens=4096)
        return {"improvedPrompt": result.content}
    except Exception as exc:
        logger.warning("Prompt improvement failed: %s", exc)
        raise HTTPException(500, f"AI improvement failed: {exc}")
