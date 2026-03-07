"""Versioned prompt registry with Neo4j-first resolution.

Prompts are stored as ``PromptConfig`` nodes in the Knowledge Graph.
This module tries Neo4j first, then falls back to the hardcoded Python
prompts bundled in ``libs/prompts/*.py`` (which are deprecated and will
be removed once all prompts are managed through the Admin UI).

Usage::

    from libs.prompts.registry import get_prompt

    system = get_prompt("extraction", version=1)
    system = get_prompt("disambiguation", version=1)
    system = get_prompt("episode_builder_system", version=1)
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

_REGISTRY: Dict[Tuple[str, int], str] = {}
_NEO4J_AVAILABLE: bool | None = None


def register(name: str, version: int, text: str) -> None:
    """Register a hardcoded (fallback) prompt."""
    _REGISTRY[(name, version)] = text


def _try_neo4j(name: str, version: int) -> str | None:
    """Attempt to read a PromptConfig node from Neo4j.

    Returns the system_prompt text if found, None otherwise.
    Silently returns None on any connection / import error so the
    caller can fall back to the hardcoded registry.
    """
    global _NEO4J_AVAILABLE

    if _NEO4J_AVAILABLE is False:
        return None

    try:
        from libs.cypher.prompt_config_queries import GET_PROMPT_BY_NAME
        from libs.neo4j_client.client import KnowledgeGraphClient

        client = KnowledgeGraphClient()
        try:
            with client.session() as session:
                row = session.run(
                    GET_PROMPT_BY_NAME, name=name, version=version
                ).single()
            if row:
                _NEO4J_AVAILABLE = True
                return row["systemPrompt"]
        finally:
            client.close()

        _NEO4J_AVAILABLE = True
        return None

    except Exception:
        if _NEO4J_AVAILABLE is None:
            logger.debug(
                "Neo4j prompt lookup unavailable — using hardcoded fallbacks"
            )
        _NEO4J_AVAILABLE = False
        return None


def get_prompt(name: str, version: int = 1) -> str:
    """Return the prompt text for *name* at *version*.

    Resolution order:
    1. Neo4j ``PromptConfig`` node (if available)
    2. Hardcoded Python registry (fallback)

    Raises ``KeyError`` if the combination is not found anywhere.
    """
    neo4j_text = _try_neo4j(name, version)
    if neo4j_text is not None:
        return neo4j_text

    key = (name, version)
    if key not in _REGISTRY:
        available = [k for k in _REGISTRY if k[0] == name]
        if available:
            versions = sorted(v for _, v in available)
            raise KeyError(
                f"Prompt {name!r} has no version {version}; "
                f"available versions: {versions}"
            )
        raise KeyError(
            f"Unknown prompt {name!r}. Registered: "
            f"{sorted(set(k[0] for k in _REGISTRY))}"
        )
    return _REGISTRY[key]


def get_prompt_with_few_shot(name: str, version: int = 1) -> tuple[str, list[dict[str, Any]]]:
    """Return (system_prompt, few_shot_examples) for the named prompt.

    Few-shot examples are only available when Neo4j resolves the prompt.
    Falls back to (hardcoded_text, []) when Neo4j is unavailable.
    """
    global _NEO4J_AVAILABLE

    if _NEO4J_AVAILABLE is not False:
        try:
            from libs.cypher.prompt_config_queries import GET_PROMPT_BY_NAME
            from libs.neo4j_client.client import KnowledgeGraphClient

            client = KnowledgeGraphClient()
            try:
                with client.session() as session:
                    row = session.run(
                        GET_PROMPT_BY_NAME, name=name, version=version
                    ).single()
                if row:
                    _NEO4J_AVAILABLE = True
                    few_shot_raw = row.get("fewShotExamples") or "[]"
                    try:
                        examples = json.loads(few_shot_raw) if isinstance(few_shot_raw, str) else few_shot_raw
                    except (json.JSONDecodeError, TypeError):
                        examples = []
                    return row["systemPrompt"], examples
            finally:
                client.close()

            _NEO4J_AVAILABLE = True
        except Exception:
            _NEO4J_AVAILABLE = False

    return get_prompt(name, version), []


def list_prompts() -> list[tuple[str, int]]:
    """Return all registered (name, version) pairs from the hardcoded registry."""
    return sorted(_REGISTRY.keys())


# Auto-register all bundled prompt modules on import (deprecated fallbacks).
from libs.prompts import extraction_v1 as _ext  # noqa: F401, E402
from libs.prompts import disambiguation_v1 as _dis  # noqa: F401, E402
from libs.prompts import episode_builder_v1 as _ep  # noqa: F401, E402
from libs.prompts import encounter_classify_v1 as _enc  # noqa: F401, E402
from libs.prompts import anchor_domain_review_v1 as _anc  # noqa: F401, E402
from libs.prompts import exclusion_detect_v1 as _excl  # noqa: F401, E402
from libs.prompts import label_verification_v2 as _lv2  # noqa: F401, E402
from libs.prompts import label_disambiguation_v1 as _ld1  # noqa: F401, E402
