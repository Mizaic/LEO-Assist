"""Patient and encounter endpoints reading from patient Neo4j graph."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from app.db.neo4j_client import CodingGraphClient, PatientGraphClient
from libs.auth.org_scope import CallerScope, get_caller_scope, require_patient_in_scope
from libs.neo4j_client.client import KnowledgeGraphClient
from libs.cypher.documents_queries import _assertion_context
from libs.cypher.gold_label_queries import (
    GET_GOLD_LABEL_BY_ID,
    UPDATE_GOLD_LABEL_ENTITIES,
)
from app.models.neo4j_schema import (
    DELETE_CODED_LINK,
    GET_ENCOUNTER,
    GET_PATIENT,
    GET_PATIENT_CODING_TIMELINE,
    LIST_APPROVED_COUNT_BY_PATIENT,
    LIST_ENCOUNTER_CODED_LINKS,
    LIST_PATIENT_ENCOUNTERS,
    LIST_PATIENTS,
    SEARCH_ENCOUNTERS_KEYWORD,
    SEARCH_ENCOUNTERS_VECTOR,
    UPDATE_CODED_LINK_MODIFIERS,
)
from app.services.inference_service import infer_encounter
from app.services.reset_review_queue_service import reset_review_queue
from app.services.reset_service import reset_encounter, reset_patient
from app.services.sync_service import sync_gold_to_patient
from services.terminology_api.app.services.writeback_service import (
    writeback_approved_terms,
)
from app.services.patient_graph_writer import PatientGraphWriter, SemanticLinkPayload

router = APIRouter(prefix="/patients", tags=["patients"])


class RecodeCodedLinkRequest(BaseModel):
    new_concept_id: str
    term: str | None = None
    read_code: str | None = None
    semantic_tag: str = "SnomedConcept"
    modifiers: dict[str, Any] | None = None


class UpdateModifiersRequest(BaseModel):
    value: str | float | None = None
    unit: str | None = None
    reference_range: str | None = None
    interpretation: str | None = None


class AddCodedLinkRequest(BaseModel):
    concept_id: str
    term: str | None = None
    read_code: str | None = None
    semantic_tag: str = "SnomedConcept"
    evidence: str = ""
    modifiers: dict[str, Any] | None = None
    context: dict[str, Any] | None = None


class SyncCodedLinksFromGoldRequest(BaseModel):
    """Dual-save request from the shared GoldLabelEditorDialog (DI-LEO-AI-210).

    The reviewer's edits are sent in the GoldLabel ``entities`` shape.  The
    server diffs them against the live :DOCUMENTS edges, applies the diff
    in a single Neo4j tx, then mirrors the entities into the GoldLabel.
    ``expected_baseline_concept_ids`` is the client's view of which
    concepts were already coded when the dialog opened -- if it disagrees
    with the live graph the request is rejected (409) so a stale tab
    cannot silently overwrite another reviewer's writes.
    """

    label_id: str = Field(..., min_length=1)
    expected_baseline_concept_ids: list[str] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)


class InferRequest(BaseModel):
    dry_run: bool = True


class ResetAndRecodeEncounterRequest(BaseModel):
    dry_run: bool = False
    rerun_episode_detector: bool = False


class BatchResetEncounterItem(BaseModel):
    patient_id: str
    encounter_id: str


class BatchResetAndRecodeRequest(BaseModel):
    items: list[BatchResetEncounterItem] = Field(min_length=1, max_length=500)
    dry_run: bool = False
    trigger_analysis: bool = False
    search_context: dict[str, Any] | None = None


def _encounter_created_payload(
    *,
    patient_id: str,
    encounter_id: str,
    dry_run: bool,
    trigger_analysis: bool,
) -> dict[str, Any]:
    return {
        "event_type": "encounter-created",
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "plan_definition_id": "pd-gp-encounter-coding",
        "mode": "extract_encounter",
        "dry_run": dry_run,
        "trigger_analysis": trigger_analysis,
        "context": {
            "encounter_id": encounter_id,
            "plan_definition_id": "pd-gp-encounter-coding",
            "mode": "extract_encounter",
            "dry_run": dry_run,
            "trigger_analysis": trigger_analysis,
        },
    }


def _record_case_finding_selection(
    *,
    client: PatientGraphClient,
    selection_id: str,
    patient_id: str,
    encounter_id: str,
    status: str,
    run_id: str | None,
    search_context: dict[str, Any] | None,
) -> None:
    audit_id = None
    original_query = None
    rewritten_query = None
    if isinstance(search_context, dict):
        audit_id = search_context.get("query_audit_id")
        original_query = search_context.get("original_query")
        rewritten_query = search_context.get("rewritten_query")
    client.run(
        "MERGE (s:CaseFindingSelection {id: $selection_id}) "
        "SET s.patient_id = $patient_id, "
        "    s.encounter_id = $encounter_id, "
        "    s.status = $status, "
        "    s.run_id = $run_id, "
        "    s.original_query = $original_query, "
        "    s.rewritten_query = $rewritten_query, "
        "    s.updated_at = datetime() "
        "WITH s "
        "OPTIONAL MATCH (q:CaseFindingQueryAudit {id: $query_audit_id}) "
        "FOREACH (_ IN CASE WHEN q IS NULL THEN [] ELSE [1] END | MERGE (s)-[:FROM_QUERY]->(q))",
        selection_id=selection_id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        status=status,
        run_id=run_id,
        original_query=original_query,
        rewritten_query=rewritten_query,
        query_audit_id=audit_id,
    )


@router.get("")
def list_patients(scope: CallerScope = Depends(get_caller_scope)):
    patient_client = PatientGraphClient()
    try:
        if scope.is_admin:
            rows = patient_client.run(LIST_PATIENTS)
        else:
            rows = patient_client.run(
                "MATCH (p:Patient) "
                "WHERE EXISTS { "
                "  MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(_gp) "
                "  WHERE _gp.id IN $scope_org_ids "
                "} "
                "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter) "
                "RETURN toString(p.id) AS patient_id, count(e) AS encounter_count "
                "ORDER BY patient_id",
                scope_org_ids=scope.org_ids,
            )
        reviewed = {
            r["patient_id"]: r["reviewed_count"]
            for r in patient_client.run(LIST_APPROVED_COUNT_BY_PATIENT)
        }
        for row in rows:
            enc = row.get("encounter_count") or 0
            rev = reviewed.get(row["patient_id"], 0)
            row["reviewed_count"] = rev
            row["progress"] = rev / enc if enc > 0 else 0.0
        return rows
    finally:
        patient_client.close()


@router.post("/{patient_id}/reset")
def reset_patient_documents(
    patient_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Remove all DOCUMENTS for a patient's encounters. Keeps Patient, Encounters, text."""
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        with client.session() as session:
            result = reset_patient(patient_id, session)
        if result.get("error") == "patient_not_found":
            raise HTTPException(status_code=404, detail="Patient not found")
        return {
            "patient_id": result["patient_id"],
            "links_deleted": result["links_deleted"],
        }
    finally:
        client.close()


