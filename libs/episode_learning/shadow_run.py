"""Shadow-run capture and comparison for v1 vs v2 episode detectors.

Atlas trace:
  DI: DI-8A5FCF4F (Defence-in-depth episode detector)

When the episode_pipeline feature flag is set to "shadow" both v1 and
v2 detectors run; v1 publishes, v2 writes its outputs to an
:EpisodeShadowRun audit node so QA can compare them later. This
module owns the comparison schema and the persistence Cypher.

The compare functions are pure on dict inputs so they are unit-test
friendly; the persistence helper requires a Neo4j-style runner with
a .run(cypher, **params) signature.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol


class GraphRunner(Protocol):
    def run(self, cypher: str, **params: Any) -> Any: ...


WRITE_SHADOW_RUN = """
MERGE (s:EpisodeShadowRun {patient_id: $patient_id, run_at: datetime($run_at)})
SET s.v1_episode_ids = $v1_episode_ids,
    s.v2_episode_ids = $v2_episode_ids,
    s.agreement      = $agreement,
    s.added_in_v2    = $added_in_v2,
    s.dropped_in_v2  = $dropped_in_v2,
    s.report_json    = $report_json
RETURN s.patient_id AS patient_id
"""


@dataclass(frozen=True)
class ShadowComparison:
    """Per-patient comparison row written to :EpisodeShadowRun."""

    patient_id: str
    run_at: datetime
    v1_episode_ids: tuple[str, ...]
    v2_episode_ids: tuple[str, ...]
    agreement: float
    added_in_v2: tuple[str, ...]
    dropped_in_v2: tuple[str, ...]


def compare_episode_lists_by_site(
    v1_episodes_by_site: dict[str, Iterable[str]],
    v2_episodes_by_site: dict[str, Iterable[str]],
) -> dict[str, dict[str, Any]]:
    """Compare episode ids per site_key.

    Each site is scored independently so a per-site champion rulebook
    can be judged on its own slice without noise from other sites.
    Site keys missing on one side default to an empty list on that
    side. Returned shape mirrors :func:`compare_episode_lists` keyed
    by site.
    """

    all_sites = set(v1_episodes_by_site) | set(v2_episodes_by_site)
    return {
        site: compare_episode_lists(
            v1_episodes_by_site.get(site, ()),
            v2_episodes_by_site.get(site, ()),
        )
        for site in sorted(all_sites)
    }


def compare_episode_lists(
    v1_episode_ids: Iterable[str],
    v2_episode_ids: Iterable[str],
) -> dict[str, Any]:
    """Compare two episode-id lists by exact match.

    The agreement metric is Jaccard similarity over episode ids; for
    the v2 detector this is conservative (different deterministic ids
    will count as disagreement even if the underlying encounters
    overlap). A second pass in the comparison report does the
    encounter-overlap analysis.
    """
    v1 = set(v1_episode_ids)
    v2 = set(v2_episode_ids)
    union = v1 | v2
    intersection = v1 & v2
    agreement = 0.0 if not union else round(len(intersection) / len(union), 4)
    return {
        "agreement": agreement,
        "added_in_v2": sorted(v2 - v1),
        "dropped_in_v2": sorted(v1 - v2),
        "v1_count": len(v1),
        "v2_count": len(v2),
        "intersection_count": len(intersection),
    }


def persist_shadow_run(
    runner: GraphRunner,
    *,
    patient_id: str,
    v1_episode_ids: Iterable[str],
    v2_episode_ids: Iterable[str],
    run_at: datetime | None = None,
) -> ShadowComparison:
    """Persist one comparison row to :EpisodeShadowRun.

    Returns the in-memory comparison so callers (currently the
    shadow branch of subgraphs/episode.py) can log a structured
    summary line as well.
    """
    when = run_at or datetime.now(timezone.utc)
    v1_ids = tuple(v1_episode_ids)
    v2_ids = tuple(v2_episode_ids)
    cmp = compare_episode_lists(v1_ids, v2_ids)
    payload = {
        "patient_id": patient_id,
        "run_at": when.isoformat(),
        "v1_episode_ids": list(v1_ids),
        "v2_episode_ids": list(v2_ids),
        "agreement": cmp["agreement"],
        "added_in_v2": cmp["added_in_v2"],
        "dropped_in_v2": cmp["dropped_in_v2"],
        "report_json": json.dumps(cmp, sort_keys=True),
    }
    runner.run(WRITE_SHADOW_RUN, **payload)
    return ShadowComparison(
        patient_id=patient_id,
        run_at=when,
        v1_episode_ids=v1_ids,
        v2_episode_ids=v2_ids,
        agreement=cmp["agreement"],
        added_in_v2=tuple(cmp["added_in_v2"]),
        dropped_in_v2=tuple(cmp["dropped_in_v2"]),
    )


@dataclass(frozen=True)
class CohortShadowReport:
    """Aggregate report across the cohort of shadow runs."""

    patients_evaluated: int
    auto_case_agreement_rate: float
    regression_recall: float
    fully_agreeing_patients: tuple[str, ...]
    diverging_patients: tuple[str, ...]
    rows: tuple[dict[str, Any], ...] = field(default_factory=tuple)


def aggregate_cohort_report(
    comparisons: Iterable[ShadowComparison],
    *,
    regression_cohort_patient_ids: Iterable[str],
) -> CohortShadowReport:
    """Roll up per-patient ShadowComparison rows into a cohort report.

    auto_case_agreement_rate -- fraction of comparisons with
        agreement == 1.0. This is the headline number ops needs to
        confirm before flipping the flag to v2.
    regression_recall -- fraction of regression-cohort patients
        whose v2 run produced ANY episodes (i.e. v2 did not silently
        drop the patient).
    """
    rows = list(comparisons)
    n = len(rows)
    fully_agreeing = tuple(
        sorted(c.patient_id for c in rows if c.agreement == 1.0)
    )
    diverging = tuple(sorted(c.patient_id for c in rows if c.agreement < 1.0))
    rate = 0.0 if n == 0 else round(len(fully_agreeing) / n, 4)
    regression_set = set(regression_cohort_patient_ids)
    regression_rows = [c for c in rows if c.patient_id in regression_set]
    if not regression_rows:
        recall = 0.0
    else:
        with_episodes = sum(
            1 for c in regression_rows if len(c.v2_episode_ids) > 0
        )
        recall = round(with_episodes / len(regression_rows), 4)
    payload = tuple(
        {
            "patient_id": c.patient_id,
            "agreement": c.agreement,
            "v1_count": len(c.v1_episode_ids),
            "v2_count": len(c.v2_episode_ids),
            "added_in_v2": list(c.added_in_v2),
            "dropped_in_v2": list(c.dropped_in_v2),
        }
        for c in rows
    )
    return CohortShadowReport(
        patients_evaluated=n,
        auto_case_agreement_rate=rate,
        regression_recall=recall,
        fully_agreeing_patients=fully_agreeing,
        diverging_patients=diverging,
        rows=payload,
    )
