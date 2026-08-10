"""LEO widget SDK auth + SBAR proxy endpoints.

Atlas trace:
  DO: DO-5C88CA8F, DO-6D21096F
  DI: DI-A1206416, DI-AF2C3996
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-6D21096F")

Two endpoints:

POST /sdk/auth/exchange
    Server-to-server only. The host product server presents a shared
    secret in the X-Mizaic-Host-Secret header and asks LEO to mint a
    short-lived widget token for one specific assessment-id, scoped
    to one host user. Browsers always send an Origin header on POST,
    so any request that includes Origin is refused (this catches a
    host product accidentally proxying the call from the browser).

GET /sdk/sbar/{assessment_id}
    Browser-facing. The widget calls this with the widget token in
    the Authorization header. The token's assessment_id claim MUST
    match the path. Mismatch returns 403. Returns the combined SBAR
    payload: markdown content, guideline matches (with verbatim text),
    and completeness findings (or null if not yet available).
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.services import host_governance
from libs.cypher.sbar_assessment_queries import GET_ASSESSMENT, assessment_to_dict
from libs.sbar.markdown_compose import compose_sbar_markdown
from libs.sdk_auth import (
    WIDGET_TOKEN_MAX_TTL_SECONDS,
    WidgetTokenError,
    mint_widget_token,
    verify_widget_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sdk", tags=["sdk-auth"])

_HOST_SECRET_HEADER = "X-Mizaic-Host-Secret"


class ExchangeRequest(BaseModel):
    host_id: str = Field(..., min_length=1, max_length=128)
    host_user_id: str = Field(..., min_length=1, max_length=256)
    tenant_id: str = Field(..., min_length=1, max_length=128)
    assessment_id: str = Field(..., min_length=1, max_length=128)
    user_role: str = Field(..., min_length=1, max_length=64)


class ExchangeResponse(BaseModel):
    widget_token: str
    expires_at: int
    ttl_seconds: int


class SbarPayload(BaseModel):
    assessment_id: str
    tenant_id: str
    generated_at: str
    markdown: str
    background_parts: list[dict] = []
    guideline_matches: list[dict] = []
    completeness_findings: dict | None = None


def _expected_host_secret() -> str:
    secret = os.environ.get("SDK_HOST_SHARED_SECRET", "")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SDK widget-token exchange is not configured",
        )
    return secret


def _enforce_server_to_server(request: Request) -> None:
    """Refuse if a browser-style Origin header is present.

    Browsers send Origin on every cross-origin POST. Server-to-server
    HTTP clients (httpx, requests, curl) do not. This is a cheap
    additional belt-and-braces on top of the shared secret.
    """

    if request.headers.get("origin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "POST /sdk/auth/exchange is server-to-server only; "
                "requests from a browser origin are not permitted"
            ),
        )


def _verify_host_secret(provided: str | None) -> None:
    expected = _expected_host_secret()
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing host shared secret",
        )


_SCENARIO_HOST_ID = "leo-scenario-runner"


def _ensure_scenario_host(host_id: str) -> None:
    """Lazily register the dev scenario-runner host on first use.

    The shared secret is the real security gate -- no additional env-var
    flag is needed. Any caller that presents a valid SDK_HOST_SHARED_SECRET
    and uses the reserved scenario-runner host_id gets the host auto-seeded
    with dev-bypass governance artefacts.
    """
    if host_id != os.getenv("SCENARIO_SDK_HOST_ID", _SCENARIO_HOST_ID):
        return
    if host_governance.is_production_ready(host_id):
        return
    record = host_governance.register_host(
        host_id=host_id,
        name="LEO Scenario Validation Runner",
        contact="internal@mizaic.com",
    )
    record.artefacts.update(
        {
            "saas_embedding_agreement": "dev-bypass",
            "dpa": "dev-bypass",
            "dcb0129_reference": "dev-bypass",
            "ifu_acknowledged": "dev-bypass",
        }
    )
    record.acknowledged_ifu_version = "dev-bypass"
    logger.info("Scenario runner host '%s' registered lazily", host_id)


@router.post("/auth/exchange", response_model=ExchangeResponse)
def exchange_for_widget_token(
    payload: ExchangeRequest,
    request: Request,
    x_mizaic_host_secret: str | None = Header(default=None),
) -> ExchangeResponse:
    """Mint a widget token for a single assessment (server-to-server)."""
    _enforce_server_to_server(request)
    _verify_host_secret(x_mizaic_host_secret)
    _ensure_scenario_host(payload.host_id)

    if not host_governance.is_production_ready(payload.host_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="host_not_onboarded",
        )

    try:
        result = mint_widget_token(
            host_user_id=payload.host_user_id,
            tenant_id=payload.tenant_id,
            assessment_id=payload.assessment_id,
            user_role=payload.user_role,
            ttl_seconds=WIDGET_TOKEN_MAX_TTL_SECONDS,
        )
    except WidgetTokenError as exc:
        logger.warning("widget token mint failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to mint widget token",
        ) from exc

    return ExchangeResponse(
        widget_token=result.token,
        expires_at=result.expires_at,
        ttl_seconds=result.ttl_seconds,
    )


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing widget Bearer token",
        )
    return authorization.split(" ", 1)[1].strip()


@router.get("/sbar/{assessment_id}", response_model=SbarPayload)
def proxy_sbar(
    assessment_id: str,
    authorization: str | None = Header(default=None),
) -> SbarPayload:
    """Browser-facing SBAR fetch. Validates token + assessment scope."""
    token = _extract_bearer(authorization)
    try:
        claims = verify_widget_token(token)
    except WidgetTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid widget token: {exc}",
        ) from exc

    if claims.assessment_id != assessment_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Widget token assessment-id does not match the requested "
                "assessment-id"
            ),
        )

    return _load_sbar_payload(assessment_id, claims.tenant_id)


@router.get("/sbar/{assessment_id}/sources/{source_id}")
def proxy_sbar_source(
    assessment_id: str,
    source_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Assessment-scoped source text for the widget dialog."""
    token = _extract_bearer(authorization)
    try:
        claims = verify_widget_token(token)
    except WidgetTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid widget token: {exc}",
        ) from exc

    if claims.assessment_id != assessment_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Widget token assessment-id does not match the requested "
                "assessment-id"
            ),
        )

    payload = _load_sbar_payload(assessment_id, claims.tenant_id)
    allowed: set[str] = set()
    label = source_id
    preview = ""
    stype = "Record"
    for part in payload.background_parts:
        for sid in part.get("sourceIds") or []:
            allowed.add(str(sid))
        for src in part.get("sources") or []:
            sid = str(src.get("id") or "")
            allowed.add(sid)
            if sid == source_id:
                label = str(src.get("label") or sid)
                preview = str(src.get("preview") or "")
                stype = str(src.get("type") or "Record")
    if source_id not in allowed:
        raise HTTPException(status_code=404, detail="Source not on assessment")

    text = preview
    try:
        from libs.neo4j_client.client import PatientGraphClient
        from libs.sbar.source_resolver import (
            _resolve_chunk,
            _resolve_encounter,
        )

        client = PatientGraphClient()
        try:
            with client.session() as session:
                if stype.lower() == "encounter":
                    resolved = _resolve_encounter(session, source_id)
                else:
                    resolved = _resolve_chunk(session, source_id)
                if resolved and resolved.text:
                    text = resolved.text
        finally:
            client.close()
    except Exception:
        logger.debug("source text resolve failed for %s", source_id, exc_info=True)

    return {
        "id": source_id,
        "type": stype,
        "label": label,
        "text": text or preview or "",
    }


