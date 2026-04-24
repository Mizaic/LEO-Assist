"""Write variation verdicts back onto EpisodeOfCare nodes.

Atlas trace: DO-64B006B5 (see libs/variation/__init__.py).

Writes are idempotent: re-running overwrites the prior verdict and bumps
variation_updated. The writer ONLY runs when score_episode returned a
non-None VariationResult; callers that receive None MUST NOT call this
function. That keeps the sample-size gate (R-31217EFA mitigation) intact.
"""

from __future__ import annotations

from typing import Optional

from libs.neo4j_client.client import PatientGraphClient
from libs.variation.attribution import AttributionResult
from libs.variation.scorer import VariationResult


_WRITE_CYPHER = """
MATCH (ep:EpisodeOfCare {id: $episode_id})
SET ep.variation_flag = $variation_flag,
    ep.variation_score = $variation_score,
    ep.variation_first_divergence = $first_divergence,
    ep.variation_outlier_steps = $outlier_steps,
    ep.variation_community_id = $community_id,
    ep.variation_compared_pairs = $compared_pairs,
    ep.variation_observed_pairs = $observed_pairs,
    ep.variation_updated = datetime()
RETURN ep.id AS id
"""


def write_variation_result(
    client: PatientGraphClient,
    result: VariationResult,
) -> bool:
    """Persist a VariationResult to its EpisodeOfCare node.

    Returns True when the node was matched and updated, False otherwise.
    """
    rows = client.run(
        _WRITE_CYPHER,
        episode_id=result.episode_id,
        variation_flag=bool(result.variation_flag),
        variation_score=float(result.variation_score),
        first_divergence=result.first_divergence,
        outlier_steps=list(result.outlier_steps),
        community_id=int(result.community_id),
        compared_pairs=int(result.compared_pairs),
        observed_pairs=int(result.observed_pairs),
    )
    return bool(rows)


_ATTRIBUTION_WRITE_CYPHER = """
MATCH (ep:EpisodeOfCare {id: $episode_id})
SET ep.variation_attributed_node_type = $node_type,
    ep.variation_attributed_node_id   = $node_id,
    ep.variation_attributed_node_name = $node_name,
    ep.variation_updated              = datetime()
RETURN ep.id AS id
"""


def write_attribution_result(
    client: PatientGraphClient,
    episode_id: str,
    attribution: Optional[AttributionResult],
) -> bool:
    """Persist an AttributionResult to its EpisodeOfCare node.

    No-op (returns False) when attribution is None so the caller can
    treat non-attributable cases uniformly.
    """
    if attribution is None:
        return False
    rows = client.run(
        _ATTRIBUTION_WRITE_CYPHER,
        episode_id=episode_id,
        node_type=attribution.node_type,
        node_id=attribution.node_id,
        node_name=attribution.node_name,
    )
    return bool(rows)
