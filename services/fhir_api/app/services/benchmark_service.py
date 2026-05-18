"""Benchmark CRUD and run logic.

Atlas trace:
  DO: DO-B3397C94
  DI: DI-FC9A8824
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-B3397C94")

Manages BenchmarkSet, BenchmarkValue, and BenchmarkRule nodes in the Knowledge Graph.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

from services.fhir_api.app.services.benchmark_loader import flatten_benchmarks
from services.fhir_api.app.services.cypher_generator import generate_cypher


def create_benchmark_set(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a BenchmarkSet node."""
    set_id = data.get("id") or _slug(data.get("name", "benchmark-set"))
    client = KnowledgeGraphClient()
    try:
        now = datetime.utcnow().isoformat() + "Z"
        client.run(
            "MERGE (s:BenchmarkSet {id: $id}) "
            "SET s.name = $name, s.source = $source, s.audit_year = $audit_year, "
            "s.effective_from = $effective_from, s.effective_to = $effective_to, "
            "s.metadata = $metadata, s.created_at = datetime(), s.updated_at = datetime()",
            id=set_id,
            name=data.get("name", set_id),
            source=data.get("source", "uploaded"),
            audit_year=data.get("audit_year"),
            effective_from=data.get("effective_from"),
            effective_to=data.get("effective_to"),
            metadata=json.dumps(data.get("metadata") or {}),
        )
        return get_benchmark_set(set_id) or {
            "id": set_id,
            "name": data.get("name"),
            "source": data.get("source"),
        }
    finally:
        client.close()


def get_benchmark_set(set_id: str) -> Optional[Dict[str, Any]]:
    """Get a BenchmarkSet by id."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (s:BenchmarkSet {id: $id}) RETURN s.id AS id, s.name AS name, s.source AS source, "
            "s.audit_year AS audit_year, s.effective_from AS effective_from, s.effective_to AS effective_to, "
            "s.metadata AS metadata, s.created_at AS created_at, s.updated_at AS updated_at",
            id=set_id,
        )
        if not rows:
            return None
        r = rows[0]
        meta = r.get("metadata")
        return {
            "id": r["id"],
            "name": r["name"],
            "source": r["source"],
            "audit_year": r["audit_year"],
            "effective_from": r["effective_from"],
            "effective_to": r["effective_to"],
            "metadata": json.loads(meta) if isinstance(meta, str) else meta,
            "created_at": _serialize_datetime(r.get("created_at")),
            "updated_at": _serialize_datetime(r.get("updated_at")),
        }
    finally:
        client.close()


def list_benchmark_sets(
    source: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List BenchmarkSets in a single round-trip (no per-row N+1)."""
    fields = (
        "RETURN s.id AS id, s.name AS name, s.source AS source, "
        "s.audit_year AS audit_year, s.effective_from AS effective_from, "
        "s.effective_to AS effective_to, s.metadata AS metadata, "
        "s.created_at AS created_at, s.updated_at AS updated_at "
        "ORDER BY s.name SKIP $offset LIMIT $limit"
    )
    client = KnowledgeGraphClient()
    try:
        if source:
            rows = client.run(
                "MATCH (s:BenchmarkSet) WHERE s.source = $source " + fields,
                source=source,
                offset=offset,
                limit=limit,
            )
        else:
            rows = client.run(
                "MATCH (s:BenchmarkSet) " + fields,
                offset=offset,
                limit=limit,
            )
        result = []
        for r in rows:
            meta = r.get("metadata")
            result.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "source": r["source"],
                    "audit_year": r["audit_year"],
                    "effective_from": r["effective_from"],
                    "effective_to": r["effective_to"],
                    "metadata": (
                        json.loads(meta) if isinstance(meta, str) else meta
                    ),
                    "created_at": _serialize_datetime(r.get("created_at")),
                    "updated_at": _serialize_datetime(r.get("updated_at")),
                }
            )
        return result
    finally:
        client.close()