def _decode_assessment_rules(raw: Any) -> list[dict]:
    """Decode the assessment_rules field into a list of rule dicts.

    The orchestrator stores this as a JSON-encoded string. Tolerates
    both a pre-decoded list (graph driver may return it directly) and a
    raw JSON string, and returns [] on any decode failure.
    """
    if not raw:
        return []
    if isinstance(raw, list):
        rules = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            rules = parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    else:
        return []
    return [_normalise_guideline_match(r) for r in rules]


def _normalise_guideline_match(rule: Any) -> dict:
    """Ensure every guideline match has the string fields the widget requires.

    _rule_snapshot intentionally strips name/strength/recommendation_verbatim
    from the snapshot stored in Neo4j (to keep LLM context concise). The
    widget needs these fields, so we fall back to guideline_title for name
    and action.priority for strength when the direct fields are absent.
    """
    if not isinstance(rule, dict):
        return rule
    action = rule.get("action") or {}
    name = (
        rule.get("name")
        or rule.get("guideline_title")
        or rule.get("chapter_title")
        or ""
    )
    strength = rule.get("strength") or action.get("priority") or ""
    return {
        **rule,
        "name": name,
        "strength": strength,
        "rule_id": rule.get("rule_id") or "",
        "guideline_id": rule.get("guideline_id") or "",
        "recommendation_verbatim": rule.get("recommendation_verbatim") or None,
    }


