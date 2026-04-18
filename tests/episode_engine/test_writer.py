"""Unit VT for the episode engine writer (VT-LEO-AI-505)."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest

from services.analysis_worker.app.episode_engine.schemas import (
    Milestone,
    Provenance,
    ReconciledEpisode,
    StageTrace,
)
from services.analysis_worker.app.episode_engine.writer import (
    ENGINE_VERSION,
    _condition_type,
    _episode_status,
    _first_seen_date,
    deterministic_episode_id,
    write_episodes,
)


def _milestone(
    *,
    type: str = "referral",
    iso_date: str = "2025-03-26",
    encounter_id: str = "enc-1",
    treatment_type: str | None = None,
) -> Milestone:
    return Milestone(
        type=type,  # type: ignore[arg-type]
        date=date.fromisoformat(iso_date),
        encounter_id=encounter_id,
        evidence_quote="quote text",
        treatment_type=treatment_type,  # type: ignore[arg-type]
        confidence=0.9,
        reasoning="r",
    )


def _episode(
    *,
    site: str = "breast",
    episode_type: str = "cancer",
    start: str = "2025-03-26",
    end: str | None = "2025-07-28",
    needs_human_review: bool = False,
    milestones: list[Milestone] | None = None,
) -> ReconciledEpisode:
    return ReconciledEpisode(
        episode_id="ignored-by-writer",
        suspected_site=site,
        episode_type=episode_type,  # type: ignore[arg-type]
        window_start=date.fromisoformat(start),
        window_end=date.fromisoformat(end) if end else None,
        milestones=milestones or [_milestone()],
        confidence=0.9,
        reasoning="r",
        needs_human_review=needs_human_review,
        merged_from=["w1"],
    )


def _provenance() -> Provenance:
    return Provenance(
        trace_id="eet-test",
        stages=[
            StageTrace(stage="segmenter", prompt_version="v1", model_id="haiku")
        ],
        total_input_tokens=100,
        total_output_tokens=10,
        total_latency_ms=1234,
        timeline_encounter_count=42,
    )


def test_deterministic_episode_id_is_stable_and_site_lowercased():
    """VT-505-TC-001: same inputs produce the same id; site is case-insensitive."""

    a = deterministic_episode_id("p-1", "Breast", "2025-03-26")
    b = deterministic_episode_id("p-1", "breast", "2025-03-26")
    c = deterministic_episode_id("p-1", "breast", "2025-03-27")
    assert a == b, "site should be normalised to lower-case"
    assert a != c, "different window_start should change the id"
    assert a.startswith("ep-")
    assert len(a) == 3 + 16


def test_episode_status_priority_order():
    """VT-505-TC-002: benign > completed > review > active in status precedence."""

    benign = _episode(episode_type="benign", milestones=[
        _milestone(type="benign_closure", iso_date="2025-04-01")
    ])
    completed = _episode(milestones=[
        _milestone(type="treatment_completed", iso_date="2025-08-01")
    ])
    review = _episode(needs_human_review=True)
    active = _episode()

    assert _episode_status(benign) == "benign_closed"
    assert _episode_status(completed) == "completed"
    assert _episode_status(review) == "review"
    assert _episode_status(active) == "active"


def test_first_seen_date_returns_iso_or_none():
    """VT-505-TC-003: first_seen_date returns ISO date if present, else None."""

    eps_with = _episode(milestones=[
        _milestone(type="first_seen", iso_date="2025-04-28")
    ])
    eps_without = _episode(milestones=[_milestone(type="referral")])

    assert _first_seen_date(eps_with.milestones) == "2025-04-28"
    assert _first_seen_date(eps_without.milestones) is None


def test_condition_type_maps_cancer_variants():
    """VT-505-TC-004: cancer + multi_site map to 'cancer'; others passthrough."""

    assert _condition_type(_episode(episode_type="cancer")) == "cancer"
    assert _condition_type(_episode(episode_type="multi_site")) == "cancer"
    assert _condition_type(_episode(episode_type="benign")) == "benign"
    assert _condition_type(_episode(episode_type="non_cancer")) == "non_cancer"


def test_dry_run_does_not_touch_neo4j():
    """VT-505-TC-005: dry_run returns materialised episodes and skips Cypher."""

    client = MagicMock()
    eps = [_episode()]
    out = write_episodes(
        client=client,
        patient_id="p-1",
        domain_id="d-1",
        episodes=eps,
        provenance=_provenance(),
        dry_run=True,
    )
    assert client.run.call_count == 0
    assert len(out) == 1
    assert out[0].episode_id.startswith("ep-")
    assert out[0].patient_id == "p-1"


def test_apply_run_deletes_then_writes_episode_and_milestone():
    """VT-505-TC-006: real run issues delete + episode write + milestone link."""

    client = MagicMock()
    client.run.return_value = [{"deleted": 0}]

    eps = [_episode(milestones=[
        _milestone(type="first_seen", iso_date="2025-04-28", encounter_id="enc-2")
    ])]
    out = write_episodes(
        client=client,
        patient_id="p-1",
        domain_id="d-1",
        episodes=eps,
        provenance=_provenance(),
        dry_run=False,
    )

    assert len(out) == 1
    queries: list[str] = [c.args[0] for c in client.run.call_args_list]
    assert any("DETACH DELETE ep" in q for q in queries)
    assert any("MERGE (ep:EpisodeOfCare" in q for q in queries)
    assert any("MERGE (e)-[r:IS_PART_OF" in q for q in queries)

    write_calls = [
        c for c in client.run.call_args_list
        if "MERGE (ep:EpisodeOfCare" in c.args[0]
    ]
    write_kwargs: dict[str, Any] = write_calls[0].kwargs
    assert write_kwargs["engine_version"] == ENGINE_VERSION
    assert write_kwargs["trace_id"] == "eet-test"
    assert write_kwargs["first_seen_date"] == "2025-04-28"
    assert write_kwargs["episode_type"] == "cancer"


def test_milestone_link_failure_does_not_break_other_milestones(caplog):
    """VT-505-TC-007: a failing milestone link is logged and skipped."""

    client = MagicMock()

    def _run(query: str, **kwargs):
        if "MERGE (e)-[r:IS_PART_OF" in query and kwargs.get("encounter_id") == "bad":
            raise RuntimeError("encounter not found")
        if "DETACH DELETE ep" in query:
            return [{"deleted": 0}]
        return []

    client.run.side_effect = _run

    eps = [_episode(milestones=[
        _milestone(type="referral", encounter_id="bad"),
        _milestone(type="first_seen", encounter_id="enc-good"),
    ])]
    with caplog.at_level("ERROR"):
        out = write_episodes(
            client=client,
            patient_id="p-1",
            domain_id="d-1",
            episodes=eps,
            provenance=_provenance(),
            dry_run=False,
        )

    assert len(out) == 1
    assert "Failed to link milestone" in caplog.text
    link_calls = [
        c for c in client.run.call_args_list
        if "MERGE (e)-[r:IS_PART_OF" in c.args[0]
    ]
    assert len(link_calls) == 2, "both milestones should still be attempted"


def test_apply_run_with_no_episodes_still_deletes_existing():
    """VT-505-TC-008: empty episode list still wipes existing episodes."""

    client = MagicMock()
    client.run.return_value = [{"deleted": 3}]
    out = write_episodes(
        client=client,
        patient_id="p-1",
        domain_id="d-1",
        episodes=[],
        provenance=_provenance(),
        dry_run=False,
    )
    assert out == []
    queries = [c.args[0] for c in client.run.call_args_list]
    assert any("DETACH DELETE ep" in q for q in queries)
    assert not any("MERGE (ep:EpisodeOfCare" in q for q in queries)


@pytest.mark.parametrize("ep_type", ["cancer", "multi_site", "benign", "non_cancer"])
def test_episode_id_unique_per_site_window_pair(ep_type):
    """VT-505-TC-009: ids are stable per (patient, site, window_start)."""

    ep1 = _episode(site="breast", start="2025-03-26", episode_type=ep_type)
    ep2 = _episode(site="skin", start="2025-03-26", episode_type=ep_type)
    id1 = deterministic_episode_id("p-1", ep1.suspected_site, "2025-03-26")
    id2 = deterministic_episode_id("p-1", ep2.suspected_site, "2025-03-26")
    assert id1 != id2
