"""Shared Neo4j client library for Patient Graph and Knowledge Graph connections.

Ported from Primary-care-audit services/api/app/db/neo4j_client.py.
Provides retry logic and connection management for both Neo4j Aura instances.
"""

from libs.neo4j_client.client import (
    PatientGraphClient,
    KnowledgeGraphClient,
    run_with_retry,
)

__all__ = ["PatientGraphClient", "KnowledgeGraphClient", "run_with_retry"]
