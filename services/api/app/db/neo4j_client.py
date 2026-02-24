"""Neo4j client wrappers for HITL MVP — patient graph and coding graph."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from neo4j import GraphDatabase

from app.config import get_settings
from app.models.neo4j_schema import SCHEMA_CONSTRAINTS


class _BaseClient:
    def __init__(self, uri: str, username: str, password: str) -> None:
        if not all([uri, username, password]):
            raise RuntimeError(f"Neo4j credentials missing for {uri or 'unknown'}")
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
    """Connects to the patient/encounter graph (NEO4J_URI)."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(
            settings.patient_neo4j_uri,
            settings.patient_neo4j_username,
            settings.patient_neo4j_password,
        )


class CodingGraphClient(_BaseClient):
    """Connects to the terminology/review graph (CODING_GRAPH_NEO4J_URI)."""

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(
            settings.coding_neo4j_uri,
            settings.coding_neo4j_username,
            settings.coding_neo4j_password,
        )

    def initialize_schema(self) -> None:
        with self.session() as s:
            for query in SCHEMA_CONSTRAINTS:
                s.run(query)
