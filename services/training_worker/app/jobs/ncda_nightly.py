"""Stage 11 - Nightly self-learning job for the NCDA detector.

Atlas trace:
  DO: DO-9488B454
  DI: DI-D46D83FA
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-9488B454")

Pipeline:
    1. Pull new reviewer signoffs from ncda_label_audit + active-learning
       queue.
    2. Re-export gold from tidied reviewed EpisodeOfCare records.
    3. LLM-refresh silver on patients with new content (skipped when no
       LLM client wired).
    4. Retrain role and linkage classifiers; refit calibrators.
    5. Run Stage 12 evaluation harness.
    6. Promote behind feature flag if metrics meet gate; alert on drift.

The job is idempotent and can be re-run; promotion to the live model slot
is gated on per-cohort precision and per-class F1 floors.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

# Promotion gates - mirror the Stage 12 thresholds.
MIN_ROLE_F1 = 0.6
MIN_COHORT_PRECISION = 0.7
DRIFT_DROP_POINTS = 0.03


@dataclass
class NightlyResult:
    started_at: str
    finished_at: str
    role_artifact: Path | None = None
    linkage_artifact: Path | None = None
    metrics: dict = field(default_factory=dict)
    promoted: bool = False
    drift_alerts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def run_nightly(
    *,
    gold_rows_loader,
    silver_rows_loader,
    pair_rows_loader,
    role_artifact_path: Path,
    linkage_artifact_path: Path,
    evaluator,
    promoter=None,
    historical_metrics: list[dict] | None = None,
) -> NightlyResult:
    """Orchestrate the nightly retrain + evaluate + promote loop.

    All inputs are dependency-injected so the job is unit-testable in
    isolation.

    Args:
        gold_rows_loader: callable() -> Iterable[dict] of role-labelled rows.
        silver_rows_loader: callable() -> Iterable[dict] of LLM silver rows.
        pair_rows_loader: callable() -> Iterable[dict] of linkage pair rows.
        role_artifact_path: target path for the trained role classifier.
        linkage_artifact_path: target path for the trained linkage classifier.
        evaluator: callable(role_artifact, linkage_artifact) -> dict metrics.
        promoter: callable(role_artifact, linkage_artifact, metrics) -> bool.
        historical_metrics: optional list of prior-day metric dicts for drift.
    """
    start = datetime.now(timezone.utc)
    result = NightlyResult(
        started_at=start.isoformat(timespec="seconds"),
        finished_at="",
    )
    role_path = _train_role(gold_rows_loader, silver_rows_loader, role_artifact_path)
    result.role_artifact = role_path
    linkage_path = _train_linkage(pair_rows_loader, linkage_artifact_path)
    result.linkage_artifact = linkage_path

    metrics = evaluator(role_artifact=role_path, linkage_artifact=linkage_path)
    result.metrics = metrics or {}
    result.drift_alerts = detect_drift(metrics, historical_metrics or [])
    result.promoted = _maybe_promote(metrics, promoter, role_path, linkage_path)

    result.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return result


def _train_role(
    gold_loader, silver_loader, artifact_path: Path
) -> Path:
    from services.training_worker.app.ncda_role_trainer import (
        train_role_classifier,
    )

    train_role_classifier(
        gold_rows=list(gold_loader()),
        silver_rows=list(silver_loader()),
        artifact_path=artifact_path,
    )
    return artifact_path


def _train_linkage(pair_loader, artifact_path: Path) -> Path:
    from services.training_worker.app.ncda_linkage_trainer import (
        train_linkage_classifier,
    )

    train_linkage_classifier(
        list(pair_loader()),
        artifact_path=artifact_path,
    )
    return artifact_path


def _maybe_promote(
    metrics: dict,
    promoter,
    role_artifact: Path,
    linkage_artifact: Path,
) -> bool:
    if promoter is None:
        return False
    if not metrics:
        return False
    if not _meets_promotion_gate(metrics):
        return False
    return bool(promoter(role_artifact, linkage_artifact, metrics))


def _meets_promotion_gate(metrics: dict) -> bool:
    role_metrics = metrics.get("role_metrics") or {}
    cohort_metrics = metrics.get("cohort_metrics") or {}
    if any(
        (entry.get("f1", 0.0) < MIN_ROLE_F1)
        for entry in role_metrics.values()
    ):
        return False
    if any(
        (entry.get("precision", 0.0) < MIN_COHORT_PRECISION)
        for entry in cohort_metrics.values()
    ):
        return False
    return True


def detect_drift(
    today_metrics: dict, historical: Iterable[dict]
) -> list[str]:
    """Compare today's per-cohort precision against the rolling 30-day mean."""
    history = list(historical)
    if not history:
        return []
    rolling = _rolling_mean_per_cohort(history)
    today_cohorts = today_metrics.get("cohort_metrics") or {}
    alerts: list[str] = []
    for cohort_id, entry in today_cohorts.items():
        prior = rolling.get(cohort_id)
        if prior is None:
            continue
        delta = prior - entry.get("precision", 0.0)
        if delta > DRIFT_DROP_POINTS:
            alerts.append(
                f"cohort {cohort_id} precision dropped {delta:.3f} below "
                f"30-day mean (was {prior:.3f}, now {entry.get('precision', 0.0):.3f})"
            )
    return alerts


def _rolling_mean_per_cohort(history: list[dict]) -> dict[str, float]:
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for snapshot in history:
        cohort_metrics = snapshot.get("cohort_metrics") or {}
        for cohort_id, entry in cohort_metrics.items():
            sums[cohort_id] = sums.get(cohort_id, 0.0) + float(
                entry.get("precision", 0.0)
            )
            counts[cohort_id] = counts.get(cohort_id, 0) + 1
    return {k: sums[k] / counts[k] for k in sums if counts[k] > 0}


def write_run_log(result: NightlyResult, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"ncda_nightly_{result.started_at.replace(':', '')}.json"
    payload = {
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "role_artifact": str(result.role_artifact) if result.role_artifact else None,
        "linkage_artifact": str(result.linkage_artifact)
        if result.linkage_artifact
        else None,
        "metrics": result.metrics,
        "promoted": result.promoted,
        "drift_alerts": result.drift_alerts,
        "notes": result.notes,
    }
    target.write_text(json.dumps(payload, indent=2))
    return target
