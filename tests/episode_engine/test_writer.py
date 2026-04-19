"""Unit VT for the episode engine writer (VT-LEO-AI-505)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest

from services.analysis_worker.app.episode_engine.schemas import (
    Disruption,
    Milestone,
    Provenance,
    ReconciledEpisode,
    SafetyNetting,
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
from services.analysis_worker.app.episode_engine.writer_rollups import (
    disruption_phase,
    disruption_summary,
    earliest_phase,
    safety_netting_payload,
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


def test_first_presentation_and_outcome_letter_persist_on_episode_and_link():
    """VT-505-TC-010: first_presentation + outcome_letter milestones project
    onto the EpisodeOfCare node and onto the IS_PART_OF relationship."""

    client = MagicMock()
    client.run.return_value = [{"deleted": 0}]

    eps = [
        _episode(
            milestones=[
                _milestone(
                    type="first_presentation",
                    iso_date="2025-03-12",
                    encounter_id="enc-pres",
                ),
                _milestone(
                    type="referral",
                    iso_date="2025-03-26",
                    encounter_id="enc-ref",
                ),
                _milestone(
                    type="outcome_letter",
                    iso_date="2025-05-12",
                    encounter_id="enc-letter",
                ),
            ]
        )
    ]
    # Override first_presentation to carry presentation_place
    eps[0].milestones[0] = Milestone(
        type="first_presentation",
        date=date.fromisoformat("2025-03-12"),
        encounter_id="enc-pres",
        evidence_quote="GP face-to-face for new breast lump.",
        presentation_place="gp_surgery",
        confidence=0.9,
        reasoning="r",
    )

    write_episodes(
        client=client,
        patient_id="p-1",
        domain_id="d-1",
        episodes=eps,
        provenance=_provenance(),
        dry_run=False,
    )

    write_calls = [
        c for c in client.run.call_args_list
        if "MERGE (ep:EpisodeOfCare" in c.args[0]
    ]
    assert len(write_calls) == 1
    write_kwargs = write_calls[0].kwargs
    assert write_kwargs["first_presentation_date"] == "2025-03-12"
    assert write_kwargs["place_of_first_presentation"] == "gp_surgery"
    assert write_kwargs["outcome_letter_date"] == "2025-05-12"

    link_calls = [
        c for c in client.run.call_args_list
        if "MERGE (e)-[r:IS_PART_OF" in c.args[0]
    ]
    by_type = {c.kwargs["milestone_type"]: c.kwargs for c in link_calls}
    assert by_type["first_presentation"]["presentation_place"] == "gp_surgery"
    assert by_type["referral"]["presentation_place"] is None
    assert by_type["outcome_letter"]["presentation_place"] is None


@pytest.mark.parametrize("ep_type", ["cancer", "multi_site", "benign", "non_cancer"])
def test_episode_id_unique_per_site_window_pair(ep_type):
    """VT-505-TC-009: ids are stable per (patient, site, window_start)."""

    ep1 = _episode(site="breast", start="2025-03-26", episode_type=ep_type)
    ep2 = _episode(site="skin", start="2025-03-26", episode_type=ep_type)
    id1 = deterministic_episode_id("p-1", ep1.suspected_site, "2025-03-26")
    id2 = deterministic_episode_id("p-1", ep2.suspected_site, "2025-03-26")
    assert id1 != id2


def test_denormalised_milestone_dates_persist_on_episode():
    """VT-505-TC-011: referral_date, diagnosis_date, treatment_started_date,
    treatment_completed_date, specialist_date are denormalised onto the
    EpisodeOfCare so the analytics dashboards can read them without a
    relationship traversal."""

    client = MagicMock()
    client.run.return_value = [{"deleted": 0}]

    eps = [
        _episode(
            milestones=[
                _milestone(
                    type="referral", iso_date="2025-03-26", encounter_id="enc-ref"
                ),
                _milestone(
                    type="first_seen",
                    iso_date="2025-04-28",
                    encounter_id="enc-fs",
                ),
                _milestone(
                    type="diagnosis_confirmed",
                    iso_date="2025-05-19",
                    encounter_id="enc-diag",
                ),
                _milestone(
                    type="treatment_started",
                    iso_date="2025-05-19",
                    encounter_id="enc-tx1",
                    treatment_type="endocrine",
                ),
                _milestone(
                    type="treatment_started",
                    iso_date="2025-07-28",
                    encounter_id="enc-tx2",
                    treatment_type="surgery",
                ),
                _milestone(
                    type="treatment_completed",
                    iso_date="2025-09-15",
                    encounter_id="enc-txdone",
                ),
            ]
        )
    ]

    write_episodes(
        client=client,
        patient_id="p-1",
        domain_id="d-1",
        episodes=eps,
        provenance=_provenance(),
        dry_run=False,
    )

    write_call = next(
        c
        for c in client.run.call_args_list
        if "MERGE (ep:EpisodeOfCare" in c.args[0]
    )
    kw: dict[str, Any] = write_call.kwargs
    assert kw["referral_date"] == "2025-03-26"
    assert kw["first_seen_date"] == "2025-04-28"
    assert kw["diagnosis_date"] == "2025-05-19"
    assert (
        kw["treatment_started_date"] == "2025-05-19"
    ), "earliest treatment_started should win"
    assert kw["treatment_completed_date"] == "2025-09-15"


def test_safety_netting_persists_to_episode_properties():
    """VT-505-TC-012: a SafetyNetting object on the reconciled episode is
    flattened onto ep.safety_netting_* properties for the dashboard."""

    client = MagicMock()
    client.run.return_value = [{"deleted": 0}]

    eps = [_episode()]
    eps[0].safety_netting = SafetyNetting(
        recorded=True,
        evidence_quote="advised to return urgently if symptoms worsen.",
        encounter_id="enc-pres",
        date=date.fromisoformat("2025-03-12"),
        confidence=0.92,
    )

    write_episodes(
        client=client,
        patient_id="p-1",
        domain_id="d-1",
        episodes=eps,
        provenance=_provenance(),
        dry_run=False,
    )

    write_call = next(
        c
        for c in client.run.call_args_list
        if "MERGE (ep:EpisodeOfCare" in c.args[0]
    )
    kw = write_call.kwargs
    assert kw["safety_netting_recorded"] is True
    assert (
        kw["safety_netting_evidence"]
        == "advised to return urgently if symptoms worsen."
    )
    assert kw["safety_netting_encounter_id"] == "enc-pres"
    assert kw["safety_netting_date"] == "2025-03-12"
    assert kw["safety_netting_confidence"] == pytest.approx(0.92)


def test_safety_netting_absent_falls_back_to_recorded_false():
    """VT-505-TC-013: an episode with no safety netting persists
    safety_netting_recorded=false and null evidence."""

    client = MagicMock()
    client.run.return_value = [{"deleted": 0}]
    eps = [_episode()]

    write_episodes(
        client=client,
        patient_id="p-1",
        domain_id="d-1",
        episodes=eps,
        provenance=_provenance(),
        dry_run=False,
    )

    write_call = next(
        c
        for c in client.run.call_args_list
        if "MERGE (ep:EpisodeOfCare" in c.args[0]
    )
    kw = write_call.kwargs
    assert kw["safety_netting_recorded"] is False
    assert kw["safety_netting_evidence"] is None
    assert kw["safety_netting_encounter_id"] is None
    assert kw["safety_netting_date"] is None


def test_disruptions_roll_up_and_link_per_encounter():
    """VT-505-TC-014: disruptions roll up into ep.* scalars and emit one
    DOCUMENTS_DISRUPTION link per disruption with the resolved phase."""

    client = MagicMock()
    client.run.return_value = [{"deleted": 0}]

    eps = [
        _episode(
            milestones=[
                _milestone(
                    type="first_presentation",
                    iso_date="2025-03-12",
                    encounter_id="enc-pres",
                ),
                _milestone(
                    type="referral", iso_date="2025-03-26", encounter_id="enc-ref"
                ),
            ]
        )
    ]
    # Override first_presentation to carry presentation_place
    eps[0].milestones[0] = Milestone(
        type="first_presentation",
        date=date.fromisoformat("2025-03-12"),
        encounter_id="enc-pres",
        evidence_quote="GP face-to-face for new lump.",
        presentation_place="gp_surgery",
        confidence=0.9,
        reasoning="r",
    )
    eps[0].disruptions = [
        Disruption(
            date=date.fromisoformat("2025-04-10"),
            category="referral_lost_or_not_received",
            description="Patient phoned: no appointment letter from clinic yet.",
            encounter_id="enc-chase",
            evidence_quote="no appointment letter from breast clinic yet",
            confidence=0.85,
        ),
        Disruption(
            date=date.fromisoformat("2025-05-02"),
            category="appointment_dna",
            description="Patient did not attend the booked clinic.",
            encounter_id="enc-dna",
            evidence_quote="DNA breast clinic appt 02/05.",
            confidence=0.9,
        ),
    ]

    write_episodes(
        client=client,
        patient_id="p-1",
        domain_id="d-1",
        episodes=eps,
        provenance=_provenance(),
        dry_run=False,
    )

    write_call = next(
        c
        for c in client.run.call_args_list
        if "MERGE (ep:EpisodeOfCare" in c.args[0]
    )
    kw = write_call.kwargs
    assert kw["disruption_count"] == 2
    assert kw["has_referral_disruption"] is True
    assert kw["avoidable_delay"] is True
    assert kw["avoidable_delay_phase"] == "after_referral"
    assert sorted(kw["disruption_categories"]) == [
        "appointment_dna",
        "referral_lost_or_not_received",
    ]
    persisted = json.loads(kw["disruptions_json"])
    assert len(persisted) == 2
    assert persisted[0]["phase"] == "after_referral"

    link_calls = [
        c
        for c in client.run.call_args_list
        if "MERGE (e)-[r:DOCUMENTS_DISRUPTION" in c.args[0]
    ]
    assert len(link_calls) == 2
    by_category = {c.kwargs["category"]: c.kwargs for c in link_calls}
    assert by_category["referral_lost_or_not_received"]["phase"] == "after_referral"
    assert by_category["appointment_dna"]["phase"] == "after_referral"


def test_disruption_phase_classifies_against_milestones():
    """VT-505-TC-015: disruption_phase buckets dates relative to the
    first_presentation and referral milestones."""

    fp = "2025-03-12"
    ref = "2025-03-26"

    assert (
        disruption_phase(date(2025, 3, 1), first_presentation_iso=fp, referral_iso=ref)
        == "before_presentation"
    )
    assert (
        disruption_phase(
            date(2025, 3, 12), first_presentation_iso=fp, referral_iso=ref
        )
        == "pres_to_referral"
    )
    assert (
        disruption_phase(
            date(2025, 3, 20), first_presentation_iso=fp, referral_iso=ref
        )
        == "pres_to_referral"
    )
    assert (
        disruption_phase(
            date(2025, 3, 26), first_presentation_iso=fp, referral_iso=ref
        )
        == "after_referral"
    )
    # No first_presentation -> falls through to after_referral
    assert (
        disruption_phase(
            date(2025, 3, 1), first_presentation_iso=None, referral_iso=None
        )
        == "after_referral"
    )


def test_earliest_phase_picks_pres_phase_over_after_referral():
    """VT-505-TC-016: earliest_phase prioritises the earliest pathway phase."""

    assert earliest_phase([]) is None
    assert earliest_phase(["after_referral", "before_presentation"]) == (
        "before_presentation"
    )
    assert (
        earliest_phase(["after_referral", "pres_to_referral"]) == "pres_to_referral"
    )


def test_disruption_summary_with_no_disruptions_emits_nullish_rollup():
    """VT-505-TC-017: an empty disruption list yields a quiet rollup."""

    out = disruption_summary(
        [], first_presentation_iso="2025-03-12", referral_iso="2025-03-26"
    )
    assert out["disruption_count"] == 0
    assert out["has_referral_disruption"] is False
    assert out["avoidable_delay"] is False
    assert out["avoidable_delay_phase"] is None
    assert out["disruption_categories"] == []
    assert json.loads(out["disruptions_json"]) == []


def test_safety_netting_payload_handles_none_and_recorded_false():
    """VT-505-TC-018: safety_netting_payload normalises absent / falsy inputs."""

    none_out = safety_netting_payload(None)
    falsy_out = safety_netting_payload(SafetyNetting(recorded=False))
    for out in (none_out, falsy_out):
        assert out["safety_netting_recorded"] is False
        assert out["safety_netting_evidence"] is None
        assert out["safety_netting_encounter_id"] is None
        assert out["safety_netting_date"] is None
        assert out["safety_netting_confidence"] == 0.0
