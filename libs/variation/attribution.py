"""Root cause attribution for flagged variation episodes.

Atlas trace: DO-64B006B5 (see libs/variation/__init__.py).

Given a flagged EpisodeOfCare's first divergence step, walk the patient's
referral graph to identify the most likely root-cause node (GPPractice or
Organization). This is NOT a causal claim -- it names the structural node
most associated with the divergence so the reviewer has a concrete entity
to investigate.

Implementation note: the MVP attribution runs Cypher against the primary
graph (not the pe-referral-network GDS projection) so attribution is
cheap per-episode and does not require a separate persist pass. If sites
accumulate enough referral volume to make on-demand ranking slow, we can
add a nightly job that writes gds_pagerank onto GPPractice nodes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from libs.neo4j_client.client import PatientGraphClient


_REFERRAL_STAGE_TOKENS = ("referral", "first_seen")


_ATTRIBUTION_CYPHER = """
MATCH (p:Patient {id: $patient_id})
OPTIONAL MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp:GPPractice)
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
OPTIONAL MATCH (e)-[:RECORDED_AT]->(gp2:GPPractice)
WITH coalesce(gp, gp2) AS practice, p
OPTIONAL MATCH (practice)-[:COMMISSIONED_BY|REFERRED_TO]->(org:Organization)
WITH practice, org, count(*) AS weight
ORDER BY weight DESC
RETURN practice.id   AS practice_id,
       practice.name AS practice_name,
       org.id        AS organisation_id,
       org.name      AS organisation_name,
       weight        AS edge_weight
LIMIT 1
"""


@dataclass
class AttributionResult:
    """Best-guess root cause node for a flagged episode."""

    node_type: str
    node_id: str
    node_name: str
    edge_weight: int = 0


def _is_referral_stage(first_divergence: Optional[str]) -> bool:
    if not first_divergence:
        return False
    lower = first_divergence.lower()
    return any(token in lower for token in _REFERRAL_STAGE_TOKENS)


def attribute_root_cause(
    client: PatientGraphClient,
    patient_id: str,
    first_divergence: Optional[str],
) -> Optional[AttributionResult]:
    """Return the best-guess root cause node, or None when attribution
    is inappropriate.

    Attribution only runs when the first divergence is a referral-stage
    step -- later divergences (diagnostic, treatment) cannot be blamed
    on the referring GP or receiving organisation.
    """
    if not _is_referral_stage(first_divergence):
        return None
    rows = client.run(_ATTRIBUTION_CYPHER, patient_id=patient_id)
    if not rows:
        return None
    row = rows[0]
    if row.get("organisation_id"):
        return AttributionResult(
            node_type="Organization",
            node_id=str(row["organisation_id"]),
            node_name=str(row.get("organisation_name") or ""),
            edge_weight=int(row.get("edge_weight") or 0),
        )
    if row.get("practice_id"):
        return AttributionResult(
            node_type="GPPractice",
            node_id=str(row["practice_id"]),
            node_name=str(row.get("practice_name") or ""),
            edge_weight=int(row.get("edge_weight") or 0),
        )
    return None
