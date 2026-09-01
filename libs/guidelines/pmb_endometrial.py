"""Apply helper for the NG12 1.5.12 / 1.5.14 PMB pair tree.

Builds a LogicNode for apply_rule_edit. Evaluate must not import this.
Live match shape lives on AppropriatenessRule.logicJson.

Atlas trace: UN-5F3BF083, DI-8BAC9BB3, DO-ABE2AE61, VT-E053BB7C.
"""

from __future__ import annotations

from libs.guidelines.soft_qualifier import SoftQualifierSpec
from services.api.app.services.guidance_rule_edit import (
    LogicCriterion,
    LogicNode,
    LogicSeed,
)

PMB_CONCEPT_ID = "76742009"
POSTMENOPAUSAL_STATE_ID = "76498008"
MENOPAUSE_PRESENT_ID = "289903006"
PV_BLEEDING_ID = "289530006"
HEAVY_PV_BLEED_ID = "315224006"

_PMB_TERM = "Postmenopausal bleeding (finding)"
_STATE_TERM = "Postmenopausal state (finding)"
_MENO_TERM = "Menopause present (finding)"
_BLEED_TERM = "Bleeding from vagina (finding)"
_HEAVY_TERM = "Heavy vaginal bleeding (finding)"
_SOURCE = "unexplained post-menopausal bleeding"


def _soft_unexplained() -> list[SoftQualifierSpec]:
    return [SoftQualifierSpec(kind="unexplained", enforcement="soft")]


def _seed(concept_id: str, term: str) -> LogicSeed:
    return LogicSeed(
        snomed_concept_id=concept_id,
        preferred_term=term,
        semantic_tag="finding",
        include_descendants=False,
    )


def _concept(concept_id: str, term: str, *, source: str | None = None) -> LogicNode:
    node = LogicNode(
        kind="CONCEPT",
        criterion=LogicCriterion(
            snomed_concept_id=concept_id,
            preferred_term=term,
            semantic_tag="finding",
            seeds=[_seed(concept_id, term)],
            primary_concept_id=concept_id,
            soft_qualifiers=_soft_unexplained(),
        ),
    )
    if source:
        node.source_row_text = source
    return node


def _bleed_or() -> LogicNode:
    return LogicNode(
        kind="OR",
        children=[
            _concept(PV_BLEEDING_ID, _BLEED_TERM, source=_SOURCE),
            _concept(HEAVY_PV_BLEED_ID, _HEAVY_TERM, source=_SOURCE),
        ],
    )


def _state_or() -> LogicNode:
    return LogicNode(
        kind="OR",
        children=[
            _concept(POSTMENOPAUSAL_STATE_ID, _STATE_TERM),
            _concept(MENOPAUSE_PRESENT_ID, _MENO_TERM),
        ],
    )


def _pmb_or_pair() -> LogicNode:
    return LogicNode(
        kind="OR",
        children=[
            _concept(PMB_CONCEPT_ID, _PMB_TERM, source=_SOURCE),
            LogicNode(
                kind="AND",
                children=[_state_or(), _bleed_or()],
            ),
        ],
    )


def _sex_female() -> LogicNode:
    return LogicNode(kind="DEMOGRAPHIC", field="sex", operator="=", value="female")


def _age(operator: str, value: str) -> LogicNode:
    return LogicNode(
        kind="DEMOGRAPHIC",
        field="age",
        operator=operator,
        value=value,
        unit="years",
    )


def build_pmb_1_5_12_logic() -> LogicNode:
    """Age 55 and over, female, PMB code or split pair."""
    return LogicNode(
        kind="AND",
        children=[_sex_female(), _age(">=", "55"), _pmb_or_pair()],
    )


def build_pmb_1_5_14_logic() -> LogicNode:
    """Under 55, female, PMB code or split pair."""
    return LogicNode(
        kind="AND",
        children=[_age("<", "55"), _sex_female(), _pmb_or_pair()],
    )
