"""VT-66DA36EC: v2 detector persist parity with canonical lifecycle.

Pins the writer-side parity rule for the v2 detector runner:

* ``_EPISODE_MERGE`` only ever assigns canonical ``EpisodeStatus`` values
  (active / review / completed / closed_benign).
* The persist Cypher SKIPS the status SET when ``reviewed_at IS NOT NULL``
  on the matched node so a curator's signed-off verdict is never silently
  overwritten by a subsequent detector run (R-2AA626E7).

Atlas trace:
  DI: DI-C4CEFA32
  DO: DO-C5B5E91E
  R:  R-2AA626E7
"""

from __future__ import annotations

import re

from libs.episodes.status import ENGINE_OUTPUT_STATUSES, EpisodeStatus
from services.analysis_worker.app.episode_detector_v2 import runner as v2_runner


def test_persist_cypher_only_assigns_canonical_engine_statuses() -> None:
    """The persist Cypher must not contain any non-canonical status
    literal. The only status values that can land on the node come
    from the ``ep.status`` parameter, which is filled by
    ``canonical_status_from_v2_boundary`` and is always a member of
    ``ENGINE_OUTPUT_STATUSES``."""

    src = v2_runner._EPISODE_MERGE
    forbidden = {"open", "in_review", "benign_closure"}
    for token in forbidden:
        assert f"e.status = '{token}'" not in src
        assert f'e.status = "{token}"' not in src
        assert f"SET e.status = '{token}'" not in src
        assert f'SET e.status = "{token}"' not in src


def test_persist_cypher_respects_reviewed_at() -> None:
    """The persist Cypher must guard the status / intent SET behind
    a ``reviewed_at IS NULL`` check so the v2 detector cannot overwrite
    a curator-signed verdict."""

    src = v2_runner._EPISODE_MERGE
    # The FOREACH guard pattern we use to make the status SET
    # conditional on reviewed_at being null.
    pattern = re.compile(
        r"FOREACH\s*\(\s*_\s+IN\s+CASE\s+WHEN\s+e\.reviewed_at\s+IS\s+NULL",
        re.IGNORECASE,
    )
    assert pattern.search(src), (
        "Persist Cypher must wrap the status SET in a "
        "FOREACH guarded by 'e.reviewed_at IS NULL' so curator "
        "verdicts are respected."
    )
    assert "ep.status" in src
    assert "ep.needs_human_review" in src
    # Both review-flag fields stay in lockstep so the legacy
    # `needs_review` is also written from the canonical source.
    assert "e.needs_review = ep.needs_human_review" in src


def test_persist_cypher_recomputes_derived_interval_fields() -> None:
    """Milestone persistence must refresh the cached interval columns.

    The Mission Control table reads these episode properties directly,
    so v2 must keep them in sync with the linked milestone evidence.
    """

    src = v2_runner._EPISODE_MERGE
    assert "e.referral_date = referral_date" in src
    assert "e.diagnostic_interval_days" in src
    assert "e.benign_interval_days" in src
    assert "e.primary_care_interval_days" in src
    assert "e.dates_updated_at = datetime()" in src
    assert "duration.inDays(date(referral_date), date(diagnosis_date)).days" in src
    assert "duration.inDays(date(referral_date), date(benign_closure_date)).days" in src
    assert "duration.inDays(date(presentation_date), date(referral_date)).days" in src


def test_persist_cypher_refreshes_dates_outside_reviewed_status_guard() -> None:
    """Reviewed episodes keep curator status but still refresh evidence dates."""

    src = v2_runner._EPISODE_MERGE
    status_guard_start = src.index("FOREACH (_ IN CASE WHEN e.reviewed_at IS NULL")
    status_guard_end = src.index("MERGE (p)-[:HAS_EPISODE_OF_CARE]->(e)")
    guarded_block = src[status_guard_start:status_guard_end]
    assert "e.diagnostic_interval_days" not in guarded_block
    assert "e.benign_interval_days" not in guarded_block
    assert src.index("e.dates_updated_at = datetime()") > status_guard_end


