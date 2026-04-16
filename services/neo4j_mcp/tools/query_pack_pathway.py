"""Pathway flow and efficiency query tools."""

from __future__ import annotations

from services.neo4j_mcp.tools.query_pack_common import _result, run_patient


def dq_missing_milestone_chains(limit: int = 200) -> dict:
    rows = run_patient(
        """
        MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
        OPTIONAL MATCH (:Encounter)-[r:IS_PART_OF]->(ep)
        WITH p, ep,
             collect(DISTINCT toLower(coalesce(r.milestone_type, ''))) AS milestone_types
        WITH p, ep, milestone_types,
             size([m IN ['presentation', 'referral', 'diagnosis', 'treatment']
               WHERE any(x IN milestone_types WHERE x CONTAINS m)]) AS matched_required
        WHERE matched_required < 3
        RETURN toString(p.id) AS patient_id,
               coalesce(toString(ep.episode_id), 'unknown') AS episode_id,
               milestone_types,
               matched_required
        ORDER BY matched_required ASC, patient_id
        LIMIT $limit
        """,
        limit=limit,
    )
    return _result(
        "dq_missing_milestone_chains",
        "pathway",
        f"Found {len(rows)} episodes with incomplete milestone chains.",
        rows,
    )


def dq_outlier_stage_delays(
    max_referral_to_diagnosis_days: int = 62,
    max_diagnosis_to_treatment_days: int = 31,
    limit: int = 200,
) -> dict:
    rows = run_patient(
        """
        MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
        OPTIONAL MATCH (e1:Encounter)-[r1:IS_PART_OF]->(ep)
          WHERE toLower(coalesce(r1.milestone_type, '')) CONTAINS 'referral'
        OPTIONAL MATCH (e2:Encounter)-[r2:IS_PART_OF]->(ep)
          WHERE toLower(coalesce(r2.milestone_type, '')) CONTAINS 'diagnos'
        OPTIONAL MATCH (e3:Encounter)-[r3:IS_PART_OF]->(ep)
          WHERE toLower(coalesce(r3.milestone_type, '')) CONTAINS 'treat'
        WITH p, ep,
             min(date(substring(toString(e1.date), 0, 10))) AS referral_date,
             min(date(substring(toString(e2.date), 0, 10))) AS diagnosis_date,
             min(date(substring(toString(e3.date), 0, 10))) AS treatment_date
        WITH p, ep, referral_date, diagnosis_date, treatment_date,
             CASE WHEN referral_date IS NOT NULL AND diagnosis_date IS NOT NULL
               THEN duration.inDays(referral_date, diagnosis_date).days ELSE NULL END AS referral_to_diagnosis_days,
             CASE WHEN diagnosis_date IS NOT NULL AND treatment_date IS NOT NULL
               THEN duration.inDays(diagnosis_date, treatment_date).days ELSE NULL END AS diagnosis_to_treatment_days
        WHERE coalesce(referral_to_diagnosis_days, 0) > $max_referral_to_diagnosis_days
           OR coalesce(diagnosis_to_treatment_days, 0) > $max_diagnosis_to_treatment_days
        RETURN toString(p.id) AS patient_id,
               coalesce(toString(ep.episode_id), 'unknown') AS episode_id,
               referral_to_diagnosis_days,
               diagnosis_to_treatment_days
        ORDER BY coalesce(referral_to_diagnosis_days, 0) DESC,
                 coalesce(diagnosis_to_treatment_days, 0) DESC
        LIMIT $limit
        """,
        max_referral_to_diagnosis_days=max_referral_to_diagnosis_days,
        max_diagnosis_to_treatment_days=max_diagnosis_to_treatment_days,
        limit=limit,
    )
    return _result(
        "dq_outlier_stage_delays",
        "pathway",
        f"Found {len(rows)} episodes breaching stage delay thresholds.",
        rows,
    )


def dq_looping_pathways(repeat_threshold: int = 3, limit: int = 200) -> dict:
    rows = run_patient(
        """
        MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
        MATCH (:Encounter)-[r:IS_PART_OF]->(ep)
        WITH p, ep, toLower(coalesce(r.milestone_type, 'unknown')) AS milestone_type, count(*) AS repeat_count
        WHERE repeat_count >= $repeat_threshold
        RETURN toString(p.id) AS patient_id,
               coalesce(toString(ep.episode_id), 'unknown') AS episode_id,
               milestone_type,
               repeat_count
        ORDER BY repeat_count DESC, patient_id
        LIMIT $limit
        """,
        repeat_threshold=repeat_threshold,
        limit=limit,
    )
    return _result(
        "dq_looping_pathways",
        "pathway",
        f"Found {len(rows)} episode milestone loops at or above threshold.",
        rows,
    )


def dq_orphan_coded_encounters(limit: int = 500) -> dict:
    rows = run_patient(
        """
        MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->()
        WHERE NOT EXISTS { MATCH (e)-[:IS_PART_OF]->(:EpisodeOfCare) }
        RETURN toString(p.id) AS patient_id,
               toString(e.id) AS encounter_id,
               toString(e.date) AS encounter_date
        ORDER BY encounter_date DESC
        LIMIT $limit
        """,
        limit=limit,
    )
    return _result(
        "dq_orphan_coded_encounters",
        "pathway",
        f"Found {len(rows)} coded encounters not linked to an episode.",
        rows,
    )


TOOLS = [
    {
        "name": "dq_missing_milestone_chains",
        "description": "Pathway audit: episodes with missing milestone chains.",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 200}}},
        "fn": dq_missing_milestone_chains,
    },
    {
        "name": "dq_outlier_stage_delays",
        "description": "Pathway audit: episodes breaching referral/diagnosis/treatment delay thresholds.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_referral_to_diagnosis_days": {"type": "integer", "default": 62},
                "max_diagnosis_to_treatment_days": {"type": "integer", "default": 31},
                "limit": {"type": "integer", "default": 200},
            },
        },
        "fn": dq_outlier_stage_delays,
    },
    {
        "name": "dq_looping_pathways",
        "description": "Pathway audit: repeated milestone loops in episodes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repeat_threshold": {"type": "integer", "default": 3},
                "limit": {"type": "integer", "default": 200},
            },
        },
        "fn": dq_looping_pathways,
    },
    {
        "name": "dq_orphan_coded_encounters",
        "description": "Pathway audit: coded encounters missing episode links.",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 500}}},
        "fn": dq_orphan_coded_encounters,
    },
]

