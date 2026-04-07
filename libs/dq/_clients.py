"""Shared client factory for the DQ toolkit.

All environment variables are read at call time (not module load) so that
tests can patch them without import-order issues.
"""
from __future__ import annotations

import os
from typing import Any


def get_patient_client() -> Any:
    """Return a PatientGraphClient connected via env vars."""
    from libs.neo4j_client.client import PatientGraphClient

    return PatientGraphClient()


def get_kg_client() -> Any:
    """Return a KnowledgeGraphClient connected via env vars."""
    from libs.neo4j_client.client import KnowledgeGraphClient

    return KnowledgeGraphClient()


def get_term_client() -> Any:
    """Return a TerminologyClient pointed at TERMINOLOGY_API_URL."""
    from libs.terminology.client import TerminologyClient

    base_url = os.environ.get("TERMINOLOGY_API_URL", "http://localhost:8001")
    return TerminologyClient(base_url=base_url)


def run_query(client: Any, cypher: str, **params: Any) -> list[dict]:
    """Execute a Cypher query via a client, returning list of dicts."""
    from libs.neo4j_client.client import run_with_retry

    return run_with_retry(client, cypher, **params)