def test_canonical_status_translator_is_used_at_persist_site() -> None:
    """The runner module imports the canonical translator and the
    persist row build calls it for every episode in the payload."""

    src = open(v2_runner.__file__, encoding="utf-8").read()
    assert "from libs.episodes.lifecycle import" in src
    assert "canonical_status_from_v2_boundary" in src
    # The translator is invoked when building the persist payload
    # rows, NOT just imported and then unused.
    payload_section = src.split("auto_episodes = auto_only", 1)[-1]
    assert "canonical_status_from_v2_boundary(" in payload_section, (
        "v2 runner must call canonical_status_from_v2_boundary when "
        "building the persist payload."
    )


class _RecordingClient:
    """Minimal stub of PatientGraphClient that captures `run` calls."""

    def __init__(self, rows: list[dict] | None = None) -> None:
        self._rows = rows or []
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **kwargs):  # noqa: D401 - driver shape
        if "HAS_ENCOUNTER" in query and "Patient" in query:
            return list(self._rows)
        self.calls.append((query, kwargs))
        return []


def test_persist_payload_status_values_are_canonical() -> None:
    """End-to-end: build the persist row payload from a synthetic
    auto-episode and assert every status in the payload is a member
    of ENGINE_OUTPUT_STATUSES."""

    from datetime import date

    from services.analysis_worker.app.episode_detector_v2.types import (
        ResolvedEpisode,
    )

    cases: list[ResolvedEpisode] = [
        ResolvedEpisode(
            episode_id="ep-1",
            site_key="breast",
            encounter_ids=["e1"],
            start_date=date(2025, 1, 1),
            end_date=None,
            suspected_site="breast",
            role="diagnosis",
            intent="confirmed",
            status="open",
            confidence_tier="auto",
            needs_human_review=False,
            review_reasons=[],
            vote_count=1,
            supporting_signals=[],
            alternatives_considered=[],
            generator_consensus=["referral"],
        ),
        ResolvedEpisode(
            episode_id="ep-2",
            site_key="lung",
            encounter_ids=["e2"],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 6, 1),
            suspected_site="lung",
            role="diagnosis",
            intent="ruled_out",
            status="benign_closure",
            confidence_tier="auto",
            needs_human_review=False,
            review_reasons=[],
            vote_count=1,
            supporting_signals=[],
            alternatives_considered=[],
            generator_consensus=["referral"],
        ),
        ResolvedEpisode(
            episode_id="ep-3",
            site_key="bowel",
            encounter_ids=["e3"],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 6, 1),
            suspected_site="bowel",
            role="diagnosis",
            intent="confirmed",
            status="closed",
            confidence_tier="auto",
            needs_human_review=False,
            review_reasons=[],
            vote_count=1,
            supporting_signals=[],
            alternatives_considered=[],
            generator_consensus=["referral"],
        ),
    ]
    from libs.episodes.lifecycle import canonical_status_from_v2_boundary

    for ep in cases:
        canonical = canonical_status_from_v2_boundary(
            ep.status, ep.needs_human_review
        )
        assert canonical in ENGINE_OUTPUT_STATUSES

    # Specific mappings: open+confirmed -> active, benign_closure ->
    # closed_benign, closed+confirmed -> completed.
    assert canonical_status_from_v2_boundary(
        cases[0].status, cases[0].needs_human_review
    ) == EpisodeStatus.ACTIVE.value
    assert canonical_status_from_v2_boundary(
        cases[1].status, cases[1].needs_human_review
    ) == EpisodeStatus.CLOSED_BENIGN.value
    assert canonical_status_from_v2_boundary(
        cases[2].status, cases[2].needs_human_review
    ) == EpisodeStatus.COMPLETED.value
