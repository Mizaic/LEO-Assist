"""HTTP surface for the historic guideline shadow-diff.

Mounted under ``/guidance/shadow`` (the proxy at /api/* exposes this to
the browser). All endpoints require the ai.admin role. This is the
surviving half of the retired test-patient "shadow-diff" endpoint --
only the real-patient ("historic") comparison, since the fixture
("TestPatient") comparison was removed with the rest of the Fixtures
library. Candidate-vs-real-pipeline testing now lives in the
Validation Lab (``libs.validation_lab``), not here.

Endpoints:
  GET  /guidance/shadow/source-patients  -- real-patient picker helper
  POST /guidance/shadow/diff             -- candidate vs baseline diff
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.db.neo4j_client import PatientGraphClient
from app.deps import require_admin
from app.services import guideline_shadow
from libs.auth.org_scope import CallerScope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/guidance/shadow", tags=["guideline-shadow"])


def _patient_client() -> PatientGraphClient:
    return PatientGraphClient()


class ShadowDiffRequest(BaseModel):
    """Compare candidate vs baseline match sets without go-live."""

    candidate_version: str
    baseline_version: str | None = None
    source_patient_ids: list[str]
    guideline_id: str | None = None
    scope_type: Literal["global", "guideline", "domain", "subdomain", "custom"] = (
        "global"
    )
    scope_id: str = "default"


@router.get("/source-patients")
def list_source_patients(
    limit: int = Query(default=50, ge=1, le=500),
    scope: CallerScope = Depends(require_admin),
) -> list[dict]:
    """Return real patients usable as a historic-shadow source.

    Reads from the patient graph and filters out any :Patient row
    flagged ``is_test``.
    """
    _ = scope
    patient_graph = _patient_client()
    try:
        return guideline_shadow.list_source_patients(patient_graph, limit=limit)
    finally:
        patient_graph.close()


@router.post("/diff")
def shadow_diff(
    body: ShadowDiffRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Compare candidate vs baseline match sets for real patients; never flips live."""
    _ = scope
    patient_graph = _patient_client()
    try:
        return guideline_shadow.shadow_diff(
            patient_graph,
            candidate_version=body.candidate_version,
            baseline_version=body.baseline_version,
            source_patient_ids=body.source_patient_ids,
            guideline_id=body.guideline_id,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        patient_graph.close()
