"""Hardcoded scope types for tenant filtering.

Prevents tenant leakage by only allowing these three scope types.
No arbitrary scope params; new scope types require code change.
"""

from __future__ import annotations

SCOPE_TYPES = ("gp", "icb", "alliance")

SCOPE_PARAM_MAP = {
    "gp": "practiceOdsCode",
    "icb": "icbOdsCode",
    "alliance": "allianceOdsCode",
}

# Cypher scope filter fragments (to be prepended to MATCH for Patient)
# Each returns the pattern from Patient to the scoped org node.
# GP scope matches GPPractice or Organization (both can have odsCode; graph may use either).
SCOPE_CYPHER_FRAGMENTS = {
    "gp": "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp) WHERE (gp:GPPractice OR gp:Organization) AND gp.odsCode = $practiceOdsCode",
    "icb": "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp:GPPractice)-[:COMMISSIONED_BY]->(icb:ICB {odsCode: $icbOdsCode})",
    "alliance": "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp:GPPractice)-[:COMMISSIONED_BY]->(icb:ICB)-[:PART_OF_ALLIANCE]->(ca:CancerAlliance {odsCode: $allianceOdsCode})",
}


def get_scope_param(scope_type: str) -> str | None:
    """Return the Cypher param name for the given scope type."""
    return SCOPE_PARAM_MAP.get(scope_type)


def get_scope_cypher_fragment(scope_type: str) -> str | None:
    """Return the Cypher MATCH fragment for the given scope type."""
    return SCOPE_CYPHER_FRAGMENTS.get(scope_type)
