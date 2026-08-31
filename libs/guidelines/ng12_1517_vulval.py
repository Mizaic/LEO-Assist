"""Apply helper for the NG12 1.5.17 vulval OR tree.

Builds a LogicNode for apply_rule_edit. Evaluate must not import this.
Live match shape lives on AppropriatenessRule.logicJson.

NICE is lump or ulceration or bleeding. Swelling of vulva is the
lump-like code Sherwood letters use when they do not say mass.

Atlas trace: UN-5F3BF083, DI-8BAC9BB3, DO-62FE139E, VT-766B13F8.
"""

from __future__ import annotations

from services.api.app.services.guidance_rule_edit import (
    LogicCriterion,
    LogicNode,
    LogicSeed,
)

VULVAL_MASS_ID = "289477004"
VULVAL_SWELLING_ID = "289475007"
VULVAL_ULCER_ID = "68640004"
GENITAL_BLEED_ID = "890094005"

_MASS_TERM = "Mass of vulva (finding)"
_SWELL_TERM = "Swelling of vulva (finding)"
_ULCER_TERM = "Ulceration of vulva (disorder)"
_BLEED_TERM = "Bleeding from genital region (finding)"


def _seed(concept_id: str, term: str, tag: str) -> LogicSeed:
    return LogicSeed(
        snomed_concept_id=concept_id,
        preferred_term=term,
        semantic_tag=tag,
        include_descendants=False,
    )


def _concept(concept_id: str, term: str, tag: str, source: str) -> LogicNode:
    return LogicNode(
        kind="CONCEPT",
        criterion=LogicCriterion(
            snomed_concept_id=concept_id,
            preferred_term=term,
            semantic_tag=tag,
            seeds=[_seed(concept_id, term, tag)],
            primary_concept_id=concept_id,
        ),
        source_row_text=source,
    )


def build_vulval_1_5_17_logic() -> LogicNode:
    """Female, then lump or swelling or ulcer or genital bleed."""
    return LogicNode(
        kind="AND",
        children=[
            LogicNode(kind="DEMOGRAPHIC", field="sex", operator="=", value="female"),
            LogicNode(
                kind="OR",
                children=[
                    _concept(VULVAL_MASS_ID, _MASS_TERM, "finding", "vulval lump,"),
                    _concept(
                        VULVAL_SWELLING_ID,
                        _SWELL_TERM,
                        "finding",
                        "significant swelling",
                    ),
                    _concept(VULVAL_ULCER_ID, _ULCER_TERM, "disorder", "ulceration"),
                    _concept(GENITAL_BLEED_ID, _BLEED_TERM, "finding", "bleeding."),
                ],
            ),
        ],
    )
