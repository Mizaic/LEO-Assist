"""Shared metric computations for LEO-AI-CORE.

Pure-math helpers with no I/O. Both the runtime analysis worker and
the one-shot ground-truth export pipeline use this module so a KPI
value for the same milestones is identical across the platform.

Public API
----------
- days_between: inclusive day difference between two ISO-8601 dates.
- pick_earliest_milestone: earliest non-empty date across equivalent keys.
- compute_interval_kpis: the four NCDA interval metrics from a milestone dict.
- INTERVAL_METRIC_NAMES: canonical set of metric names exposed by this module.

See DI-LEO-AI-125 (KPI persistence), DO-LEO-AI-125 (metrics consolidation).
"""

from libs.metrics.intervals import (
    INTERVAL_METRIC_NAMES,
    compute_interval_kpis,
    days_between,
    pick_earliest_milestone,
)

__all__ = [
    "INTERVAL_METRIC_NAMES",
    "compute_interval_kpis",
    "days_between",
    "pick_earliest_milestone",
]
