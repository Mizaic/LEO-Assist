"""Neo4j client wrappers for HITL MVP — patient graph and coding graph.

Atlas trace:
  DO: DO-448BFA1A
  DI: DI-84F44836
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-448BFA1A")
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

from libs.neo4j_client.client import (
    _get_or_create_driver,
    run_with_retry as _shared_run_with_retry,
)

from app.config import get_settings
from app.models.neo4j_schema import (
    CODING_SCHEMA_CONSTRAINTS,
    PATIENT_SCHEMA_CONSTRAINTS,
)

logger = logging.getLogger(__name__)


def run_with_retry(
    client: "_BaseClient",
    query: str,
    **params: Any,
) -> list[dict[str, Any]]:
    """Re-export of the shared retry runner so existing imports keep working."""
    return _shared_run_with_retry(client, query, **params)


class _BaseClient:
    """Thin wrapper that re-uses the process-wide Neo4j driver pool.

    Constructing this class previously created a fresh ``GraphDatabase.driver``
    -- and a full TLS handshake to Aura -- per FastAPI request. The driver is
    designed to be a long-lived singleton, so we cache it in
    :mod:`libs.neo4j_client.client` and resolve the cached driver here.
    """

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
        self._driver = _get_or_create_driver(
            uri,
            username,
            password,
            notifications_min_severity=notifications_min_severity,
        )

    def close(self) -> None:
        # The shared driver pool is closed at interpreter exit. Keep this a
        # no-op so legacy ``client.close()`` calls do not tear down the
        # process-wide pool out from under concurrent callers.
        return None

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
