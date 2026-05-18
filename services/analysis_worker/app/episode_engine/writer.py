"""Stage 6: idempotent Neo4j writer for the episode engine.

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")

Per-patient contract:
    1. DETACH DELETE every existing EpisodeOfCare for the patient (including
       its IS_PART_OF edges, DOCUMENTS_DISRUPTION edges and the
       HAS_EPISODE_OF_CARE link). This is intentional: the engine is the
       new owner of episode state; partial merges across runs would
       create silent drift.
    2. Write one EpisodeOfCare node per reconciled episode with the full
       milestone payload, denormalised milestone dates, the safety-netting
       record, the disruption summary, evidence_quotes, confidence,
       provenance and trace_id.
    3. Re-attach (Encounter)-[:IS_PART_OF {milestone_type, treatment_type,
       evidence_quote, confidence}]-> (EpisodeOfCare) for each milestone.
    4. Re-attach (Encounter)-[:DOCUMENTS_DISRUPTION {category, phase,
       date, description, evidence_quote, confidence}]-> (EpisodeOfCare)
       for each disruption.

A ``dry_run=True`` path runs all the deterministic id work but skips the
graph mutations -- used by the cohort dry-run before cutover.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from libs.episodes.status import EpisodeStatus
from libs.neo4j_client.client import PatientGraphClient
from libs.oncology.cancer_types import normalise_cancer_type
from services.analysis_worker.app.episode_engine.schemas import (
    Episode,
    Provenance,
    ReconciledEpisode,
)
from services.analysis_worker.app.episode_engine.writer_rollups import (
    disruption_summary as _disruption_summary,
    earliest_milestone_date as _earliest_milestone_date,
    first_presentation as _first_presentation,
    first_seen_date as _first_seen_date,
    outcome_letter_date as _outcome_letter_date,
    safety_netting_payload as _safety_netting_payload,
)

logger = logging.getLogger(__name__)


# -- Cypher ---------------------------------------------------------------

_DELETE_EXISTING_Q = """
MATCH (p:Patient {id: $patient_id})-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
DETACH DELETE ep
RETURN count(ep) AS deleted
"""

_WRITE_EPISODE_Q = """
MATCH (p:Patient {id: $patient_id})
MERGE (ep:EpisodeOfCare {episode_id: $episode_id})
SET ep.patient_id                       = $patient_id,
    ep.condition_type                   = $condition_type,
    ep.cancer_type                      = $suspected_site,
    ep.episode_type                     = $episode_type,
    ep.suspected_site                   = $suspected_site,
    ep.start_date                       = date($window_start),
    ep.end_date                         = CASE WHEN $window_end IS NULL
                                                THEN null
                                                ELSE date($window_end) END,
    ep.first_presentation_date          = CASE WHEN $first_presentation_date IS NULL
                                                THEN null
                                                ELSE date($first_presentation_date) END,
    ep.place_of_first_presentation      = $place_of_first_presentation,
    ep.referral_date                    = CASE WHEN $referral_date IS NULL
                                                THEN null
                                                ELSE date($referral_date) END,
    ep.first_seen_date                  = CASE WHEN $first_seen_date IS NULL
                                                THEN null
                                                ELSE date($first_seen_date) END,
    ep.specialist_date                  = CASE WHEN $first_seen_date IS NULL
                                                THEN null
                                                ELSE date($first_seen_date) END,
    ep.outcome_letter_date              = CASE WHEN $outcome_letter_date IS NULL
                                                THEN null
                                                ELSE date($outcome_letter_date) END,
    ep.diagnosis_date                   = CASE WHEN $diagnosis_date IS NULL
                                                THEN null
                                                ELSE date($diagnosis_date) END,
    ep.treatment_started_date           = CASE WHEN $treatment_started_date IS NULL
                                                THEN null
                                                ELSE date($treatment_started_date) END,
    ep.treatment_completed_date         = CASE WHEN $treatment_completed_date IS NULL
                                                THEN null
                                                ELSE date($treatment_completed_date) END,
    ep.safety_netting_recorded          = $safety_netting_recorded,
    ep.safety_netting_evidence          = $safety_netting_evidence,
    ep.safety_netting_encounter_id      = $safety_netting_encounter_id,
    ep.safety_netting_date              = CASE WHEN $safety_netting_date IS NULL
                                                THEN null
                                                ELSE date($safety_netting_date) END,
    ep.safety_netting_confidence        = $safety_netting_confidence,
    ep.disruption_count                 = $disruption_count,
    ep.disruption_categories            = $disruption_categories,
    ep.has_referral_disruption          = $has_referral_disruption,
    ep.avoidable_delay                  = $avoidable_delay,
    ep.avoidable_delay_phase            = $avoidable_delay_phase,
    ep.disruptions_json                 = $disruptions_json,
    ep.confidence                       = $confidence,
    ep.reasoning                        = $reasoning,
    ep.needs_human_review               = $needs_human_review,
    ep.merged_from_json                 = $merged_from_json,
    ep.engine_version                   = $engine_version,
    ep.engine_trace_id                  = $trace_id,
    ep.engine_provenance_json           = $provenance_json,
    ep.created_at                       = coalesce(ep.created_at,
                                                   datetime($created_at)),
    ep.updated_at                       = datetime($created_at),
    ep.status                           = $status,
    ep.domain_id                        = $domain_id