def delete_benchmark_set(set_id: str) -> None:
    """Delete BenchmarkSet and all its BenchmarkValue nodes."""
    client = KnowledgeGraphClient()
    try:
        client.run(
            "MATCH (v:BenchmarkValue {audit_id: $aid}) DETACH DELETE v",
            aid=set_id,
        )
        client.run("MATCH (s:BenchmarkSet {id: $id}) DETACH DELETE s", id=set_id)
    finally:
        client.close()


def delete_benchmark_values_by_metric_ids(audit_id: str, metric_ids: List[str]) -> int:
    """Delete BenchmarkValue nodes for given metric_ids. Returns count deleted."""
    if not metric_ids:
        return 0
    client = KnowledgeGraphClient()
    try:
        result = client.run(
            "MATCH (v:BenchmarkValue) WHERE v.audit_id = $audit_id AND v.metric_id IN $metric_ids "
            "DETACH DELETE v RETURN count(v) AS deleted",
            audit_id=audit_id,
            metric_ids=metric_ids,
        )
        return result[0]["deleted"] if result else 0
    finally:
        client.close()


def upsert_benchmark_values(audit_id: str, values: List[Dict[str, Any]]) -> int:
    """Batch MERGE BenchmarkValue nodes via UNWIND. Returns count upserted.

    Previously this issued one Cypher round-trip per value; benchmark
    sets routinely contain 500+ values, which meant 500+ Bolt requests
    and the same number of write transactions. The UNWIND form does
    the whole batch in a single transaction.
    """
    if not values:
        return 0
    rows: List[Dict[str, Any]] = []
    for v in values:
        v_audit = v.get("audit_id", audit_id)
        v_metric = v.get("metric_id", "")
        v_scope = v.get("scope_id", "")
        value_json = v.get("value_json")
        value_json_str = (
            json.dumps(value_json) if value_json is not None else None
        )
        rows.append(
            {
                "id": f"{v_audit}_{v_metric}_{v_scope}",
                "audit_id": v_audit,
                "metric_id": v_metric,
                "scope_type": v.get("scope_type", ""),
                "scope_id": v_scope,
                "scope_name": v.get("scope_name", ""),
                "value": v.get("value"),
                "value_json": value_json_str,
                "unit": v.get("unit") or "",
                "label": v.get("label", ""),
                "category": v.get("category", ""),
                "source": v.get("source", ""),
                "sample_size": v.get("sample_size"),
            }
        )
    client = KnowledgeGraphClient()
    try:
        client.run(
            "UNWIND $rows AS row "
            "MERGE (b:BenchmarkValue {id: row.id}) "
            "SET b.audit_id = row.audit_id, b.metric_id = row.metric_id, "
            "b.scope_type = row.scope_type, b.scope_id = row.scope_id, "
            "b.scope_name = row.scope_name, b.value = row.value, "
            "b.value_json = row.value_json, b.unit = row.unit, "
            "b.label = row.label, b.category = row.category, "
            "b.source = row.source, b.sample_size = row.sample_size, "
            "b.updated_at = datetime()",
            rows=rows,
        )
        return len(rows)
    finally:
        client.close()


