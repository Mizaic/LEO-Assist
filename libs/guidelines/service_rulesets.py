"""Service-to-guideline catalogue for pipeline matching.

Atlas:
  DI: DI-D260D249
  DO: DO-C9F7BFC8
  VT: VT-76A1816F
"""

from __future__ import annotations

BREAST_SERVICE_ID = "117038"
GYNAE_SERVICE_ID = "7980224"
BREAST_GUIDELINE_IDS = ("NG12",)
GYNAE_GUIDELINE_IDS = ("NG12",)
PLACEHOLDER_GUIDELINE_IDS = frozenset({"val-gardena-defaults", "val-gardena-default"})

_SERVICE_GUIDELINES: dict[str, tuple[str, ...]] = {
    BREAST_SERVICE_ID: BREAST_GUIDELINE_IDS,
    GYNAE_SERVICE_ID: GYNAE_GUIDELINE_IDS,
}


def guideline_ids_for_service(service_id: str | None) -> tuple[str, ...]:
    """Return compiled guideline ids bound to a receiving service."""
    key = str(service_id or "").strip()
    return _SERVICE_GUIDELINES.get(key, ())


def is_placeholder_guideline_id(guideline_id: str) -> bool:
    """True when a Service guideline id is a seed default, not a ruleset."""
    return guideline_id.strip().lower() in PLACEHOLDER_GUIDELINE_IDS


def resolve_primary_guideline_ids(
    service_id: str | None,
    graph_ids: list[str] | None = None,
    *,
    ers_service_id: str | None = None,
) -> list[str]:
    """Prefer compiled catalogue ids over a placeholder Service binding."""
    catalogue = list(guideline_ids_for_service(service_id))
    if not catalogue:
        catalogue = list(guideline_ids_for_service(ers_service_id))
    real = [
        item.strip()
        for item in (graph_ids or [])
        if item and str(item).strip() and not is_placeholder_guideline_id(str(item))
    ]
    if real:
        return real
    if catalogue:
        return catalogue
    return [item.strip() for item in (graph_ids or []) if str(item).strip()]
