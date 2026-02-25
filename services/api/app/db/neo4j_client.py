"""Neo4j client wrappers for HITL MVP — patient graph and coding graph."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import ConfigurationError

from app.config import get_settings
from app.models.neo4j_schema import CODING_SCHEMA_CONSTRAINTS, PATIENT_SCHEMA_CONSTRAINTS


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
            # Fallback for Neo4j < 5.7 that doesn't support notifications_min_severity
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
        with self.session() as s:
            return [dict(r) for r in s.run(query, **params)]


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
    """Connects to the terminology graph (CODING_GRAPH_NEO4J_URI). Read-only for app code."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(
            settings.coding_neo4j_uri,
            settings.coding_neo4j_username,
            settings.coding_neo4j_password,
        )

    def initialize_schema(self) -> None:
        with self.session() as s:
            for query in CODING_SCHEMA_CONSTRAINTS:
                s.run(query)
