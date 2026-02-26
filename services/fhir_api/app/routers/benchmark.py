"""Benchmark CRUD and run endpoints.

Serves BenchmarkSet, BenchmarkValue, BenchmarkRule, and upload/run operations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from services.fhir_api.app.services import benchmark_service
from services.fhir_api.app.services.benchmark_loader import flatten_benchmarks, infer_structure

router = APIRouter()


@router.get("/sets")
def list_benchmark_sets(
    source: Optional[str] = Query(default=None),
    _count: int = Query(default=100, alias="_count"),
    _offset: int = Query(default=0, alias="_offset"),
):
    """List benchmark sets."""
    return benchmark_service.list_benchmark_sets(source=source, limit=_count, offset=_offset)


@router.post("/sets")
def create_benchmark_set(body: Dict[str, Any]):
    """Create a benchmark set (manual)."""
    return benchmark_service.create_benchmark_set(body)


@router.get("/sets/{set_id}")
def get_benchmark_set(set_id: str):
    """Get a benchmark set by id."""
    s = benchmark_service.get_benchmark_set(set_id)
    if not s:
        raise HTTPException(404, f"BenchmarkSet/{set_id} not found")
    return s


@router.delete("/sets/{set_id}", status_code=204)
def delete_benchmark_set(set_id: str):
    """Delete a benchmark set and all its values."""
    benchmark_service.delete_benchmark_set(set_id)


@router.get("/sets/{set_id}/values")
def get_benchmark_values(
    set_id: str,
    metric_id: Optional[str] = Query(default=None),
    scope_type: Optional[str] = Query(default=None),
):
    """Get benchmark values for a set, optionally filtered."""
    return benchmark_service.get_benchmark_values(set_id, metric_id=metric_id, scope_type=scope_type)


@router.get("/sets/{set_id}/comparison/{metric_id}")
def get_benchmark_comparison(set_id: str, metric_id: str):
    """Get benchmark comparison for one metric across all scopes."""
    return benchmark_service.get_benchmark_comparison(set_id, metric_id)


@router.post("/upload")
def upload_benchmarks(body: Dict[str, Any]):
    """Upload benchmark JSON with mapping. Creates BenchmarkSet and BenchmarkValues.

    Body: { rawJson, templateId?, mapping?, auditId?, name? }
    """
    raw_json = body.get("rawJson")
    if not raw_json:
        raise HTTPException(400, "rawJson is required")

    template_id = body.get("templateId", "ncda")
    audit_id = body.get("auditId")
    name = body.get("name")

    values = flatten_benchmarks(
        raw_json,
        mapping=body.get("mapping"),
        template_id=template_id,
        audit_id=audit_id,
    )
    if not values:
        raise HTTPException(400, "No benchmark values extracted. Check template or mapping.")

    audit_id = audit_id or values[0].get("audit_id", "uploaded")
    if not benchmark_service.get_benchmark_set(audit_id):
        set_data = {
            "id": audit_id,
            "name": name or audit_id,
            "source": "uploaded",
            "audit_year": raw_json.get("audit", {}).get("year"),
            "metadata": raw_json.get("audit", {}),
        }
        benchmark_service.create_benchmark_set(set_data)

    count = benchmark_service.upsert_benchmark_values(audit_id, values)
    return {"audit_id": audit_id, "count": count, "status": "completed"}


@router.post("/infer-structure")
def infer_benchmark_structure(body: Dict[str, Any]):
    """Infer JSON structure for upload wizard step 2."""
    raw_json = body.get("rawJson")
    if not raw_json:
        raise HTTPException(400, "rawJson is required")
    return infer_structure(raw_json)


@router.get("/rules")
def list_benchmark_rules(
    _count: int = Query(default=100, alias="_count"),
    _offset: int = Query(default=0, alias="_offset"),
):
    """List benchmark rules."""
    return benchmark_service.list_benchmark_rules(limit=_count, offset=_offset)


@router.post("/rules")
def create_benchmark_rule(body: Dict[str, Any]):
    """Create a benchmark rule."""
    return benchmark_service.create_benchmark_rule(body)


@router.get("/rules/{rule_id}")
def get_benchmark_rule(rule_id: str):
    """Get a benchmark rule by id."""
    r = benchmark_service.get_benchmark_rule(rule_id)
    if not r:
        raise HTTPException(404, f"BenchmarkRule/{rule_id} not found")
    return r


@router.put("/rules/{rule_id}")
def update_benchmark_rule(rule_id: str, body: Dict[str, Any]):
    """Update a benchmark rule."""
    return benchmark_service.update_benchmark_rule(rule_id, body)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_benchmark_rule(rule_id: str):
    """Delete a benchmark rule."""
    benchmark_service.delete_benchmark_rule(rule_id)


@router.post("/rules/{rule_id}/run")
def run_benchmark_rule(
    rule_id: str,
    org_id: Optional[str] = Query(default=None),
    org_ods_code: Optional[str] = Query(default=None),
    scope_type: str = Query(default="gp"),
):
    """Run a benchmark rule. For Azure Functions or manual trigger."""
    return benchmark_service.run_benchmark_rule(
        rule_id,
        org_id=org_id,
        org_ods_code=org_ods_code,
        scope_type=scope_type,
    )
