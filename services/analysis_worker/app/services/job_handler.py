"""Handle incoming analysis job messages from the message bus.

Orchestrates the full analysis pipeline for a patient:
1. Anchor detection
2. Episode building + consolidation
3. Safety-net / unwarranted variation
4. Abnormal results
5. KPI metrics
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List
from uuid import uuid4

from libs.message_bus.base import Message
from libs.neo4j_client.client import PatientGraphClient, KnowledgeGraphClient
from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors
from services.analysis_worker.app.analyzers.episode_builder import build_episodes
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

    patient_client = PatientGraphClient()
    knowledge_client = KnowledgeGraphClient()

    try:
        # Step 1: Anchor detection
        anchors = detect_anchors(
            patient_id=patient_id,
            start_date=start_date,
            end_date=end_date,
            patient_client=patient_client,
        )
        logger.info(
            "Anchors: referrals=%d diagnosis=%d treatment=%d",
            len(anchors.referral_anchors),
            len(anchors.diagnosis_anchors),
            len(anchors.treatment_anchors),
        )

        # Step 2: Episode building + consolidation
        episode_result = await build_episodes(
            patient_id=patient_id,
            anchors=anchors,
            patient_client=patient_client,
            max_episodes=None,
        )
        logger.info(
            "Episodes: created=%d completed=%d merged=%d",
            episode_result.episodes_created,
            episode_result.episodes_completed,
            episode_result.episodes_merged,
        )

        # Step 3: Safety-net / unwarranted variation
        safety_net_signals = detect_safety_net_signals(
            patient_id=patient_id,
            episode_ids=episode_result.episode_ids,
            patient_client=patient_client,
            knowledge_client=knowledge_client,
        )
        _persist_safety_net_alerts(patient_id, safety_net_signals, patient_client)
        logger.info("safety-net signals: %d detected and persisted", len(safety_net_signals))

        # Step 4: Abnormal results
        abnormal = detect_abnormal_results(
            patient_id=patient_id,
            start_date=start_date,
            end_date=end_date,
            patient_client=patient_client,
        )
        logger.info("Abnormal results: %d flagged", len(abnormal))

        # Step 5: KPI metrics
        kpis = calculate_kpis(
            patient_id=patient_id,
            episode_ids=episode_result.episode_ids,
            patient_client=patient_client,
        )
        logger.info("KPIs calculated: %d metrics", len(kpis))

        logger.info("Analysis job completed: patient=%s", patient_id)
    except Exception:
        logger.exception("Analysis job failed: patient=%s", patient_id)
    finally:
        patient_client.close()
        knowledge_client.close()


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
