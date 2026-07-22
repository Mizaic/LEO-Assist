"""Bootstrap ModelConfig nodes into the Knowledge Graph on first run.

Atlas trace:
  DO: DO-92F92EFB
  DI: DI-88C1715A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-92F92EFB")

Neo4j is the source of truth. Env vars / hardcoded defaults bootstrap
missing keys and refresh ``source='seed'`` rows on every API start.
User-edited ModelConfig nodes (``source='user'``) are never overwritten.

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
# Baseline cost defaults (USD per 1M tokens). Verified 2026-07-22.
#
# AWS EU cross-region inference profiles = Anthropic base * 1.1:
#   Haiku 4.5: 1.10 / 0.110 / 1.375 write / 5.50
#   Sonnet 4.6: 3.30 / 0.330 / 4.125 write / 16.50
#   Opus 4.6: 5.50 / 0.550 / 6.875 write / 27.50
# Cache write = 5-minute TTL at 1.25x input (Bedrock / Anthropic default).
#
# Azure OpenAI Data Zone (EU) from azure.com pricing page:
#   GPT-5-mini: 0.28 / 0.03 / 2.20
#   GPT-5: 1.38 / 0.14 / 11.00
# Azure has no separate cache-write rate; write defaults to input rate.
# ---------------------------------------------------------------------------

_COST_DEFAULTS: dict[str, dict[str, dict[str, float]]] = {
    "aws": {
        "small": {
            "input": 1.10,
            "cached": 0.110,
            "cache_write": 1.375,
            "output": 5.50,
        },
        "big": {
            "input": 3.30,
            "cached": 0.330,
            "cache_write": 4.125,
            "output": 16.50,
        },
        "max": {
            "input": 5.50,
            "cached": 0.550,
            "cache_write": 6.875,
            "output": 27.50,
        },
    },
    "azure": {
        "small": {
            "input": 0.28,
            "cached": 0.03,
            "cache_write": 0.28,
            "output": 2.20,
        },
        "big": {
            "input": 1.38,
            "cached": 0.14,
            "cache_write": 1.38,
            "output": 11.00,
        },
    },
}


def _model_seed_row(provider: str, tier: str) -> dict:
    prefix = _COST_ENV_PREFIXES[provider][tier]
    model_id_env = _MODEL_ID_ENVS[provider][tier]
    defaults = _COST_DEFAULTS[provider][tier]
    input_rate = float(
        os.getenv(f"{prefix}_COST_PER_1M_INPUT_TOKEN", str(defaults["input"]))
    )
    write_default = defaults.get("cache_write", input_rate * 1.25)
    return {
        "key": f"{provider}:{tier}",
        "provider": provider,
        "tier": tier,
        "display_name": _DISPLAY_NAMES[provider][tier],
        "model_id": os.getenv(model_id_env, _MODEL_ID_DEFAULTS[provider][tier]),
        "cost_per_1m_input": input_rate,
        "cost_per_1m_cached": float(
            os.getenv(
                f"{prefix}_COST_PER_1M_CACHED_INPUT_TOKEN", str(defaults["cached"])
            )
        ),
        "cost_per_1m_cache_write": float(
            os.getenv(
                f"{prefix}_COST_PER_1M_CACHE_WRITE_TOKEN",
                str(write_default),
            )
        ),
        "cost_per_1m_output": float(
            os.getenv(f"{prefix}_COST_PER_1M_OUTPUT_TOKEN", str(defaults["output"]))
        ),
        "is_active": True,
    }


def seed_model_configs(client) -> None:
    """Upsert seeded ModelConfig rows; leave user-edited rows untouched.

    UPSERT_MODEL_CONFIG only overwrites cost/display fields when
    ``source='seed'``. Missing keys are created. User overrides keep
    ``source='user'`` and are skipped on MATCH.
    """
    from libs.cypher.model_config_queries import (
        CREATE_CONSTRAINT_MODEL_CONFIG,
        UPSERT_MODEL_CONFIG,
    )

    try:
        with client.session() as session:
            session.run(CREATE_CONSTRAINT_MODEL_CONFIG)

        upserted = 0
        for provider in ("aws", "azure"):
            for tier in _MODEL_ID_ENVS[provider]:
                row = _model_seed_row(provider, tier)
                with client.session() as session:
                    result = session.run(UPSERT_MODEL_CONFIG, **row).single()
                source = (result or {}).get("source", "seed")
                logger.info(
                    "ModelConfig %s upserted source=%s "
                    "(input=$%.2f cached=$%.3f write=$%.3f out=$%.2f /1M)",
                    row["key"],
                    source,
                    row["cost_per_1m_input"],
                    row["cost_per_1m_cached"],
                    row["cost_per_1m_cache_write"],
                    row["cost_per_1m_output"],
                )
                upserted += 1
        logger.info("ModelConfig seed refresh done: %d models upserted", upserted)
    except Exception as exc:
        logger.warning("ModelConfig seed failed (non-fatal): %s", exc)
