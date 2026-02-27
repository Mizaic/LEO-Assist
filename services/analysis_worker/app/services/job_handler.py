"""Handle incoming analysis job messages from the message bus.

Orchestrates the full analysis pipeline for a patient:
1. Anchor detection
2. Episode building + consolidation
3. Safety-net / unwarranted variation
4. Abnormal results
5. KPI metrics

Checkpointing:
    Each stage writes a checkpoint to Redis on completion.  If the job is
    retried (e.g. after a transient Neo4j failure), completed stages are
    replayed from cache — no LLM calls or Neo4j writes are repeated.

    Key scheme:
        analysis:{patient_id}:anchors     — AnchorResult fields as JSON
        analysis:{patient_id}:episodes    — EpisodeBuildResult fields as JSON
        analysis:{patient_id}:safety_net  — list of signal dicts
        analysis:{patient_id}:abnormal    — list of result dicts
        analysis:{patient_id}:kpis        — list of KPI dicts

    Each stage also uses a fresh PatientGraphClient to avoid idle-connection
    SSL timeouts that occur during long-running jobs.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Dict, List
from uuid import uuid4

from libs.message_bus.base import Message
from libs.neo4j_client.client import PatientGraphClient, KnowledgeGraphClient
from libs.redis_client.checkpoint import CheckpointStore
from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult, detect_anchors
from services.analysis_worker.app.analyzers.episode_builder import EpisodeBuildResult, build_episodes
from services.analysis_worker.app.analyzers.safety_net_detector import detect_safety_net_signals
from services.analysis_worker.app.analyzers.abnormal_results import detect_abnormal_results
from services.analysis_worker.app.analyzers.kpi_calculator import calculate_kpis

logger = logging.getLogger(__name__)


async def handle_analysis_job(msg: Message) -> None:
    body = msg.body
    patient_id = body.get("patient_id")
    start_date = body.get("start_date", "2020-01-01")
    end_date = body.get("end_date", "2030-12-31")

    logger.info("Analysis job started: patient=%s", patient_id)

    store = CheckpointStore()
    if store.ping():
        logger.info("Patient %s — checkpoint store connected (Redis)", patient_id)
    else:
        logger.warning(
            "Patient %s — checkpoint store unavailable; stage caching disabled", patient_id
        )

    try:
        # ---------------------------------------------------------- #
        # Step 1: Anchor detection                                     #
        # ---------------------------------------------------------- #
        anchors = _checkpoint_load(store, f"analysis:{patient_id}:anchors", AnchorResult)
        if anchors:
            logger.info(
                "Patient %s — anchors: resumed from checkpoint "
                "(referrals=%d diagnosis=%d treatment=%d specialist_visits=%d method=%s)",
                patient_id,
                len(anchors.referral_anchors),
                len(anchors.diagnosis_anchors),
                len(anchors.treatment_anchors),
                len(getattr(anchors, "specialist_visit_anchors", [])),
                getattr(anchors, "detection_method", "unknown"),
            )
        else:
            client = PatientGraphClient()
            try:
                anchors = detect_anchors(
                    patient_id=patient_id,
                    start_date=start_date,
                    end_date=end_date,
                    patient_client=client,
                )
            finally:
                client.close()
            _checkpoint_save(store, f"analysis:{patient_id}:anchors", dataclasses.asdict(anchors))
            logger.info(
                "Patient %s — anchors: referrals=%d diagnosis=%d treatment=%d "
                "specialist_visits=%d [method=%s]",
                patient_id,
                len(anchors.referral_anchors),
                len(anchors.diagnosis_anchors),
                len(anchors.treatment_anchors),
                len(anchors.specialist_visit_anchors),
                anchors.detection_method,
            )

        # ---------------------------------------------------------- #
        # Step 2: Episode building + consolidation                     #
        # ---------------------------------------------------------- #
        episode_result = _checkpoint_load(
            store, f"analysis:{patient_id}:episodes", EpisodeBuildResult
        )
        if episode_result:
            logger.info(
                "Patient %s — episodes: resumed from checkpoint "
                "(created=%d completed=%d merged=%d)",
                patient_id,
                episode_result.episodes_created,
                episode_result.episodes_completed,
                episode_result.episodes_merged,
            )
        else:
            client = PatientGraphClient()
            try:
                episode_result = await build_episodes(
                    patient_id=patient_id,
                    anchors=anchors,
                    patient_client=client,
                    max_episodes=None,
                )
            finally:
                client.close()
            _checkpoint_save(
                store,
                f"analysis:{patient_id}:episodes",
                dataclasses.asdict(episode_result),
            )
            logger.info(
                "Patient %s — episodes: created=%d completed=%d merged=%d",
                patient_id,
                episode_result.episodes_created,
                episode_result.episodes_completed,
                episode_result.episodes_merged,
            )

        # ---------------------------------------------------------- #
        # Step 3: Safety-net / unwarranted variation                   #
        # ---------------------------------------------------------- #
        safety_net_signals = _checkpoint_load_list(
            store, f"analysis:{patient_id}:safety_net"
        )
        if safety_net_signals is not None:
            logger.info(
                "Patient %s — safety-net: resumed from checkpoint (%d signals)",
                patient_id, len(safety_net_signals),
            )
        else:
            patient_client = PatientGraphClient()
            knowledge_client = KnowledgeGraphClient()
            try:
                safety_net_signals = detect_safety_net_signals(
                    patient_id=patient_id,
                    episode_ids=episode_result.episode_ids,
                    patient_client=patient_client,
                    knowledge_client=knowledge_client,
                )
                _persist_safety_net_alerts(patient_id, safety_net_signals, patient_client)
            finally:
                patient_client.close()
                knowledge_client.close()
            _checkpoint_save(store, f"analysis:{patient_id}:safety_net", safety_net_signals)
            logger.info(
                "Patient %s — safety-net: %d signals detected and persisted",
                patient_id, len(safety_net_signals),
            )

        # ---------------------------------------------------------- #
        # Step 4: Abnormal results                                     #
        # ---------------------------------------------------------- #
        abnormal = _checkpoint_load_list(store, f"analysis:{patient_id}:abnormal")
        if abnormal is not None:
            logger.info(
                "Patient %s — abnormal results: resumed from checkpoint (%d flagged)",
                patient_id, len(abnormal),
            )
        else:
            client = PatientGraphClient()
            try:
                abnormal = detect_abnormal_results(
                    patient_id=patient_id,
                    start_date=start_date,
                    end_date=end_date,
                    patient_client=client,
                )
            finally:
                client.close()
            _checkpoint_save(store, f"analysis:{patient_id}:abnormal", abnormal)
            logger.info("Patient %s — abnormal results: %d flagged", patient_id, len(abnormal))

        # ---------------------------------------------------------- #
        # Step 5: KPI metrics                                          #
        # ---------------------------------------------------------- #
        kpis = _checkpoint_load_list(store, f"analysis:{patient_id}:kpis")
        if kpis is not None:
            logger.info(
                "Patient %s — KPIs: resumed from checkpoint (%d metrics)",
                patient_id, len(kpis),
            )
        else:
            client = PatientGraphClient()
            try:
                kpis = calculate_kpis(
                    patient_id=patient_id,
                    episode_ids=episode_result.episode_ids,
                    patient_client=client,
                )
            finally:
                client.close()
            _checkpoint_save(store, f"analysis:{patient_id}:kpis", kpis)
            logger.info("Patient %s — KPIs: %d metrics calculated", patient_id, len(kpis))

        logger.info("Analysis job completed: patient=%s", patient_id)

    except Exception:
        logger.exception("Analysis job failed: patient=%s", patient_id)
        raise  # re-raise so the Azure adapter abandons the message for retry


# ------------------------------------------------------------------
# Checkpoint helpers
# ------------------------------------------------------------------

def _checkpoint_load(store: CheckpointStore, key: str, dataclass_type) -> Any | None:
    """Load a dataclass from a Redis checkpoint, or return None on miss."""
    cached = store.get(key)
    if cached is None:
        return None
    try:
        # Strip keys not in the dataclass to avoid unexpected kwarg errors
        fields = {f.name for f in dataclasses.fields(dataclass_type)}
        filtered = {k: v for k, v in cached.items() if k in fields}
        return dataclass_type(**filtered)
    except Exception:
        logger.debug("Failed to deserialise checkpoint %s as %s", key, dataclass_type.__name__)
        return None


def _checkpoint_load_list(store: CheckpointStore, key: str) -> list | None:
    """Load a list from a Redis checkpoint, or return None on miss."""
    cached = store.get(key)
    if cached is None:
        return None
    if isinstance(cached, list):
        return cached
    return None


def _checkpoint_save(store: CheckpointStore, key: str, value: Any) -> None:
    """Persist a checkpoint value; silently ignores errors."""
    try:
        store.set(key, value)
    except Exception:
        logger.debug("Failed to save checkpoint %s", key, exc_info=True)


# ------------------------------------------------------------------
# Persistence helpers
# ------------------------------------------------------------------

def _persist_safety_net_alerts(
    patient_id: str,
    signals: List[Dict[str, Any]],
    client: PatientGraphClient,
) -> None:
    """Persist detected safety-net signals as SafetyNetAlert nodes linked to Patient and Episode."""
    for signal in signals:
        alert_id = f"safetynet_{uuid4().hex[:12]}"
        try:
            client.run(
                "MATCH (p:Patient) WHERE toString(p.id) = $pid "
                "MERGE (a:SafetyNetAlert {id: $aid}) "
                "SET a.alert_type       = $alert_type, "
                "    a.rule_name        = $alert_type, "
                "    a.patient_id       = $pid, "
                "    a.severity         = $severity, "
                "    a.status           = 'open', "
                "    a.recommendation_title = $description, "
                "    a.suggested_action = $description, "
                "    a.actioned         = false, "
                "    a.needs_review     = true, "
                "    a.created_at       = datetime() "
                "MERGE (p)-[:HAS_SAFETY_NET_ALERT]->(a) "
                "WITH a "
                "OPTIONAL MATCH (ep:EpisodeOfCare {episode_id: $eid}) "
                "FOREACH (_ IN CASE WHEN ep IS NOT NULL THEN [1] ELSE [] END | "
                "    MERGE (a)-[:FOR_EPISODE]->(ep))",
                pid=patient_id,
                aid=alert_id,
                alert_type=signal.get("type", "unknown"),
                severity=signal.get("severity", "warning"),
                description=signal.get("description", ""),
                eid=signal.get("episode_id", ""),
            )
        except Exception:
            logger.warning("Failed to persist safety-net alert %s", alert_id, exc_info=True)
