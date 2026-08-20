"""Shape and validate product non-conformance records.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Atlas: DI-287FFFD0
"""

from __future__ import annotations

import re
from typing import Any

from libs.atlas_qms.redact import contains_identifiers, redact_for_atlas

LEO_CDS_PRODUCT_ID = "PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4"
LOCKED_NC_TYPE = "product"
LOCKED_DETECTION_SOURCE = "testing"
NCR_SEVERITIES = frozenset({"catastrophic", "major", "minor", "cosmetic"})
# SOP-18 lifecycle from Atlas advance_non_conformance gates.
NCR_OPEN_STATUSES = frozenset(
    {"identified", "contained", "investigated", "disposition_pending"}
)
NCR_CLOSED_STATUSES = frozenset({"closed", "cancelled", "canceled"})
_MIN_TITLE = 5
_MIN_DESCRIPTION = 5
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_ID_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class NcrShapeError(ValueError):
    """Raised when an NCR create payload is not valid."""


def compact_ncr(raw: dict[str, Any]) -> dict[str, str]:
    """Keep list fields only. Drop embeddings and other bulk."""
    return {
        "id": str(raw.get("id") or raw.get("dc_id") or ""),
        "title": str(raw.get("title") or ""),
        "description": str(raw.get("description") or ""),
        "severity": str(raw.get("severity") or ""),
        "status": str(raw.get("status") or ""),
        "created_at": str(raw.get("created_at") or ""),
        "nc_type": str(raw.get("nc_type") or ""),
        "detection_source": str(raw.get("detection_source") or ""),
        "product_id": str(raw.get("product_id") or ""),
    }


def is_open_ncr(row: dict[str, str]) -> bool:
    status = str(row.get("status") or "").strip().lower()
    return status not in NCR_CLOSED_STATUSES


def looks_like_ncr_id(text: str) -> bool:
    raw = text.strip()
    if _UUID_RE.fullmatch(raw):
        return True
    return bool(_ID_TOKEN_RE.fullmatch(raw))


def filter_ncrs(rows: list[dict[str, str]], query: str) -> list[dict[str, str]]:
    needle = " ".join(query.lower().split())
    if needle:
        exact = [row for row in rows if _id_matches(row, needle)]
        if exact:
            return exact
    open_rows = [row for row in rows if is_open_ncr(row)]
    if not needle:
        return open_rows
    return [row for row in open_rows if needle in _haystack(row)]


def _id_matches(row: dict[str, str], needle: str) -> bool:
    return needle in {
        str(row.get("id") or "").lower(),
        str(row.get("dc_id") or "").lower(),
    }


def validate_ncr_create(
    *, title: str, description: str, severity: str
) -> dict[str, str]:
    clean_title = _safe_field(" ".join(title.split()), "Title")
    clean_desc = _safe_field(" ".join(description.split()), "Description")
    clean_sev = severity.strip().lower()
    if len(clean_title) < _MIN_TITLE:
        raise NcrShapeError("Title needs at least five characters.")
    if len(clean_desc) < _MIN_DESCRIPTION:
        raise NcrShapeError("Say what went wrong in at least five characters.")
    if clean_sev not in NCR_SEVERITIES:
        raise NcrShapeError("Severity must be catastrophic, major, minor, or cosmetic.")
    return {
        "title": clean_title,
        "description": clean_desc,
        "severity": clean_sev,
        "product_id": LEO_CDS_PRODUCT_ID,
        "nc_type": LOCKED_NC_TYPE,
        "detection_source": LOCKED_DETECTION_SOURCE,
    }


def _safe_field(text: str, label: str) -> str:
    clean = redact_for_atlas(text)
    if contains_identifiers(clean):
        raise NcrShapeError(f"{label} still looks like a patient number.")
    return clean


def build_create_description(description: str, run_id: str = "", why: str = "") -> str:
    parts = [" ".join(description.split())]
    why_text = " ".join(why.split())
    run_text = " ".join(run_id.split())
    if why_text:
        parts.append(f"Why opened: {why_text}")
    if run_text:
        parts.append(f"Pipeline run: {run_text}")
    return "\n\n".join(parts)


def _haystack(row: dict[str, str]) -> str:
    return " ".join(
        [
            row.get("title", ""),
            row.get("description", ""),
            row.get("id", ""),
            row.get("dc_id", ""),
            row.get("status", ""),
            row.get("severity", ""),
            row.get("nc_type", ""),
            row.get("detection_source", ""),
        ]
    ).lower()
