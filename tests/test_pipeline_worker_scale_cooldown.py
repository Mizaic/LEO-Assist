"""Pipeline worker may scale to zero only after a long idle cooldown.

KEDA counts waiting Service Bus messages, not a locked extract.
A short cooldown therefore kills the replica mid-run. The scale
block must keep minReplicas at 0 and wait at least one hour.
"""

from __future__ import annotations

import re
from pathlib import Path

CONTAINER_APPS = (
    Path(__file__).parent.parent / "infra" / "bicep" / "modules" / "container-apps.bicep"
)
_MIN_COOLDOWN_SECONDS = 3600


def _pipeline_worker_scale_block(source: str) -> str:
    match = re.search(
        r"name: 'pipeline-worker'.*?scale:\s*\{(?P<body>.*?)\n      \}",
        source,
        re.DOTALL,
    )
    assert match, "pipeline-worker scale block missing from container-apps.bicep"
    return match.group("body")


def test_pipeline_worker_can_scale_to_zero() -> None:
    body = _pipeline_worker_scale_block(CONTAINER_APPS.read_text())
    assert re.search(r"minReplicas:\s*0\b", body), (
        "pipeline-worker must keep minReplicas 0 so idle hours can scale to zero"
    )


def test_pipeline_worker_cooldown_covers_locked_extract() -> None:
    source = CONTAINER_APPS.read_text()
    body = _pipeline_worker_scale_block(source)
    cooldown = re.search(r"cooldownPeriod:\s*(\d+)", body)
    assert cooldown, (
        "pipeline-worker scale must set cooldownPeriod; "
        "KEDA otherwise uses 300s and kills a locked extract"
    )
    assert int(cooldown.group(1)) >= _MIN_COOLDOWN_SECONDS, (
        f"pipeline-worker cooldownPeriod must be >= {_MIN_COOLDOWN_SECONDS}s "
        "to outlast a leased extract"
    )
    worker = re.search(
        r"resource pipelineWorker 'Microsoft\.App/containerApps@([^']+)'",
        source,
    )
    assert worker, "pipeline-worker resource missing"
    year, month = (int(part) for part in worker.group(1).split("-")[:2])
    assert (year, month) >= (2025, 1), (
        "pipeline-worker must use containerApps@2025-01-01 or later "
        "so cooldownPeriod is a real ARM property"
    )
