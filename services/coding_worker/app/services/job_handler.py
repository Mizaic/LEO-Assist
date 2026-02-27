"""Handle incoming coding job messages from the message bus.

Each message contains a patient_id and optional encounter_id.
The handler runs the two-phase coding pipeline and publishes
progress events to Redis for the Core API.

Message modes
-------------
consensus         — single worker classifies + extracts all encounters for a patient
                    (original mode, good for single-worker local runs)
consensus_fanout  — coordinator: fetch encounters, split into N chunks,
                    publish N consensus_chunk messages, complete quickly
consensus_chunk   — worker: classify a provided subset of encounter IDs,
                    persist, atomically track completion, last chunk fans out
                    individual extract_encounter messages
extract_encounter — worker: run_single_encounter for one clinical encounter,
                    track completion, last triggers analysis job

Checkpointing
-------------
Classification results are written to Redis immediately after each LLM call
so a retry can skip already-classified encounters.  Neo4j is updated in
batches of PERSIST_BATCH_SIZE using a fresh connection per batch, preventing
the idle SSL timeout that kills long-running jobs.

Fan-out Redis keys  (TTL 86400 s)
----------------------------------
fanout:{run_id}:chunks_total:{patient_id}   — N set by coordinator
fanout:{run_id}:chunks_done:{patient_id}    — INCR per chunk worker
fanout:{run_id}:clinical_ids:{patient_id}   — SADD by each chunk worker
fanout:{run_id}:extract_total:{patient_id}  — set by last chunk worker
fanout:{run_id}:extracted:{patient_id}      — INCR per extract worker
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
from typing import Any

from libs.message_bus.base import Message
from libs.neo4j_client.client import PatientGraphClient, KnowledgeGraphClient
from libs.redis_client.checkpoint import CheckpointStore
from services.coding_worker.app.services.progress_publisher import publish_progress
from services.coding_worker.app.pipeline.pipeline_service import CodingPipeline

logger = logging.getLogger(__name__)

ANALYSIS_QUEUE = os.getenv("ANALYSIS_QUEUE_NAME", "analysis-jobs")
CODING_QUEUE = os.getenv("CODING_QUEUE_NAME", "coding-jobs")
PERSIST_BATCH_SIZE = int(os.getenv("CLASSIFY_PERSIST_BATCH_SIZE", "25"))
CLASSIFY_CHUNKS = int(os.getenv("CLASSIFY_CHUNKS", "3"))


async def handle_coding_job(msg: Message) -> None:
    body = msg.body
    patient_id = body.get("patient_id")
    encounter_id = body.get("encounter_id")
    run_id = msg.correlation_id or msg.message_id
    dry_run = body.get("dry_run", False)
    mode = body.get("mode", "all")

    logger.info(
        "Received coding job: patient=%s encounter=%s run=%s mode=%s",
        patient_id, encounter_id, run_id, mode,
    )

    patient_client = PatientGraphClient()
    knowledge_client = KnowledgeGraphClient()

    try:
        pipeline = CodingPipeline(
            patient_client=patient_client,
            knowledge_client=knowledge_client,
        )

        def progress_hook(payload: dict[str, Any]) -> None:
            payload["run_id"] = run_id
            publish_progress(run_id, payload)

        if mode == "consensus_fanout":
            await _run_fanout_coordinator(
                patient_id=patient_id,
                run_id=run_id,
                pipeline=pipeline,
                dry_run=dry_run,
                trigger_analysis=body.get("trigger_analysis", True),
                n_chunks=body.get("n_chunks", CLASSIFY_CHUNKS),
            )
        elif mode == "consensus_chunk":
            await _run_consensus_chunk(
                patient_id=patient_id,
                run_id=run_id,
                pipeline=pipeline,
                dry_run=dry_run,
                encounter_ids=body.get("encounter_ids", []),
                chunk_index=body.get("chunk_index", 0),
                total_chunks=body.get("total_chunks", 1),
                trigger_analysis=body.get("trigger_analysis", True),
                progress_hook=progress_hook,
            )
        elif mode == "extract_encounter":
            await _run_extract_encounter(
                patient_id=patient_id,
                run_id=run_id,
                encounter_id=encounter_id or body.get("encounter_id", ""),
                pipeline=pipeline,
                dry_run=dry_run,
                trigger_analysis=body.get("trigger_analysis", True),
                progress_hook=progress_hook,
            )
        elif mode == "extract_patient":
            await _run_extract_patient(
                patient_id=patient_id,
                run_id=run_id,
                pipeline=pipeline,
                dry_run=dry_run,
                trigger_analysis=body.get("trigger_analysis", True),
                progress_hook=progress_hook,
            )
        elif mode == "consensus":
            await _run_consensus(
                patient_id=patient_id,
                run_id=run_id,
                pipeline=pipeline,
                dry_run=dry_run,
                progress_hook=progress_hook,
            )
            if body.get("trigger_analysis"):
                await _publish_analysis_job(patient_id, run_id)
        elif encounter_id:
            await pipeline.run_single_encounter(
                patient_id=patient_id,
                encounter_id=encounter_id,
                dry_run=dry_run,
                progress_hook=progress_hook,
            )
        elif mode == "unprocessed":
            await pipeline.run_unprocessed(
                patient_ids=[patient_id],
                dry_run=dry_run,
                progress_hook=progress_hook,
            )
        else:
            await pipeline.run(
                patient_ids=[patient_id],
                dry_run=dry_run,
                progress_hook=progress_hook,
            )

        logger.info("Coding job completed: run=%s mode=%s", run_id, mode)
    except Exception:
        logger.exception("Coding job failed: run=%s", run_id)
        publish_progress(run_id, {"type": "run_error", "run_id": run_id, "error": "internal_error"})
        raise  # re-raise so the Azure adapter abandons the message for retry
    finally:
        patient_client.close()
        knowledge_client.close()


# ------------------------------------------------------------------
# Fan-out coordinator
# ------------------------------------------------------------------

async def _run_fanout_coordinator(
    patient_id: str,
    run_id: str,
    pipeline: CodingPipeline,
    dry_run: bool,
    trigger_analysis: bool,
    n_chunks: int,
) -> None:
    """Fetch all encounters, split into N chunks, publish chunk messages.

    Completes quickly — no LLM calls.  Each chunk message is picked up
    by an available worker (including this one if it loops back quickly).
    """
    logger.info(
        "Patient %s — fan-out coordinator starting (run=%s, chunks=%d)",
        patient_id, run_id, n_chunks,
    )

    encounters = await asyncio.to_thread(
        _fetch_encounters_sync, pipeline.patient_client, patient_id
    )
    total = len(encounters)
    logger.info("Patient %s — fetched %d encounters, splitting into %d chunks", patient_id, total, n_chunks)

    if not total:
        logger.info("Patient %s — no encounters, nothing to do", patient_id)
        return

    # Store total chunks in Redis so chunk workers can detect completion
    store = CheckpointStore()
    store.set(f"fanout:{run_id}:chunks_total:{patient_id}", {"value": n_chunks})

    # Split encounters into n_chunks (last chunk may be slightly smaller)
    chunk_size = max(1, (total + n_chunks - 1) // n_chunks)
    chunks = [
        encounters[i : i + chunk_size]
        for i in range(0, total, chunk_size)
    ]
    actual_chunks = len(chunks)

    if actual_chunks != n_chunks:
        # Update with the real number if rounding changed it
        store.set(f"fanout:{run_id}:chunks_total:{patient_id}", {"value": actual_chunks})

    from libs.message_bus.factory import create_message_bus
    bus = create_message_bus()
    try:
        for idx, chunk in enumerate(chunks):
            enc_ids = [str(e.get("encounter_id", e.get("id", ""))) for e in chunk]
            msg = Message(
                body={
                    "patient_id": patient_id,
                    "mode": "consensus_chunk",
                    "chunk_index": idx,
                    "total_chunks": actual_chunks,
                    "encounter_ids": enc_ids,
                    "dry_run": dry_run,
                    "trigger_analysis": trigger_analysis,
                },
                correlation_id=run_id,
            )
            await bus.send(CODING_QUEUE, msg)
            logger.info(
                "Patient %s — published chunk %d/%d (%d encounters)",
                patient_id, idx + 1, actual_chunks, len(enc_ids),
            )
    finally:
        await bus.close()

    logger.info(
        "Patient %s — fan-out complete: %d chunk messages published to %s",
        patient_id, actual_chunks, CODING_QUEUE,
    )


# ------------------------------------------------------------------
# Chunk worker — classifies a subset of encounters
# ------------------------------------------------------------------

async def _run_consensus_chunk(
    patient_id: str,
    run_id: str,
    pipeline: CodingPipeline,
    dry_run: bool,
    encounter_ids: list[str],
    chunk_index: int,
    total_chunks: int,
    trigger_analysis: bool,
    progress_hook,
) -> None:
    """Classify a provided subset of encounter IDs for a patient.

    After completing, atomically increments the chunks_done counter.
    If this is the last chunk to finish, writes the PatientEncounterIndex
    node and publishes individual extract_encounter messages for each
    clinical encounter.
    """
    from services.api.app.services.v3.encounter_classifier import (
        ClassificationResult,
    )

    store = CheckpointStore()
    total = len(encounter_ids)
    logger.info(
        "Patient %s — chunk %d/%d: classifying %d encounters",
        patient_id, chunk_index + 1, total_chunks, total,
    )

    # Fetch encounter texts for the provided IDs
    encounters = await asyncio.to_thread(
        _fetch_encounters_for_ids, pipeline.patient_client, patient_id, encounter_ids
    )

    # Build a lookup so we can iterate in the original order
    enc_map = {str(e.get("encounter_id", e.get("id", ""))): e for e in encounters}

    all_classifications: dict[str, ClassificationResult] = {}
    admin_count = doc_count = clinical_count = 0
    pending_batch: list[tuple[str, ClassificationResult]] = []

    for n, enc_id in enumerate(encounter_ids, 1):
        enc = enc_map.get(enc_id, {})
        text = enc.get("text", "")

        cache_key = f"classify:{patient_id}:{enc_id}"
        cached = store.get(cache_key)

        if cached:
            result = ClassificationResult(**cached)
            logger.info(
                "  [chunk %d | %d/%d] Encounter %s → %s [cached]",
                chunk_index, n, total, enc_id, result.content_type,
            )
        else:
            result = await asyncio.to_thread(
                _classify_single, enc_id, text, n, total, chunk_index
            )
            store.set(cache_key, dataclasses.asdict(result))

        all_classifications[enc_id] = result
        pending_batch.append((enc_id, result))

        if result.content_type == "admin_only":
            admin_count += 1
        elif result.content_type == "document_transfer":
            doc_count += 1
        else:
            clinical_count += 1

        if len(pending_batch) >= PERSIST_BATCH_SIZE:
            await asyncio.to_thread(_persist_batch, patient_id, run_id, pending_batch)
            pending_batch.clear()

    if pending_batch:
        await asyncio.to_thread(_persist_batch, patient_id, run_id, pending_batch)
        pending_batch.clear()

    # Track clinical encounter IDs in shared Redis set
    clinical_ids_in_chunk = [
        enc_id
        for enc_id, r in all_classifications.items()
        if r.content_type == "clinical"
    ]
    if clinical_ids_in_chunk:
        store.sadd(
            f"fanout:{run_id}:clinical_ids:{patient_id}",
            *clinical_ids_in_chunk,
        )

    logger.info(
        "Patient %s — chunk %d/%d classified: %d admin, %d doc, %d clinical",
        patient_id, chunk_index + 1, total_chunks,
        admin_count, doc_count, clinical_count,
    )

    # Atomically mark this chunk as done
    done_count = store.incr(f"fanout:{run_id}:chunks_done:{patient_id}")
    logger.info(
        "Patient %s — chunks_done=%d/%d", patient_id, done_count, total_chunks
    )

    if done_count == total_chunks:
        logger.info(
            "Patient %s — all %d chunks complete — writing index and fanning out extraction",
            patient_id, total_chunks,
        )
        await _finalize_classification(
            patient_id=patient_id,
            run_id=run_id,
            pipeline=pipeline,
            dry_run=dry_run,
            trigger_analysis=trigger_analysis,
            store=store,
        )


async def _finalize_classification(
    patient_id: str,
    run_id: str,
    pipeline: CodingPipeline,
    dry_run: bool,
    trigger_analysis: bool,
    store: CheckpointStore,
) -> None:
    """Called by the last chunk worker: write PatientEncounterIndex + fan out extraction."""
    from services.api.app.services.v3.encounter_classifier import (
        ClassificationResult,
        PatientEncounterIndex,
    )
    import json

    # Reconstruct full classification map from Redis checkpoints
    all_enc_ids_raw = store.smembers(f"fanout:{run_id}:all_encounter_ids:{patient_id}")
    if not all_enc_ids_raw:
        # Fall back: scan classify:{patient_id}:* keys
        all_enc_ids_raw = store._client.keys(f"classify:{patient_id}:*")
        all_enc_ids_raw = {k.split(":")[-1] for k in all_enc_ids_raw} if all_enc_ids_raw else set()

    total_classified = len(all_enc_ids_raw)
    admin_count = doc_count = clinical_count = 0
    domain_summary: dict[str, int] = {}
    classifications: dict[str, ClassificationResult] = {}

    for enc_id in all_enc_ids_raw:
        cached = store.get(f"classify:{patient_id}:{enc_id}")
        if not cached:
            continue
        result = ClassificationResult(**cached)
        classifications[enc_id] = result
        if result.content_type == "admin_only":
            admin_count += 1
        elif result.content_type == "document_transfer":
            doc_count += 1
        else:
            clinical_count += 1
            for domain in result.domains:
                domain_summary[domain] = domain_summary.get(domain, 0) + 1

    index = PatientEncounterIndex(
        patient_id=patient_id,
        run_id=run_id,
        total=total_classified,
        admin_count=admin_count,
        document_transfer_count=doc_count,
        clinical_count=clinical_count,
        domain_summary=domain_summary,
        classifications=classifications,
    )
    await asyncio.to_thread(
        _persist_index_node, patient_id, run_id, index
    )
    logger.info(
        "Patient %s — PatientEncounterIndex written: %d total, %d clinical",
        patient_id, total_classified, clinical_count,
    )

    clinical_ids = list(store.smembers(f"fanout:{run_id}:clinical_ids:{patient_id}"))
    logger.info(
        "Patient %s — fanning out %d extract_encounter messages", patient_id, len(clinical_ids)
    )

    if not clinical_ids:
        logger.info("Patient %s — no clinical encounters, skipping extraction", patient_id)
        if trigger_analysis:
            await _publish_analysis_job(patient_id, run_id)
        return

    # Set extraction total BEFORE publishing messages so workers don't race ahead
    store.set(f"fanout:{run_id}:extract_total:{patient_id}", {"value": len(clinical_ids)})

    from libs.message_bus.factory import create_message_bus
    bus = create_message_bus()
    try:
        for enc_id in clinical_ids:
            msg = Message(
                body={
                    "patient_id": patient_id,
                    "encounter_id": enc_id,
                    "mode": "extract_encounter",
                    "dry_run": dry_run,
                    "trigger_analysis": trigger_analysis,
                },
                correlation_id=run_id,
            )
            await bus.send(CODING_QUEUE, msg)
    finally:
        await bus.close()

    logger.info(
        "Patient %s — published %d extract_encounter messages",
        patient_id, len(clinical_ids),
    )


# ------------------------------------------------------------------
# Extract worker — codes a single clinical encounter
# ------------------------------------------------------------------

async def _run_extract_encounter(
    patient_id: str,
    run_id: str,
    encounter_id: str,
    pipeline: CodingPipeline,
    dry_run: bool,
    trigger_analysis: bool,
    progress_hook,
) -> None:
    """Extract and code a single clinical encounter.

    Atomically increments the extracted counter.  When all extractions
    are complete, triggers the analysis job if requested.
    """
    store = CheckpointStore()

    logger.info("Patient %s — extracting encounter %s", patient_id, encounter_id)
    await pipeline.run_single_encounter(
        patient_id=patient_id,
        encounter_id=encounter_id,
        dry_run=dry_run,
        progress_hook=progress_hook,
    )
    logger.info("Patient %s — encounter %s extraction complete", patient_id, encounter_id)

    extracted = store.incr(f"fanout:{run_id}:extracted:{patient_id}")
    total_raw = store.get(f"fanout:{run_id}:extract_total:{patient_id}")
    total = int(total_raw.get("value", 0)) if total_raw else 0

    logger.info(
        "Patient %s — extracted %d/%d encounters", patient_id, extracted, total
    )

    if total > 0 and extracted >= total:
        logger.info(
            "Patient %s — all %d encounters extracted — run complete", patient_id, total
        )
        progress_hook({
            "type": "consensus_extraction_done",
            "patient_id": patient_id,
            "clinical_processed": extracted,
        })
        if trigger_analysis:
            await _publish_analysis_job(patient_id, run_id)


# ------------------------------------------------------------------
# Original single-worker consensus (kept for backward compatibility)
# ------------------------------------------------------------------

async def _run_consensus(
    patient_id: str,
    run_id: str,
    pipeline: CodingPipeline,
    dry_run: bool,
    progress_hook,
) -> None:
    """Single-worker consensus: classify all encounters then extract clinicals.

    Retained for single-worker local runs and backward compatibility.
    """
    from services.api.app.services.v3.encounter_classifier import (
        ClassificationResult,
        persist_encounter_classification_batch,
    )

    store = CheckpointStore()
    if store.ping():
        logger.info("Patient %s — checkpoint store connected (Redis)", patient_id)
    else:
        logger.warning(
            "Patient %s — checkpoint store unavailable; classifying without cache",
            patient_id,
        )

    logger.info("Patient %s — fetching encounters from graph", patient_id)
    encounters = await asyncio.to_thread(
        _fetch_encounters_sync, pipeline.patient_client, patient_id
    )
    total = len(encounters)
    logger.info("Patient %s — found %d encounters", patient_id, total)

    if not encounters:
        logger.info("Patient %s — no encounters to process, done", patient_id)
        return

    logger.info(
        "Patient %s — classifying %d encounters (2-model consensus: Haiku + GPT-5-mini)",
        patient_id, total,
    )

    all_classifications: dict[str, ClassificationResult] = {}
    admin_count = doc_count = clinical_count = 0
    pending_batch: list[tuple[str, ClassificationResult]] = []

    for n, enc in enumerate(encounters, 1):
        enc_id = str(enc.get("encounter_id", enc.get("id", "")))
        text = enc.get("text", "")

        cache_key = f"classify:{patient_id}:{enc_id}"
        cached = store.get(cache_key)

        if cached:
            result = ClassificationResult(**cached)
            logger.info(
                "  [%d/%d] Encounter %s → %s [cached]",
                n, total, enc_id, result.content_type,
            )
        else:
            result = await asyncio.to_thread(_classify_single, enc_id, text, n, total)
            store.set(cache_key, dataclasses.asdict(result))

        all_classifications[enc_id] = result
        pending_batch.append((enc_id, result))

        if result.content_type == "admin_only":
            admin_count += 1
        elif result.content_type == "document_transfer":
            doc_count += 1
        else:
            clinical_count += 1

        if len(pending_batch) >= PERSIST_BATCH_SIZE:
            await asyncio.to_thread(_persist_batch, patient_id, run_id, pending_batch)
            pending_batch.clear()

    if pending_batch:
        await asyncio.to_thread(_persist_batch, patient_id, run_id, pending_batch)
        pending_batch.clear()

    from services.api.app.services.v3.encounter_classifier import PatientEncounterIndex
    index = PatientEncounterIndex(
        patient_id=patient_id,
        run_id=run_id,
        total=total,
        admin_count=admin_count,
        document_transfer_count=doc_count,
        clinical_count=clinical_count,
        domain_summary=_build_domain_summary(all_classifications),
        classifications=all_classifications,
    )
    await asyncio.to_thread(
        _persist_index_node, patient_id, run_id, index
    )

    logger.info(
        "Patient %s — classification complete: %d admin, %d doc_transfer, %d clinical",
        patient_id, admin_count, doc_count, clinical_count,
    )

    clinical_ids = [
        enc_id
        for enc_id, result in all_classifications.items()
        if result.content_type == "clinical"
    ]
    skipped_non_clinical = total - len(clinical_ids)

    progress_hook({
        "type": "consensus_classification_done",
        "patient_id": patient_id,
        "total": total,
        "admin": admin_count,
        "document_transfer": doc_count,
        "clinical": len(clinical_ids),
        "skipped_non_clinical": skipped_non_clinical,
        "classification_persisted": {
            "total": total,
            "classified_count": len(all_classifications),
            "clinical_count": clinical_count,
        },
    })

    if not clinical_ids:
        logger.info("Patient %s — no clinical encounters, skipping extraction", patient_id)
        return

    logger.info(
        "Patient %s — extracting %d clinical encounters (skipping %d)",
        patient_id, len(clinical_ids), skipped_non_clinical,
    )

    processed = 0
    for i, enc_id in enumerate(clinical_ids, 1):
        logger.info(
            "Patient %s — extracting encounter %d/%d (id=%s)",
            patient_id, i, len(clinical_ids), enc_id,
        )
        await pipeline.run_single_encounter(
            patient_id=patient_id,
            encounter_id=enc_id,
            dry_run=dry_run,
            progress_hook=progress_hook,
        )
        processed += 1
        logger.info(
            "Patient %s — encounter %s done (%d/%d)",
            patient_id, enc_id, processed, len(clinical_ids),
        )

    logger.info(
        "Patient %s — consensus complete: %d extracted, %d skipped",
        patient_id, processed, skipped_non_clinical,
    )
    progress_hook({
        "type": "consensus_extraction_done",
        "patient_id": patient_id,
        "clinical_processed": processed,
        "skipped_non_clinical": skipped_non_clinical,
    })


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------

def _classify_single(enc_id: str, text: str, n: int, total: int, chunk: int = -1):
    """Classify a single encounter (runs in a thread via asyncio.to_thread)."""
    from services.api.app.services.v3.encounter_classifier import (
        ClassificationResult,
        classify_encounter,
    )

    if not text or not text.strip():
        prefix = f"[chunk {chunk} | {n}/{total}]" if chunk >= 0 else f"[{n}/{total}]"
        logger.info("  %s Encounter %s → admin_only (empty text)", prefix, enc_id)
        return ClassificationResult(content_type="admin_only", consensus_agreement=True)

    result = classify_encounter(text, enc_id)
    agreement = "✓" if result.consensus_agreement else "✗ DISAGREE"
    domains_str = ",".join(result.domains) if result.domains else "none"
    prefix = f"[chunk {chunk} | {n}/{total}]" if chunk >= 0 else f"[{n}/{total}]"
    logger.info(
        "  %s Encounter %s → %s [%s] domains=%s significance=%s",
        prefix, enc_id, result.content_type, agreement,
        domains_str, result.clinical_significance,
    )
    return result


def _persist_batch(
    patient_id: str,
    run_id: str,
    batch: list[tuple[str, Any]],
) -> None:
    """Persist a batch of classification results using a fresh Neo4j connection."""
    from datetime import datetime, timezone

    fresh_client = PatientGraphClient()
    try:
        updated_at = datetime.now(timezone.utc).isoformat()
        rows = [
            {
                "encounter_id": enc_id,
                "classification_content_type": result.content_type,
                "classification_domains": [str(v) for v in result.domains],
                "classification_encounter_purpose": [str(v) for v in result.encounter_purpose],
                "classification_expected_semantic_tags": [
                    str(v) for v in result.expected_semantic_tags
                ],
                "classification_clinical_significance": str(result.clinical_significance),
                "classification_consensus_agreement": bool(result.consensus_agreement),
                "classification_model_a_type": str(result.model_a_type),
                "classification_model_b_type": str(result.model_b_type),
                "classification_run_id": str(run_id),
                "classification_updated_at": updated_at,
            }
            for enc_id, result in batch
        ]
        with fresh_client.session() as session:
            session.run(
                "MATCH (p:Patient) WHERE toString(p.id) = $pid "
                "UNWIND $rows AS row "
                "MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter) "
                "WHERE toString(e.id) = row.encounter_id "
                "SET e.classification_content_type      = row.classification_content_type, "
                "    e.classification_domains           = row.classification_domains, "
                "    e.classification_encounter_purpose = row.classification_encounter_purpose, "
                "    e.classification_expected_semantic_tags = row.classification_expected_semantic_tags, "
                "    e.classification_clinical_significance  = row.classification_clinical_significance, "
                "    e.classification_consensus_agreement    = row.classification_consensus_agreement, "
                "    e.classification_model_a_type      = row.classification_model_a_type, "
                "    e.classification_model_b_type      = row.classification_model_b_type, "
                "    e.classification_run_id            = row.classification_run_id, "
                "    e.classification_updated_at        = datetime(row.classification_updated_at)",
                pid=patient_id,
                rows=rows,
            )
        logger.info(
            "Patient %s — persisted batch of %d classification(s) to Neo4j",
            patient_id, len(batch),
        )
    except Exception:
        logger.exception(
            "Patient %s — failed to persist classification batch of %d",
            patient_id, len(batch),
        )
        raise
    finally:
        fresh_client.close()


def _persist_index_node(patient_id: str, run_id: str, index) -> None:
    """Write the PatientEncounterIndex summary node using a fresh connection.

    A fresh PatientGraphClient is created (and closed) here for the same
    reason _persist_neo4j_batch does so: the job-level client may have an
    idle SSL connection that the server has already torn down, causing an
    SSLEOFError / ServiceUnavailable on the first write.
    """
    import json

    fresh_client = PatientGraphClient()
    try:
        with fresh_client.session() as session:
            session.run(
                "MATCH (p:Patient) WHERE toString(p.id) = $pid "
                "MERGE (idx:PatientEncounterIndex {patient_id: $pid, run_id: $run_id}) "
                "SET idx.total                   = $total, "
                "    idx.admin_count             = $admin_count, "
                "    idx.document_transfer_count = $doc_count, "
                "    idx.clinical_count          = $clinical_count, "
                "    idx.domain_summary_json     = $domain_summary_json, "
                "    idx.classified_count        = $classified_count, "
                "    idx.updated_at              = datetime(), "
                "    idx.created_at              = coalesce(idx.created_at, datetime()) "
                "MERGE (p)-[:HAS_ENCOUNTER_INDEX]->(idx)",
                pid=patient_id,
                run_id=run_id,
                total=index.total,
                admin_count=index.admin_count,
                doc_count=index.document_transfer_count,
                clinical_count=index.clinical_count,
                domain_summary_json=json.dumps(index.domain_summary, sort_keys=True),
                classified_count=len(index.classifications),
            )
    finally:
        fresh_client.close()


def _build_domain_summary(classifications: dict) -> dict[str, int]:
    summary: dict[str, int] = {}
    for result in classifications.values():
        if result.content_type == "clinical":
            for domain in result.domains:
                summary[domain] = summary.get(domain, 0) + 1
    return summary


def _fetch_encounters_sync(patient_client, patient_id: str) -> list[dict]:
    """Fetch all encounters ordered by date."""
    with patient_client.session() as session:
        result = session.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text "
            "ORDER BY e.date",
            pid=patient_id,
        )
        return [dict(row) for row in result]


def _fetch_clinical_encounter_ids_sync(patient_client, patient_id: str) -> list[str]:
    """Return IDs of encounters already classified as clinical in Neo4j.

    Used by ``extract_patient`` mode to skip classification and jump straight
    to extraction using the existing classification results.
    """
    with patient_client.session() as session:
        result = session.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "  AND e.classification_content_type = 'clinical' "
            "RETURN toString(e.id) AS encounter_id "
            "ORDER BY e.date",
            pid=patient_id,
        )
        return [row["encounter_id"] for row in result]


def _fetch_encounters_for_ids(
    patient_client, patient_id: str, encounter_ids: list[str]
) -> list[dict]:
    """Fetch specific encounters by their IDs."""
    with patient_client.session() as session:
        result = session.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "  AND toString(e.id) IN $ids "
            "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text",
            pid=patient_id,
            ids=[str(i) for i in encounter_ids],
        )
        return [dict(row) for row in result]


async def _run_extract_patient(
    patient_id: str,
    run_id: str,
    pipeline: CodingPipeline,
    dry_run: bool,
    trigger_analysis: bool,
    progress_hook,
) -> None:
    """Fan out extraction for a patient whose encounters are already classified.

    Reads ``classification_content_type = 'clinical'`` directly from Neo4j,
    bypassing the classification step entirely.  Publishes one
    ``extract_encounter`` message per clinical encounter.

    Use this to re-run the coding (extraction) step after fixing a persist bug
    without paying the cost of re-classifying every encounter again.
    """
    store = CheckpointStore()

    clinical_ids = await asyncio.to_thread(
        _fetch_clinical_encounter_ids_sync, pipeline.patient_client, patient_id
    )

    if not clinical_ids:
        logger.info(
            "Patient %s — no clinical encounters found in Neo4j, nothing to extract",
            patient_id,
        )
        progress_hook({
            "type": "consensus_extraction_done",
            "patient_id": patient_id,
            "clinical_processed": 0,
        })
        return

    logger.info(
        "Patient %s — extract_patient: found %d clinical encounters, fanning out",
        patient_id, len(clinical_ids),
    )

    if dry_run:
        logger.info("Patient %s — dry_run, skipping fan-out", patient_id)
        progress_hook({
            "type": "consensus_extraction_done",
            "patient_id": patient_id,
            "clinical_processed": 0,
        })
        return

    # Set the extraction total so the last worker can detect completion
    store.set(f"fanout:{run_id}:extract_total:{patient_id}", {"value": len(clinical_ids)})

    from libs.message_bus.factory import create_message_bus
    bus = create_message_bus()
    try:
        for enc_id in clinical_ids:
            msg = Message(
                body={
                    "patient_id": patient_id,
                    "encounter_id": enc_id,
                    "mode": "extract_encounter",
                    "dry_run": dry_run,
                    "trigger_analysis": trigger_analysis,
                },
                correlation_id=run_id,
            )
            await bus.send(CODING_QUEUE, msg)
    finally:
        await bus.close()

    logger.info(
        "Patient %s — published %d extract_encounter messages (extract_patient mode)",
        patient_id, len(clinical_ids),
    )
    progress_hook({
        "type": "extract_patient_fanout_done",
        "patient_id": patient_id,
        "clinical_count": len(clinical_ids),
    })


async def _publish_analysis_job(patient_id: str, run_id: str) -> None:
    """Publish an analysis job to the analysis-jobs queue."""
    try:
        from libs.message_bus.factory import create_message_bus
        bus = create_message_bus()
        await bus.send(ANALYSIS_QUEUE, Message(
            body={"patient_id": patient_id, "trigger": "coding_complete"},
            correlation_id=run_id,
        ))
        await bus.close()
        logger.info("Published analysis job for patient %s", patient_id)
    except Exception:
        logger.warning("Failed to publish analysis job for %s", patient_id, exc_info=True)
