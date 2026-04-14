"""Configuration helpers for HITL MVP API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets


class CodingMode(str, Enum):
    """Pipeline operating mode.

    HITL: uncertain items route to the coding review queue for human review.
    AUTONOMOUS: no review queue -- items are auto-coded, coded with an audit
    flag, or skipped and logged based on confidence tier.
    """

    HITL = "hitl"
    AUTONOMOUS = "autonomous"


ROOT = Path(__file__).resolve().parents[3]
# Load non-secret config (.env.config contains AZURE_KEYVAULT_URL and safe defaults).
# Secrets come exclusively from Azure Key Vault -- no local secret files.
load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_keyvault_secrets()


@dataclass(frozen=True)
class Settings:
    patient_neo4j_uri: str
    patient_neo4j_username: str
    patient_neo4j_password: str
    knowledge_neo4j_uri: str
    knowledge_neo4j_username: str
    knowledge_neo4j_password: str
    pipeline_version: str
    extractor_version: str
    validator_version: str
    model_id: str
    prompt_version: str
    terminology_version: str
    coding_mode: CodingMode


def get_settings() -> Settings:
    raw_mode = os.getenv("CODING_MODE", "hitl").strip().lower()
    try:
        coding_mode = CodingMode(raw_mode)
    except ValueError:
        coding_mode = CodingMode.HITL

    return Settings(
        patient_neo4j_uri=os.getenv("NEO4J_URI", ""),
        patient_neo4j_username=os.getenv("NEO4J_USER", "neo4j"),
        patient_neo4j_password=os.getenv("NEO4J_PASSWORD", ""),
        knowledge_neo4j_uri=os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", ""),
        knowledge_neo4j_username=os.getenv(
            "KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j"
        ),
        knowledge_neo4j_password=os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", ""),
        pipeline_version=os.getenv("TRAINING_PIPELINE_VERSION", "v2.0.0-mvp"),
        extractor_version=os.getenv("TRAINING_EXTRACTOR_VERSION", "v2.surface_patch"),
        validator_version=os.getenv("TRAINING_VALIDATOR_VERSION", "v2.gates"),
        model_id=os.getenv("AWS_SMALL_MODEL", "unconfigured"),
        prompt_version=os.getenv("TRAINING_PROMPT_VERSION", "v2"),
        terminology_version=os.getenv("TERMINOLOGY_VERSION", "snomed-uk-current"),
        coding_mode=coding_mode,
    )
