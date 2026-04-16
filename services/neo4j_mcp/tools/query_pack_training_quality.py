"""Training quality and writeback effectiveness query tools."""

from __future__ import annotations

from services.neo4j_mcp.tools.query_pack_common import _result, run_knowledge


def dq_training_candidate_pipeline_health() -> dict:
    rows = run_knowledge(
        """
        MATCH (c:TrainingCandidate)
        RETURN c.status AS status,
               count(*) AS count,
               min(toString(c.updated_at)) AS earliest_updated_at,
               max(toString(c.updated_at)) AS latest_updated_at
        ORDER BY count DESC
        """
    )
    return _result(
        "dq_training_candidate_pipeline_health",
        "training",
        "Computed TrainingCandidate queue health by status.",
        rows,
    )


def dq_gold_label_conflicts(limit: int = 200) -> dict:
    rows = run_knowledge(
        """
        MATCH (g:GoldLabel)
        WHERE g.text IS NOT NULL AND trim(g.text) <> ''
        WITH toLower(trim(g.text)) AS phrase,
             collect(DISTINCT toLower(coalesce(g.entities_json, ''))) AS entity_payloads,
             count(*) AS label_count
        WHERE size(entity_payloads) > 1
        RETURN phrase, label_count, size(entity_payloads) AS distinct_entity_payloads
        ORDER BY distinct_entity_payloads DESC, label_count DESC
        LIMIT $limit
        """,
        limit=limit,
    )
    return _result(
        "dq_gold_label_conflicts",
        "training",
        f"Found {len(rows)} phrase-level gold label conflicts.",
        rows,
    )


def dq_gold_label_span_payload_issues(limit: int = 500) -> dict:
    rows = run_knowledge(
        """
        MATCH (g:GoldLabel)
        WHERE g.entities_json IS NULL
           OR trim(toString(g.entities_json)) = ''
           OR NOT trim(toString(g.entities_json)) STARTS WITH '['
           OR NOT trim(toString(g.entities_json)) ENDS WITH ']'
        RETURN g.label_id AS label_id,
               g.candidate_id AS candidate_id,
               toString(g.updated_at) AS updated_at,
               left(toString(g.entities_json), 120) AS payload_preview
        ORDER BY updated_at DESC
        LIMIT $limit
        """,
        limit=limit,
    )
    return _result(
        "dq_gold_label_span_payload_issues",
        "training",
        f"Found {len(rows)} gold labels with malformed/empty entity payloads.",
        rows,
    )


def dq_writeback_effectiveness_drift(min_use_count: int = 5, limit: int = 300) -> dict:
    rows = run_knowledge(
        """
        MATCH (sf:SurfaceForm)
        OPTIONAL MATCH (sf)-[:MAPS_TO]->(c:Concept)
        WITH sf,
             count(DISTINCT c) AS mapping_count,
             coalesce(sf.use_count, 0) AS use_count
        WHERE use_count >= $min_use_count
        RETURN sf.normalized AS normalized,
               sf.form AS form,
               use_count,
               mapping_count,
               CASE WHEN mapping_count = 0 THEN 'no_mapping'
                    WHEN mapping_count > 1 THEN 'multi_mapping'
                    ELSE 'ok' END AS mapping_state
        ORDER BY use_count DESC, mapping_count ASC
        LIMIT $limit
        """,
        min_use_count=min_use_count,
        limit=limit,
    )
    return _result(
        "dq_writeback_effectiveness_drift",
        "training",
        "Evaluated surface-form writeback drift on high-usage terms.",
        rows,
    )


TOOLS = [
    {
        "name": "dq_training_candidate_pipeline_health",
        "description": "Training audit: queue health for TrainingCandidate statuses.",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": dq_training_candidate_pipeline_health,
    },
    {
        "name": "dq_gold_label_conflicts",
        "description": "Training audit: phrase-level GoldLabel conflicts.",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 200}}},
        "fn": dq_gold_label_conflicts,
    },
    {
        "name": "dq_gold_label_span_payload_issues",
        "description": "Training audit: malformed or empty GoldLabel entity payloads.",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 500}}},
        "fn": dq_gold_label_span_payload_issues,
    },
    {
        "name": "dq_writeback_effectiveness_drift",
        "description": "Training audit: high-usage surface form mapping drift.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_use_count": {"type": "integer", "default": 5},
                "limit": {"type": "integer", "default": 300},
            },
        },
        "fn": dq_writeback_effectiveness_drift,
    },
]