@router.post("/{patient_id}/reset-review-queue")
def reset_patient_review_queue(
    patient_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Remove all EncounterCandidates and ReviewTasks for a patient. Use after pipeline failure to clear pending tasks before re-running."""
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        with client.session() as session:
            result = reset_review_queue(patient_id, session)
        return {
            "patient_id": result["patient_id"],
            "deleted": result["deleted"],
        }
    finally:
        client.close()


@router.post("/{patient_id}/sync-gold")
def sync_gold_to_patient_graph(
    patient_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Sync approved EncounterCandidates into DOCUMENTS on the patient graph, then write back surface forms to the coding graph."""
    patient_client = PatientGraphClient()
    require_patient_in_scope(patient_client, scope, patient_id)
    coding_client = CodingGraphClient()
    try:
        with patient_client.session() as patient_session:
            result = sync_gold_to_patient(
                patient_id,
                patient_session=patient_session,
            )
        if result.get("error") == "no_approved_gold":
            raise HTTPException(
                status_code=400,
                detail="No approved gold for this patient. Complete review and approve first.",
            )
        with (
            patient_client.session() as patient_session,
            coding_client.session() as coding_session,
        ):
            wb = writeback_approved_terms(
                patient_session=patient_session,
                knowledge_session=coding_session,
                patient_id=patient_id,
            )
        return {
            "patient_id": result["patient_id"],
            "encounters_synced": result["encounters_synced"],
            "links_created": result["links_created"],
            "surface_forms_written": wb.get("surface_forms_written", 0),
        }
    finally:
        patient_client.close()
        coding_client.close()


@router.get("/{patient_id}")
def get_patient(
    patient_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        rows = client.run(GET_PATIENT, patient_id=patient_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Patient not found")
        return rows[0]
    finally:
        client.close()


@router.get("/{patient_id}/coding-summary")
def get_patient_coding_summary(
    patient_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Return high-level coding and analysis state for one patient."""
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        rows = client.run(
            """
            MATCH (p:Patient)
            WHERE toString(p.id) = $patient_id

            OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
            WITH p, collect(DISTINCT e) AS encounters

            OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e2:Encounter)
            OPTIONAL MATCH (c:EncounterCandidate {
              patient_id: toString(p.id),
              encounter_id: toString(e2.id)
            })
            WITH p, encounters, collect(DISTINCT c) AS candidates

            OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
            WITH p, encounters, candidates, count(DISTINCT ep) AS episode_count

            OPTIONAL MATCH (p)-[:HAS_SAFETY_NET_ALERT]->(a:SafetyNetAlert)
            WITH p, encounters, candidates, episode_count, count(DISTINCT a) AS safety_alert_count

            RETURN toString(p.id) AS patient_id,
                   p.gender AS gender,
                   toString(p.birthDate) AS birth_date,
                   size(encounters) AS total_encounters,
                   size([e IN encounters WHERE e.classification_content_type IS NOT NULL]) AS classified_count,
                   size([e IN encounters WHERE e.classification_content_type = 'clinical']) AS clinical_count,
                   size([e IN encounters WHERE e.classification_content_type = 'admin_only']) AS admin_count,
                   size([e IN encounters WHERE e.classification_content_type = 'document_transfer']) AS document_transfer_count,
                   size([e IN encounters WHERE any(c IN candidates WHERE c IS NOT NULL AND c.encounter_id = toString(e.id))]) AS coded_count,
                   size([e IN encounters WHERE NOT any(c IN candidates WHERE c IS NOT NULL AND c.encounter_id = toString(e.id))]) AS uncoded_count,
                   size([c IN candidates WHERE c IS NOT NULL AND c.approval_status = 'approved']) AS approved_count,
                   size([c IN candidates WHERE c IS NOT NULL AND c.approval_status = 'pending']) AS pending_review_count,
                   size([
                     c IN candidates
                     WHERE c IS NOT NULL AND (
                       c.approval_status = 'rejected'
                       OR (c.hard_fail_reasons IS NOT NULL AND size(c.hard_fail_reasons) > 0)
                     )
                   ]) AS failed_count,
                   reduce(
                     m = 0,
                     c IN [c IN candidates WHERE c IS NOT NULL AND c.approval_status = 'approved' | 1]
                     | m + c
                   ) AS approved_candidate_count,
                   reduce(
                     m = 0,
                     c IN [c IN candidates WHERE c IS NOT NULL AND c.approval_status = 'pending' | 1]
                     | m + c
                   ) AS pending_candidate_count,
                   toString(reduce(d = null, e IN encounters |
                     CASE WHEN d IS NULL OR (e.date IS NOT NULL AND e.date < d) THEN e.date ELSE d END
                   )) AS date_from,
                   toString(reduce(d = null, e IN encounters |
                     CASE WHEN d IS NULL OR (e.date IS NOT NULL AND e.date > d) THEN e.date ELSE d END
                   )) AS date_to,
                   episode_count,
                   safety_alert_count
            """,
            patient_id=patient_id,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Patient not found")
        row = rows[0]

        semantic_rows = client.run(
            """
            MATCH (p:Patient)-[:HAS_ENCOUNTER]->(:Encounter)-[:DOCUMENTS]->(c:Concept)
            WHERE toString(p.id) = $patient_id
            WITH coalesce(c.semantic_tag, 'unknown') AS semantic_tag, count(*) AS cnt
            RETURN semantic_tag, cnt
            ORDER BY cnt DESC, semantic_tag
            """,
            patient_id=patient_id,
        )
        semantic_tag_counts = [
            {"semantic_tag": r["semantic_tag"], "count": int(r["cnt"])}
            for r in semantic_rows
        ]

        total_encounters = int(row.get("total_encounters") or 0)
        coded_count = int(row.get("coded_count") or 0)
        return {
            "patient_id": row.get("patient_id"),
            "demographics": {
                "gender": row.get("gender"),
                "birth_date": row.get("birth_date"),
            },
            "encounters": {
                "total": total_encounters,
                "classified": int(row.get("classified_count") or 0),
                "clinical": int(row.get("clinical_count") or 0),
                "admin_only": int(row.get("admin_count") or 0),
                "document_transfer": int(row.get("document_transfer_count") or 0),
                "coded": coded_count,
                "uncoded": int(row.get("uncoded_count") or 0),
                "progress_pct": (
                    round((coded_count / total_encounters) * 100, 1)
                    if total_encounters > 0
                    else 0.0
                ),
                "date_from": row.get("date_from"),
                "date_to": row.get("date_to"),
            },
            "review": {
                "approved": int(row.get("approved_count") or 0),
                "pending": int(row.get("pending_review_count") or 0),
                "failed": int(row.get("failed_count") or 0),
                "approved_candidates": int(row.get("approved_candidate_count") or 0),
                "pending_candidates": int(row.get("pending_candidate_count") or 0),
            },
            "semantic_tag_counts": semantic_tag_counts,
            "analysis": {
                "episode_count": int(row.get("episode_count") or 0),
                "safety_alert_count": int(row.get("safety_alert_count") or 0),
                "has_analysis_outputs": (
                    int(row.get("episode_count") or 0) > 0
                    or int(row.get("safety_alert_count") or 0) > 0
                ),
            },
        }
    finally:
        client.close()


@router.get("/{patient_id}/encounters")
def list_encounters(
    patient_id: str,
    limit: int = Query(default=500, ge=1, le=2000),
    scope: CallerScope = Depends(get_caller_scope),
):
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        return client.run(LIST_PATIENT_ENCOUNTERS, patient_id=patient_id, limit=limit)
    finally:
        client.close()


@router.get("/{patient_id}/encounters/search")
def search_encounters(
    patient_id: str,
    q: str = Query(min_length=1),
    mode: str = Query(default="hybrid", pattern="^(keyword|semantic|hybrid)$"),
    limit: int = Query(default=50, ge=1, le=200),
    scope: CallerScope = Depends(get_caller_scope),
):
    """Hybrid encounter search: keyword on text + vector similarity on encounter embeddings."""
    from app.services.pipeline_service import PipelineService

    results: dict[str, dict] = {}

    patient_client = PatientGraphClient()
    try:
        require_patient_in_scope(patient_client, scope, patient_id)
        if mode in ("keyword", "hybrid"):
            for row in patient_client.run(
                SEARCH_ENCOUNTERS_KEYWORD,
                patient_id=patient_id,
                q=q,
                limit=limit,
            ):
                eid = str(row["encounter_id"])
                results[eid] = {
                    **row,
                    "match_type": "keyword",
                    "similarity": None,
                }

        if mode in ("semantic", "hybrid"):
            embedder = PipelineService._try_load_embedder()
            if embedder is not None:
                query_vec = embedder.encode([q])[0]
                k = min(limit * 3, 200)
                for row in patient_client.run(
                    SEARCH_ENCOUNTERS_VECTOR,
                    patient_id=patient_id,
                    query_vector=query_vec,
                    k=k,
                    limit=limit,
                ):
                    eid = str(row["encounter_id"])
                    sim = float(row.pop("similarity", 0))
                    if eid in results:
                        results[eid]["match_type"] = "both"
                        results[eid]["similarity"] = sim
                    else:
                        results[eid] = {
                            **row,
                            "match_type": "semantic",
                            "similarity": sim,
                        }
    finally:
        patient_client.close()

    ordered = sorted(
        results.values(),
        key=lambda r: (
            (
                0
                if r["match_type"] == "both"
                else 1 if r["match_type"] == "keyword" else 2
            ),
            -(r.get("similarity") or 0),
        ),
    )
    return ordered[:limit]


@router.get("/{patient_id}/encounters/{encounter_id}")
def get_encounter(
    patient_id: str,
    encounter_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        rows = client.run(
            GET_ENCOUNTER, patient_id=patient_id, encounter_id=encounter_id
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Encounter not found")
        return rows[0]
    finally:
        client.close()


@router.post("/{patient_id}/encounters/{encounter_id}/infer")
def infer_encounter_coding(
    patient_id: str,
    encounter_id: str,
    body: InferRequest | None = None,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Run MedSpaCy inference on encounter. dry_run=true returns entities only."""
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        rows = client.run(
            GET_ENCOUNTER, patient_id=patient_id, encounter_id=encounter_id
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Encounter not found")
        encounter = rows[0]
        text = encounter.get("text", "") or ""
        dry_run = body.dry_run if body else True
        result = infer_encounter(text, encounter_id, dry_run=dry_run)
        return result
    finally:
        client.close()


@router.post("/{patient_id}/encounters/{encounter_id}/reset-and-recode")
async def reset_and_recode_encounter(
    patient_id: str,
    encounter_id: str,
    body: ResetAndRecodeEncounterRequest | None = None,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Reset one encounter coding artefacts and queue a fresh coding run."""
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        with client.session() as session:
            encounter_rows = [
                dict(r)
                for r in session.run(
                    GET_ENCOUNTER,
                    patient_id=patient_id,
                    encounter_id=encounter_id,
                )
            ]
            if not encounter_rows:
                raise HTTPException(status_code=404, detail="Encounter not found")
            reset_result = reset_encounter(patient_id, encounter_id, session)
        if reset_result.get("error") == "encounter_not_found":
            raise HTTPException(status_code=404, detail="Encounter not found")
    finally:
        client.close()

    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    run_id = str(uuid.uuid4())
    dry_run = body.dry_run if body else False
    rerun_episode_detector = body.rerun_episode_detector if body else False
    queue_name = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")

    bus = create_message_bus()
    try:
        await bus.send(
            queue_name,
            Message(
                body=_encounter_created_payload(
                    patient_id=patient_id,
                    encounter_id=encounter_id,
                    dry_run=dry_run,
                    trigger_analysis=rerun_episode_detector,
                ),
                correlation_id=run_id,
                subject="encounter-created",
            ),
        )
    finally:
        await bus.close()

    return {
        **reset_result,
        "queued": True,
        "run_id": run_id,
        "mode": "extract_encounter",
        "dry_run": dry_run,
        "rerun_episode_detector": rerun_episode_detector,
    }


@router.post("/encounters/batch-reset-and-recode")
async def batch_reset_and_recode_encounters(
    body: BatchResetAndRecodeRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Reset and recode multiple encounters across patients in one request."""
    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    queue_name = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")
    batch_id = str(uuid.uuid4())
    dry_run = bool(body.dry_run)
    trigger_analysis = bool(body.trigger_analysis)

    client = PatientGraphClient()
    bus = create_message_bus()
    queued: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    validated_patients: set[str] = set()
    try:
        for item in body.items:
            patient_id = item.patient_id.strip()
            encounter_id = item.encounter_id.strip()
            if not patient_id or not encounter_id:
                failed.append(
                    {
                        "patient_id": patient_id,
                        "encounter_id": encounter_id,
                        "error": "patient_id and encounter_id are required",
                    }
                )
                continue

            try:
                if patient_id not in validated_patients:
                    require_patient_in_scope(client, scope, patient_id)
                    validated_patients.add(patient_id)
                with client.session() as session:
                    rows = [
                        dict(r)
                        for r in session.run(
                            GET_ENCOUNTER,
                            patient_id=patient_id,
                            encounter_id=encounter_id,
                        )
                    ]
                    if not rows:
                        selection_id = str(uuid.uuid4())
                        _record_case_finding_selection(
                            client=client,
                            selection_id=selection_id,
                            patient_id=patient_id,
                            encounter_id=encounter_id,
                            status="failed_not_found",
                            run_id=None,
                            search_context=body.search_context,
                        )
                        failed.append(
                            {
                                "patient_id": patient_id,
                                "encounter_id": encounter_id,
                                "error": "Encounter not found",
                            }
                        )
                        continue
                    reset_result = reset_encounter(patient_id, encounter_id, session)
                if reset_result.get("error") == "encounter_not_found":
                    selection_id = str(uuid.uuid4())
                    _record_case_finding_selection(
                        client=client,
                        selection_id=selection_id,
                        patient_id=patient_id,
                        encounter_id=encounter_id,
                        status="failed_not_found",
                        run_id=None,
                        search_context=body.search_context,
                    )
                    failed.append(
                        {
                            "patient_id": patient_id,
                            "encounter_id": encounter_id,
                            "error": "Encounter not found",
                        }
                    )
                    continue

                run_id = str(uuid.uuid4())
                await bus.send(
                    queue_name,
                    Message(
                        body=_encounter_created_payload(
                            patient_id=patient_id,
                            encounter_id=encounter_id,
                            dry_run=dry_run,
                            trigger_analysis=trigger_analysis,
                        ),
                        correlation_id=run_id,
                        subject="encounter-created",
                    ),
                )
                queued.append(
                    {
                        "patient_id": patient_id,
                        "encounter_id": encounter_id,
                        "run_id": run_id,
                        "stream_path": f"/api/pipeline/progress/{run_id}",
                    }
                )
                selection_id = str(uuid.uuid4())
                _record_case_finding_selection(
                    client=client,
                    selection_id=selection_id,
                    patient_id=patient_id,
                    encounter_id=encounter_id,
                    status="queued",
                    run_id=run_id,
                    search_context=body.search_context,
                )
            except HTTPException as exc:
                selection_id = str(uuid.uuid4())
                _record_case_finding_selection(
                    client=client,
                    selection_id=selection_id,
                    patient_id=patient_id,
                    encounter_id=encounter_id,
                    status="failed_scope",
                    run_id=None,
                    search_context=body.search_context,
                )
                failed.append(
                    {
                        "patient_id": patient_id,
                        "encounter_id": encounter_id,
                        "error": exc.detail,
                    }
                )
            except Exception as exc:
                selection_id = str(uuid.uuid4())
                _record_case_finding_selection(
                    client=client,
                    selection_id=selection_id,
                    patient_id=patient_id,
                    encounter_id=encounter_id,
                    status="failed_error",
                    run_id=None,
                    search_context=body.search_context,
                )
                failed.append(
                    {
                        "patient_id": patient_id,
                        "encounter_id": encounter_id,
                        "error": str(exc),
                    }
                )
    finally:
        client.close()
        await bus.close()

    return {
        "batch_id": batch_id,
        "requested": len(body.items),
        "queued_count": len(queued),
        "failed_count": len(failed),
        "dry_run": dry_run,
        "trigger_analysis": trigger_analysis,
        "queued": queued,
        "failed": failed,
    }


@router.post("/{patient_id}/encounters/{encounter_id}/coded-links")
def add_coded_link(
    patient_id: str,
    encounter_id: str,
    body: AddCodedLinkRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    from libs.ner.training_label_writer import upsert_training_label

    writer = PatientGraphWriter()
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        with client.session() as session:
            payload = SemanticLinkPayload(
                encounter_id=encounter_id,
                semantic_tag=body.semantic_tag,
                concept_id=body.concept_id,
                term=body.term,
                read_code=body.read_code,
                evidence=body.evidence,
                confidence=0.95,
                domain="clinical",
                context=body.context or {},
                modifiers=body.modifiers or {},
                source="manual",
            )
            writer.upsert_documents_link(payload, session=session)

        # Capture manual coding as a training label so the correction is
        # learned by the NER model on the next retrain.
        evidence_text = body.evidence or body.term or ""
        if evidence_text and body.term and body.semantic_tag:
            try:
                entity = {
                    "text": body.term,
                    "label": body.semantic_tag.upper(),
                    "start": 0,
                    "end": len(body.term),
                    "confidence": 1.0,
                }
                upsert_training_label(
                    encounter_id=encounter_id,
                    patient_id=patient_id,
                    text=evidence_text,
                    entities=[entity],
                    source="coding_correction",
                    source_ref=body.concept_id or "",
                    quality_score=1.0,
                    client=client,
                )
            except Exception:
                import logging as _logging

                _logging.getLogger(__name__).warning(
                    "Training label write failed for coded-link %s/%s — non-fatal",
                    encounter_id,
                    body.concept_id,
                    exc_info=True,
                )

        return {"added": True, "concept_id": body.concept_id}
    finally:
        client.close()


@router.get("/{patient_id}/encounters/{encounter_id}/coded-links")
def get_encounter_coded_links(
    patient_id: str,
    encounter_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        rows = client.run(
            LIST_ENCOUNTER_CODED_LINKS,
            patient_id=patient_id,
            encounter_id=encounter_id,
        )
        # Filter out placeholder row when no DOCUMENTS exist (concept_id is null)
        result = []
        for r in rows:
            if not r.get("concept_id"):
                continue
            row = dict(r)
            # Parse context/modifiers from JSON strings (Neo4j stores primitives only)
            ctx = row.get("context")
            mod = row.get("modifiers")
            if isinstance(ctx, str):
                try:
                    row["context"] = json.loads(ctx) if ctx else {}
                except json.JSONDecodeError:
                    row["context"] = {}
            elif ctx is None:
                row["context"] = {}
            row["assertion"] = (row.get("context") or {}).get("assertion", "present")
            if isinstance(mod, str):
                try:
                    row["modifiers"] = json.loads(mod) if mod else {}
                except json.JSONDecodeError:
                    row["modifiers"] = {}
            elif mod is None:
                row["modifiers"] = {}
            result.append(row)
        return result
    finally:
        client.close()


@router.delete("/{patient_id}/encounters/{encounter_id}/coded-links/{concept_id}")
def delete_coded_link(
    patient_id: str,
    encounter_id: str,
    concept_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        rows = client.run(
            DELETE_CODED_LINK,
            patient_id=patient_id,
            encounter_id=encounter_id,
            concept_id=concept_id,
        )
        deleted = int(rows[0].get("deleted") or 0) if rows else 0
        if deleted == 0:
            raise HTTPException(status_code=404, detail="Coded link not found")
        return {"deleted": True, "deleted_count": deleted}
    finally:
        client.close()


@router.patch("/{patient_id}/encounters/{encounter_id}/coded-links/{concept_id}")
def recode_coded_link(
    patient_id: str,
    encounter_id: str,
    concept_id: str,
    body: RecodeCodedLinkRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    writer = PatientGraphWriter()
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        try:
            with client.session() as session:
                payload = SemanticLinkPayload(
                    encounter_id=encounter_id,
                    semantic_tag=body.semantic_tag,
                    concept_id=body.new_concept_id,
                    term=body.term,
                    read_code=body.read_code,
                    evidence="",
                    confidence=0.9,
                    domain="clinical",
                    context={},
                    modifiers=body.modifiers or {},
                    source="manual_recode",
                )
                writer.recode_documents_link(
                    patient_id=patient_id,
                    old_concept_id=concept_id,
                    new_payload=payload,
                    session=session,
                )
        except ValueError as exc:
            if str(exc) == "coded_link_not_found":
                raise HTTPException(
                    status_code=404, detail="Coded link not found"
                ) from exc
            raise
        return {"recode": True, "new_concept_id": body.new_concept_id}
    finally:
        client.close()


# -- Dual-save sync (DI-LEO-AI-210) -------------------------------------------
# The shared GoldLabelEditorDialog opens against the de-identified text
# (so PHI never enters the gold dataset).  When the reviewer saves on a
# /care/* surface, the dialog's edits must also be applied back to the
# live Encounter's :DOCUMENTS edges -- otherwise the patient record would
# silently disagree with what the reviewer just confirmed.  This endpoint
# performs the diff/apply transactionally and then mirrors the gold-side
# entities so retraining gets the same view the reviewer agreed to.

_GOLD_SYNC_SOURCE = "manual_gold_sync"

_SYNC_LIVE_DOMAIN = "clinical"

_SYNC_LIVE_CONFIDENCE = 0.95


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _build_link_payload_from_gold_entity(
    *,
    encounter_id: str,
    entity: dict[str, Any],
) -> SemanticLinkPayload | None:
    """Map an editor-side gold entity onto a SemanticLinkPayload.

    Returns ``None`` when the entity has no SNOMED concept (i.e. the
    reviewer marked a span but has not yet linked it).  Such entities
    are still persisted in the gold label but skipped from the live
    Neo4j sync because :DOCUMENTS requires a concept node.
    """

    concept_id = _coerce_str(entity.get("snomed_concept_id"))
    if not concept_id:
        return None
    semantic_tag = _coerce_str(entity.get("semantic_tag")) or _coerce_str(
        entity.get("label")
    ) or "SnomedConcept"
    term = _coerce_str(entity.get("snomed_term")) or _coerce_str(
        entity.get("text")
    ) or concept_id
    evidence = _coerce_str(entity.get("text"))
    assertion = _coerce_str(entity.get("assertion")) or "present"
    modifiers: dict[str, Any] = {}
    body_site_concept_id = _coerce_str(entity.get("body_site_concept_id"))
    body_site_term = _coerce_str(entity.get("body_site_term"))
    if body_site_concept_id:
        modifiers["body_site_concept_id"] = body_site_concept_id
    if body_site_term:
        modifiers["body_site_term"] = body_site_term
    return SemanticLinkPayload(
        encounter_id=encounter_id,
        semantic_tag=semantic_tag,
        concept_id=concept_id,
        term=term,
        read_code=None,
        evidence=evidence,
        confidence=_SYNC_LIVE_CONFIDENCE,
        domain=_SYNC_LIVE_DOMAIN,
        context=_assertion_context(assertion),
        modifiers=modifiers,
        source=_GOLD_SYNC_SOURCE,
    )


def _list_baseline_concept_ids(session, patient_id: str, encounter_id: str) -> list[str]:
    """Return the current set of concept_ids coded on (patient, encounter)."""

    rows = session.run(
        LIST_ENCOUNTER_CODED_LINKS,
        patient_id=patient_id,
        encounter_id=encounter_id,
    )
    baseline: list[str] = []
    for row in rows:
        cid = row.get("concept_id")
        if cid is None or cid == "":
            continue
        baseline.append(str(cid))
    return baseline


@router.post(
    "/{patient_id}/encounters/{encounter_id}/coded-links/sync-from-gold"
)
def sync_coded_links_from_gold(
    patient_id: str,
    encounter_id: str,
    body: SyncCodedLinksFromGoldRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Apply the dialog's gold edits to live :DOCUMENTS and the GoldLabel.

    Optimistic concurrency: ``expected_baseline_concept_ids`` must match
    the current live concept_ids.  If another writer has touched this
    encounter since the dialog opened, the request is rejected with 409
    so the reviewer can refresh and re-confirm.

    Live writes are atomic (single Neo4j write tx).  The gold mirror is
    written immediately after; if that step fails the live writes have
    already been committed and the next save attempt will reconcile.
    """

    label_id = body.label_id.strip()
    if not label_id:
        raise HTTPException(status_code=400, detail="label_id must not be empty")

    expected_baseline = sorted(
        {
            str(cid).strip()
            for cid in (body.expected_baseline_concept_ids or [])
            if str(cid).strip()
        }
    )

    # Build the desired set of live links from the gold entities.  Last
    # write wins on duplicate concept_ids (the dialog should not produce
    # duplicates but be defensive).
    desired_links: dict[str, SemanticLinkPayload] = {}
    for entity in body.entities or []:
        if not isinstance(entity, dict):
            continue
        link = _build_link_payload_from_gold_entity(
            encounter_id=encounter_id,
            entity=entity,
        )
        if link is None:
            continue
        desired_links[link.concept_id] = link
    desired_ids = set(desired_links)

    writer = PatientGraphWriter()
    client = PatientGraphClient()
    added = 0
    removed = 0
    updated = 0
    new_baseline: list[str] = []
    try:
        require_patient_in_scope(client, scope, patient_id)
        with client.session() as session:
            # Single write tx -> add/remove/update all coded links.
            def _apply(tx) -> tuple[int, int, int, list[str]]:
                rows = tx.run(
                    LIST_ENCOUNTER_CODED_LINKS,
                    patient_id=patient_id,
                    encounter_id=encounter_id,
                )
                current_ids: set[str] = set()
                for row in rows:
                    cid = row.get("concept_id")
                    if cid is None or cid == "":
                        continue
                    current_ids.add(str(cid))
                if sorted(current_ids) != expected_baseline:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Live coded links changed since the editor opened. "
                            "Refresh the encounter and re-apply your edits."
                        ),
                    )
                local_added = 0
                local_updated = 0
                for cid, payload in desired_links.items():
                    writer.upsert_documents_link(payload, session=tx)
                    if cid in current_ids:
                        local_updated += 1
                    else:
                        local_added += 1
                local_removed = 0
                for cid in current_ids - desired_ids:
                    try:
                        writer.delete_documents_link(
                            encounter_id=encounter_id,
                            concept_id=cid,
                            patient_id=patient_id,
                            session=tx,
                        )
                        local_removed += 1
                    except ValueError as exc:
                        if str(exc) != "coded_link_not_found":
                            raise
                final_ids = sorted(desired_ids)
                return local_added, local_removed, local_updated, final_ids

            added, removed, updated, new_baseline = session.execute_write(_apply)
    finally:
        client.close()

    # Mirror entities into the gold label.  Failure here means the live
    # writes have committed but the gold view lags -- surface a 502 so
    # the dialog can prompt the reviewer to retry without rolling back
    # the clinical record.
    entities_json = json.dumps(body.entities or [], ensure_ascii=False)
    kg_client = KnowledgeGraphClient()
    try:
        with kg_client.session() as session:
            existing = session.run(
                GET_GOLD_LABEL_BY_ID, label_id=label_id
            ).single()
            if existing is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "Gold label not found. Live coded links were updated "
                        "but the gold mirror could not be located."
                    ),
                )
            session.run(
                UPDATE_GOLD_LABEL_ENTITIES,
                label_id=label_id,
                entities_json=entities_json,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Live coded links were updated but the gold mirror write "
                f"failed: {exc}. Press save again to retry the gold sync."
            ),
        ) from exc
    finally:
        kg_client.close()

    return {
        "gold_label_id": label_id,
        "live_links_added": added,
        "live_links_removed": removed,
        "live_links_updated": updated,
        "baseline_concept_ids": new_baseline,
    }


@router.put(
    "/{patient_id}/encounters/{encounter_id}/coded-links/{concept_id}/modifiers"
)
def update_coded_link_modifiers(
    patient_id: str,
    encounter_id: str,
    concept_id: str,
    body: UpdateModifiersRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Update value/unit/reference_range/interpretation on an existing coded link."""
    modifiers = {k: v for k, v in body.model_dump().items() if v is not None}
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        rows = client.run(
            UPDATE_CODED_LINK_MODIFIERS,
            patient_id=patient_id,
            encounter_id=encounter_id,
            concept_id=concept_id,
            modifiers=json.dumps(modifiers) if modifiers else "{}",
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Coded link not found")
        return {"concept_id": concept_id, "modifiers": modifiers}
    finally:
        client.close()


class TimelineEvent(BaseModel):
    encounter_date: str
    encounter_id: str
    concept_id: str
    term: str
    semantic_tag: str
    read_code: Optional[str] = None
    assertion: str
    confidence: Optional[float] = None
    domain: Optional[str] = None
    decision_tier: Optional[int] = None


def _parse_assertion_from_context(context_json: str | None) -> str:
    """Extract the assertion string from the context JSON stored on :DOCUMENTS."""
    if not context_json:
        return "present"
    try:
        ctx = json.loads(context_json)
        return str(ctx.get("assertion") or "present")
    except (json.JSONDecodeError, AttributeError):
        return "present"


@router.get("/{patient_id}/timeline", response_model=list[TimelineEvent])
def get_patient_coding_timeline(
    patient_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Return all coded SNOMED terms for a patient ordered by encounter date."""
    client = PatientGraphClient()
    try:
        require_patient_in_scope(client, scope, patient_id)
        rows = client.run(GET_PATIENT_CODING_TIMELINE, patient_id=patient_id)
        events = []
        for row in rows:
            concept_id = row.get("concept_id")
            if not concept_id:
                continue
            events.append(
                TimelineEvent(
                    encounter_date=str(row.get("encounter_date") or ""),
                    encounter_id=str(row.get("encounter_id") or ""),
                    concept_id=str(concept_id),
                    term=str(row.get("term") or concept_id),
                    semantic_tag=str(row.get("semantic_tag") or "other"),
                    read_code=row.get("read_code"),
                    assertion=_parse_assertion_from_context(row.get("context_json")),
                    confidence=(
                        float(row["confidence"])
                        if row.get("confidence") is not None
                        else None
                    ),
                    domain=row.get("domain"),
                    decision_tier=(
                        int(row["decision_tier"])
                        if row.get("decision_tier") is not None
                        else None
                    ),
                )
            )
        return events
    finally:
        client.close()
