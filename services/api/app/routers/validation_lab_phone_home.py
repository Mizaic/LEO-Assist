"""Validation Lab trigger for gated LEO phone-home.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")

Atlas: DI-C7DEF132
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_admin_or_service
from libs.atlas_qms.ncr_client import NcrClientError, NcrNotConfigured
from libs.atlas_qms.phone_home import digest_phone_home, preview_phone_home
from libs.auth.org_scope import CallerScope

router = APIRouter(prefix="/validation-lab", tags=["validation-lab"])


@router.get("/phone-home/preview")
def preview_digest(
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    try:
        return preview_phone_home()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not read pipeline issue queues.",
        ) from exc


@router.post("/phone-home/digest")
def run_digest(
    _scope: CallerScope = Depends(require_admin_or_service),
) -> dict[str, Any]:
    try:
        return digest_phone_home()
    except NcrNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except NcrClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not run the phone-home digest.",
        ) from exc
