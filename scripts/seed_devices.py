"""Seed AI model Device nodes into the Knowledge Graph.

Each Device node represents a configurable AI model (LLM, NER, ML) in a
FHIR-aligned schema.  Sensitive credentials (model IDs, API keys) stay in
env vars / Azure Key Vault — Neo4j stores only the catalog metadata,
enabled/disabled status, and pipeline routing config.

Run:
    python scripts/seed_devices.py

Only seeds when no Device nodes exist; skips if any are already present
to avoid overwriting user-modified device config.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path("secrets/.env.config"), override=True)
load_dotenv(Path("secrets/.env"), override=False)

try:
    from libs.keyvault.loader import load_keyvault_secrets

    load_keyvault_secrets()
except Exception as e:
    print(f"[warn] Key Vault load skipped: {e}")

from libs.cypher.device_queries import (
    CREATE_DEVICE_INDEXES,
    UPSERT_DEVICE,
    UPSERT_PIPELINE_CONFIG,
)
from libs.neo4j_client.client import KnowledgeGraphClient


def _fhir_device(
    device_id: str,
    name: str,
    provider: str,
    device_type: str,
    role: str,
    env_var: str,
    default_model_id: str,
    endpoint_env_var: str = "",
    notes: str = "",
) -> str:
    """Build a minimal FHIR Device JSON string for the raw_json field."""
    resource = {
        "resourceType": "Device",
        "id": device_id,
        "status": "active",
        "manufacturer": provider,
        "deviceName": [{"name": name, "type": "user-friendly-name"}],
        "type": {
            "coding": [
                {
                    "system": "https://leo-ai.health/device-type",
                    "code": device_type,
                    "display": device_type.upper(),
                }
            ]
        },
        "property": [
            {
                "type": {"coding": [{"code": "role"}]},
                "valueCode": role,
            },
            {
                "type": {"coding": [{"code": "env-var"}]},
                "valueCode": env_var,
            },
            {
                "type": {"coding": [{"code": "default-model-id"}]},
                "valueCode": default_model_id,
            },
        ],
    }
    if endpoint_env_var:
        resource["property"].append(
            {
                "type": {"coding": [{"code": "endpoint-env-var"}]},
                "valueCode": endpoint_env_var,
            }
        )
    return json.dumps(resource, indent=2)


DEVICES: list[dict] = [
    # ----------------------------------------------------------------
    # AWS Bedrock — Claude models
    # ----------------------------------------------------------------
    {
        "device_id": "device-aws-small",
        "name": "Claude Haiku (small)",
        "provider": "AWS Bedrock",
        "device_type": "llm",
        "role": "small",
        "status": "active",
        "env_var": "AWS_SMALL_MODEL",
        "default_model_id": "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        "endpoint_env_var": "",
        "notes": "Fast, cost-effective model for first-pass extraction and consensus checks.",
    },
    {
        "device_id": "device-aws-big",
        "name": "Claude Sonnet (big)",
        "provider": "AWS Bedrock",
        "device_type": "llm",
        "role": "big",
        "status": "active",
        "env_var": "AWS_BIG_MODEL",
        "default_model_id": "eu.anthropic.claude-sonnet-4-6",
        "endpoint_env_var": "",
        "notes": "Mid-tier model used when small models disagree or for complex clinical reasoning.",
    },
    {
        "device_id": "device-aws-max",
        "name": "Claude Opus (max)",
        "provider": "AWS Bedrock",
        "device_type": "llm",
        "role": "max",
        "status": "active",
        "env_var": "AWS_MAX_MODEL",
        "default_model_id": "eu.anthropic.claude-opus-4-6-v1",
        "endpoint_env_var": "",
        "notes": "Highest capability model. Used for verification, prompt tuning, and escalation.",
    },
    # ----------------------------------------------------------------
    # Azure OpenAI — GPT models
    # ----------------------------------------------------------------
    {
        "device_id": "device-azure-small",
        "name": "GPT-5-mini (small)",
        "provider": "Azure OpenAI",
        "device_type": "llm",
        "role": "small",
        "status": "active",
        "env_var": "AZURE_OPENAI_SMALL_MODEL",
        "default_model_id": "gpt-5-mini",
        "endpoint_env_var": "AZURE_OPENAI_ENDPOINT",
        "notes": "Azure alternative for small-tier extraction.",
    },
    {
        "device_id": "device-azure-big",
        "name": "GPT-5 (big)",
        "provider": "Azure OpenAI",
        "device_type": "llm",
        "role": "big",
        "status": "active",
        "env_var": "AZURE_OPENAI_BIG_MODEL",
        "default_model_id": "gpt-5",
        "endpoint_env_var": "AZURE_OPENAI_ENDPOINT",
        "notes": "Azure alternative for big-tier and max-tier extraction.",
    },
    # ----------------------------------------------------------------
    # NER inference service
    # ----------------------------------------------------------------
    {
        "device_id": "device-ner-medspacy",
        "name": "MedSpaCy Clinical NER",
        "provider": "Custom",
        "device_type": "ner",
        "role": "ner",
        "status": "active",
        "env_var": "CODING_MODEL_NAME",
        "default_model_id": "medspacy_clinical_ner",
        "endpoint_env_var": "CODING_MODEL_ENDPOINT",
        "notes": "Deployed NER model. Runs at CODING_MODEL_ENDPOINT (default: http://localhost:8004). "
        "Used when extractor backend is 'model' or 'auto'.",
    },
]

# Initial pipeline routing config.
# These mirror the env vars PIPELINE_MODEL_PROVIDER / PIPELINE_MODEL_TIER /
# CODING_EXTRACTOR_BACKEND so the UX can change them without a redeploy.
PIPELINE_CONFIG = {
    "provider": os.getenv("PIPELINE_MODEL_PROVIDER", "aws"),
    "tier": os.getenv("PIPELINE_MODEL_TIER", "small"),
    "extractor_backend": os.getenv("CODING_EXTRACTOR_BACKEND", "llm"),
    "strict": os.getenv("CODING_EXTRACTOR_STRICT", "false").lower() == "true",
    # consensus_mode: run two cheap models in parallel; only use big model if they disagree.
    # Recommended for accuracy. Defaults to True.
    "consensus_mode": os.getenv("PIPELINE_CONSENSUS_MODE", "true").lower() == "true",
}


def main() -> None:
    client = KnowledgeGraphClient()
    print(f"Seeding Device nodes into Knowledge Graph...")

    with client.session() as session:
        result = session.run("MATCH (d:Device) RETURN count(d) AS cnt").single()
        existing = result["cnt"] if result else 0
        if existing > 0:
            print(f"Skipped — {existing} Device(s) already present.")
            client.close()
            return

        # Ensure indexes
        for idx in CREATE_DEVICE_INDEXES:
            try:
                session.run(idx)
            except Exception:
                pass

        # Upsert each device
        for d in DEVICES:
            session.run(
                UPSERT_DEVICE,
                device_id=d["device_id"],
                name=d["name"],
                provider=d["provider"],
                device_type=d["device_type"],
                role=d["role"],
                status=d["status"],
                env_var=d["env_var"],
                default_model_id=d["default_model_id"],
                endpoint_env_var=d.get("endpoint_env_var", ""),
                notes=d.get("notes", ""),
                raw_json=_fhir_device(
                    device_id=d["device_id"],
                    name=d["name"],
                    provider=d["provider"],
                    device_type=d["device_type"],
                    role=d["role"],
                    env_var=d["env_var"],
                    default_model_id=d["default_model_id"],
                    endpoint_env_var=d.get("endpoint_env_var", ""),
                    notes=d.get("notes", ""),
                ),
            )
            print(f"  [ok] {d['device_id']} — {d['name']}")

        # Upsert pipeline config
        session.run(UPSERT_PIPELINE_CONFIG, **PIPELINE_CONFIG)
        print(
            f"  [ok] PipelineConfig: provider={PIPELINE_CONFIG['provider']} "
            f"tier={PIPELINE_CONFIG['tier']} backend={PIPELINE_CONFIG['extractor_backend']}"
        )

    client.close()
    print(f"Done. {len(DEVICES)} devices seeded.")


if __name__ == "__main__":
    main()
