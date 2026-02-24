"""Configuration helpers for HITL MVP API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / "secrets" / ".env")


@dataclass(frozen=True)
class Settings:
    patient_neo4j_uri: str
    patient_neo4j_username: str
    patient_neo4j_password: str
    coding_neo4j_uri: str
    coding_neo4j_username: str
    coding_neo4j_password: str
    pipeline_version: str
    extractor_version: str
    validator_version: str
    model_id: str
    prompt_version: str
    terminology_version: str


def get_settings() -> Settings:
    return Settings(
        patient_neo4j_uri=os.getenv("NEO4J_URI", ""),
        patient_neo4j_username=os.getenv("NEO4J_USER", ""),
        patient_neo4j_password=os.getenv("NEO4J_PASSWORD", ""),
        coding_neo4j_uri=os.getenv("CODING_GRAPH_NEO4J_URI", ""),
        coding_neo4j_username=os.getenv("CODING_GRAPH_NEO4J_USERNAME", ""),
        coding_neo4j_password=os.getenv("CODING_GRAPH_NEO4J_PASSWORD", ""),
        pipeline_version=os.getenv("TRAINING_PIPELINE_VERSION", "v2.0.0-mvp"),
        extractor_version=os.getenv("TRAINING_EXTRACTOR_VERSION", "v2.surface_patch"),
        validator_version=os.getenv("TRAINING_VALIDATOR_VERSION", "v2.gates"),
        model_id=os.getenv("AWS_SMALL_MODEL", "unconfigured"),
        prompt_version=os.getenv("TRAINING_PROMPT_VERSION", "v1"),
        terminology_version=os.getenv("TERMINOLOGY_VERSION", "snomed-uk-current"),
    )