def get_benchmark_values(
    audit_id: str,
    metric_id: Optional[str] = None,
    scope_type: Optional[str] = None,
    scope_id: Optional[str] = None,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get BenchmarkValues for a set, optionally filtered."""
    client = KnowledgeGraphClient()
    try:
        where_parts = ["v.audit_id = $audit_id"]
        params: Dict[str, Any] = {"audit_id": audit_id}
        if metric_id:
            where_parts.append("v.metric_id = $metric_id")
            params["metric_id"] = metric_id
        if scope_type:
            where_parts.append("v.scope_type = $scope_type")
            params["scope_type"] = scope_type
        if scope_id:
            where_parts.append("v.scope_id = $scope_id")
            params["scope_id"] = scope_id
        if category:
            where_parts.append("v.category = $category")
            params["category"] = category
        where = " AND ".join(where_parts)
        rows = client.run(
            f"MATCH (v:BenchmarkValue) WHERE {where} "
            "RETURN v.id AS id, v.metric_id AS metric_id, v.scope_type AS scope_type, "
            "v.scope_id AS scope_id, v.scope_name AS scope_name, v.value AS value, "
            "v.value_json AS value_json, v.unit AS unit, v.label AS label, "
            "v.category AS category ORDER BY v.metric_id, v.scope_type",
            **params,
        )
        result = []
        for r in rows:
            val_json = r.get("value_json")
            if isinstance(val_json, str):
                try:
                    val_json = json.loads(val_json)
                except json.JSONDecodeError:
                    val_json = None
            result.append(
                {
                    "id": r.get("id"),
                    "metric_id": r["metric_id"],
                    "scope_type": r["scope_type"],
                    "scope_id": r["scope_id"],
                    "scope_name": r["scope_name"],
                    "value": r["value"],
                    "value_json": val_json,
                    "unit": r["unit"],
                    "label": r["label"],
                    "category": r["category"],
                }
            )
        return result
    finally:
        client.close()


def get_benchmark_categories(audit_id: str) -> List[str]:
    """Return distinct categories present in a benchmark set."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (v:BenchmarkValue {audit_id: $audit_id}) "
            "RETURN DISTINCT v.category AS category ORDER BY category",
            audit_id=audit_id,
        )
        return [r["category"] for r in rows if r.get("category")]
    finally:
        client.close()


def get_benchmark_scopes(audit_id: str) -> List[Dict[str, str]]:
    """Return distinct scopes (scope_id, scope_type, scope_name) in a benchmark set."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (v:BenchmarkValue {audit_id: $audit_id}) "
            "RETURN DISTINCT v.scope_id AS scope_id, v.scope_type AS scope_type, "
            "v.scope_name AS scope_name ORDER BY v.scope_type, v.scope_name",
            audit_id=audit_id,
        )
        return [
            {
                "scope_id": r["scope_id"],
                "scope_type": r["scope_type"],
                "scope_name": r["scope_name"],
            }
            for r in rows
        ]
    finally:
        client.close()


def update_benchmark_value(value_id: str, new_value: float) -> Optional[Dict[str, Any]]:
    """Update the numeric value of a BenchmarkValue node by id."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (v:BenchmarkValue {id: $id}) SET v.value = $value, v.updated_at = datetime() "
            "RETURN v.id AS id, v.metric_id AS metric_id, v.scope_type AS scope_type, "
            "v.scope_id AS scope_id, v.scope_name AS scope_name, v.value AS value, "
            "v.unit AS unit, v.label AS label, v.category AS category",
            id=value_id,
            value=new_value,
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "id": r["id"],
            "metric_id": r["metric_id"],
            "scope_type": r["scope_type"],
            "scope_id": r["scope_id"],
            "scope_name": r["scope_name"],
            "value": r["value"],
            "unit": r["unit"],
            "label": r["label"],
            "category": r["category"],
        }
    finally:
        client.close()


