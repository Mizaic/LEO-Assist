"""Bootstrap shared ServiceConfig nodes into the knowledge graph."""

from __future__ import annotations

import json
import logging
import os

from libs.cypher.service_config_queries import (
    CREATE_CONSTRAINT_SERVICE_CONFIG,
    GET_SERVICE_CONFIG,
    UPSERT_SERVICE_CONFIG,
)

logger = logging.getLogger(__name__)


def _terminology_runtime_defaults() -> dict[str, float | int]:
    return {
        "timeout_seconds": float(os.getenv("TERMINOLOGY_API_TIMEOUT", "15.0")),
        "max_retries": int(os.getenv("TERMINOLOGY_API_RETRIES", "3")),
        "cooldown_seconds": float(os.getenv("TERMINOLOGY_API_COOLDOWN_SECONDS", "60")),
        "final_attempts": int(os.getenv("TERMINOLOGY_API_FINAL_ATTEMPTS", "1")),
        "max_concurrent_requests": int(
            os.getenv("TERMINOLOGY_API_MAX_CONCURRENT_REQUESTS", "2")
        ),
        "max_terms_per_request": int(
            os.getenv("TERMINOLOGY_API_MAX_TERMS_PER_REQUEST", "8")
        ),
    }


def seed_service_configs(client) -> None:
    """Ensure baseline ServiceConfig rows exist without overwriting user edits."""
    try:
        with client.session() as session:
            session.run(CREATE_CONSTRAINT_SERVICE_CONFIG)
            existing = session.run(
                GET_SERVICE_CONFIG,
                key="terminology:resolve_runtime",
            ).single()
            if existing:
                logger.info(
                    "ServiceConfig %s already in Neo4j — skipping seed",
                    "terminology:resolve_runtime",
                )
                return
            config = _terminology_runtime_defaults()
            session.run(
                UPSERT_SERVICE_CONFIG,
                key="terminology:resolve_runtime",
                category="terminology",
                display_name="Terminology resolve runtime",
                description=(
                    "Shared runtime controls for batched terminology resolution across API replicas."
                ),
                config_json=json.dumps(config, sort_keys=True),
                source="seed",
            )
        logger.info(
            "ServiceConfig bootstrap done: terminology runtime settings created"
        )
    except Exception as exc:
        logger.warning("ServiceConfig seed failed (non-fatal): %s", exc)
