"""FHIR Measure CRUD and $evaluate-measure endpoints."""

from __future__ import annotations

import base64
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from libs.auth.tenant_context import TenantContext, get_tenant_context
from services.fhir_api.app.config.scopes import SCOPE_PARAM_MAP
from services.fhir_api.app.services import library_service, measure_service
from services.fhir_api.app.services.cypher_generator import generate_cypher
from services.fhir_api.app.services.org_resolver import get_org_by_id

router = APIRouter()


@router.get("/Measure")
def search_measures(
    name: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    _count: int = Query(default=100, alias="_count"),
    _offset: int = Query(default=0, alias="_offset"),
):
    items, total = measure_service.search_measures(name=name, status=status, count=_count, offset=_offset)
    return {"resourceType": "Bundle", "type": "searchset", "total": total, "entry": [{"resource": m} for m in items]}


@router.get("/Measure/{measure_id}")
def get_measure(measure_id: str):
    m = measure_service.get_measure(measure_id)
    if not m:
        raise HTTPException(404, f"Measure/{measure_id} not found")
    return m


@router.put("/Measure/{measure_id}")
def upsert_measure(measure_id: str, resource: Dict[str, Any]):
    return measure_service.upsert_measure(measure_id, resource)


@router.delete("/Measure/{measure_id}", status_code=204)
def delete_measure(measure_id: str):
    measure_service.delete_measure(measure_id)


@router.post("/Measure/$preview")
def preview_measure_query(
    body: Dict[str, Any],
    org_id: Optional[str] = Query(default=None),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Preview query results without creating a Library. Requires org_id for scope params."""
    if not org_id:
        raise HTTPException(400, "org_id is required for preview (select an organisation in the header)")
    email = tenant.user_email
    if not email:
        raise HTTPException(401, "User email not found in token")
    org = get_org_by_id(email, org_id)
    if not org:
        raise HTTPException(403, "User does not have access to this organization")
    scope_type = org.get("scopeType", "gp")
    ods_code = org.get("odsCode")
    if not ods_code:
        raise HTTPException(400, "Organization has no odsCode")
    param_name = SCOPE_PARAM_MAP.get(scope_type)
    if not param_name:
        raise HTTPException(400, f"Unknown scope type: {scope_type}")
    # Use org's scope type so cypher matches the selected organisation
    preview_body = {**body, "scopeType": scope_type}
    try:
        cypher, cypher_params = generate_cypher(preview_body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    params = {**cypher_params, param_name: ods_code}
    from libs.neo4j_client.client import PatientGraphClient
    patient_client = PatientGraphClient()
    try:
        results = patient_client.run(cypher, **params)
    finally:
        patient_client.close()
    return {"rows": results}


@router.post("/Measure/$generate")
def generate_measure_query(body: Dict[str, Any]):
    """Generate a Library from a query definition (no-code builder).

    Accepts: nodeLabel, filters, groupBy, scopeType.
    Returns: { libraryId, cypher }.
    """
    try:
        cypher, cypher_params = generate_cypher(body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    library_id = str(uuid.uuid4())
    library = {
        "resourceType": "Library",
        "id": library_id,
        "status": "active",
        "name": body.get("name") or f"Generated query {library_id[:8]}",
        "content": [
            {
                "contentType": "text/plain",
                "title": "cypher",
                "data": base64.b64encode(cypher.encode("utf-8")).decode("ascii"),
            },
        ],
    }
    library_service.upsert_library(library_id, library)
    return {"libraryId": library_id, "cypher": cypher}


@router.get("/Measure/{measure_id}/$evaluate-measure")
def evaluate_measure(
    measure_id: str,
    org_id: Optional[str] = Query(default=None),
    period_start: Optional[str] = Query(default=None, alias="periodStart"),
    period_end: Optional[str] = Query(default=None, alias="periodEnd"),
    ce_status: Optional[str] = Query(default=None),
    ce_status_exclude: Optional[str] = Query(default=None),
    ce_condition_type: Optional[str] = Query(default=None),
    ce_referral_date_start: Optional[str] = Query(default=None),
    ce_referral_date_end: Optional[str] = Query(default=None),
    tenant: TenantContext = Depends(get_tenant_context),
):
    # Option B: require org selection; reject if missing
    if not org_id:
        raise HTTPException(400, "org_id is required for measure evaluation")

    email = tenant.user_email
    if not email:
        raise HTTPException(401, "User email not found in token")

    org = get_org_by_id(email, org_id)
    if not org:
        raise HTTPException(403, "User does not have access to this organization")

    scope_type = org.get("scopeType", "gp")
    ods_code = org.get("odsCode")
    if not ods_code:
        raise HTTPException(400, "Organization has no odsCode")

    # Inject scope param (never trust client-sent scope params)
    param_name = SCOPE_PARAM_MAP.get(scope_type)
    if param_name:
        params = {param_name: ods_code}
    else:
        params = {}

    if period_start:
        params["periodStart"] = period_start
    if period_end:
        params["periodEnd"] = period_end
    if ce_status:
        params["ce_status"] = [s.strip() for s in ce_status.split(",") if s.strip()]
    if ce_status_exclude:
        params["ce_status_exclude"] = [s.strip() for s in ce_status_exclude.split(",") if s.strip()]
    if ce_condition_type:
        params["ce_condition_type"] = [s.strip() for s in ce_condition_type.split(",") if s.strip()]
    if ce_referral_date_start:
        params["ce_referral_date_start"] = ce_referral_date_start
    if ce_referral_date_end:
        params["ce_referral_date_end"] = ce_referral_date_end

    org_name = org.get("name") or org.get("displayName") or org_id
    params["_org_id"] = org_id
    params["_org_name"] = org_name

    result = measure_service.evaluate_measure(measure_id, params)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result
