"""Atlas public NCR facade: list, get, create, update, and journal notes.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Uses the same service-token pattern as verification-runs.
Does not call advance, close, or cancel.

Atlas: DI-287FFFD0 / DI-ED5A9AC3
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from libs.atlas_qms.ncr_shape import (
    LEO_CDS_PRODUCT_ID,
    compact_ncr,
    filter_ncrs,
    validate_ncr_create,
)
from libs.atlas_qms.redact import contains_identifiers, redact_for_atlas

_SUFFIXES = ("/validation-runs", "/verification-runs", "/non-conformances")


class NcrNotConfigured(RuntimeError):
    """Raised when Atlas quality-system env is missing."""


class NcrClientError(RuntimeError):
    """Raised when Atlas rejects or cannot complete an NCR call."""


def qms_base_url() -> str:
    explicit = os.getenv("ATLAS_QMS_GRAPH_BASE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    for key in (
        "ATLAS_NCR_BASE_URL",
        "ATLAS_VALIDATION_RUNS_BASE_URL",
        "ATLAS_VERIFICATION_RUNS_BASE_URL",
    ):
        raw = os.getenv(key, "").strip().rstrip("/")
        for suffix in _SUFFIXES:
            if raw.endswith(suffix):
                return raw[: -len(suffix)]
    return ""


# Atlas sits behind bot protection that rejects Python-urllib's default
# signature. Match the verification-runs client User-Agent.
_ATLAS_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def facade_headers(token: str, org_id: str) -> dict[str, str]:
    """Public NCR facade auth. Missing org returns Atlas 400 ORGANIZATION_REQUIRED."""
    return {
        "X-Service-Token": token,
        "X-Organization-ID": org_id,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": _ATLAS_UA,
    }


def list_product_ncrs(query: str = "", limit: int = 50) -> list[dict[str, str]]:
    params = urllib.parse.urlencode({"product_id": LEO_CDS_PRODUCT_ID, "limit": 200})
    payload = _request("GET", f"/non-conformances?{params}")
    rows = [compact_ncr(item) for item in _items(payload)]
    product_only = [row for row in rows if row["product_id"] == LEO_CDS_PRODUCT_ID]
    return filter_ncrs(product_only, query)[: max(1, min(limit, 200))]


def get_product_ncr(nc_id: str) -> dict[str, str]:
    safe_id = urllib.parse.quote(nc_id.strip(), safe="")
    if not safe_id:
        raise NcrClientError("A non-conformance id is required.")
    payload = _request("GET", f"/non-conformances/{safe_id}")
    if not isinstance(payload, dict):
        raise NcrClientError("Atlas did not return a non-conformance record.")
    row = compact_ncr(payload)
    if row["product_id"] and row["product_id"] != LEO_CDS_PRODUCT_ID:
        raise NcrClientError("That record is not for this product.")
    return row


def create_product_ncr(
    *,
    title: str,
    description: str,
    severity: str,
) -> dict[str, str]:
    body = validate_ncr_create(title=title, description=description, severity=severity)
    created = _request("POST", "/non-conformances", body)
    if isinstance(created, dict):
        return compact_ncr(created)
    raise NcrClientError("Atlas did not return a non-conformance record.")


def update_product_ncr(
    nc_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
) -> dict[str, str]:
    safe_id = _safe_nc_id(nc_id)
    body: dict[str, str] = {}
    if title is not None:
        body["title"] = safe_atlas_text(title)
    if description is not None:
        body["description"] = safe_atlas_text(description)
    if not body:
        raise NcrClientError("Nothing to update.")
    updated = _request("PATCH", f"/non-conformances/{safe_id}", body)
    if isinstance(updated, dict):
        return compact_ncr(updated)
    raise NcrClientError("Atlas did not return a non-conformance record.")


def add_product_ncr_comment(nc_id: str, text: str) -> dict[str, str]:
    safe_id = _safe_nc_id(nc_id)
    payload = _request(
        "POST",
        f"/non-conformances/{safe_id}/comments",
        {"text": safe_atlas_text(text)},
    )
    if isinstance(payload, dict):
        return {str(k): str(v) for k, v in payload.items()}
    return {"ok": "true"}


def list_product_ncr_activity(nc_id: str) -> list[dict[str, Any]]:
    safe_id = _safe_nc_id(nc_id)
    payload = _request("GET", f"/non-conformances/{safe_id}/activity")
    return _items(payload)


def safe_atlas_text(text: str) -> str:
    clean = redact_for_atlas(text)
    if contains_identifiers(clean):
        raise NcrClientError(
            "Could not send that text. It still looks like a patient number."
        )
    return clean


def _safe_nc_id(nc_id: str) -> str:
    safe_id = urllib.parse.quote(nc_id.strip(), safe="")
    if not safe_id:
        raise NcrClientError("A non-conformance id is required.")
    return safe_id


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("items") or payload.get("results") or []
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    base, token, org = _facade_config()
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers=facade_headers(token, org),
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise NcrClientError(_http_error(exc)) from exc
    except urllib.error.URLError as exc:
        raise NcrClientError("Could not reach Atlas. Try again.") from exc
    if not raw:
        return {}
    return json.loads(raw)


def _facade_config() -> tuple[str, str, str]:
    base = qms_base_url()
    token = os.getenv("QMS_SERVICE_TOKEN", "").strip()
    org = os.getenv("ATLAS_ORGANIZATION_ID", "").strip()
    if not base or not token or not org:
        raise NcrNotConfigured(
            "Could not reach the product non-conformance list. "
            "Ask an admin to connect Atlas."
        )
    return base, token, org


def _http_error(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return "Atlas could not save that non-conformance."
    text = str(payload)
    if "ORGANIZATION_REQUIRED" in text:
        return "Atlas needs the organisation header."
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message") or payload.get("code")
        if detail:
            return str(detail)
    return "Atlas could not save that non-conformance."