def delete_benchmark_value(value_id: str) -> bool:
    """Delete a single BenchmarkValue by id. Returns True if deleted."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (v:BenchmarkValue {id: $id}) "
            "WITH v, v.id AS deleted_id DETACH DELETE v RETURN deleted_id",
            id=value_id,
        )
        return bool(rows)
    finally:
        client.close()


def get_benchmark_comparison(audit_id: str, metric_id: str) -> List[Dict[str, Any]]:
    """Get benchmark comparison for one metric across all scopes (practice/alliance/national).

    Returns list of {metric_id, label, scope_type, scope_name, value, unit, source} for frontend BenchmarkPoint.
    """
    rows = get_benchmark_values(audit_id, metric_id=metric_id)
    if not rows:
        return []
    label = rows[0].get("label", metric_id) if rows else metric_id
    unit = rows[0].get("unit")
    set_data = get_benchmark_set(audit_id)
    source = set_data.get("name", audit_id) if set_data else audit_id
    out = []
    for r in rows:
        val_json = r.get("value_json")
        point = {
            "metric_id": metric_id,
            "label": r.get("label", label),
            "scope_type": r["scope_type"],
            "scope_name": r["scope_name"],
            "value": r["value"],
            "unit": unit,
            "source": source,
        }
        if val_json and isinstance(val_json, dict):
            point["value_breakdown"] = val_json
            point["value"] = None
        out.append(point)
    return out


def create_benchmark_rule(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a BenchmarkRule node."""
    rule_id = data.get("id")
    client = KnowledgeGraphClient()
    try:
        if not rule_id:
            rule_id = str(uuid.uuid4())
        client.run(
            "MERGE (r:BenchmarkRule {id: $id}) "
            "SET r.name = $name, r.query_definition = $query_definition, r.scope = $scope, "
            "r.output_metric_id = $output_metric_id, r.benchmark_set_id = $benchmark_set_id, "
            "r.created_at = datetime(), r.updated_at = datetime()",
            id=rule_id,
            name=data.get("name", "Unnamed rule"),
            query_definition=json.dumps(data.get("query_definition") or {}),
            scope=data.get("scope", "all"),
            output_metric_id=data.get("output_metric_id", ""),
            benchmark_set_id=data.get("benchmark_set_id", ""),
        )
        return get_benchmark_rule(rule_id) or {"id": rule_id}
    finally:
        client.close()


def get_benchmark_rule(rule_id: str) -> Optional[Dict[str, Any]]:
    """Get a BenchmarkRule by id."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (r:BenchmarkRule {id: $id}) RETURN r.id AS id, r.name AS name, "
            "r.query_definition AS query_definition, r.scope AS scope, "
            "r.output_metric_id AS output_metric_id, r.benchmark_set_id AS benchmark_set_id, "
            "r.last_run_at AS last_run_at, r.last_run_status AS last_run_status, "
            "r.created_at AS created_at, r.updated_at AS updated_at",
            id=rule_id,
        )
        if not rows:
            return None
        r = rows[0]
        qd = r.get("query_definition")
        return {
            "id": r["id"],
            "name": r["name"],
            "query_definition": json.loads(qd) if isinstance(qd, str) else qd,
            "scope": r["scope"],
            "output_metric_id": r["output_metric_id"],
            "benchmark_set_id": r["benchmark_set_id"],
            "last_run_at": _serialize_datetime(r.get("last_run_at")),
            "last_run_status": r.get("last_run_status"),
            "created_at": _serialize_datetime(r.get("created_at")),
            "updated_at": _serialize_datetime(r.get("updated_at")),
        }
    finally:
        client.close()


def list_benchmark_rules(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """List BenchmarkRules in a single round-trip (no per-row N+1)."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (r:BenchmarkRule) "
            "RETURN r.id AS id, r.name AS name, "
            "r.query_definition AS query_definition, r.scope AS scope, "
            "r.output_metric_id AS output_metric_id, "
            "r.benchmark_set_id AS benchmark_set_id, "
            "r.last_run_at AS last_run_at, r.last_run_status AS last_run_status, "
            "r.created_at AS created_at, r.updated_at AS updated_at "
            "ORDER BY r.name SKIP $offset LIMIT $limit",
            offset=offset,
            limit=limit,
        )
        out: List[Dict[str, Any]] = []
        for r in rows:
            qd = r.get("query_definition")
            out.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "query_definition": (
                        json.loads(qd) if isinstance(qd, str) else qd
                    ),
                    "scope": r["scope"],
                    "output_metric_id": r["output_metric_id"],
                    "benchmark_set_id": r["benchmark_set_id"],
                    "last_run_at": _serialize_datetime(r.get("last_run_at")),
                    "last_run_status": r.get("last_run_status"),
                    "created_at": _serialize_datetime(r.get("created_at")),
                    "updated_at": _serialize_datetime(r.get("updated_at")),
                }
            )
        return out
    finally:
        client.close()


