"""Neo4j-backed per-label precision gate loader.

Atlas trace:
  DO: DO-A35D2D57
  DI: DI-37B3DC71

Wave 5 moves the hand-maintained dict of per-label minimum F1 values out of
``evaluator.py`` and into Neo4j so QA leads can tune gates without editing
code. The evaluator keeps the baked-in defaults as a safety net — if Neo4j is
unreachable or the node type is missing, we fall back to the defaults with a
warning.

Schema (Neo4j)::

    (:PrecisionGate {
        label: "DISORDER",
        min_f1: 0.82,
        active: true,
        rationale: "Safety-critical core coding entity",
        updated_at: datetime(),
        updated_by: "qa-lead-1"
    })

Only ``active=true`` rows are read. Deactivating a row returns the evaluator
to the code-level default for that label without removing audit history.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


_READ_QUERY = """
MATCH (g:PrecisionGate)
WHERE coalesce(g.active, true) = true
RETURN g.label AS label, g.min_f1 AS min_f1
"""


def load_precision_gates_from_neo4j(
    fallback: dict[str, float],
    *,
    session=None,
) -> dict[str, float]:
    """Merge Neo4j overrides on top of the hard-coded fallback dict.

    Args:
        fallback: The baked-in per-label gate dict (e.g. from
            :mod:`services.training_worker.app.evaluator`).
        session: Optional open Neo4j session for testability. When omitted,
            we acquire one from :class:`KnowledgeGraphClient` and close it.

    Returns:
        A new dict containing fallback values plus any overrides from
        ``(:PrecisionGate)`` nodes. When Neo4j is unavailable the fallback
        dict is returned unchanged (with a warning logged).
    """
    merged: dict[str, float] = dict(fallback)
    owned_client = None
    used_session = session
    if used_session is None:
        client = _kg_client()
        if client is None:
            return merged
        owned_client = client
        try:
            used_session = client.session().__enter__()
        except Exception as exc:
            logger.warning("[precision-gates] could not open Neo4j session: %s", exc)
            return merged

    try:
        rows = list(used_session.run(_READ_QUERY))
    except Exception as exc:
        logger.warning("[precision-gates] Neo4j read failed (%s) — using defaults", exc)
        rows = []
    finally:
        if session is None and used_session is not None:
            try:
                used_session.__exit__(None, None, None)
            except Exception:
                pass
            if owned_client is not None:
                try:
                    owned_client.close()
                except Exception:
                    pass

    for row in rows:
        label = str(row.get("label") or "").strip().upper()
        if not label:
            continue
        min_f1 = row.get("min_f1")
        try:
            merged[label] = float(min_f1)
        except (TypeError, ValueError):
            logger.warning(
                "[precision-gates] ignoring non-numeric min_f1 for %r", label
            )
    return merged


def _kg_client() -> Optional[object]:
    try:
        from libs.neo4j_client.client import KnowledgeGraphClient

        return KnowledgeGraphClient()
    except Exception as exc:
        logger.warning(
            "[precision-gates] KnowledgeGraphClient unavailable (%s) — using defaults",
            exc,
        )
        return None
