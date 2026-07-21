"""Historic guideline shadow-diff: candidate vs baseline, real patients only.

Atlas trace:
  DO: DO-92F92EFB
  DI: DI-88C1715A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-92F92EFB")

Used by the Bitmap Lifecycle "Historic shadow" action (DI-8DD23CE2).
Compares match sets for real, already-coded patients from the patient
graph -- it never activates the candidate and never writes anything.
The retired :TestPatient "fixture" comparison lived here too; that
branch is gone now that fixtures have been replaced by real Validation
Lab pipeline runs (see ``libs.validation_lab``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.db.neo4j_client import PatientGraphClient
from libs.auth.service_auth import get_service_auth_header
from libs.cypher.guideline_shadow_queries import (
    ALLOWED_SHADOW_CONCEPT_EDGE_TYPES,
    LIST_REAL_PATIENTS_FOR_SHADOW,
    READ_SHADOW_SOURCE_CONCEPT_EDGES,
    READ_SHADOW_SOURCE_ENCOUNTERS,
    READ_SHADOW_SOURCE_PATIENT,
)

TERMINOLOGY_API_URL = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001").rstrip(
    "/"
)
EVAL_TIMEOUT_S = float(os.getenv("TEST_PATIENT_EVAL_TIMEOUT", "30"))


@dataclass
class ShadowPatientPayload:
    """Minimal code payload a real patient needs for guideline evaluation."""

    codes: list[str] = field(default_factory=list)
    age: float | None = None
    sex: str | None = None
    name: str = ""

    def normalised_codes(self) -> list[str]:
        return sorted({str(c).strip() for c in self.codes if str(c).strip()})


def list_source_patients(
    patient_graph: PatientGraphClient, *, limit: int = 50
) -> list[dict]:
    """Return real patients usable as a shadow-diff source, busiest first."""
    rows = patient_graph.run(LIST_REAL_PATIENTS_FOR_SHADOW, limit=int(limit))
    return [dict(r) for r in rows]


def _read_source_payload(
    patient_graph: PatientGraphClient, source_patient_id: str
) -> ShadowPatientPayload | None:
    rows = patient_graph.run(
        READ_SHADOW_SOURCE_PATIENT, source_patient_id=source_patient_id
    )
    if not rows:
        return None
    source = dict(rows[0])
    enc_rows = patient_graph.run(
        READ_SHADOW_SOURCE_ENCOUNTERS, source_patient_id=source_patient_id
    )
    edge_rows = patient_graph.run(
        READ_SHADOW_SOURCE_CONCEPT_EDGES,
        source_patient_id=source_patient_id,
        allowed_types=list(ALLOWED_SHADOW_CONCEPT_EDGE_TYPES),
    )
    codes: set[str] = set()
    for row in enc_rows:
        codes.update(str(c) for c in (row.get("concept_ids") or []) if c)
    for row in edge_rows:
        codes.update(str(c) for c in (row.get("concept_ids") or []) if c)
    return ShadowPatientPayload(
        codes=sorted(codes),
        age=source.get("age"),
        sex=source.get("sex"),
        name=f"historic:{source_patient_id}",
    )


def _evaluate_against_terminology(
    payload: ShadowPatientPayload,
    *,
    scope_type: str,
    scope_id: str,
    ruleset_version: str | None,
    guideline_id: str | None,
) -> dict:
    body = {
        "patient_codes": payload.normalised_codes(),
        "patient_age": payload.age,
        "patient_sex": payload.sex,
        "pathway_id": guideline_id,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "ruleset_version": ruleset_version,
    }
    url = f"{TERMINOLOGY_API_URL}/terminology/guidelines/evaluate"
    try:
        with httpx.Client(timeout=EVAL_TIMEOUT_S) as http:
            resp = http.post(url, json=body, headers=get_service_auth_header())
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Terminology API returned {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Could not reach the terminology API at {url}: {exc}"
        ) from exc


def _rule_ids(eval_result: dict) -> set[str]:
    ids: set[str] = set()
    for row in eval_result.get("matched_rules") or []:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("rule_id") or "").strip()
        if rid:
            ids.add(rid)
    return ids


def _eval_ids(
    payload: ShadowPatientPayload,
    *,
    scope_type: str,
    scope_id: str,
    ruleset_version: str | None,
    guideline_id: str | None,
) -> tuple[set[str], str | None]:
    try:
        result = _evaluate_against_terminology(
            payload,
            scope_type=scope_type,
            scope_id=scope_id,
            ruleset_version=ruleset_version,
            guideline_id=guideline_id,
        )
    except RuntimeError as exc:
        return set(), str(exc)
    return _rule_ids(result), None


def _diff_sets(candidate: set[str], baseline: set[str]) -> dict[str, list[str]]:
    return {
        "gained": sorted(candidate - baseline),
        "lost": sorted(baseline - candidate),
        "unchanged": sorted(candidate & baseline),
    }


def _one_patient_diff(
    payload: ShadowPatientPayload,
    *,
    patient_id: str,
    scope_type: str,
    scope_id: str,
    candidate_version: str,
    baseline_version: str | None,
    guideline_id: str | None,
) -> dict[str, Any]:
    cand_ids, cand_err = _eval_ids(
        payload,
        scope_type=scope_type,
        scope_id=scope_id,
        ruleset_version=candidate_version,
        guideline_id=guideline_id,
    )
    base_ids, base_err = _eval_ids(
        payload,
        scope_type=scope_type,
        scope_id=scope_id,
        ruleset_version=baseline_version,
        guideline_id=guideline_id,
    )
    error = cand_err or base_err
    if error:
        return {
            "patient_id": patient_id,
            "patient_name": payload.name,
            "error": error,
            "gained": [],
            "lost": [],
            "unchanged": [],
            "changed": False,
        }
    delta = _diff_sets(cand_ids, base_ids)
    return {
        "patient_id": patient_id,
        "patient_name": payload.name,
        "error": None,
        **delta,
        "changed": bool(delta["gained"] or delta["lost"]),
    }


def shadow_diff(
    patient_graph: PatientGraphClient,
    *,
    candidate_version: str,
    baseline_version: str | None = None,
    source_patient_ids: list[str],
    guideline_id: str | None = None,
    scope_type: str = "global",
    scope_id: str = "default",
) -> dict[str, Any]:
    """Compare candidate vs baseline match sets for real historic patients.

    ``baseline_version=None`` uses the live current pointer for the scope.
    Never touches that pointer -- this is a read-only comparison.
    """
    if not candidate_version or not str(candidate_version).strip():
        raise ValueError("candidate_version is required")
    if not source_patient_ids:
        raise ValueError("source_patient_ids is required")

    results: list[dict[str, Any]] = []
    for sid in source_patient_ids:
        payload = _read_source_payload(patient_graph, sid)
        if payload is None:
            results.append(
                {
                    "patient_id": sid,
                    "patient_name": f"historic:{sid}",
                    "error": "Source patient not found",
                    "gained": [],
                    "lost": [],
                    "unchanged": [],
                    "changed": False,
                }
            )
            continue
        results.append(
            _one_patient_diff(
                payload,
                patient_id=sid,
                scope_type=scope_type,
                scope_id=scope_id,
                candidate_version=candidate_version,
                baseline_version=baseline_version,
                guideline_id=guideline_id,
            )
        )

    changed = sum(1 for r in results if r.get("changed"))
    errors = sum(1 for r in results if r.get("error"))
    return {
        "candidate_version": candidate_version,
        "baseline_version": baseline_version or "current",
        "scope_type": scope_type,
        "scope_id": scope_id,
        "guideline_id": guideline_id,
        "patient_count": len(results),
        "changed_count": changed,
        "error_count": errors,
        "live_pointer_unchanged": True,
        "results": results,
    }
