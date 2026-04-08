"""Second and third pass: auto-close, merge, and outcome inference."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from libs.pipeline.outcome_inference import score_post_specialist_encounters

from . import _config as cfg
from . import _cypher as cypher
from ._persistence import _run_with_retry
from ._types import _parse_date

logger = logging.getLogger(__name__)


def _merge_same_site_duplicates(patient_id: str, patient_client: Any) -> None:
    """Collapse same-site episodes whose referral_dates are within the
    time window.  Earliest episode per site cluster is kept as primary."""
    try:
        rows = patient_client.run(
            cypher.FETCH_EPISODES_FOR_MERGE_Q, patient_id=patient_id
        )
    except Exception:  # noqa: BLE001
        logger.error(
            "Failed to fetch episodes for merge dedup, patient %s", patient_id
        )
        return

    by_site: dict[str, list[dict]] = {}
    for r in rows:
        ctype = r.get("cancer_type") or ""
        if ctype == "non_site_specific":
            continue
        by_site.setdefault(ctype, []).append(r)

    for ctype, eps in by_site.items():
        if len(eps) < 2:
            continue
        eps_sorted = sorted(eps, key=lambda e: str(e.get("referral_date") or ""))
        primary = eps_sorted[0]
        primary_date = _parse_date(primary["referral_date"])
        if not primary_date:
            continue
        for dup in eps_sorted[1:]:
            dup_date = _parse_date(dup["referral_date"])
            if not dup_date:
                continue
            gap = (dup_date - primary_date).days
            if 0 <= gap <= cfg.SAME_EPISODE_DAYS:
                try:
                    _run_with_retry(
                        patient_client,
                        cypher.MARK_MERGED_Q,
                        f"MERGE dup {dup['episode_id']}",
                        dup_id=dup["episode_id"],
                        primary_id=primary["episode_id"],
                        reasoning=(
                            f"Auto-merged: same cancer type ({ctype}) within "
                            f"{gap} days of {primary['episode_id']}"
                        ),
                    )
                except Exception:  # noqa: BLE001
                    logger.error(
                        "Failed to merge episode %s into %s",
                        dup["episode_id"],
                        primary["episode_id"],
                    )


def _apply_auto_close_rules(
    patient_id: str,
    episode_ids: list[str],
    patient_client: Any,
) -> None:
    """Second-pass: merge dedup, NSS closure, stale-close."""
    if not episode_ids:
        return

    _merge_same_site_duplicates(patient_id, patient_client)

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
        logger.error(
            "Inference fetch failed for patient %s", patient_id
        )
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
            logger.warning(
                "Inference encounter fetch failed for episode %s", ep_id
            )
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
