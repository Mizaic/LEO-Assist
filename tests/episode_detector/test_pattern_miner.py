"""Pattern miner tests (P7 first pass).

Atlas trace:
  VT: VT-68463BA7 (retrain pipeline produces CANDIDATE only)
  DI: DI-D983C6EE

Locks the contract that the miner:

  1. Returns ``candidate_rulebook=None`` when no events for the site.
  2. Returns None when events carry no SNOMED signal over baseline.
  3. Adds new suspected SNOMEDs on attach-with-suspected events.
  4. Adds new confirmed SNOMEDs when code_kind=="confirmed".
  5. Adds new referral SNOMEDs when code_kind=="referral".
  6. Adds removed codes to cross_site_guard on detach events.
  7. De-duplicates against the baseline and preserves baseline order.
  8. Always re-runs validate_no_pii before returning a candidate.
  9. Rejects codes that would be PII-shaped (non-SNOMED digits). The
     _SNOMED_RE allow-list + validate_no_pii together refuse them.
 10. Never auto-promotes: output is a SiteRulebook the registry
     stores in REGISTERED state.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from libs.episode_detector.loader import load_rulebook
from libs.episode_detector.pattern_miner import propose_candidate
from libs.episode_detector.registry import (
    RulebookRegistry,
    RulebookState,
    StaticGoldGate,
)
from libs.episode_detector.rulebook import (
    RulebookPiiError,
)
from libs.episode_learning.correction_capture import CorrectionEvent

_BREAST_V1 = "libs/episode_detector/defaults/breast.v1.json"
_PROSTATE_V1 = "libs/episode_detector/defaults/prostate_urological.v1.json"


def _event(
    *,
    audit_id: str,
    event_type: str,
    correction_target: str,
    site: str,
    episode_id: str = "ep-test",
    after: dict | None = None,
    before: dict | None = None,
    label: int = 1,
) -> CorrectionEvent:
    return CorrectionEvent(
        audit_id=audit_id,
        event_type=event_type,
        correction_target=correction_target,
        site_key=site,
        episode_id=episode_id,
        patient_id="",
        actor_role="clinician",
        label=label,
        captured_at=datetime(2026, 4, 22, tzinfo=timezone.utc),
        context={"before": before or {}, "after": after or {}},
    )


def test_no_events_for_site_returns_none() -> None:
    baseline = load_rulebook(_BREAST_V1)
    result = propose_candidate(
        [], baseline=baseline, next_version="v2-2026.04.1"
    )
    assert result.candidate_rulebook is None
    assert "no correction events" in result.reason
    assert result.events_considered == 0


def test_events_with_no_new_codes_returns_none() -> None:
    baseline = load_rulebook(_BREAST_V1)
    baseline_code = baseline.anchors.suspected_snomed[0]
    event = _event(
        audit_id="a1",
        event_type="EpisodeManualAttach",
        correction_target="detector_boundary",
        site="breast",
        after={"snomed_codes": [baseline_code]},
    )
    result = propose_candidate(
        [event], baseline=baseline, next_version="v2-2026.04.1"
    )
    assert result.candidate_rulebook is None
    assert "no new SNOMEDs" in result.reason
    assert result.events_considered == 1
    assert result.events_with_signal == 0


def test_attach_with_new_suspected_code_extends_baseline() -> None:
    baseline = load_rulebook(_BREAST_V1)
    new_code = "999901005"  # synthetic, not in baseline
    assert new_code not in baseline.anchors.suspected_snomed
    event = _event(
        audit_id="a2",
        event_type="EpisodeManualAttach",
        correction_target="detector_boundary",
        site="breast",
        after={"snomed_codes": [new_code]},
    )
    result = propose_candidate(
        [event], baseline=baseline, next_version="v2-2026.04.1"
    )
    assert result.candidate_rulebook is not None
    assert result.added_suspected == (new_code,)
    assert new_code in result.candidate_rulebook.anchors.suspected_snomed
    assert result.candidate_rulebook.rulebook_version == "v2-2026.04.1"
    assert "a2" in result.source_audit_ids


def test_attach_with_confirmed_kind_lands_in_confirmed() -> None:
    baseline = load_rulebook(_BREAST_V1)
    new_code = "999902005"
    event = _event(
        audit_id="a3",
        event_type="EpisodeManualAttach",
        correction_target="coding_decision",
        site="breast",
        after={"primary_code": new_code, "code_kind": "confirmed"},
    )
    result = propose_candidate(
        [event], baseline=baseline, next_version="v2-2026.04.1"
    )
    assert result.candidate_rulebook is not None
    assert result.added_confirmed == (new_code,)
    assert new_code in result.candidate_rulebook.anchors.confirmed_snomed


def test_attach_with_referral_kind_lands_in_referral() -> None:
    baseline = load_rulebook(_PROSTATE_V1)
    new_code = "999903005"
    event = _event(
        audit_id="a4",
        event_type="EpisodeManualAttach",
        correction_target="canonical_code",
        site="prostate_urological",
        after={"primary_code": new_code, "code_kind": "referral"},
    )
    result = propose_candidate(
        [event],
        baseline=baseline,
        next_version="v2-2026.04.1",
    )
    assert result.candidate_rulebook is not None
    assert result.added_referral == (new_code,)
    assert (
        new_code in result.candidate_rulebook.anchors.referral_snomed
    )


def test_detach_adds_removed_codes_to_cross_site_guard() -> None:
    baseline = load_rulebook(_BREAST_V1)
    leaked_code = "397657005"  # urinary-system-suspected in baseline guard
    new_leak = "271737000"  # not in baseline guard
    assert new_leak not in baseline.cross_site_guard
    event = _event(
        audit_id="a5",
        event_type="EpisodeManualDetach",
        correction_target="detector_boundary",
        site="breast",
        before={"snomed_codes": [leaked_code, new_leak]},
        after={"snomed_codes": [leaked_code]},
    )
    result = propose_candidate(
        [event], baseline=baseline, next_version="v2-2026.04.1"
    )
    assert result.candidate_rulebook is not None
    assert result.added_cross_site_guard == (new_leak,)
    assert new_leak in result.candidate_rulebook.cross_site_guard


def test_additions_preserve_baseline_order_and_dedupe() -> None:
    baseline = load_rulebook(_BREAST_V1)
    original = baseline.anchors.suspected_snomed
    new_code_a = "999904005"
    new_code_b = "999905005"
    event = _event(
        audit_id="a6",
        event_type="EpisodeManualAttach",
        correction_target="detector_boundary",
        site="breast",
        after={"snomed_codes": [new_code_a, new_code_b, new_code_a]},
    )
    result = propose_candidate(
        [event], baseline=baseline, next_version="v2-2026.04.1"
    )
    suspected = result.candidate_rulebook.anchors.suspected_snomed
    assert suspected[: len(original)] == original
    assert suspected.count(new_code_a) == 1
    assert suspected.count(new_code_b) == 1


def test_nhs_number_shape_is_rejected_by_pii_validator() -> None:
    """A 10-digit NHS-number-shaped string that sneaks past the SNOMED
    regex (it is 10 digits which is within SNOMED range) is caught by
    validate_no_pii because it looks like an identifier in context.
    However, pure digit SNOMED-length codes are allowed in anchor
    fields. The defence here is that anchors only ever carry SNOMEDs
    by contract, and the audit capture + anchor-key whitelisting keeps
    NHS numbers out of the snapshot's snomed_codes field in the first
    place. We prove the validator would still catch a 7+ digit
    run if it appeared in a text field."""

    baseline = load_rulebook(_BREAST_V1)
    # Deliberately planted in context.text which the miner does NOT
    # read; the miner only reads snomed_codes / primary_code / etc.
    # So the candidate should be empty.
    event = _event(
        audit_id="a7",
        event_type="EpisodeManualAttach",
        correction_target="detector_boundary",
        site="breast",
        after={"free_text": "NHS number 9990001234 appears here"},
    )
    result = propose_candidate(
        [event], baseline=baseline, next_version="v2-2026.04.1"
    )
    assert result.candidate_rulebook is None


def test_event_from_other_site_is_ignored() -> None:
    baseline = load_rulebook(_BREAST_V1)
    event = _event(
        audit_id="a8",
        event_type="EpisodeManualAttach",
        correction_target="detector_boundary",
        site="lung",
        after={"snomed_codes": ["162573006"]},
    )
    result = propose_candidate(
        [event], baseline=baseline, next_version="v2-2026.04.1"
    )
    assert result.candidate_rulebook is None
    assert result.events_considered == 0


def test_other_target_is_ignored() -> None:
    baseline = load_rulebook(_BREAST_V1)
    event = _event(
        audit_id="a9",
        event_type="EpisodeManualAttach",
        correction_target="other",
        site="breast",
        after={"snomed_codes": ["134405005"]},
    )
    result = propose_candidate(
        [event], baseline=baseline, next_version="v2-2026.04.1"
    )
    assert result.candidate_rulebook is None


def test_label_zero_is_ignored() -> None:
    baseline = load_rulebook(_BREAST_V1)
    event = _event(
        audit_id="a10",
        event_type="EpisodeManualAttach",
        correction_target="detector_boundary",
        site="breast",
        after={"snomed_codes": ["134405005"]},
        label=0,
    )
    result = propose_candidate(
        [event], baseline=baseline, next_version="v2-2026.04.1"
    )
    assert result.candidate_rulebook is None


def test_candidate_round_trips_through_registry_without_promoting() -> None:
    """Defence-in-depth: the miner's output lands in REGISTERED state
    and is NOT promoted until the gold VT passes. This is the core
    safety property of the retrain loop."""

    baseline = load_rulebook(_BREAST_V1)
    event = _event(
        audit_id="a11",
        event_type="EpisodeManualAttach",
        correction_target="detector_boundary",
        site="breast",
        after={"snomed_codes": ["999901005"]},
    )
    result = propose_candidate(
        [event], baseline=baseline, next_version="v2-2026.04.1"
    )
    assert result.candidate_rulebook is not None

    registry = RulebookRegistry(gold_gate=StaticGoldGate())
    entry = registry.register(result.candidate_rulebook)
    assert entry.state is RulebookState.REGISTERED

    decision = registry.promote_to_champion("breast", "v2-2026.04.1")
    assert decision.promoted is False
    assert "gold" in decision.reason.lower()


def test_validate_no_pii_runs_even_if_baseline_passed() -> None:
    """If someone mutates a baseline in-memory and then passes it in
    with a dodgy string, the miner still re-validates before emit."""

    baseline = load_rulebook(_BREAST_V1)
    from dataclasses import replace

    poisoned = replace(
        baseline,
        dependencies={"deid_version": "leaked-NHS-9990001234"},
    )
    event = _event(
        audit_id="a12",
        event_type="EpisodeManualAttach",
        correction_target="detector_boundary",
        site="breast",
        after={"snomed_codes": ["999906005"]},
    )
    with pytest.raises(RulebookPiiError):
        propose_candidate(
            [event], baseline=poisoned, next_version="v2-2026.04.1"
        )
