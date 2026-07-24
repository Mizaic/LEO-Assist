"""Prior SNOMED resolution lookup for the concept-mapping nudge.

Atlas trace:
  DO: DO-77A48DBC
  DI: DI-4746A178, DI-B7FEA996, DI-F8634363
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-77A48DBC")

"Has this free-text phrase already been coded elsewhere in the rule
library, and to which SNOMED concept(s)?" -- surfaced in
ConceptSearchPanel as a soft nudge only (a suggested default, never an
auto-applied pick), per the highlight-to-build wizard plan's rubber-
stamping-risk discussion: propagating a code change across rules
silently is exactly the failure mode being designed against here.
"""

from __future__ import annotations

from libs.cypher.terminology_queries import RULES_WITH_LOGIC_JSON_CONTAINING_TERM
from libs.guidance.logic_tree_terms import (
    concept_terms,
    normalise_concept_term,
    parse_logic_json,
    walk_concept_criteria,
)
from libs.neo4j_client.client import KnowledgeGraphClient

_SCAN_LIMIT = 500


def find_prior_concept_resolutions(term: str, limit: int = 5) -> list[dict]:
    """Rank SNOMED concepts this ``term`` has already been coded as.

    Returns at most ``limit`` entries, shaped like
    ``{snomed_concept_id, preferred_term, semantic_tag, count}``,
    ordered by how many rules in the library used that exact concept
    for this phrase (most-used first). Returns ``[]`` for an empty
    term or when nothing in the library matches.
    """
    normalised = normalise_concept_term(term)
    if not normalised:
        return []
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            RULES_WITH_LOGIC_JSON_CONTAINING_TERM,
            term=normalised,
            scan_limit=_SCAN_LIMIT,
        )
    finally:
        client.close()
    counts = _count_matching_concepts(rows, normalised)
    ranked = sorted(counts.values(), key=lambda c: c["count"], reverse=True)
    return ranked[:limit]


def _count_matching_concepts(rows: list[dict], normalised_term: str) -> dict[str, dict]:
    counts: dict[str, dict] = {}
    for row in rows:
        tree = parse_logic_json(row.get("logic_json"))
        if not tree:
            continue
        for criterion in walk_concept_criteria(tree):
            if normalised_term in concept_terms(criterion):
                _accumulate(counts, criterion)
    return counts


def _accumulate(counts: dict[str, dict], criterion: dict) -> None:
    concept_id = str(criterion["snomed_concept_id"])
    entry = counts.setdefault(
        concept_id,
        {
            "snomed_concept_id": concept_id,
            "preferred_term": criterion.get("preferred_term")
            or criterion.get("term")
            or concept_id,
            "semantic_tag": criterion.get("semantic_tag"),
            "count": 0,
        },
    )
    entry["count"] += 1
