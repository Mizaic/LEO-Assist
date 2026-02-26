"""Neo4j client wrappers for Patient Graph and Knowledge Graph.

Ported from Primary-care-audit services/api/app/db/neo4j_client.py.
Renamed CodingGraphClient -> KnowledgeGraphClient to reflect the merged
terminology + FHIR resource graph.
"""

from __future__ import annotations

import logging
import os
import random
import time
from contextlib import contextmanager
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import (
    ConfigurationError,
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)

logger = logging.getLogger("libs.neo4j_client")

_RETRYABLE_EXCEPTIONS = (ServiceUnavailable, SessionExpired, TransientError, OSError)
_MAX_RETRIES = 4
_BASE_DELAY = 1.0
_MAX_DELAY = 15.0


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
        try:
            self._driver = GraphDatabase.driver(
                uri,
                auth=(username, password),
                notifications_min_severity=notifications_min_severity,
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
    Approval, Change, CancerEpisode, CSSAlert, Benchmark, etc.
    """

    def __init__(self) -> None:
        super().__init__(
            os.getenv("NEO4J_URI", ""),
            os.getenv("NEO4J_USER", ""),
            os.getenv("NEO4J_PASSWORD", ""),
        )


class KnowledgeGraphClient(_BaseClient):
    """Connects to the Knowledge Graph (KNOWLEDGE_GRAPH_NEO4J_URI).

    Contains: Concept, Term, SurfaceForm, ReadCode, Icd10Code,
    ValueSet, ConceptMap, Measure, Library, MeasureReport, Device,
    PlanDefinition, Organization.
    """

    def __init__(self) -> None:
        super().__init__(
            os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", ""),
            os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", ""),
            os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", ""),
        )