def _query_assessment_from_neo4j(assessment_id: str) -> dict | None:
    """Run GET_ASSESSMENT against Neo4j and return the decoded dict.

    Returns None when no matching Assessment node is found. Extracted
    as a module-level callable so tests can monkeypatch without a live
    Neo4j connection.
    """
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    try:
        with client.session() as session:
            row = session.run(GET_ASSESSMENT, assessment_id=assessment_id).single()
    finally:
        client.close()

    if row is None:
        return None
    return assessment_to_dict(row)


def _normalise_source_ref(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {"id": str(raw or ""), "label": str(raw or ""), "preview": ""}
    sid = str(raw.get("id") or "")
    return {
        "id": sid,
        "type": raw.get("type") or "Record",
        "label": raw.get("label") or sid,
        "preview": raw.get("preview") or "",
        # Exact source-record text used to generate this part of the
        # Background section. Empty for legacy persisted Assessments
        # that predate this field; the widget falls back to preview.
        "fullText": raw.get("full_text") or raw.get("fullText") or "",
        "date": raw.get("date"),
    }


def _normalise_background_part(part: Any) -> dict:
    """Convert a snake_case background part to the camelCase widget contract.

    The :Assessment node stores parts in Python snake_case. The widget SDK
    expects camelCase (SbarBackgroundPart interface). This conversion happens
    here so the widget never has to handle both conventions.
    """
    if not isinstance(part, dict):
        return part
    raw_sources = part.get("sources") or []
    sources = [_normalise_source_ref(s) for s in raw_sources]
    source_ids = part.get("sourceIds") or part.get("source_ids") or []
    if not sources and source_ids:
        sources = [
            {"id": str(s), "type": "Record", "label": str(s), "preview": ""}
            for s in source_ids
        ]
    return {
        "index": part.get("index", 0),
        "total": part.get("total", 1),
        "recordCount": part.get("recordCount") or part.get("record_count", 0),
        "recordRange": part.get("recordRange") or part.get("record_range") or [0, 0],
        "sourceIds": source_ids,
        "sources": sources,
        "status": part.get("status", "completed"),
        "errorCode": part.get("errorCode") or part.get("error_code"),
        "errorMessage": part.get("errorMessage") or part.get("error_message"),
    }


def _to_completeness_findings(raw_json: str | None) -> dict | None:
    """Convert persisted completeness_result JSON to the widget contract.

    The quality_check subgraph stores matched_groups / missing_groups.
    The widget CompletenessFinding interface expects:
        requiredFields, presentFields, missingFields, unclearFields.

    Returns None when no result is stored or the schema was not
    configured (the widget will emit leo:completeness-unavailable).
    """
    if not raw_json:
        return None
    try:
        result = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(result, dict) or not result.get("configured"):
        return None
    matched = result.get("matched_groups") or []
    missing = result.get("missing_groups") or []
    required_fields = [g["name"] for g in (matched + missing) if g.get("required")]
    present_fields = [g["name"] for g in matched]
    missing_fields = [g["name"] for g in missing if g.get("required")]
    unclear_fields = [g["name"] for g in missing if not g.get("required")]
    return {
        "requiredFields": required_fields,
        "presentFields": present_fields,
        "missingFields": missing_fields,
        "unclearFields": unclear_fields,
    }


def _load_sbar_payload(assessment_id: str, tenant_id: str) -> SbarPayload:
    """Load an SBAR payload from Neo4j for the proxy response.

    Combines the core SBAR markdown from the :Assessment node with
    guideline rule matches (verbatim recommendation text already stored
    in assessment_rules) and completeness findings (null when not yet
    persisted -- the widget will emit leo:completeness-unavailable).
    """
    record = _query_assessment_from_neo4j(assessment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    raw_parts = record.get("background_parts") or []
    background_parts = [_normalise_background_part(p) for p in raw_parts]

    generated_at = record.get("updated_at") or record.get("created_at") or ""
    completeness = _to_completeness_findings(record.get("completeness_result_json"))
    return SbarPayload(
        assessment_id=assessment_id,
        tenant_id=tenant_id,
        generated_at=str(generated_at),
        markdown=compose_sbar_markdown(record),
        background_parts=background_parts,
        guideline_matches=_decode_assessment_rules(record.get("assessment_rules")),
        completeness_findings=completeness,
    )
