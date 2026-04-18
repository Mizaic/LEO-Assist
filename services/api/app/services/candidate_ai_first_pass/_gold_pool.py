"""Gold-pool loader + FewShotSelector wrapper.

DI-LEO-AI-208 / DO-LEO-AI-205.

Loads status='completed' TrainingCandidate rows from Neo4j and converts
them into the `{category, description, input}` shape that
``libs.prompts.few_shot_selector.FewShotSelector`` expects.

The constructed selector is cached PROCESS-WIDE so the BioClinicalBERT
pool embedding (the expensive step) is computed at most once per API
process. Callers can refresh the pool on demand via
``invalidate_cache()`` after a known gold-write event.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Sequence

from libs.cypher.training_candidate_queries import READ_GOLD_POOL_FOR_FEW_SHOT
from libs.prompts.few_shot_selector import FewShotSelector

logger = logging.getLogger(__name__)

_CACHE_LOCK = threading.Lock()
_SELECTOR_CACHE: FewShotSelector | None = None
_CACHE_POOL_SIZE: int = 0


def _row_to_example(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a gold candidate row into a few-shot example dict.

    Keys consumed by FewShotSelector._example_text():
      - category    -> short label used for routing buckets
      - description -> human-readable summary
      - input       -> raw text the example demonstrates
    Plus 'output' (entities_json) preserved for prompt rendering.
    """
    text = str(row.get("text") or "").strip()
    source = str(row.get("source") or "").strip().lower()
    raw_entities = row.get("entities_json")
    try:
        entities = (
            json.loads(raw_entities)
            if isinstance(raw_entities, str) and raw_entities.strip()
            else raw_entities
        )
    except (json.JSONDecodeError, TypeError):
        entities = []
    if not isinstance(entities, list):
        entities = []

    if source.startswith("manual_gold_seed"):
        category = "gold:manual_seed"
    elif "lab" in source or "value" in source or "observ" in source:
        category = "gold:labs"
    elif "referral" in source or "admin" in source:
        category = "gold:referral_admin"
    elif "oncology" in source or "cancer" in source:
        category = "gold:oncology"
    else:
        category = "gold:generic"

    return {
        "category": category,
        "description": (text[:120] + ("..." if len(text) > 120 else "")),
        "input": text,
        "output": entities,
    }


def load_gold_pool_rows(client: Any, limit: int) -> list[dict[str, Any]]:
    """Fetch raw rows from Neo4j -- public so callers can build their own
    selector without going through the cache (used by tests)."""
    safe_limit = max(1, int(limit))
    rows: list[dict[str, Any]] = []
    with client.session() as session:
        result = session.run(READ_GOLD_POOL_FOR_FEW_SHOT, limit=safe_limit)
        for r in result:
            rows.append(dict(r))
    return rows


def _build_selector(rows: Sequence[dict[str, Any]]) -> FewShotSelector:
    """Construct + warm a FewShotSelector from gold rows."""
    examples = [_row_to_example(r) for r in rows]
    selector = FewShotSelector(dynamic_pool=examples)
    try:
        selector.warm()
    except Exception:  # noqa: BLE001
        logger.warning(
            "FewShotSelector warm-up failed; selector will warm lazily",
            exc_info=True,
        )
    return selector


def get_few_shot_selector(client: Any, *, limit: int = 1500) -> FewShotSelector:
    """Return a process-wide cached FewShotSelector backed by gold rows.

    The cache key is the pool size; callers re-running the AI first-pass
    repeatedly within the same process pay the embedding cost only once.
    """
    global _SELECTOR_CACHE, _CACHE_POOL_SIZE

    with _CACHE_LOCK:
        if _SELECTOR_CACHE is not None:
            return _SELECTOR_CACHE
        rows = load_gold_pool_rows(client, limit=limit)
        if not rows:
            logger.warning(
                "Gold pool empty; FewShotSelector will return [] for every query"
            )
        _SELECTOR_CACHE = _build_selector(rows)
        _CACHE_POOL_SIZE = len(rows)
        logger.info(
            "AI first-pass FewShotSelector primed: gold_examples=%d", len(rows)
        )
        return _SELECTOR_CACHE


def invalidate_cache() -> None:
    """Drop the cached selector (next call rebuilds the pool)."""
    global _SELECTOR_CACHE, _CACHE_POOL_SIZE
    with _CACHE_LOCK:
        _SELECTOR_CACHE = None
        _CACHE_POOL_SIZE = 0


def cache_size() -> int:
    """Inspect the cached pool size (for tests / diagnostics)."""
    return _CACHE_POOL_SIZE
