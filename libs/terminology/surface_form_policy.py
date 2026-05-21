"""Surface-form approval status rules for resolve and admin workflows.

Atlas trace:
  UN: UN-72B60B2D
  DI: DI-47D2CD86
  DO: DO-5A88E0B9
"""

from __future__ import annotations

# Legacy loader upserts used status='active'; treat as approved for resolve.
RESOLVABLE_SURFACE_FORM_STATUSES: frozenset[str] = frozenset({"approved", "active"})

PENDING_SURFACE_FORM_STATUS = "pending"
APPROVED_SURFACE_FORM_STATUS = "approved"
DEACTIVATED_SURFACE_FORM_STATUS = "deactivated"
REVOKED_SURFACE_FORM_STATUS = "revoked"


def is_resolvable_surface_form_status(status: str | None) -> bool:
    """Return True when a SurfaceForm status may be used at resolve time."""
    if not status:
        return True
    return str(status).strip().lower() in RESOLVABLE_SURFACE_FORM_STATUSES


def cypher_resolvable_surface_form_where(alias: str = "sf") -> str:
    """Cypher predicate: SurfaceForm node is approved for runtime resolve."""
    return (
        f"coalesce({alias}.status, 'approved') "
        f"IN ['approved', 'active']"
    )
