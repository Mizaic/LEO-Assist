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
# An abdomen-only scan (45036003) leaves the pelvis unimaged, so it is
# deliberately not a member.
PELVIC_US_MEMBER_IDS: tuple[str, ...] = (
    "418394000",  # Ultrasound scan of abdomen and pelvis (procedure)
    "24848001",  # Pelvic echography (procedure)
    "426491001",  # Transvaginal ultrasound examination of female genital tract
    "315011000000105",  # Transvaginal ultrasound scan of pelvis (procedure)
    "447801003",  # Endometrium thickened (finding)
)

CA125_FAMILY_ID = "ca125"
CA125_FAMILY_NAME = "Cancer antigen 125 measurement"
# Substance codes (103084007) are not evidence that the test was carried out.
CA125_MEMBER_IDS: tuple[str, ...] = (
    "909121000000107",  # Measurement of cancer antigen 125 in serum specimen
    "408253004",  # CA125 level (procedure)
    # The three approved SurfaceForms for "CA 125" resolve to 80529009,
    # 909121000000107 or 1027511000000100. All three must count, or which
    # one the resolver happens to pick decides whether the test reads as
    # done.
    "80529009",  # CA 125 measurement (procedure)
    "144297009",  # Carbohydrate antigen 125 level (procedure)
    "1000461000000109",  # Serum cancer antigen 125 level (observable entity)
    "1027511000000100",  # Cancer antigen 125 level (observable entity)
    "1106431000000109",  # Arbitrary concentration of CA125 in serum
    "15731000237103",  # Arbitrary concentration of CA125 in serum
    "1106411000000101",  # Arbitrary concentration of CA125 in plasma
    "85821000000108",  # CA125 level
    "106221000000106",  # CA125 level
    "432519008",  # Cancer antigen 125 above reference range (finding)
)

FIT_FAMILY_ID = "fit"
FIT_FAMILY_NAME = "Faecal immunochemical test"
FIT_MEMBER_IDS: tuple[str, ...] = (
    "149421000000109",  # Provision of faecal immunochemical test kit
    "1049361000000101",  # Quantitative faecal immunochemical test (observable)
    "1101361000000103",  # BCSP liquid FIT normal
    "1101371000000105",  # BCSP liquid FIT abnormal
    "1101381000000107",  # BCSP liquid FIT technical failure
    "1101391000000109",  # BCSP liquid FIT sample rejected
)

SHARED_FAMILIES: tuple[dict[str, Any], ...] = (
    {
        "family_id": PELVIC_US_FAMILY_ID,
        "name": PELVIC_US_FAMILY_NAME,
        "members": PELVIC_US_MEMBER_IDS,
    },
    {
        "family_id": CA125_FAMILY_ID,
        "name": CA125_FAMILY_NAME,
        "members": CA125_MEMBER_IDS,
    },
    {
        "family_id": FIT_FAMILY_ID,
        "name": FIT_FAMILY_NAME,
        "members": FIT_MEMBER_IDS,
    },
)


def seed_family_rows() -> list[dict[str, Any]]:
    """Seed definitions in the shape ``FETCH_INVESTIGATION_FAMILIES`` returns.

    This is the authoring source for seeding Neo4j. It is not a runtime
    fallback: the evaluator reads the graph via ``load_family_index``.
    """
    return [
        {"family_id": family["family_id"], "members": list(family["members"])}
        for family in SHARED_FAMILIES
    ]


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
