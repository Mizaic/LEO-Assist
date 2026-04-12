"""Encounter-centric Mission Control endpoints.

Provides org-scoped encounter listing, KPI summary, and hybrid search
(fulltext + vector) for the /care/pathways replacement UI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher
import logging
import re
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from libs.auth.org_scope import ORG_PATIENT_FILTER, CallerScope, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient
from services.analytics_api.app.services.encounter_query_understanding import (
    feature_match_rationale,
    understand_query,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_PATIENT_ID_LEN = 64


def _normalise_patient_id(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = raw.strip()
    if not value or len(value) > _MAX_PATIENT_ID_LEN:
        return None
    return value


def _encounter_scope_prefix(
    org_id: Optional[str], scope: CallerScope
) -> tuple[str, dict[str, Any]]:
    effective_org = org_id if scope.is_admin else (org_id or scope.primary_org_id)
    if effective_org:
        return (
            "MATCH (_scope:Organization {id: $org}) "
            "MATCH (p:Patient)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
            "WHERE (gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
            "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope) "
            "MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE trim(coalesce(e.text, '')) <> '' ",
            {"org": effective_org},
        )
    if scope.is_admin:
        return (
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE trim(coalesce(e.text, '')) <> '' ",
            {},
        )
    return (
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
        f"WHERE {ORG_PATIENT_FILTER} "
        "  AND trim(coalesce(e.text, '')) <> '' ",
        scope.to_query_params(),
    )


def _append_filters(
    base: str,
    params: dict[str, Any],
    *,
    date_from: Optional[str],
    date_to: Optional[str],
    patient_id: Optional[str],
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    if date_from:
        clauses.append("toString(e.date) >= $date_from")
        params["date_from"] = date_from
    if date_to:
        clauses.append("toString(e.date) <= $date_to")
        params["date_to"] = date_to
    if patient_id:
        clauses.append("toString(p.id) = $patient_id")
        params["patient_id"] = patient_id
    if clauses:
        base = base.rstrip() + " AND " + " AND ".join(clauses) + " "
    return base, params


def _sort_clause(sort_by: str, sort_dir: str) -> str:
    allowed = {
        "encounter_date": "toString(e.date)",
        "patient_id": "toString(p.id)",
        "coded_count": "coded_count",
    }
    field = allowed.get(sort_by, "toString(e.date)")
    direction = "ASC" if sort_dir.upper() == "ASC" else "DESC"
    return f"ORDER BY ({field} IS NULL) ASC, {field} {direction}"


def _safe_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10])
    except Exception:
        return None


def _try_embed_query(query: str) -> Optional[list[float]]:
    try:
        from libs.prompts.few_shot_selector import _get_shared_embedder
    except Exception:
        return None
    embedder = _get_shared_embedder()
    vectors = embedder.encode([query])
    if vectors is None or len(vectors) == 0:
        return None
    return [float(x) for x in vectors[0]]


def _normalise_similarity_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _text_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        jaccard = 0.0
    else:
        jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    seq = SequenceMatcher(None, left, right).ratio()
    return max(jaccard, seq)


def _suppress_near_duplicates(
    ranked: list[dict[str, Any]], threshold: float | None
) -> tuple[list[dict[str, Any]], int]:
    if threshold is None:
        return ranked, 0
    kept: list[dict[str, Any]] = []
    kept_text: list[str] = []
    filtered = 0
    for item in ranked:
        normalised = _normalise_similarity_text(item.get("text"))
        if not normalised:
            kept.append(item)
            kept_text.append("")
            continue
        is_duplicate = any(
            existing and _text_similarity(normalised, existing) >= threshold
            for existing in kept_text
        )
        if is_duplicate:
            filtered += 1
            continue
        kept.append(item)
        kept_text.append(normalised)
    return kept, filtered


def _rank_with_features(
    merged: dict[str, dict[str, Any]], *, expanded_terms: list[str]
) -> list[dict[str, Any]]:
    if not merged:
        return []
    max_fulltext = (
        max(float(v.get("fulltext_score") or 0.0) for v in merged.values()) or 1.0
    )
    max_vector = (
        max(float(v.get("vector_score") or 0.0) for v in merged.values()) or 1.0
    )
    max_coded = max(int(v.get("coded_count") or 0) for v in merged.values()) or 1
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    ranked: list[dict[str, Any]] = []
    for item in merged.values():
        rationale = feature_match_rationale(
            text=item.get("text"),
            expanded_terms=expanded_terms,
        )
        fulltext_norm = float(item.get("fulltext_score") or 0.0) / max_fulltext
        vector_norm = float(item.get("vector_score") or 0.0) / max_vector
        coded_norm = int(item.get("coded_count") or 0) / max_coded
        encounter_date = _safe_iso_date(item.get("encounter_date"))
        if encounter_date is not None:
            age_days = max(0.0, (now - encounter_date).days)
            recency = max(0.0, 1.0 - min(age_days / 365.0, 1.0))
        else:
            recency = 0.0
        score = (
            (0.45 * fulltext_norm)
            + (0.35 * vector_norm)
            + (0.10 * float(rationale["term_coverage"]))
            + (0.05 * recency)
            + (0.05 * coded_norm)
        )
        item["score"] = round(score, 6)
        item["rank_features"] = {
            "fulltext_norm": round(fulltext_norm, 6),
            "vector_norm": round(vector_norm, 6),
            "term_coverage": round(float(rationale["term_coverage"]), 6),
            "term_hits": int(rationale["term_hits"]),
            "recency": round(recency, 6),
            "coded_norm": round(coded_norm, 6),
        }
        item["match_rationale"] = rationale["hit_terms"]
        ranked.append(item)
    ranked.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    return ranked


def _write_query_audit(
    *,
    client: PatientGraphClient,
    audit_id: str,
    scope: CallerScope,
    org_id: Optional[str],
    diagnostics: dict[str, Any],
    total_results: int,
    top_ids: list[str],
) -> None:
    params = {
        "audit_id": audit_id,
        "org_id": org_id,
        "is_admin": bool(scope.is_admin),
        "query_original": diagnostics.get("original_query"),
        "query_normalized": diagnostics.get("normalized_query"),
        "query_rewritten": diagnostics.get("rewritten_query"),
        "rewrite_source": diagnostics.get("rewrite_source"),
        "rewrite_applied": bool(diagnostics.get("rewrite_applied")),
        "rewrite_confidence": diagnostics.get("rewrite_confidence"),
        "result_count": int(total_results),
        "top_encounter_ids": top_ids,
    }
    client.run(
        "MERGE (q:CaseFindingQueryAudit {id: $audit_id}) "
        "SET q.org_id = $org_id, "
        "    q.is_admin = $is_admin, "
        "    q.query_original = $query_original, "
        "    q.query_normalized = $query_normalized, "
        "    q.query_rewritten = $query_rewritten, "
        "    q.rewrite_source = $rewrite_source, "
        "    q.rewrite_applied = $rewrite_applied, "
        "    q.rewrite_confidence = $rewrite_confidence, "
        "    q.result_count = $result_count, "
        "    q.top_encounter_ids = $top_encounter_ids, "
        "    q.created_at = datetime()",
        **params,
    )


@router.get("/mission-control/encounters")
async def get_mission_control_encounters(
    org_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    patient_id: Optional[str] = Query(None, max_length=_MAX_PATIENT_ID_LEN),
    q: Optional[str] = Query(None, min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    max_results: int = Query(1200, ge=100, le=2000),
    near_duplicate_threshold: Optional[float] = Query(None, ge=0.8, le=0.99),
    sort_by: str = Query("encounter_date"),
    sort_dir: str = Query("DESC"),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    pid = _normalise_patient_id(patient_id)
    base, params = _encounter_scope_prefix(org_id, scope)
    base, params = _append_filters(
        base, params, date_from=date_from, date_to=date_to, patient_id=pid
    )
    client = PatientGraphClient()
    try:
        if not q:
            count_q = f"{base} RETURN count(DISTINCT e) AS total"
            total_rows = client.run(count_q, **params)
            total = int(total_rows[0]["total"]) if total_rows else 0

            skip = (page - 1) * page_size
            data_q = (
                f"{base}"
                "OPTIONAL MATCH (e)-[r:DOCUMENTS]->() "
                "WITH p, e, count(r) AS coded_count "
                f"{_sort_clause(sort_by, sort_dir)} "
                "SKIP $skip LIMIT $limit "
                "RETURN toString(e.id) AS encounter_id, "
                "       toString(p.id) AS patient_id, "
                "       toString(e.date) AS encounter_date, "
                "       e.text AS text, "
                "       e.flags AS flags, "
                "       coded_count AS coded_count"
            )
            rows = client.run(data_q, **{**params, "skip": skip, "limit": page_size})
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [
                    {
                        "encounter_id": r.get("encounter_id"),
                        "patient_id": r.get("patient_id"),
                        "encounter_date": r.get("encounter_date"),
                        "text": r.get("text"),
                        "flags": r.get("flags"),
                        "coded_count": int(r.get("coded_count") or 0),
                        "match_type": "none",
                        "fulltext_score": None,
                        "vector_score": None,
                        "score": None,
                    }
                    for r in rows
                ],
            }

        fulltext_rows: list[dict[str, Any]] = []
        vector_rows: list[dict[str, Any]] = []
        query_ctx = understand_query(str(q).strip())
        text_q = (
            query_ctx.rewritten_query
            or query_ctx.normalized_query
            or query_ctx.original_query
        )

        try:
            fulltext_q = (
                "CALL db.index.fulltext.queryNodes('encounter_text_index', $q_text, {limit: $limit}) "
                "YIELD node, score "
                "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(node) "
                "WITH p, node AS e, score "
                "WHERE trim(coalesce(e.text, '')) <> '' "
            )
            fulltext_params = {
                "q_text": query_ctx.fulltext_query or text_q,
                "limit": min(max(max_results, page_size * 3), 1500),
            }
            where_chunks: list[str] = []
            if "org" in params:
                where_chunks.append(
                    "EXISTS { MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
                    "WHERE (gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(:Organization {id: $org}) "
                    "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(:Organization {id: $org}) }"
                )
                fulltext_params["org"] = params["org"]
            elif not scope.is_admin:
                # Scope fallback handled by post-filter when non-admin/no explicit org.
                pass
            if date_from:
                where_chunks.append("toString(e.date) >= $date_from")
                fulltext_params["date_from"] = date_from
            if date_to:
                where_chunks.append("toString(e.date) <= $date_to")
                fulltext_params["date_to"] = date_to
            if pid:
                where_chunks.append("toString(p.id) = $patient_id")
                fulltext_params["patient_id"] = pid
            if where_chunks:
                fulltext_q += " AND " + " AND ".join(where_chunks) + " "
            fulltext_q += (
                "OPTIONAL MATCH (e)-[r:DOCUMENTS]->() "
                "WITH p, e, score, count(r) AS coded_count "
                "RETURN toString(e.id) AS encounter_id, "
                "       toString(p.id) AS patient_id, "
                "       toString(e.date) AS encounter_date, "
                "       e.text AS text, "
                "       e.flags AS flags, "
                "       coded_count, "
                "       score AS fulltext_score "
                "ORDER BY fulltext_score DESC "
                "LIMIT $limit"
            )
            fulltext_rows = client.run(fulltext_q, **fulltext_params)
        except Exception:
            logger.warning("Encounter fulltext leg unavailable", exc_info=True)

        try:
            query_vector = _try_embed_query(text_q)
            if query_vector:
                vector_q = (
                    "CALL db.index.vector.queryNodes('encounter_vector_index', $k, $query_vector) "
                    "YIELD node, score "
                    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(node) "
                    "WITH p, node AS e, score "
                    "WHERE trim(coalesce(e.text, '')) <> '' "
                )
                vector_params = {
                    "k": min(max(max_results, page_size * 4), 2500),
                    "query_vector": query_vector,
                    "limit": min(max(max_results, page_size * 3), 1500),
                }
                where_chunks = []
                if "org" in params:
                    where_chunks.append(
                        "EXISTS { MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
                        "WHERE (gp.id = $org) OR (gp)-[:COMMISSIONED_BY]->(:Organization {id: $org}) "
                        "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(:Organization {id: $org}) }"
                    )
                    vector_params["org"] = params["org"]
                if date_from:
                    where_chunks.append("toString(e.date) >= $date_from")
                    vector_params["date_from"] = date_from
                if date_to:
                    where_chunks.append("toString(e.date) <= $date_to")
                    vector_params["date_to"] = date_to
                if pid:
                    where_chunks.append("toString(p.id) = $patient_id")
                    vector_params["patient_id"] = pid
                if where_chunks:
                    vector_q += " AND " + " AND ".join(where_chunks) + " "
                vector_q += (
                    "OPTIONAL MATCH (e)-[r:DOCUMENTS]->() "
                    "WITH p, e, score, count(r) AS coded_count "
                    "RETURN toString(e.id) AS encounter_id, "
                    "       toString(p.id) AS patient_id, "
                    "       toString(e.date) AS encounter_date, "
                    "       e.text AS text, "
                    "       e.flags AS flags, "
                    "       coded_count, "
                    "       score AS vector_score "
                    "ORDER BY vector_score DESC "
                    "LIMIT $limit"
                )
                vector_rows = client.run(vector_q, **vector_params)
        except Exception:
            logger.warning("Encounter vector leg unavailable", exc_info=True)

        merged: dict[str, dict[str, Any]] = {}
        for row in fulltext_rows:
            eid = str(row.get("encounter_id") or "")
            if not eid:
                continue
            merged[eid] = {
                "encounter_id": eid,
                "patient_id": row.get("patient_id"),
                "encounter_date": row.get("encounter_date"),
                "text": row.get("text"),
                "flags": row.get("flags"),
                "coded_count": int(row.get("coded_count") or 0),
                "match_type": "keyword",
                "fulltext_score": float(row.get("fulltext_score") or 0.0),
                "vector_score": None,
            }

        for row in vector_rows:
            eid = str(row.get("encounter_id") or "")
            if not eid:
                continue
            vec_score = float(row.get("vector_score") or 0.0)
            if eid in merged:
                merged[eid]["match_type"] = "hybrid"
                merged[eid]["vector_score"] = vec_score
            else:
                merged[eid] = {
                    "encounter_id": eid,
                    "patient_id": row.get("patient_id"),
                    "encounter_date": row.get("encounter_date"),
                    "text": row.get("text"),
                    "flags": row.get("flags"),
                    "coded_count": int(row.get("coded_count") or 0),
                    "match_type": "semantic",
                    "fulltext_score": None,
                    "vector_score": vec_score,
                }

        ranked = _rank_with_features(merged, expanded_terms=query_ctx.expanded_terms)
        ranked, dedupe_filtered_count = _suppress_near_duplicates(
            ranked, near_duplicate_threshold
        )
        total = len(ranked)
        start = (page - 1) * page_size
        end = start + page_size
        audit_id = str(uuid.uuid4())
        diagnostics = {
            "query_audit_id": audit_id,
            "original_query": query_ctx.original_query,
            "normalized_query": query_ctx.normalized_query,
            "rewritten_query": query_ctx.rewritten_query,
            "rewrite_applied": query_ctx.rewrite_applied,
            "rewrite_source": query_ctx.rewrite_source,
            "rewrite_confidence": query_ctx.rewrite_confidence,
            "expanded_terms": query_ctx.expanded_terms,
            "fulltext_query": query_ctx.fulltext_query,
            "reasoning": query_ctx.reasoning,
            "near_duplicate_threshold": near_duplicate_threshold,
            "near_duplicate_filtered_count": dedupe_filtered_count,
        }
        try:
            _write_query_audit(
                client=client,
                audit_id=audit_id,
                scope=scope,
                org_id=org_id,
                diagnostics=diagnostics,
                total_results=total,
                top_ids=[
                    str(i.get("encounter_id"))
                    for i in ranked[:20]
                    if i.get("encounter_id")
                ],
            )
        except Exception:
            logger.warning("Case-finding query audit write failed", exc_info=True)
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": ranked[start:end],
            "query_diagnostics": diagnostics,
        }
    finally:
        client.close()


@router.get("/mission-control/encounters/kpis")
async def get_mission_control_encounter_kpis(
    org_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    patient_id: Optional[str] = Query(None, max_length=_MAX_PATIENT_ID_LEN),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    pid = _normalise_patient_id(patient_id)
    base, params = _encounter_scope_prefix(org_id, scope)
    base, params = _append_filters(
        base, params, date_from=date_from, date_to=date_to, patient_id=pid
    )
    q = (
        f"{base}"
        "OPTIONAL MATCH (e)-[r:DOCUMENTS]->() "
        "WITH p, e, count(r) AS coded_count "
        "RETURN count(DISTINCT e) AS total_encounters, "
        "       count(DISTINCT p) AS total_patients, "
        "       count(DISTINCT CASE WHEN coded_count > 0 THEN e END) AS coded_encounters, "
        "       percentileCont(toFloat(coded_count), 0.5) AS median_codes_per_encounter"
    )
    client = PatientGraphClient()
    try:
        rows = client.run(q, **params)
    finally:
        client.close()
    if not rows:
        return {
            "total_encounters": 0,
            "total_patients": 0,
            "coded_encounters": 0,
            "median_codes_per_encounter": 0,
        }
    row = rows[0]
    return {
        "total_encounters": int(row.get("total_encounters") or 0),
        "total_patients": int(row.get("total_patients") or 0),
        "coded_encounters": int(row.get("coded_encounters") or 0),
        "median_codes_per_encounter": float(row.get("median_codes_per_encounter") or 0),
    }


@router.get("/mission-control/encounters/quality-metrics")
async def get_encounter_case_finding_quality_metrics(
    org_id: Optional[str] = Query(None),
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = PatientGraphClient()
    try:
        effective_org = org_id if scope.is_admin else (org_id or scope.primary_org_id)
        if effective_org:
            rows = client.run(
                "MATCH (q:CaseFindingQueryAudit {org_id: $org}) "
                "OPTIONAL MATCH (s:CaseFindingSelection)-[:FROM_QUERY]->(q) "
                "RETURN count(DISTINCT q) AS query_count, "
                "       count(DISTINCT s) AS selection_count, "
                "       avg(toFloat(q.result_count)) AS avg_results",
                org=effective_org,
            )
        else:
            rows = client.run(
                "MATCH (q:CaseFindingQueryAudit) "
                "OPTIONAL MATCH (s:CaseFindingSelection)-[:FROM_QUERY]->(q) "
                "RETURN count(DISTINCT q) AS query_count, "
                "       count(DISTINCT s) AS selection_count, "
                "       avg(toFloat(q.result_count)) AS avg_results"
            )
        row = rows[0] if rows else {}
        query_count = int(row.get("query_count") or 0)
        selection_count = int(row.get("selection_count") or 0)
        return {
            "query_count": query_count,
            "selection_count": selection_count,
            "selection_rate": (
                round(selection_count / query_count, 4) if query_count > 0 else 0.0
            ),
            "avg_results_per_query": float(row.get("avg_results") or 0.0),
        }
    finally:
        client.close()
