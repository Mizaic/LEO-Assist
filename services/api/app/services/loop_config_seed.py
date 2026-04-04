"""Seed default LoopConfig nodes for the three learning loops.

Creates one LoopConfig node per loop with enabled=true if the node does not
already exist. Called during API startup (non-fatal on failure).

Loop IDs (canonical):
  loop1_audit         -- weekly coding quality audit
  loop2_surface_form  -- surface form vocabulary growth
  loop3_evidence      -- NER training evidence collection
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_LOOP_DEFAULTS = [
    {
        "loop_id": "loop1_audit",
        "description": "Weekly quality check",
        "enabled": True,
    },
    {
        "loop_id": "loop2_surface_form",
        "description": "Dictionary learning",
        "enabled": True,
    },
    {
        "loop_id": "loop3_evidence",
        "description": "Training data collection",
        "enabled": True,
    },
]

_UPSERT_LOOP_CONFIG = """
MERGE (c:LoopConfig {loop_id: $loop_id})
ON CREATE SET
    c.enabled     = $enabled,
    c.description = $description,
    c.updated_by  = 'system_seed',
    c.updated_at  = datetime()
RETURN c.loop_id AS loop_id, c.enabled AS enabled
"""


def seed_loop_configs(client) -> None:
    """Create LoopConfig nodes if they do not already exist."""
    for cfg in _LOOP_DEFAULTS:
        try:
            client.run(_UPSERT_LOOP_CONFIG, **cfg)
            logger.debug("LoopConfig seeded: %s", cfg["loop_id"])
        except Exception as exc:
            logger.warning(
                "LoopConfig seed failed for %s: %s", cfg["loop_id"], exc
            )
    logger.info("LoopConfig seed complete (%d loops).", len(_LOOP_DEFAULTS))
