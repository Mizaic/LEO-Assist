"""Bootstrap ModelConfig nodes into the Knowledge Graph on first run.

Neo4j is the source of truth.  Env vars / hardcoded defaults are used
**only** when no ModelConfig nodes exist yet (fresh instance or DR restore).
If any nodes are found in the graph at startup the seed is skipped entirely.

Called from ``services/api/app/main.py`` lifespan.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static metadata (model IDs and display names)
# ---------------------------------------------------------------------------

_MODEL_ID_ENVS: dict[str, dict[str, str]] = {
    "aws": {
        "small": "AWS_SMALL_MODEL",
        "big": "AWS_BIG_MODEL",
        "max": "AWS_MAX_MODEL",
    },
    "azure": {
        "small": "AZURE_OPENAI_SMALL_MODEL",
        "big": "AZURE_OPENAI_BIG_MODEL",
    },
}

_MODEL_ID_DEFAULTS: dict[str, dict[str, str]] = {
    "aws": {
        "small": "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        "big": "eu.anthropic.claude-sonnet-4-6",
        "max": "eu.anthropic.claude-opus-4-6-v1",
    },
    "azure": {
        "small": "gpt-5-mini",
        "big": "gpt-5.2-chat",
    },
}

_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    "aws": {
        "small": "Claude Haiku (AWS Bedrock)",
        "big": "Claude Sonnet (AWS Bedrock)",
        "max": "Claude Opus (AWS Bedrock)",
    },
    "azure": {
        "small": "GPT-5 mini (Azure OpenAI)",
        "big": "GPT-5 (Azure OpenAI)",
    },
}

_COST_ENV_PREFIXES: dict[str, dict[str, str]] = {
    "aws": {
        "small": "AWS_BEDROCK_MODEL_SMALL_MODEL",
        "big": "AWS_BEDROCK_MODEL_BIG_MODEL",
        "max": "AWS_BEDROCK_MODEL_MAX_MODEL",
    },
    "azure": {
        "small": "AZURE_OPENAI_SMALL_MODEL",
        "big": "AZURE_OPENAI_BIG_MODEL",
    },
}


# ---------------------------------------------------------------------------
# Baseline cost defaults (EU cross-region inference profile rates, per 1M tokens).
# EU prefix adds ~10% over US on-demand rates.
# Sources: cloudprice.net / AWS Bedrock pricing page — verified 2026-03-08.
# Override any of these at runtime via the corresponding env vars.
# ---------------------------------------------------------------------------

_COST_DEFAULTS: dict[str, dict[str, dict[str, float]]] = {
    "aws": {
        # eu.anthropic.claude-haiku-4-5-20251001-v1:0
        "small": {"input": 1.10, "cached": 0.110, "output": 5.50},
        # eu.anthropic.claude-sonnet-4-6
        "big": {"input": 3.30, "cached": 0.330, "output": 16.50},
        # eu.anthropic.claude-opus-4-6-v1
        "max": {"input": 5.50, "cached": 0.550, "output": 27.50},
    },
    "azure": {
        # azure/eu/gpt-5-mini-2025-08-07
        "small": {"input": 0.275, "cached": 0.028, "output": 2.20},
        # azure/eu/gpt-5-2025-08-07
        "big": {"input": 1.375, "cached": 0.138, "output": 11.00},
    },
}


def _model_seed_row(provider: str, tier: str) -> dict:
    prefix = _COST_ENV_PREFIXES[provider][tier]
    model_id_env = _MODEL_ID_ENVS[provider][tier]
    defaults = _COST_DEFAULTS[provider][tier]
    return {
        "key": f"{provider}:{tier}",
        "provider": provider,
        "tier": tier,
        "display_name": _DISPLAY_NAMES[provider][tier],
        "model_id": os.getenv(model_id_env, _MODEL_ID_DEFAULTS[provider][tier]),
        "cost_per_1m_input": float(
            os.getenv(f"{prefix}_COST_PER_1M_INPUT_TOKEN", str(defaults["input"]))
        ),
        "cost_per_1m_cached": float(
            os.getenv(
                f"{prefix}_COST_PER_1M_CACHED_INPUT_TOKEN", str(defaults["cached"])
            )
        ),
        "cost_per_1m_output": float(
            os.getenv(f"{prefix}_COST_PER_1M_OUTPUT_TOKEN", str(defaults["output"]))
        ),
        "is_active": True,
    }


def seed_model_configs(client) -> None:
    """Bootstrap ModelConfig nodes if and only if none exist in Neo4j.

    On a running instance the graph is always the source of truth — this
    function exits immediately if any ModelConfig nodes are present.
    The env-var defaults are only applied on a fresh instance or after a
    full DR restore where the graph has been wiped.
    """
    from libs.cypher.model_config_queries import (
        COUNT_MODEL_CONFIGS,
        CREATE_CONSTRAINT_MODEL_CONFIG,
        UPSERT_MODEL_CONFIG,
    )

    try:
        with client.session() as session:
            session.run(CREATE_CONSTRAINT_MODEL_CONFIG)
            total = session.run(COUNT_MODEL_CONFIGS).single()["total"]

        if total > 0:
            logger.info(
                "ModelConfig: %d node(s) already in Neo4j — skipping seed", total
            )
            return

        logger.info("ModelConfig: no nodes found — bootstrapping from defaults")
        seeded = 0
        for provider in ("aws", "azure"):
            for tier in _MODEL_ID_ENVS[provider]:
                row = _model_seed_row(provider, tier)
                with client.session() as session:
                    session.run(UPSERT_MODEL_CONFIG, **row)
                logger.info(
                    "ModelConfig %s created (input=$%.2f/1M out=$%.2f/1M cached=$%.3f/1M)",
                    row["key"],
                    row["cost_per_1m_input"],
                    row["cost_per_1m_output"],
                    row["cost_per_1m_cached"],
                )
                seeded += 1
        logger.info("ModelConfig bootstrap done: %d models written", seeded)
    except Exception as exc:
        logger.warning("ModelConfig seed failed (non-fatal): %s", exc)
