"""Training corpus statistics + schema sample-node router.

Atlas trace:
  DO: DO-236545C8
  Also implements: DO-2D2CE052, DO-54397CCD, DO-6CD07544, DO-94D87FA7, DO-A35D2D57, DO-B88D4941, DO-BA2B7A99
  DI: DI-2D9F5064, DI-37B3DC71, DI-3EA60D5A, DI-54D00E21, DI-6EFD68D0, DI-A0579B64, DI-AF5A1668, DI-D2D0117E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

Extracted from services/api/app/routers/training.py (2026-07 CTO peer-review
item 2: core-api router decomposition). Pure move, no behaviour change --
existing DO/DI trace headers carried over unchanged.

Routes: corpus/stats, schema/sample-node.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from libs.auth.org_scope import (
    CallerScope,
    get_caller_scope,
)
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from app.deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()


_Q_CORPUS_STATS_BY_SOURCE = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(s)
WHERE r.evidence_sentence IS NOT NULL
RETURN
    r.source                                    AS source,
    r.holdout                                   AS holdout,
    coalesce(toString(s.semanticTag), 'other')  AS semantic_tag,
    coalesce(r.context, '{}')                   AS context_json,
    count(r)                                    AS cnt
"""

_Q_NEGATIVE_SENTENCES = """
MATCH (e:Encounter)
WHERE e.text IS NOT NULL AND trim(e.text) <> ''
AND NOT EXISTS {
    MATCH (e)-[r:DOCUMENTS]->()
    WHERE r.evidence_sentence IS NOT NULL
}
RETURN count(e) AS negative_count
"""

_Q_CORPUS_LAST_UPDATED = """
MATCH (e:Encounter)-[r:DOCUMENTS]->()
WHERE r.evidence_sentence IS NOT NULL
RETURN toString(max(r.coded_at)) AS last_updated
"""

_GOLD_SOURCES = {"reviewer_correction", "approved", "gold"}
_SILVER_SOURCES = {"provisional", "terminology_api", "llm_auto_detected"}
_SAFETY_TAGS = {"cancer", "oncology", "safeguarding", "mental_health", "suicide"}
_SAFETY_MIN = 20
_IMBALANCE_MIN = 50
_GOLD_MINIMUM = 5000


