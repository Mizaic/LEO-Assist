"""NHS Organisation Data Service (ODS) ORD API client.

Atlas trace:
  DO: DO-273A4EC4
  DI: DI-C978B245
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-273A4EC4")

Migrated from the deprecated FHIR STU3 endpoint (retired December 2025) to the
ORD 2-0-0 API, which is supported until at least September 2026.

ORD endpoint:
  GET https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations/{ods_code}

No authentication required — the ORD API is public.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

ORD_BASE_URL = "https://directory.spineservices.nhs.uk/ORD/2-0-0/organisations"

# Maps ORD primary role IDs → our org type labels.
# Verified against live ORD API March 2026.
_ORD_TYPE_MAP: dict[str, str] = {
    "RO177": "gp",  # PRESCRIBING COST CENTRE — primary role for GP practices
    "RO76": "gp",  # GP PRACTICE — secondary role, used as fallback
    "RO272": "pcn",  # PRIMARY CARE NETWORK
    "RO98": "icb",  # CLINICAL COMMISSIONING GROUP / ICB
    "RO209": "alliance",  # CANCER ALLIANCE (was incorrectly RO72 in STU3 client)
}

# Active relationship IDs that indicate a commissioned/operated-by parent.
_PARENT_REL_IDS = {"RE4", "RE6"}  # RE4=Operated by, RE6=Commissioned by


class OdsNotFoundError(Exception):
    """Raised when ODS returns 404 for an ODS code."""


class OdsApiError(Exception):
    """Raised when ODS returns an unexpected error response."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class OdsRateLimitError(OdsApiError):
    """Raised when ODS returns HTTP 429 Too Many Requests."""


class OdsAccessError(OdsApiError):
    """Raised when ODS returns HTTP 403 Forbidden (org exists but access is restricted)."""


@dataclass
class OdsOrg:
    """Parsed ODS organisation record."""

    ods_code: str
    name: str
    status: str  # "Active" | "Inactive"
    org_type: str  # "gp" | "pcn" | "icb" | "alliance" | "unknown"
    address: dict  # {line1, city, postcode}
    part_of_ods: str | None = None  # ODS code of active parent org, if present


def get_org(ods_code: str, timeout: float = 10.0) -> OdsOrg:
    """Fetch and parse an organisation from the NHS ODS ORD 2-0-0 API.

    Raises:
        OdsNotFoundError:  organisation not found (HTTP 404)
        OdsAccessError:    access restricted (HTTP 403) — non-fatal, skip silently
        OdsRateLimitError: rate limited (HTTP 429)
        OdsApiError:       any other HTTP or parse error
    """
    url = f"{ORD_BASE_URL}/{ods_code.upper().strip()}"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers={"Accept": "application/json"})
    except httpx.TimeoutException as exc:
        raise OdsApiError(f"ODS API timeout for {ods_code}") from exc
    except httpx.RequestError as exc:
        raise OdsApiError(f"ODS API connection error for {ods_code}: {exc}") from exc

    if resp.status_code == 404:
        raise OdsNotFoundError(f"ODS code not found: {ods_code}")
    if resp.status_code == 403:
        # ODS returns 403 for some org types (e.g. commissioning regions, umbrella bodies).
        # Treat as non-fatal — the org exists but we can't validate it.
        raise OdsAccessError(f"ODS access restricted for {ods_code}", status_code=403)
    if resp.status_code == 429:
        raise OdsRateLimitError(f"ODS API rate limited for {ods_code}", status_code=429)
    if resp.status_code != 200:
        raise OdsApiError(
            f"ODS API returned {resp.status_code} for {ods_code}",
            status_code=resp.status_code,
        )

    try:
        data = resp.json()
    except Exception as exc:
        raise OdsApiError(f"ODS API returned non-JSON for {ods_code}") from exc

    return _parse(ods_code, data)


def _parse(ods_code: str, data: dict) -> OdsOrg:
    """Parse an ORD 2-0-0 Organisation response into OdsOrg."""
    org = data.get("Organisation", {})

    name: str = org.get("Name", "")
    status: str = org.get("Status", "Active")  # "Active" | "Inactive"

    # Org type — prefer primary role, fall back to any matching secondary role
    org_type = "unknown"
    roles = _ensure_list(org.get("Roles", {}).get("Role"))
    # Try primary role first
    for role in roles:
        if (
            role.get("primaryRole") is True
            or str(role.get("primaryRole", "")).lower() == "true"
        ):
            code = role.get("id", "")
            if code in _ORD_TYPE_MAP:
                org_type = _ORD_TYPE_MAP[code]
                break
    # Fall back to any active secondary role
    if org_type == "unknown":
        for role in roles:
            code = role.get("id", "")
            if code in _ORD_TYPE_MAP and role.get("Status") == "Active":
                org_type = _ORD_TYPE_MAP[code]
                break

    # Address from GeoLoc
    address: dict = {}
    location = org.get("GeoLoc", {}).get("Location", {})
    if location:
        address = {
            "line1": location.get("AddrLn1", ""),
            "city": location.get("Town", ""),
            "postcode": location.get("PostCode", ""),
        }

    # Active parent org from Rels (RE4 = Operated by, RE6 = Commissioned by)
    part_of_ods: str | None = None
    rels = _ensure_list(org.get("Rels", {}).get("Rel"))
    for rel in rels:
        if rel.get("id") in _PARENT_REL_IDS and rel.get("Status") == "Active":
            ext = rel.get("Target", {}).get("OrgId", {}).get("extension")
            if ext:
                part_of_ods = ext
                break

    return OdsOrg(
        ods_code=ods_code.upper(),
        name=name,
        status=status,
        org_type=org_type,
        address=address,
        part_of_ods=part_of_ods,
    )


def _ensure_list(value: list | dict | None) -> list:
    """ORD API returns a single item as a dict and multiple as a list — normalise to list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