MERGE (p)-[:HAS_EPISODE_OF_CARE]->(ep)
RETURN ep.episode_id AS episode_id
"""

_LINK_MILESTONE_Q = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
MATCH (e:Encounter {id: $encounter_id})
MERGE (e)-[r:IS_PART_OF {milestone_type: $milestone_type}]->(ep)
SET r.treatment_type     = $treatment_type,
    r.presentation_place = $presentation_place,
    r.evidence_quote     = $evidence_quote,
    r.confidence         = $confidence,
    r.engine             = true,
    r.linked_by          = 'episode_engine',
    r.created_at         = coalesce(r.created_at, datetime($created_at))
RETURN type(r) AS rt
"""

_LINK_DISRUPTION_Q = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
MATCH (e:Encounter {id: $encounter_id})
MERGE (e)-[r:DOCUMENTS_DISRUPTION {category: $category, date: date($date)}]->(ep)
SET r.phase          = $phase,
    r.description    = $description,
    r.evidence_quote = $evidence_quote,
    r.confidence     = $confidence,
    r.engine         = true,
    r.linked_by      = 'episode_engine',
    r.created_at     = coalesce(r.created_at, datetime($created_at))
RETURN type(r) AS rt
"""


# -- Engine version --------------------------------------------------------

ENGINE_VERSION = "haiku-engine-v1"


# -- Helpers --------------------------------------------------------------


def deterministic_episode_id(
    patient_id: str, suspected_site: str, window_start: str
) -> str:
    """Stable id so reruns of the same window keep the same episode_id (audit)."""
    raw = f"{patient_id}|{suspected_site.lower()}|{window_start}".encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:16]
    return f"ep-{digest}"


def _episode_status(ep: ReconciledEpisode) -> str:
    """Map a reconciled episode to a canonical EpisodeOfCare.status value.

    Returns one of ``EpisodeStatus.{CLOSED_BENIGN, COMPLETED, REVIEW,
    ACTIVE}`` (the four engine-output statuses). The ranking is
    deliberate -- a benign closure beats every other signal because the
    reconciler has already decided the pathway never developed into
    cancer; a treatment_completed milestone outranks needs_human_review;
    review outranks active.

    See ``libs/episodes/status.py`` for the full vocabulary and the
    consumer-side OPEN/CLOSED groupings the dashboard uses.
    """
    if ep.episode_type == "benign":
        return EpisodeStatus.CLOSED_BENIGN.value
    types = {m.type for m in ep.milestones}
    if "treatment_completed" in types:
        return EpisodeStatus.COMPLETED.value
    if ep.needs_human_review:
        return EpisodeStatus.REVIEW.value
    return EpisodeStatus.ACTIVE.value


def _condition_type(ep: ReconciledEpisode) -> str:
    return "cancer" if ep.episode_type in ("cancer", "multi_site") else ep.episode_type


# -- Public API ------------------------------------------------------------


def write_episodes(
    *,
    client: PatientGraphClient,
    patient_id: str,
    domain_id: str,
    episodes: list[ReconciledEpisode],
    provenance: Provenance,
    dry_run: bool = False,
) -> list[Episode]:
    """Write the engine output for one patient and return the materialised
    Episode list (with deterministic episode_ids).

    Idempotent: if you re-run the engine for the same patient, the previous
    episodes are wiped and rewritten. The patient's encounters are not
    touched.
    """

    now_iso = datetime.now(timezone.utc).isoformat()
    provenance_json = json.dumps(provenance.model_dump(), default=str)

    materialised: list[Episode] = []
    for ep in episodes:
        ep_id = deterministic_episode_id(
            patient_id, ep.suspected_site, ep.window_start.isoformat()
        )
        materialised.append(
            Episode(
                episode_id=ep_id,
                patient_id=patient_id,
                suspected_site=ep.suspected_site,
                episode_type=ep.episode_type,
                window_start=ep.window_start,
                window_end=ep.window_end,
                milestones=list(ep.milestones),
                confidence=ep.confidence,
                reasoning=ep.reasoning,
                needs_human_review=ep.needs_human_review,
                merged_from=list(ep.merged_from),
                provenance=provenance,
            )
        )

    if dry_run:
        logger.info(
            "[dry_run] writer would replace %d episodes for patient %s",
            len(materialised),
            patient_id,
        )
        return materialised

    deleted = client.run(_DELETE_EXISTING_Q, patient_id=patient_id) or []
    n_deleted = (deleted[0] or {}).get("deleted", 0) if deleted else 0
    logger.info(
        "writer: deleted %d existing episodes for patient %s", n_deleted, patient_id
    )

    for ep, final in zip(episodes, materialised):
        _write_one_episode(
            client=client,
            ep=ep,
            final=final,
            patient_id=patient_id,
            domain_id=domain_id,
            provenance=provenance,
            provenance_json=provenance_json,
            now_iso=now_iso,
        )

    return materialised


def _write_one_episode(
    *,
    client: PatientGraphClient,
    ep: ReconciledEpisode,
    final: Episode,
    patient_id: str,
    domain_id: str,
    provenance: Provenance,
    provenance_json: str,
    now_iso: str,
) -> None:
    """Write one episode + all of its links. Kept short for code-quality
    cap (writer.py is approaching the 60-LOC function cap)."""

    first_pres_date, first_pres_place = _first_presentation(ep.milestones)
    referral_date = _earliest_milestone_date(ep.milestones, "referral")
    diag_date = _earliest_milestone_date(ep.milestones, "diagnosis_confirmed")
    tx_started = _earliest_milestone_date(ep.milestones, "treatment_started")
    tx_completed = _earliest_milestone_date(ep.milestones, "treatment_completed")

    sn_kwargs = _safety_netting_payload(ep.safety_netting)
    disruption_summary = _disruption_summary(
        ep.disruptions,
        first_presentation_iso=first_pres_date,
        referral_iso=referral_date,
    )
    per_disruption = disruption_summary.pop("per_disruption")

    client.run(
        _WRITE_EPISODE_Q,
        patient_id=patient_id,
        episode_id=final.episode_id,
        condition_type=_condition_type(ep),
        suspected_site=normalise_cancer_type(ep.suspected_site),
        episode_type=ep.episode_type,
        window_start=ep.window_start.isoformat(),
        window_end=ep.window_end.isoformat() if ep.window_end else None,
        first_presentation_date=first_pres_date,
        place_of_first_presentation=first_pres_place,
        referral_date=referral_date,
        first_seen_date=_first_seen_date(ep.milestones),
        outcome_letter_date=_outcome_letter_date(ep.milestones),
        diagnosis_date=diag_date,
        treatment_started_date=tx_started,
        treatment_completed_date=tx_completed,
        confidence=float(ep.confidence),
        reasoning=ep.reasoning,
        needs_human_review=bool(ep.needs_human_review),
        merged_from_json=json.dumps(list(ep.merged_from)),
        engine_version=ENGINE_VERSION,
        trace_id=provenance.trace_id,
        provenance_json=provenance_json,
        created_at=now_iso,
        status=_episode_status(ep),
        domain_id=domain_id,
        **sn_kwargs,
        **disruption_summary,
    )

    for m in ep.milestones:
        try:
            client.run(
                _LINK_MILESTONE_Q,
                episode_id=final.episode_id,
                encounter_id=m.encounter_id,
                milestone_type=m.type,
                treatment_type=m.treatment_type,
                presentation_place=m.presentation_place,
                evidence_quote=m.evidence_quote,
                confidence=float(m.confidence),
                created_at=now_iso,
            )
        except Exception:
            logger.exception(
                "Failed to link milestone %s for episode %s (encounter %s)",
                m.type,
                final.episode_id,
                m.encounter_id,
            )

    for d in per_disruption:
        try:
            client.run(
                _LINK_DISRUPTION_Q,
                episode_id=final.episode_id,
                encounter_id=d["encounter_id"],
                category=d["category"],
                date=d["date"],
                phase=d["phase"],
                description=d["description"],
                evidence_quote=d["evidence_quote"],
                confidence=d["confidence"],
                created_at=now_iso,
            )
        except Exception:
            logger.exception(
                "Failed to link disruption %s for episode %s (encounter %s)",
                d["category"],
                final.episode_id,
                d["encounter_id"],
            )


def episodes_to_dicts(eps: list[Episode]) -> list[dict[str, Any]]:
    return [e.model_dump() for e in eps]
