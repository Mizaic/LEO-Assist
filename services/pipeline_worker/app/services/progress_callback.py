"""Progress callback factory for the pipeline_worker message bus consumer.

Atlas trace:
  DO: DO-4641EEE1
  VT: VT-297D9C18
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4641EEE1")

Builds a step_callback that the WorkflowEngine invokes after each step
and at run completion. The callback publishes events to Redis pub/sub via
services.coding_worker.app.services.progress_publisher.publish_progress
so the SSE stream /pipeline/progress/{run_id} receives matching events.

This mirrors services.coding_worker.app.services.job_handler so that the
SSE behaviour is identical regardless of which worker drains the
pipeline-jobs queue.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("pipeline-worker")

StepCallback = Callable[[dict[str, Any]], None]


def build_progress_callback(run_id: str, *, patient_id: str = "") -> StepCallback:
    """Return a step_callback that publishes WorkflowEngine events to Redis.

    Args:
        run_id: Correlation id used as the SSE channel suffix
            ("pipeline:{run_id}"). Required and non-empty.
        patient_id: Optional patient id stamped onto every payload so
            consumers can scope events to a patient.
    """
    if not run_id:
        raise ValueError("run_id is required for progress callback")

    from services.coding_worker.app.services.progress_publisher import (
        publish_progress,
    )
    from libs.redis_client.rebuild_status import update_from_event

    def _callback(event: dict[str, Any]) -> None:
        payload = dict(event)
        payload.setdefault("run_id", run_id)
        if patient_id:
            payload.setdefault("patient_id", patient_id)
        publish_progress(run_id, payload)
        try:
            update_from_event(patient_id or "", run_id, payload)
        except Exception:
            logger.debug(
                "rebuild status update failed patient=%s run=%s",
                patient_id,
                run_id,
                exc_info=True,
            )

    return _callback
