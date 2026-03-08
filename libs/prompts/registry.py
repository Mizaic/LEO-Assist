"""Neo4j-only prompt registry.

Prompts are stored as ``PromptConfig`` nodes in the Knowledge Graph and
are editable at runtime via /admin/prompts without a code deploy.

There is no Python fallback.  If a prompt is not in Neo4j the caller
receives a ``RuntimeError`` with instructions to run the seed script.
On API startup ``seed_if_missing()`` in ``scripts.seed_prompt_configs``
is called in a background thread to ensure all factory-default prompts
are present before any request that needs them can arrive.

Usage::

    from libs.prompts.registry import get_prompt, get_prompt_with_few_shot

    system = get_prompt("extraction", version=1)
    system, examples = get_prompt_with_few_shot("guidance_rule_extraction_NG12", version=1)
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _neo4j_fetch(name: str, version: int) -> dict | None:
    """Fetch a PromptConfig row from Neo4j.

    Returns the full row dict on success, None if no matching node exists.
    Raises on connection or query errors so the caller can surface them.
    """
    from libs.cypher.prompt_config_queries import GET_PROMPT_BY_NAME
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_PROMPT_BY_NAME, name=name, version=version).single()
        return dict(row) if row else None
    finally:
        client.close()


def get_prompt(name: str, version: int = 1) -> str:
    """Return the system prompt text for *name* at *version* from Neo4j.

    Raises:
        RuntimeError: Prompt not found, or Neo4j is unreachable.
            Run ``python -m scripts.seed_prompt_configs`` to populate
            factory-default prompts.
    """
    try:
        row = _neo4j_fetch(name, version)
    except Exception as exc:
        raise RuntimeError(
            f"Prompt {name!r} v{version} could not be loaded from Neo4j: {exc}. "
            "Run: python -m scripts.seed_prompt_configs"
        ) from exc

    if row is None:
        raise RuntimeError(
            f"Prompt {name!r} v{version} not found in Neo4j. "
            "Run: python -m scripts.seed_prompt_configs"
        )
    return row["systemPrompt"]


def get_prompt_with_few_shot(
    name: str,
    version: int = 1,
) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(system_prompt, few_shot_examples)`` for the named prompt.

    Raises:
        RuntimeError: Prompt not found, or Neo4j is unreachable.
    """
    try:
        row = _neo4j_fetch(name, version)
    except Exception as exc:
        raise RuntimeError(
            f"Prompt {name!r} v{version} could not be loaded from Neo4j: {exc}. "
            "Run: python -m scripts.seed_prompt_configs"
        ) from exc

    if row is None:
        raise RuntimeError(
            f"Prompt {name!r} v{version} not found in Neo4j. "
            "Run: python -m scripts.seed_prompt_configs"
        )

    few_shot_raw = row.get("fewShotExamples") or "[]"
    try:
        examples = (
            json.loads(few_shot_raw)
            if isinstance(few_shot_raw, str)
            else few_shot_raw
        )
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning(
            "Prompt %r v%d: fewShotExamples could not be parsed as JSON — "
            "returning empty examples list. LLM output quality may be degraded. Error: %s",
            name, version, exc,
        )
        examples = []

    return row["systemPrompt"], examples
