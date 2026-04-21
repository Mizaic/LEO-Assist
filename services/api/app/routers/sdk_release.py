"""LEO widget release manifest + CSO advisory channel.

Atlas trace:
  DO: DO-3B62F38E
  DI: DI-3C06AFD0
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3B62F38E")

Two CDN-served endpoints under the Mizaic-controlled origin:

GET /v1/manifest.json
    The active build hash within the pinned major. Cache-Control
    max-age <=60s so a CSO rollback propagates within the
    documented window.

GET /v1/advisory.json
    The active LEO Clinical Safety Officer advisory. The widget
    polls this endpoint on load and every 60s. When active=true the
    widget renders a non-dismissible banner inside the trust
    boundary.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1", tags=["sdk-release"])

_CACHE_CONTROL = "public, max-age=60, must-revalidate"

_state = {
    "manifest": {
        "major": 1,
        "active": "1.0.0",
        "released_at": "2026-04-20T00:00:00Z",
        "notes": "Initial slice 5 placeholder release",
    },
    "advisory": {
        "active": False,
        "severity": None,
        "headline": None,
        "body": None,
        "published_at": None,
    },
}


class ManifestResponse(BaseModel):
    major: int = Field(..., ge=0)
    active: str = Field(..., min_length=1)
    released_at: str
    notes: str


class AdvisoryResponse(BaseModel):
    active: bool
    severity: Literal["info", "safety", "critical"] | None = None
    headline: str | None = None
    body: str | None = None
    published_at: str | None = None


@router.get(
    "/manifest.json",
    response_model=ManifestResponse,
    response_model_exclude_none=False,
)
def get_manifest(response: Response) -> ManifestResponse:
    """Serve the active widget build manifest."""
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return ManifestResponse(**_state["manifest"])


@router.get(
    "/advisory.json",
    response_model=AdvisoryResponse,
    response_model_exclude_none=False,
)
def get_advisory(response: Response) -> AdvisoryResponse:
    """Serve the current CSO clinical safety advisory."""
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return AdvisoryResponse(**_state["advisory"])


def _set_manifest_for_testing(major: int, active: str) -> None:
    """Test seam used by VTs and the CSO rollback rehearsal."""
    _state["manifest"]["major"] = major
    _state["manifest"]["active"] = active


def _set_advisory_for_testing(
    active: bool,
    severity: str | None = None,
    headline: str | None = None,
    body: str | None = None,
    published_at: str | None = None,
) -> None:
    _state["advisory"] = {
        "active": active,
        "severity": severity,
        "headline": headline,
        "body": body,
        "published_at": published_at,
    }


def _reset_release_state_for_testing() -> None:
    _set_manifest_for_testing(1, "1.0.0")
    _set_advisory_for_testing(False)
