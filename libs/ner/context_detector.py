"""Situation lookup normalisation for UK primary care NER entities.

Atlas trace:
  DO: DO-A8000E51
  Also implements: DO-170F0DEE
  DI: DI-34712A9A, DI-31126C6C, DI-3B3F7D4B
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A8000E51")

Context assertion detection (negation, historical, hypothetical, declined)
has been moved to libs/ner/context_engine.py which uses MedSpaCy ConText.

This module retains only normalize_situation_lookup(), which rewrites
freeform situation-entity text to SNOMED-friendly lookup terms. Rules are
loaded from a JSON seed file (builtin) and Neo4j (custom) so a platform
admin can add or adjust patterns without a code deployment.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_SEED_PATH = Path(__file__).parent / "resources" / "situation_lookup.json"
_FAMILY = "situation_lookup"

# Module-level singleton: list of (compiled_pattern, canonical | None).
# Rebuilt on import and on each call to _reload_singleton().
_singleton: list[tuple[re.Pattern[str], str | None]] = []


def _fetch_neo4j_rules(family: str) -> list[dict]:
    """Fetch active :NerGuardRule nodes for the situation_lookup family.

    Returns [] and logs a warning when Neo4j is unreachable.
    Defined at module level so tests can patch it directly.
    """
    try:
        from libs.pipeline.config_loader import _fetch_neo4j_rules as _loader

        return _loader(family)
    except Exception:
        logger.warning(
            "Could not fetch Neo4j rules for family %r -- using builtins only",
            family,
            exc_info=True,
        )
        return []


def _parse_row(row: dict, source: str) -> tuple[str, str | None, bool, int]:
    """Extract (pattern, canonical, active, priority) from a raw rule dict."""
    return (
        row.get("pattern", ""),
        row.get("canonical"),
        bool(row.get("active", True)),
        int(row.get("priority", 10)),
    )


def _build_singleton() -> list[tuple[re.Pattern[str], str | None]]:
    """Compile rules from seed JSON + Neo4j into a ready-to-use list."""
    from libs.pipeline.config_loader import _load_seed

    raw_seed = _load_seed(_SEED_PATH)
    neo4j_rows = _fetch_neo4j_rules(_FAMILY)

    all_rows: list[tuple[str, str | None, bool, int]] = []
    for r in raw_seed:
        pattern, canonical, active, priority = _parse_row(r, "builtin")
        if active and pattern:
            all_rows.append((pattern, canonical, active, priority))
    for r in neo4j_rows:
        pattern, canonical, active, priority = _parse_row(r, "custom")
        if active and pattern:
            all_rows.append((pattern, canonical, active, priority))

    all_rows.sort(key=lambda t: t[3], reverse=True)

    compiled = []
    for raw_pattern, canonical, _, _ in all_rows:
        try:
            compiled.append((re.compile(raw_pattern, re.I), canonical))
        except re.error:
            logger.warning(
                "Invalid regex in situation_lookup rules: %r -- skipped", raw_pattern
            )
    return compiled


def _reload_singleton() -> None:
    """Rebuild the singleton rule list, re-fetching custom rules from Neo4j.

    Call this after creating or deactivating a :NerGuardRule node with
    family='situation_lookup' so the pipeline picks up the change without
    a service restart.
    """
    global _singleton
    _singleton = _build_singleton()
    logger.info("Situation lookup singleton reloaded (%d rules)", len(_singleton))


# Initialise on module import.
_reload_singleton()


def normalize_situation_lookup(entity_text: str) -> str | None:
    """Return a SNOMED-friendly lookup term for freeform situation phrases.

    Returns None if no normalisation pattern matches, meaning the original
    text should be used as-is for terminology lookup.
    """
    for pattern, canonical in _singleton:
        if pattern.search(entity_text):
            return canonical
    return None
