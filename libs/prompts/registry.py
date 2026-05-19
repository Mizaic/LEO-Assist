"""Neo4j-only prompt registry.

Atlas trace:
  DO: DO-54397CCD
  Also implements: DO-8620A68B, DO-EDA32DB1
  DI: DI-5A802C83, DI-66F1B177, DI-6EFD68D0
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-54397CCD")

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

_ANNOTATION_GUIDELINES_NAME = "annotation_guidelines"
_ANNOTATION_GUIDELINES_VERSION = 1
_ANNOTATION_TARGET_PROMPTS = frozenset(
    {
        "extraction",
        "referral_extraction",
        "label_verification",
        "extraction_check",
        "coding_check",
        "relation_linking",
    }
)


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


def _load_annotation_guidelines_text() -> str:
    """Return canonical annotation guidelines from Neo4j or code fallback."""
    try:
        row = _neo4j_fetch(_ANNOTATION_GUIDELINES_NAME, _ANNOTATION_GUIDELINES_VERSION)
        if row:
            text = str(row.get("systemPrompt") or "").strip()
            if text:
                return text
    except Exception:
        logger.debug("Could not load annotation_guidelines from Neo4j", exc_info=True)

    try:
        from libs.prompts.annotation_guidelines_v1 import ANNOTATION_GUIDELINES_V1

        return str(ANNOTATION_GUIDELINES_V1).strip()
    except Exception:
        logger.debug(
            "Could not load annotation_guidelines fallback constant", exc_info=True
        )
        return ""


def compose_prompt_with_annotation_guidelines(name: str, prompt_text: str) -> str:
    """Append canonical annotation guidelines to selected prompt families."""
    base = str(prompt_text or "").strip()
    if not base:
        return base
    if name not in _ANNOTATION_TARGET_PROMPTS:
        return base
    if name == _ANNOTATION_GUIDELINES_NAME:
        return base

    guidance = _load_annotation_guidelines_text()
    if not guidance:
        return base
    if guidance in base:
        return base
    return f"{base}\n\n{guidance}"


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
    return compose_prompt_with_annotation_guidelines(name, row["systemPrompt"])


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

    cfg = _normalise_prompt_config_row(name, version, row)
    return cfg["systemPrompt"], cfg["fewShotExamples"]


def _normalise_prompt_config_row(
    name: str,
    version: int,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Normalise PromptConfig payload fields into a stable dict shape."""
    few_shot_raw = row.get("fewShotExamples") or "[]"
    try:
        examples = (
            json.loads(few_shot_raw) if isinstance(few_shot_raw, str) else few_shot_raw
        )
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning(
            "Prompt %r v%d: fewShotExamples could not be parsed as JSON - "
            "returning empty examples list. LLM output quality may be degraded. Error: %s",
            name,
            version,
            exc,
        )
        examples = []
    if not isinstance(examples, list):
        examples = []

    return {
        "id": row.get("id", ""),
        "name": row.get("name", name),
        "version": int(row.get("version", version) or version),
        "systemPrompt": compose_prompt_with_annotation_guidelines(
            name, row["systemPrompt"]
        ),
        "outputSchema": row.get("outputSchema") or None,
        "fewShotExamples": examples,
        "maxFewShot": int(row.get("maxFewShot", 20) or 20),
    }


def get_prompt_config(name: str, version: int = 1) -> dict[str, Any]:
    """Return full prompt config (system, schema, examples) from Neo4j."""
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

    return _normalise_prompt_config_row(name, version, row)