@router.get("/corpus/stats")
def get_corpus_stats(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return NER corpus statistics grouped by source, semantic tag and assertion.

    Used by CorpusCard in the Train section to show progress toward the
    5,000 gold label minimum and flag imbalance or safety-critical gaps.
    """
    import json as _json
    from collections import Counter

    client = PatientGraphClient()
    try:
        with client.session() as session:
            rows = [dict(r) for r in session.run(_Q_CORPUS_STATS_BY_SOURCE)]
            neg_row = session.run(_Q_NEGATIVE_SENTENCES).single()
            updated_row = session.run(_Q_CORPUS_LAST_UPDATED).single()
    finally:
        client.close()

    gold_count = 0
    silver_count = 0
    holdout_count = 0
    entity_type_breakdown: Counter = Counter()
    assertion_breakdown: Counter = Counter()
    safety_counts: Counter = Counter()

    for row in rows:
        source = str(row.get("source") or "")
        holdout = bool(row.get("holdout"))
        tag = str(row.get("semantic_tag") or "other").lower()
        cnt = int(row.get("cnt") or 0)

        try:
            ctx = _json.loads(str(row.get("context_json") or "{}"))
            assertion = str(ctx.get("assertion") or "present")
        except Exception:
            assertion = "present"

        entity_type_breakdown[tag] += cnt
        assertion_breakdown[assertion] += cnt

        for kw in _SAFETY_TAGS:
            if kw in tag and assertion in ("present", "historical"):
                safety_counts[tag] += cnt

        if holdout:
            holdout_count += cnt
        elif source in _GOLD_SOURCES:
            gold_count += cnt
        else:
            silver_count += cnt

    negative_sentence_count = int(neg_row["negative_count"]) if neg_row else 0
    last_updated = str(updated_row["last_updated"]) if updated_row else None

    imbalance_warnings: list[str] = [
        f"Low examples for '{tag}': {cnt} (need {_IMBALANCE_MIN})"
        for tag, cnt in entity_type_breakdown.items()
        if cnt < _IMBALANCE_MIN
    ]
    safety_critical_blocked = any(cnt < _SAFETY_MIN for cnt in safety_counts.values())

    return {
        "gold_count": gold_count,
        "silver_count": silver_count,
        "holdout_count": holdout_count,
        "negative_sentence_count": negative_sentence_count,
        "entity_type_breakdown": dict(entity_type_breakdown),
        "assertion_breakdown": dict(assertion_breakdown),
        "imbalance_warnings": imbalance_warnings,
        "safety_critical_blocked": safety_critical_blocked,
        "training_ready": gold_count >= _GOLD_MINIMUM and not safety_critical_blocked,
        "minimum_gold_met": gold_count >= _GOLD_MINIMUM,
        "last_updated": last_updated,
    }


# ── Source node sample preview ──────────────────────────────────────────────


# Allowlist of source-configurator node labels the sample-node endpoint will
# query. node_label flows directly into a Cypher MATCH clause, so we MUST
# refuse anything that is not a known training-pipeline label. The list is
# kept narrow on purpose -- training authors only need a handful of source
# labels to design new pathways.
_SAMPLE_NODE_LABEL_ALLOWLIST = frozenset(
    {
        "Encounter",
        "EncounterCandidate",
        "Patient",
        "Document",
        "Observation",
        "Condition",
        "MedicationRequest",
        "MedicationStatement",
        "Procedure",
        "DiagnosticReport",
        "AllergyIntolerance",
        "Immunization",
        "Concept",
        "ConceptDescription",
        "ValueSetMember",
        "GuidelineRule",
    }
)
_SAMPLE_NODE_GRAPH_ALLOWLIST = frozenset({"patient", "knowledge"})


@router.get("/schema/sample-node")
def get_sample_node(
    node_label: str = Query(
        ..., description="Node label to sample (e.g. EncounterCandidate)"
    ),
    graph: str = Query(
        "patient", description="Which graph to query: 'patient' or 'knowledge'"
    ),
    text_property: str = Query(
        "text", description="Property to highlight as the main text field"
    ),
    scope: CallerScope = Depends(require_admin),
):
    """Return one sample node so users can verify field names in the source configurator.

    Admin-only: the source configurator inspects raw graph nodes and is
    only used by training authors who already have admin scope. Restricting
    here removes a Cypher-injection style surface from non-admin sessions.

    Sanitises the result: sensitive fields are redacted, long text is truncated to
    300 characters, and Neo4j datetime objects are converted to ISO strings.
    The selected text_property is surfaced first in the response.
    """
    _ = scope
    if graph not in _SAMPLE_NODE_GRAPH_ALLOWLIST:
        raise HTTPException(
            status_code=400,
            detail="graph must be 'patient' or 'knowledge'",
        )
    if node_label not in _SAMPLE_NODE_LABEL_ALLOWLIST:
        raise HTTPException(
            status_code=400,
            detail="Unsupported node_label",
        )

    _REDACT = {
        "nhs_number",
        "date_of_birth",
        "dob",
        "birthdate",
        "birthDate",
        "postcode",
    }
    _MAX_TEXT = 300

    try:
        client: Any = (
            KnowledgeGraphClient() if graph == "knowledge" else PatientGraphClient()
        )
        try:
            with client.session() as session:
                rows = list(
                    session.run(
                        f"MATCH (n:{node_label}) RETURN properties(n) AS props LIMIT 1"
                    )
                )
        finally:
            client.close()

        if not rows:
            from fastapi.responses import JSONResponse as _JSONResponse

            return _JSONResponse(
                status_code=404,
                content={
                    "detail": f"No {node_label} nodes found in the {graph} graph."
                },
            )

        raw: dict = dict(rows[0]["props"])

        def _sanitise(k: str, v: Any) -> Any:
            if k.lower() in _REDACT:
                return "***redacted***"
            if isinstance(v, str) and len(v) > _MAX_TEXT:
                return v[:_MAX_TEXT] + "..."
            if hasattr(v, "iso_format"):
                return v.iso_format()
            return v

        preview = {k: _sanitise(k, v) for k, v in raw.items()}
        ordered: dict = {}
        if text_property in preview:
            ordered[text_property] = preview.pop(text_property)
        ordered.update(preview)

        return {
            "nodeLabel": node_label,
            "graph": graph,
            "textProperty": text_property,
            "properties": ordered,
        }

    except HTTPException:
        raise
    except Exception as exc:
        from fastapi.responses import JSONResponse as _JSONResponse

        logger.warning("sample-node error for %s/%s: %s", graph, node_label, exc)
        return _JSONResponse(
            status_code=500,
            content={"detail": "sample-node lookup failed"},
        )
