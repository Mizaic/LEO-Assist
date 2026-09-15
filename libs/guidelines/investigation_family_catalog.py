"""Load shared InvestigationFamily rows from the knowledge graph.

Atlas trace:
  DI: DI-B3B44F09
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B3B44F09")
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)

FETCH_INVESTIGATION_FAMILIES = """
MATCH (f:InvestigationFamily {status: 'active'})-[:INCLUDES]->(member)
WITH f, collect(DISTINCT toString(coalesce(member.id, member.conceptId))) AS members
WHERE size(members) > 0
RETURN f.id AS family_id, members
"""

SEED_INVESTIGATION_FAMILY = """
MERGE (f:InvestigationFamily {id: $family_id})
SET f.name = $name, f.status = 'active'
WITH f
UNWIND $member_ids AS cid
MATCH (c:Concept {id: cid})
MERGE (f)-[:INCLUDES]->(c)
RETURN f.id AS family_id, count(c) AS linked
"""

PELVIC_US_FAMILY_ID = "pelvic-us"
PELVIC_US_FAMILY_NAME = "Pelvic ultrasound"
PELVIC_US_MEMBER_IDS: tuple[str, ...] = (
    "418394000",
    "24848001",
    "426491001",
    "447801003",
)


def index_family_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    """Map each member id to every id in its family."""
    index: dict[str, set[str]] = {}
    for row in rows:
        members = {
            str(item).strip()
            for item in (row.get("members") or [])
            if str(item).strip()
        }
        for concept_id in members:
            index.setdefault(concept_id, set()).update(members)
    return index


def family_ids_for_concept(
    concept_id: str,
    families: Mapping[str, set[str]] | None,
) -> set[str]:
    """Return family members for this concept, or empty when unknown."""
    cid = str(concept_id or "").strip()
    if not cid or not families:
        return set()
    return set(families.get(cid) or ())


def seed_investigation_family(
    runner: Any,
    *,
    family_id: str,
    name: str,
    member_ids: Iterable[str],
) -> list[Any]:
    """MERGE one family and INCLUDES edges to existing Concept nodes."""
    return list(
        runner.run(
            SEED_INVESTIGATION_FAMILY,
            family_id=family_id,
            name=name,
            member_ids=[str(item).strip() for item in member_ids if str(item).strip()],
        )
    )


def load_family_index(session: Any) -> dict[str, set[str]]:
    """Read active InvestigationFamily nodes. Empty on any lookup failure."""
    if session is None:
        return {}
    try:
        rows = list(session.run(FETCH_INVESTIGATION_FAMILIES))
    except Exception:
        logger.warning("InvestigationFamily lookup failed", exc_info=True)
        return {}
    parsed: list[dict[str, Any]] = []
    for row in rows:
        parsed.append(dict(row) if not isinstance(row, dict) else row)
    return index_family_rows(parsed)
