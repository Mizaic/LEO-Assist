"""Neo4j client wrappers for HITL MVP — patient graph and coding graph.

Atlas trace:
  DO: DO-448BFA1A
  DI: DI-84F44836
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-448BFA1A")
"""

from __future__ import annotations

import logging
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

from app.config import get_settings
from app.models.neo4j_schema import (
    CODING_SCHEMA_CONSTRAINTS,
    PATIENT_SCHEMA_CONSTRAINTS,
)

logger = logging.getLogger(__name__)

_RETRYABLE_EXCEPTIONS = (ServiceUnavailable, SessionExpired, TransientError, OSError)
_MAX_RETRIES = 4
_BASE_DELAY = 1.0
_MAX_DELAY = 15.0


def run_with_retry(
    client: "_BaseClient",
    query: str,
    **params: Any,
) -> list[dict[str, Any]]:
    """Execute a Cypher query with automatic retry on transient connection errors.

    Opens a fresh session per attempt so stale connections are discarded.
    """
    last_exc: BaseException | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            with client.session() as s:
                return [dict(r) for r in s.run(query, **params)]
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            if attempt == _MAX_RETRIES - 1:
                raise
            delay = min(_MAX_DELAY, _BASE_DELAY * (2**attempt)) + random.uniform(0, 0.5)
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
    """Connects to the patient/encounter/HITL graph (NEO4J_URI)."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(
            settings.patient_neo4j_uri,
            settings.patient_neo4j_username,
            settings.patient_neo4j_password,
        )

    def initialize_schema(self) -> None:
        with self.session() as s:
            for query in PATIENT_SCHEMA_CONSTRAINTS:
                s.run(query)


class CodingGraphClient(_BaseClient):
    """Connects to the Knowledge Graph (KNOWLEDGE_GRAPH_NEO4J_URI). Read-only for app code."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(
            settings.knowledge_neo4j_uri,
            settings.knowledge_neo4j_username,
            settings.knowledge_neo4j_password,
        )

    def initialize_schema(self) -> None:
        with self.session() as s:
            for query in CODING_SCHEMA_CONSTRAINTS:
                s.run(query)
