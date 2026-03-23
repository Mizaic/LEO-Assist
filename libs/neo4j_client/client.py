"""Neo4j client wrappers for Patient Graph and Knowledge Graph.

Ported from Primary-care-audit services/api/app/db/neo4j_client.py.
Renamed CodingGraphClient -> KnowledgeGraphClient to reflect the merged
terminology + FHIR resource graph.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Fallback for scripts and test harnesses that import this lib directly without
# going through a service main.py (which calls load_keyvault_secrets() first).
# Services always call load_keyvault_secrets() before importing, so KV wins.
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_REPO_ROOT / "secrets" / ".env", override=False)
import random
import time
from contextlib import contextmanager
from typing import Any

from neo4j import AsyncGraphDatabase, GraphDatabase
from neo4j.exceptions import (
    ConfigurationError,
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)

logger = logging.getLogger("libs.neo4j_client")

_RETRYABLE_EXCEPTIONS = (ServiceUnavailable, SessionExpired, TransientError, OSError)
_MAX_RETRIES = 6
_BASE_DELAY = 1.0
_MAX_DELAY = 30.0


def run_with_retry(
    client: "_BaseClient",
    query: str,
    **params: Any,
) -> list[dict[str, Any]]:
    """Execute a Cypher query with automatic retry on transient connection errors."""
    last_exc: BaseException | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            with client.session() as s:
                return [dict(r) for r in s.run(query, **params)]
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            if attempt == _MAX_RETRIES - 1:
                raise
            delay = min(_MAX_DELAY, _BASE_DELAY * (2**attempt)) + random.uniform(
                0, 0.5
            )
            logger.warning(
                "Neo4j transient error (attempt %d/%d): %s — retrying in %.1fs",
                attempt + 1,
                _MAX_RETRIES,
                exc,
                delay,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Neo4j request failed after retries")


class _BaseClient:
    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        *,
        notifications_min_severity: str = "OFF",
    ) -> None:
        if not all([uri, username, password]):
            raise RuntimeError(f"Neo4j credentials missing for {uri or 'unknown'}")
        # liveness_check_timeout: if a pooled connection has been idle for this
        # many seconds the driver sends a lightweight check before reusing it.
        # This prevents SSLEOFError when Aura closes idle TCP connections during
        # long-running operations (e.g. LLM disambiguation batches).
        # max_connection_lifetime: retire connections older than 5 min regardless.
        _pool_kwargs: dict = {
            "liveness_check_timeout": 5,   # Aura closes idle TCP in ~7-10s; check at 5s
            "max_connection_lifetime": 300,
        }
        try:
            self._driver = GraphDatabase.driver(
                uri,
                auth=(username, password),
                notifications_min_severity=notifications_min_severity,
                **_pool_kwargs,
            )
        except ConfigurationError:
            # Older driver versions don't accept all kwargs; try without extras.
            try:
                self._driver = GraphDatabase.driver(
                    uri,
                    auth=(username, password),
                    **_pool_kwargs,
                )
            except ConfigurationError:
                self._driver = GraphDatabase.driver(uri, auth=(username, password))

    def close(self) -> None:
        self._driver.close()

    @contextmanager
    def session(self):
        s = self._driver.session()
        try:
            yield s
        finally:
            s.close()

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        return run_with_retry(self, query, **params)


class PatientGraphClient(_BaseClient):
    """Connects to the Patient Graph (NEO4J_URI).

    Contains: Patient, Encounter, EncounterCandidate, ReviewTask,
    Approval, Change, EpisodeOfCare, SafetyNetAlert, Benchmark, etc.
    """

    def __init__(self) -> None:
        super().__init__(
            os.getenv("NEO4J_URI", ""),
            os.getenv("NEO4J_USER", ""),
            os.getenv("NEO4J_PASSWORD", ""),
        )


class KnowledgeGraphClient(_BaseClient):
    """Connects to the Knowledge Graph (KNOWLEDGE_GRAPH_NEO4J_URI).

    Contains anonymous/de-identified model knowledge — no patient identifiers:
      Terminology:   Concept, Term, SurfaceForm, ReadCode, Icd10Code, ValueSet,
                     ConceptMap, CodingDecision, SurfaceFormTask
      Learning loop: TrainingCandidate, GoldLabel  (GDPR-isolated)
      Pipeline:      PromptConfig, PipelineConfig, Device, PlanDefinition,
                     ModelVersion, ModelRegistryConfig, ModelPreset
      Org/FHIR:      Measure, Library, MeasureReport, Organization
    """

    def __init__(self) -> None:
        super().__init__(
            os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", ""),
            os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", ""),
            os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", ""),
        )


def get_async_driver():
    """Return an async Neo4j driver for the Knowledge Graph.

    Workflow plans, actions, and activity definitions are stored in the
    knowledge graph, so the pipeline worker needs an async KG driver rather
    than the patient-graph client wrappers above.
    """
    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "")
    username = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "")
    password = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")
    if not all([uri, username, password]):
        raise RuntimeError("Neo4j credentials missing for async knowledge graph driver")
    return AsyncGraphDatabase.driver(uri, auth=(username, password))
