"""Handle incoming analysis job messages from the message bus.

Orchestrates the full analysis pipeline for a patient:
1. Anchor detection
2. Episode building + consolidation
3. CSS / unwarranted variation
4. Abnormal results
5. KPI metrics
"""

from __future__ import annotations

import logging
from typing import Any

from libs.message_bus.base import Message
from libs.neo4j_client.client import PatientGraphClient, KnowledgeGraphClient
from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors
from services.analysis_worker.app.analyzers.episode_builder import build_episodes
from services.analysis_worker.app.analyzers.css_detector import detect_css_signals
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
        )
        logger.info(
            "Episodes: created=%d completed=%d merged=%d",
            episode_result.episodes_created,
            episode_result.episodes_completed,
            episode_result.episodes_merged,
        )

        # Step 3: CSS / unwarranted variation
        css_signals = detect_css_signals(
            patient_id=patient_id,
            episode_ids=episode_result.episode_ids,
            patient_client=patient_client,
            knowledge_client=knowledge_client,
        )
        logger.info("CSS signals: %d detected", len(css_signals))

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