def update_benchmark_rule(
    rule_id: str, data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Update a BenchmarkRule."""
    client = KnowledgeGraphClient()
    try:
        updates = []
        params: Dict[str, Any] = {"id": rule_id}
        for key in (
            "name",
            "query_definition",
            "scope",
            "output_metric_id",
            "benchmark_set_id",
        ):
            if key in data:
                if key == "query_definition":
                    params[key] = (
                        json.dumps(data[key])
                        if isinstance(data[key], dict)
                        else data[key]
                    )
                else:
                    params[key] = data[key]
                updates.append(f"r.{key} = ${key}")
        if updates:
            client.run(
                f"MATCH (r:BenchmarkRule {{id: $id}}) SET {', '.join(updates)}, r.updated_at = datetime()",
                **params,
            )
        return get_benchmark_rule(rule_id)
    finally:
        client.close()


def delete_benchmark_rule(rule_id: str) -> None:
    """Delete a BenchmarkRule."""
    client = KnowledgeGraphClient()
    try:
        client.run("MATCH (r:BenchmarkRule {id: $id}) DETACH DELETE r", id=rule_id)
    finally:
        client.close()


def run_benchmark_rule(
    rule_id: str,
    org_id: Optional[str] = None,
    org_ods_code: Optional[str] = None,
    scope_type: str = "gp",
) -> Dict[str, Any]:
    """Execute a benchmark rule: run its Cypher against Patient Graph, write results to BenchmarkValue.

    Returns {status, count, error?}.
    """
    rule = get_benchmark_rule(rule_id)
    if not rule:
        return {"status": "error", "error": f"BenchmarkRule/{rule_id} not found"}

    qd = rule.get("query_definition") or {}
    benchmark_set_id = rule.get("benchmark_set_id") or f"computed-{rule_id}"
    output_metric_id = rule.get("output_metric_id") or rule.get("name", "value")

    try:
        cypher, cypher_params = generate_cypher(qd)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    if org_ods_code:
        from services.fhir_api.app.config.scopes import SCOPE_PARAM_MAP

        param_name = SCOPE_PARAM_MAP.get(scope_type)
        if param_name:
            cypher_params[param_name] = org_ods_code

    patient_client = PatientGraphClient()
    try:
        results = patient_client.run(cypher, **cypher_params)
    finally:
        patient_client.close()

    values: List[Dict[str, Any]] = []
    scope_id = org_id or "all"
    scope_name = org_id or "All"
    scope_type_actual = rule.get("scope", "all")
    if scope_type_actual == "practice" and org_ods_code:
        scope_id = org_ods_code
        scope_name = org_ods_code
    elif scope_type_actual == "alliance":
        scope_type_actual = "cancer_alliance"
    elif scope_type_actual == "all":
        scope_type_actual = "national"
        scope_id = "england"
        scope_name = "England"

    for row in results:
        name = row.get("name", "Total")
        value = row.get("value", 0)
        metric_id = (
            f"{output_metric_id}.{name}" if name != "Total" else output_metric_id
        )
        values.append(
            {
                "audit_id": benchmark_set_id,
                "metric_id": metric_id,
                "scope_id": scope_id,
                "scope_type": scope_type_actual,
                "scope_name": scope_name,
                "value": value,
                "unit": "count",
                "label": name,
                "category": output_metric_id,
                "source": "computed",
            }
        )

    if values:
        upsert_benchmark_values(benchmark_set_id, values)
        create_benchmark_set(
            {
                "id": benchmark_set_id,
                "name": rule.get("name", benchmark_set_id),
                "source": "computed",
            }
        )

    client = KnowledgeGraphClient()
    try:
        client.run(
            "MATCH (r:BenchmarkRule {id: $id}) SET r.last_run_at = datetime(), r.last_run_status = $status",
            id=rule_id,
            status="completed",
        )
    finally:
        client.close()

    return {"status": "completed", "count": len(values)}


def _slug(name: str) -> str:
    """Convert name to URL-safe slug."""
    return (
        "".join(c if c.isalnum() or c in "-_" else "_" for c in name.lower()).strip("_")
        or "benchmark-set"
    )


def _serialize_datetime(dt: Any) -> Optional[str]:
    """Serialize Neo4j datetime to ISO string."""
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)
