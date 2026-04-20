"""Density preference helpers (Wave E Phase 1 / DI-LEO-AI-169).

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Reads and writes the per-practitioner UI density preference. Modeled after
``libs/auth/role_state.py`` so callers get the same fail-soft behaviour: any
graph error returns ``None`` and the UI falls back to the comfortable
default.
"""

from __future__ import annotations

import logging

from libs.cypher.density_queries import (
    ALLOWED_DENSITIES,
    GET_PRACTITIONER_DENSITY,
    SET_PRACTITIONER_DENSITY,
)
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)


class DensityNotAllowedError(ValueError):
    """Raised when the requested density value is not in the allowlist."""


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def fetch_density(email: str) -> str | None:
    """Return the practitioner's stored density preference, or ``None``.

    Returns ``None`` for missing practitioners, missing preferences, or any
    graph error (logged at WARNING). The UI falls back to ``comfortable``
    in that case.
    """

    normalized = _normalize_email(email)
    if not normalized:
        return None
    client = PatientGraphClient()
    try:
        rows = client.run(GET_PRACTITIONER_DENSITY, email=normalized)
        if not rows:
            return None
        value = rows[0].get("density_preference")
        if isinstance(value, str) and value in ALLOWED_DENSITIES:
            return value
        return None
    except Exception as exc:
        logger.warning("density_state.fetch_failed email=%s err=%s", normalized, exc)
        return None
    finally:
        client.close()


def set_density(email: str, density: str) -> str:
    """Persist a new density preference and return the stored value.

    Raises ``DensityNotAllowedError`` if ``density`` is not one of the
    allowed values. Raises ``LookupError`` if the practitioner does not
    exist (so the API can surface a 404 rather than silently dropping the
    write).
    """

    normalized = _normalize_email(email)
    if not normalized:
        raise DensityNotAllowedError("missing_email")
    if density not in ALLOWED_DENSITIES:
        raise DensityNotAllowedError(density)
    client = PatientGraphClient()
    try:
        rows = client.run(
            SET_PRACTITIONER_DENSITY,
            email=normalized,
            density=density,
        )
        if not rows:
            raise LookupError(normalized)
        value = rows[0].get("density_preference")
        if not isinstance(value, str) or value not in ALLOWED_DENSITIES:
            return density
        return value
    finally:
        client.close()
