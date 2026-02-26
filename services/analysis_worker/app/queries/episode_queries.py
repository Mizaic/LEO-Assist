"""Neo4j query helpers for episode building and consolidation.

Ported from VRB clinical-ai/app/agent/tools/neo4j_tools.py (episode CRUD section).
Adapted to use PCA's PatientGraphClient instead of VRB's singleton Neo4jClient.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)


def _default_client() -> PatientGraphClient:
    return PatientGraphClient()


# ── Encounter queries ────────────────────────────────────────────────────


def get_encounters_by_timeframe(
    patient_id: str,
    start_date: str,
    end_date: str,
    client: Optional[PatientGraphClient] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    c = client or _default_client()
    return c.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
        "WHERE toString(p.id) = $pid "
        "  AND toString(e.date) >= $start AND toString(e.date) <= $end "
        "RETURN e.id AS encounter_id, toString(e.date) AS encounter_date, "
        "       coalesce(e.text, e.flags) AS encounter_text "
        "ORDER BY e.date ASC LIMIT $limit",
        pid=patient_id, start=start_date, end=end_date, limit=limit,
    )


def get_encounters_with_codes(
    patient_id: str,
    start_date: str,
    end_date: str,
    client: Optional[PatientGraphClient] = None,
    domains: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    c = client or _default_client()
    domain_filter = "AND r.domain IN $domains" if domains else ""
    params: Dict[str, Any] = {
        "pid": patient_id, "start": start_date, "end": end_date,
    }
    if domains:
        params["domains"] = domains

    return c.run(
        f"MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
        f"WHERE toString(p.id) = $pid "
        f"  AND e.date IS NOT NULL "
        f"  AND toString(e.date) >= $start AND toString(e.date) <= $end "
        f"OPTIONAL MATCH (e)-[r:DOCUMENTS]->(concept) "
        f"{domain_filter} "
        f"WITH e, collect(CASE WHEN concept IS NOT NULL THEN {{ "
        f"    concept_id: concept.conceptId, name: concept.name, "
        f"    semantic_tag: concept.semanticTag, domain: r.domain, "
        f"    confidence: r.confidence, context: r.context, "
        f"    is_negated: r.is_negated, source: r.source "
        f"}} ELSE null END) AS codes "
        f"RETURN e.id AS encounter_id, toString(e.date) AS encounter_date, "
        f"       coalesce(e.text, e.flags) AS encounter_text, "
        f"       [c IN codes WHERE c IS NOT NULL] AS coded_concepts "
        f"ORDER BY e.date ASC",
        **params,
    )


def get_encounter_full_text(
    encounter_id: str,
    client: Optional[PatientGraphClient] = None,
    include_same_day: bool = True,
) -> Dict[str, Any]:
    c = client or _default_client()
    rows = c.run(
        "MATCH (e:Encounter {id: $eid}) "
        "OPTIONAL MATCH (e)<-[:HAS_ENCOUNTER]-(p:Patient) "
        "OPTIONAL MATCH (e)-[r:IS_PART_OF]->(ep:CancerEpisode) "
        "RETURN e.id AS encounter_id, toString(e.date) AS encounter_date, "
        "       coalesce(e.text, e.flags) AS encounter_text, "
        "       toString(p.id) AS patient_id, ep.episode_id AS episode_id, "
        "       r.milestone_type AS milestone_type",
        eid=encounter_id,
    )
    if not rows:
        return {"error": f"Encounter {encounter_id} not found"}

    result = rows[0]
    if include_same_day and result.get("patient_id") and result.get("encounter_date"):
        date_str = str(result["encounter_date"])[:10]
        same_day = c.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "  AND toString(e.date) STARTS WITH $prefix AND e.id <> $eid "
            "RETURN e.id AS encounter_id, toString(e.date) AS encounter_date, "
            "       coalesce(e.text, e.flags) AS encounter_text "
            "ORDER BY e.date",
            pid=result["patient_id"], prefix=date_str, eid=encounter_id,
        )
        result["same_day_encounters"] = same_day
    return result


# ── Episode CRUD ─────────────────────────────────────────────────────────


def create_episode(
    patient_id: str,
    cancer_type: str,
    referral_encounter_id: str,
    referral_date: str,
    client: Optional[PatientGraphClient] = None,
) -> Dict[str, Any]:
    c = client or _default_client()
    safe_type = cancer_type.upper().replace(" ", "_")[:20]
    episode_id = f"EP_{safe_type}_{referral_date[:4]}_{uuid4().hex[:8]}"

    rows = c.run(
        "MATCH (p:Patient) WHERE toString(p.id) = $pid "
        "MATCH (e:Encounter {id: $ref_id}) "
        "CREATE (ep:CancerEpisode { "
        "    episode_id: $eid, patient_id: $pid, cancer_type: $ct, "
        "    referral_date: $rd, first_encounter_date: $rd, "
        "    last_encounter_date: $rd, status: 'building', "
        "    needs_review: false, created_at: datetime(), "
        "    created_by: 'episode_builder' "
        "}) "
        "CREATE (p)-[:HAS_EPISODE]->(ep) "
        "MERGE (e)-[r:IS_PART_OF]->(ep) "
        "ON CREATE SET r.milestone_type = 'referral', "
        "              r.is_first_of_type = true, "
        "              r.linked_by = 'episode_builder', "
        "              r.linked_at = datetime() "
        "RETURN ep.episode_id AS episode_id, ep.status AS status, "
        "       ep.referral_date AS referral_date",
        pid=patient_id, ref_id=referral_encounter_id, eid=episode_id,
        ct=cancer_type, rd=referral_date,
    )
    return rows[0] if rows else {"error": "Failed to create episode"}


def link_encounter_to_episode(
    encounter_id: str,
    episode_id: str,
    milestone_type: Optional[str] = None,
    reason: Optional[str] = None,
    client: Optional[PatientGraphClient] = None,
) -> Dict[str, Any]:
    c = client or _default_client()
    rows = c.run(
        "MATCH (ep:CancerEpisode {episode_id: $epid}) "
        "MATCH (e:Encounter {id: $eid}) "
        "MERGE (e)-[r:IS_PART_OF]->(ep) "
        "ON CREATE SET r.milestone_type = $mt, r.agent_reasoning = $reason, "
        "              r.linked_by = 'episode_builder', r.linked_at = datetime() "
        "ON MATCH SET r.milestone_type = CASE WHEN $mt IS NOT NULL THEN $mt ELSE r.milestone_type END, "
        "             r.agent_reasoning = CASE WHEN $reason IS NOT NULL THEN $reason ELSE r.agent_reasoning END "
        "WITH e, ep, r "
        "OPTIONAL MATCH (other:Encounter)-[o:IS_PART_OF]->(ep) "
        "  WHERE o.milestone_type = r.milestone_type AND other <> e "
        "WITH e, ep, r, count(other) AS prior_count "
        "SET r.is_first_of_type = (prior_count = 0), "
        "    ep.first_encounter_date = CASE "
        "      WHEN ep.first_encounter_date IS NULL OR toString(e.date) < ep.first_encounter_date "
        "      THEN toString(e.date) ELSE ep.first_encounter_date END, "
        "    ep.last_encounter_date = CASE "
        "      WHEN ep.last_encounter_date IS NULL OR toString(e.date) > ep.last_encounter_date "
        "      THEN toString(e.date) ELSE ep.last_encounter_date END "
        "RETURN e.id AS encounter_id, ep.episode_id AS episode_id, r.milestone_type AS milestone_type",
        eid=encounter_id, epid=episode_id, mt=milestone_type, reason=reason,
    )
    return rows[0] if rows else {"error": "Failed to link encounter"}


def complete_episode(
    episode_id: str,
    status: str,
    confidence: int,
    reasoning: str,
    milestones: Optional[Dict[str, str]] = None,
    client: Optional[PatientGraphClient] = None,
) -> Dict[str, Any]:
    c = client or _default_client()
    milestone_sets = ""
    params: Dict[str, Any] = {
        "eid": episode_id, "status": status,
        "confidence": confidence, "reasoning": reasoning,
    }
    if milestones:
        for key, value in milestones.items():
            safe_key = key.replace("-", "_")
            milestone_sets += f", ep.{safe_key}_date = ${safe_key}_date"
            params[f"{safe_key}_date"] = value

    needs_review = status == "inconclusive" or confidence < 70
    review_reason = ""
    if status == "inconclusive":
        review_reason = "Episode status inconclusive"
    elif confidence < 70:
        review_reason = f"Low confidence ({confidence}%)"

    params["needs_review"] = needs_review
    params["review_reason"] = review_reason

    rows = c.run(
        f"MATCH (ep:CancerEpisode {{episode_id: $eid}}) "
        f"SET ep.status = $status, ep.agent_confidence = $confidence, "
        f"    ep.agent_reasoning = $reasoning, ep.needs_review = $needs_review, "
        f"    ep.review_reason = $review_reason, "
        f"    ep.completed_by = 'episode_builder', ep.completed_at = datetime(), "
        f"    ep.status_updated_at = datetime(){milestone_sets} "
        f"RETURN ep.episode_id AS episode_id, ep.status AS status, "
        f"       ep.agent_confidence AS confidence, ep.needs_review AS needs_review",
        **params,
    )
    return rows[0] if rows else {"error": "Failed to complete episode"}


def get_episode_place_of_presentation(
    episode_id: str,
    client: Optional[PatientGraphClient] = None,
) -> Optional[str]:
    c = client or _default_client()
    rows = c.run(
        "MATCH (e:Encounter)-[r:IS_PART_OF]->(ep:CancerEpisode {episode_id: $eid}) "
        "WHERE r.milestone_type = 'first_presentation' "
        "MATCH (e)-[rc:DOCUMENTS]->(concept) "
        "WHERE rc.domain = 'place_of_presentation' "
        "  AND (rc.is_negated IS NULL OR rc.is_negated = false) "
        "RETURN concept.name AS place ORDER BY rc.confidence DESC LIMIT 1",
        eid=episode_id,
    )
    return rows[0]["place"] if rows else None


def set_episode_ncda_fields(
    episode_id: str,
    referral_route: Optional[str] = None,
    place_of_presentation: Optional[str] = None,
    safety_netting_recorded: Optional[bool] = None,
    client: Optional[PatientGraphClient] = None,
) -> None:
    c = client or _default_client()
    sets: List[str] = []
    params: Dict[str, Any] = {"eid": episode_id}
    if referral_route is not None:
        sets.append("ep.referral_route = $rr")
        params["rr"] = referral_route
    if place_of_presentation is not None:
        sets.append("ep.place_of_presentation = $pop")
        params["pop"] = place_of_presentation
    if safety_netting_recorded is not None:
        sets.append("ep.safety_netting_recorded = $snr")
        params["snr"] = safety_netting_recorded
    if not sets:
        return
    c.run(
        f"MATCH (ep:CancerEpisode {{episode_id: $eid}}) SET {', '.join(sets)}",
        **params,
    )


def get_earliest_episode_milestone_dates(
    episode_id: str,
    milestone_types: Optional[List[str]] = None,
    client: Optional[PatientGraphClient] = None,
) -> Dict[str, str]:
    c = client or _default_client()
    if milestone_types is None:
        milestone_types = ["treatment", "diagnosis"]
    rows = c.run(
        "MATCH (e:Encounter)-[r:IS_PART_OF]->(ep:CancerEpisode {episode_id: $eid}) "
        "WHERE r.milestone_type IN $types "
        "RETURN r.milestone_type AS milestone_type, toString(min(e.date)) AS earliest_date",
        eid=episode_id, types=milestone_types,
    )
    return {
        row["milestone_type"]: str(row["earliest_date"])[:10]
        for row in rows if row.get("earliest_date")
    }


def merge_episodes(
    primary_id: str,
    secondary_ids: List[str],
    reasoning: str,
    original_referral_types: List[str],
    client: Optional[PatientGraphClient] = None,
) -> Dict[str, Any]:
    """Merge secondary episodes into the primary.

    Moves IS_PART_OF edges, marks secondaries as 'merged',
    updates the primary with metadata and earliest referral_date.
    """
    c = client or _default_client()

    c.run(
        "UNWIND $sids AS sec_id "
        "MATCH (enc:Encounter)-[r:IS_PART_OF]->(sec:CancerEpisode {episode_id: sec_id}) "
        "MATCH (primary:CancerEpisode {episode_id: $pid}) "
        "MERGE (enc)-[r2:IS_PART_OF]->(primary) "
        "ON CREATE SET r2.milestone_type = r.milestone_type, "
        "              r2.agent_reasoning = 'Merged from ' + sec_id, "
        "              r2.linked_by = 'episode_consolidator', r2.linked_at = datetime() "
        "DELETE r",
        pid=primary_id, sids=secondary_ids,
    )

    c.run(
        "UNWIND $sids AS sec_id "
        "MATCH (ep:CancerEpisode {episode_id: sec_id}) "
        "SET ep.status = 'merged', ep.merged_into = $pid, "
        "    ep.merged_at = datetime(), ep.merge_reasoning = $reasoning, "
        "    ep.needs_review = false, ep.status_updated_at = datetime()",
        pid=primary_id, sids=secondary_ids, reasoning=reasoning,
    )

    result = c.run(
        "MATCH (primary:CancerEpisode {episode_id: $pid}) "
        "OPTIONAL MATCH (enc:Encounter)-[:IS_PART_OF]->(primary) "
        "WITH primary, min(toString(enc.date)) AS earliest, max(toString(enc.date)) AS latest "
        "SET primary.first_encounter_date = earliest, "
        "    primary.last_encounter_date = latest, "
        "    primary.merged_from = $sids, "
        "    primary.original_referral_types = $rt, "
        "    primary.consolidation_reasoning = $reasoning, "
        "    primary.consolidated_at = datetime() "
        "RETURN primary.episode_id AS episode_id, "
        "       primary.referral_date AS referral_date, "
        "       primary.first_encounter_date AS first_date, "
        "       primary.last_encounter_date AS last_date",
        pid=primary_id, sids=secondary_ids, rt=original_referral_types, reasoning=reasoning,
    )

    c.run(
        "MATCH (primary:CancerEpisode {episode_id: $pid}) "
        "UNWIND $sids AS sec_id "
        "MATCH (sec:CancerEpisode {episode_id: sec_id}) "
        "WITH primary, min(sec.referral_date) AS earliest_sec "
        "WITH primary, CASE WHEN earliest_sec < primary.referral_date "
        "  THEN earliest_sec ELSE primary.referral_date END AS new_ref "
        "SET primary.referral_date = new_ref",
        pid=primary_id, sids=secondary_ids,
    )

    merged = result[0] if result else {}
    logger.info("Merged %d episodes into %s: %s",
                len(secondary_ids), primary_id, ", ".join(secondary_ids))
    return merged


def get_episode_summary(
    episode_id: str,
    client: Optional[PatientGraphClient] = None,
) -> Optional[Dict[str, Any]]:
    c = client or _default_client()
    rows = c.run(
        "MATCH (ep:CancerEpisode {episode_id: $eid}) "
        "RETURN ep.episode_id AS episode_id, ep.cancer_type AS cancer_type, "
        "       ep.status AS status, ep.agent_confidence AS confidence, "
        "       ep.agent_reasoning AS reasoning, "
        "       toString(ep.referral_date) AS referral_date",
        eid=episode_id,
    )
    return rows[0] if rows else None
