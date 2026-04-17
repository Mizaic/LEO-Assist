"""Second and third pass: auto-close, merge, and outcome inference."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from libs.episodes.duplicate_resolver import (
    EpisodeRecord,
    MergeDecision,
    cluster_episodes,
    pick_evidence_winner,
)
from libs.pipeline.outcome_inference import score_post_specialist_encounters

from . import _config as cfg
from . import _cypher as cypher
from ._persistence import _run_with_retry
from ._types import _parse_date

logger = logging.getLogger(__name__)


def _row_to_record(row: dict) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id=str(row.get("episode_id") or ""),
        cancer_type=str(row.get("cancer_type") or ""),
        referral_date=_parse_date(row.get("referral_date")),
        end_date=_parse_date(row.get("end_date")),
        status=str(row.get("status") or ""),
        diagnosis_texts=[
            str(t) for t in (row.get("diagnosis_texts") or []) if t
        ],
        treatment_count=int(row.get("treatment_count") or 0),
        match_method=str(row.get("match_method") or "strict_site"),
    )


def _apply_merge_decision(
    decision: MergeDecision,
    patient_client: Any,
) -> None:
    """DI-LEO-AI-137: move IS_PART_OF edges onto the primary, then mark
    duplicates as merged. Both Cypher calls are wrapped in retry and
    failure of either aborts the remaining duplicates in the cluster
    only -- other clusters are unaffected."""
    for dup_id in decision.duplicates:
        try:
            _run_with_retry(
                patient_client,
                cypher.MOVE_LINKS_Q,
                f"MOVE links {dup_id} -> {decision.primary_id}",
                dup_id=dup_id,
                primary_id=decision.primary_id,
            )
        except Exception:  # noqa: BLE001
            logger.error(
                "Failed to move IS_PART_OF edges from %s to %s; skipping merge",
                dup_id,
                decision.primary_id,
            )
            continue
        try:
            _run_with_retry(
                patient_client,
                cypher.MARK_MERGED_Q,
                f"MERGE dup {dup_id}",
                dup_id=dup_id,
                primary_id=decision.primary_id,
                reasoning=decision.reasoning,
            )
        except Exception:  # noqa: BLE001
            logger.error("Failed to mark episode %s merged", dup_id)


def _merge_duplicate_episodes(patient_id: str, patient_client: Any) -> None:
    """Evidence-wins duplicate-episode merger (DI-LEO-AI-137).

    Replaces the legacy same-site same-cancer_type merger which was
    blind to NSS episodes and diagnosis-only floating episodes. See
    ``libs.episodes.duplicate_resolver`` for algorithm details.
    """
    try:
        rows = patient_client.run(
            cypher.FETCH_EPISODES_FOR_MERGE_Q, patient_id=patient_id
        )
    except Exception:  # noqa: BLE001
        logger.error("Failed to fetch episodes for merge dedup, patient %s", patient_id)
        return
    records = [_row_to_record(r) for r in rows]
    clusters = cluster_episodes(records, cfg.SAME_EPISODE_DAYS)
    for cluster in clusters:
        decision = pick_evidence_winner(cluster)
        if decision is None:
            continue
        _apply_merge_decision(decision, patient_client)


def _apply_auto_close_rules(
    patient_id: str,
    episode_ids: list[str],
    patient_client: Any,
) -> None:
    """Second-pass: merge dedup, NSS closure, stale-close."""
    if not episode_ids:
        return

    _merge_duplicate_episodes(patient_id, patient_client)

    try:
        _run_with_retry(
            patient_client,
            cypher.RELATED_CLOSE_Q,
            f"NSS close for {patient_id}",
            patient_id=patient_id,
            episode_ids=episode_ids,
            window_days=cfg.PHANTOM_COMPLETED_WINDOW,
        )
    except Exception:  # noqa: BLE001
        logger.error("NSS companion closure failed for patient %s", patient_id)

    try:
        _run_with_retry(
            patient_client,
            cypher.STALE_CLOSE_Q,
            f"Stale close for {patient_id}",
            patient_id=patient_id,
            episode_ids=episode_ids,
            post_spec_days=cfg.STALE_POST_SPECIALIST_DAYS,
            hard_days=cfg.STALE_HARD_DAYS,
        )
    except Exception:  # noqa: BLE001
        logger.error("Stale-close failed for patient %s", patient_id)


def _apply_outcome_inference(
    patient_id: str,
    episode_ids: list[str],
    patient_client: Any,
) -> None:
    """Third-pass: infer outcome for stale_post_specialist episodes.

    Design controls: DI-LEO-AI-088, R-LEO-AI-062.
    """
    if not episode_ids:
        return
    try:
        stale_eps = patient_client.run(
            cypher.INFERENCE_FETCH_Q,
            patient_id=patient_id,
            episode_ids=episode_ids,
        )
    except Exception:  # noqa: BLE001
        logger.error("Inference fetch failed for patient %s", patient_id)
        return

    for ep in stale_eps:
        ep_id = ep.get("episode_id")
        specialist_date = ep.get("specialist_date") or ""
        if not ep_id or not specialist_date:
            continue
        try:
            to_date = (
                date.fromisoformat(specialist_date)
                + timedelta(days=cfg.INFERENCE_POST_WINDOW_DAYS)
            ).isoformat()
            enc_rows = patient_client.run(
                cypher.INFERENCE_ENC_Q,
                pid=patient_id,
                from_date=specialist_date,
                to_date=to_date,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Inference encounter fetch failed for episode %s", ep_id)
            continue

        result = score_post_specialist_encounters(enc_rows)

        try:
            _run_with_retry(
                patient_client,
                cypher.INFERENCE_UPDATE_Q,
                f"Inference update {ep_id}",
                episode_id=ep_id,
                inferred_outcome=result.inferred_outcome,
                inferred_outcome_date=result.inferred_outcome_date,
                inferred_confidence=result.inferred_confidence,
                inference_signals=(
                    "|".join(result.inference_signals)
                    if result.inference_signals
                    else ""
                ),
            )
        except Exception:  # noqa: BLE001
            logger.error("Inference update failed for episode %s", ep_id)
