"""Milestone-scoped episode and rollup SBAR for patient journeys."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from libs.patient_documents.queries import (
    LIST_EPISODE_ENCOUNTERS_UP_TO_MILESTONE,
    SET_ASSESSMENT_MILESTONE,
)

logger = logging.getLogger(__name__)

_MILESTONE_ORDER: dict[str, int] = {
    "first_presentation": 0,
    "referral": 1,
    "referral_sent": 2,
    "first_seen": 3,
    "specialist_diagnostics": 4,
    "outcome_letter": 5,
    "diagnosis_confirmed": 6,
    "treatment_started": 7,
    "treatment_completed": 8,
    "benign_closure": 9,
    "care_obstruction": 10,
}

_RUNS_LOCK = threading.Lock()
_RUNS: dict[str, dict[str, Any]] = {}


class MilestoneSbarError(Exception):
    """Raised when milestone SBAR cannot be started."""


@dataclass(frozen=True)
class MilestoneSbarStart:
    run_id: str
    episode_assessment_id: str
    rollup_assessment_id: str | None
    status: str


def milestone_types_up_to(milestone_type: str) -> list[str]:
    """Return pathway milestone types at or before the requested slot."""
    target = _MILESTONE_ORDER.get(milestone_type)
    if target is None:
        raise MilestoneSbarError(f"Unknown milestone_type: {milestone_type}")
    return [name for name, order in _MILESTONE_ORDER.items() if order <= target]


def resolve_episode_encounters(
    client: Any,
    *,
    episode_id: str,
    milestone_type: str,
) -> list[str]:
    """Load encounter ids linked to episode up to milestone order."""
    types = milestone_types_up_to(milestone_type)
    rows = client.run(
        LIST_EPISODE_ENCOUNTERS_UP_TO_MILESTONE,
        episode_id=episode_id,
        milestone_types=types,
    )
    seen: set[str] = set()
    encounter_ids: list[str] = []
    for row in rows:
        enc_id = str(row.get("encounter_id") or "").strip()
        if enc_id and enc_id not in seen:
            seen.add(enc_id)
            encounter_ids.append(enc_id)
    if not encounter_ids:
        raise MilestoneSbarError(
            "No encounters linked to this episode for the requested milestone."
        )
    return encounter_ids


def _set_run(run_id: str, payload: dict[str, Any]) -> None:
    with _RUNS_LOCK:
        _RUNS[run_id] = payload


def get_milestone_sbar_run(run_id: str) -> dict[str, Any] | None:
    with _RUNS_LOCK:
        return dict(_RUNS.get(run_id) or {})


async def _run_milestone_sbar_async(
    *,
    run_id: str,
    patient_id: str,
    episode_id: str,
    milestone_type: str,
    encounter_ids: list[str],
    include_rollup: bool,
    requested_by: str,
    tenant_id: str | None,
    client: Any,
) -> None:
    from services.pipeline_worker.app.services.episode_sbar_orchestrator import (
        EpisodeSBAROrchestrator,
        EpisodeSBARRequest,
    )
    from services.pipeline_worker.app.services.patient_rollup_sbar_orchestrator import (
        PatientRollupRequest,
        PatientRollupSBAROrchestrator,
    )

    episode_assessment_id = uuid.uuid4().hex
    rollup_assessment_id = uuid.uuid4().hex if include_rollup else None
    _set_run(
        run_id,
        {
            "run_id": run_id,
            "status": "running",
            "episode_assessment_id": episode_assessment_id,
            "rollup_assessment_id": rollup_assessment_id,
            "error_message": "",
        },
    )
    try:
        episode_orch = EpisodeSBAROrchestrator(patient_graph_client=client)
        episode_req = EpisodeSBARRequest(
            run_id=run_id,
            patient_id=patient_id,
            episode_id=episode_id,
            encounter_ids=tuple(encounter_ids),
            suspected_site="",
            requested_by=requested_by,
            tenant_id=tenant_id,
        )
        episode_payload = episode_orch._build_payload(episode_req)
        episode_payload.assessment_id = episode_assessment_id
        episode_result = await episode_orch._inner.run(episode_payload)
        episode_orch._link_episode(client, episode_result.assessment_id, episode_id)
        flags = episode_orch._run_coherence(episode_req, episode_result)
        episode_orch._persist_coherence(client, episode_result.assessment_id, flags)
        with client.session() as session:
            session.run(
                SET_ASSESSMENT_MILESTONE,
                assessment_id=episode_result.assessment_id,
                milestone_type=milestone_type,
                assessment_scope="episode",
            )

        rollup_id = None
        if include_rollup and rollup_assessment_id:
            rollup_orch = PatientRollupSBAROrchestrator(patient_graph_client=client)
            rollup_req = PatientRollupRequest(
                run_id=f"{run_id}:rollup",
                patient_id=patient_id,
                requested_by=requested_by,
                tenant_id=tenant_id,
            )
            rollup_resp = await rollup_orch.run(rollup_req)
            rollup_id = rollup_resp.assessment_id
            with client.session() as session:
                session.run(
                    SET_ASSESSMENT_MILESTONE,
                    assessment_id=rollup_id,
                    milestone_type=milestone_type,
                    assessment_scope="rollup",
                )

        _set_run(
            run_id,
            {
                "run_id": run_id,
                "status": "completed",
                "episode_assessment_id": episode_result.assessment_id,
                "rollup_assessment_id": rollup_id,
                "error_message": "",
            },
        )
    except Exception as exc:
        logger.warning("milestone SBAR run failed: %s", exc, exc_info=True)
        _set_run(
            run_id,
            {
                "run_id": run_id,
                "status": "failed",
                "episode_assessment_id": episode_assessment_id,
                "rollup_assessment_id": rollup_assessment_id,
                "error_message": str(exc),
            },
        )


def start_milestone_sbar(
    client: Any,
    *,
    patient_id: str,
    episode_id: str,
    milestone_type: str,
    include_rollup: bool = True,
    requested_by: str = "",
    tenant_id: str | None = None,
) -> MilestoneSbarStart:
    """Start background milestone SBAR generation."""
    encounter_ids = resolve_episode_encounters(
        client,
        episode_id=episode_id,
        milestone_type=milestone_type,
    )
    run_id = uuid.uuid4().hex
    episode_assessment_id = uuid.uuid4().hex
    rollup_assessment_id = uuid.uuid4().hex if include_rollup else None
    _set_run(
        run_id,
        {
            "run_id": run_id,
            "status": "queued",
            "episode_assessment_id": episode_assessment_id,
            "rollup_assessment_id": rollup_assessment_id,
            "error_message": "",
        },
    )

    def _worker() -> None:
        asyncio.run(
            _run_milestone_sbar_async(
                run_id=run_id,
                patient_id=patient_id,
                episode_id=episode_id,
                milestone_type=milestone_type,
                encounter_ids=encounter_ids,
                include_rollup=include_rollup,
                requested_by=requested_by,
                tenant_id=tenant_id,
                client=client,
            )
        )

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return MilestoneSbarStart(
        run_id=run_id,
        episode_assessment_id=episode_assessment_id,
        rollup_assessment_id=rollup_assessment_id,
        status="queued",
    )
