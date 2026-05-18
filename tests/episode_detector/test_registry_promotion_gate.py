"""Gold-patient promotion gate tests for the rulebook registry.

Atlas trace:
  VT: VT-RULEBOOK-PROMOTION-GATE
  DI: DI-AC6838DD

Locks the following contract:

  1. Promotion is blocked without a gold-patient VT pass.
  2. Promotion is blocked if the VT pass is older than the candidate.
  3. Promotion succeeds when the VT pass is newer than the candidate.
  4. Promotion demotes the prior champion and records a rollback path.
  5. `force=True` bypasses the gate but stamps an audit tag.
  6. Rollback restores the prior champion when one was recorded.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from libs.episode_detector.loader import load_rulebook
from libs.episode_detector.registry import (
    InMemoryRulebookStore,
    RulebookRegistry,
    RulebookState,
    StaticGoldGate,
)
from libs.episode_detector.rulebook import SiteRulebook

_DEFAULTS = (
    "libs/episode_detector/defaults"
)


def _load_breast_v1() -> SiteRulebook:
    return load_rulebook(f"{_DEFAULTS}/breast.v1.json")


def _load_breast_v0() -> SiteRulebook:
    return load_rulebook(f"{_DEFAULTS}/breast.v0.json")


def test_register_runs_pii_validator() -> None:
    registry = RulebookRegistry()
    rb = _load_breast_v1()
    entry = registry.register(rb)
    assert entry.state is RulebookState.REGISTERED
    assert entry.site_key == "breast"
    assert registry.get("breast", rb.rulebook_version) is entry


def test_duplicate_registration_rejected() -> None:
    registry = RulebookRegistry()
    rb = _load_breast_v1()
    registry.register(rb)
    with pytest.raises(ValueError):
        registry.register(rb)


def test_promotion_blocked_without_any_vt_pass() -> None:
    gate = StaticGoldGate()
    registry = RulebookRegistry(
        store=InMemoryRulebookStore(), gold_gate=gate
    )
    rb = _load_breast_v1()
    registry.register(rb)
    decision = registry.promote_to_champion("breast", rb.rulebook_version)
    assert decision.promoted is False
    assert "no gold-patient VT pass" in decision.reason


def test_promotion_blocked_when_vt_pass_is_stale() -> None:
    gate = StaticGoldGate(
        {"breast": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    )
    registry = RulebookRegistry(
        store=InMemoryRulebookStore(), gold_gate=gate
    )
    rb = _load_breast_v1()
    registry.register(
        rb,
        now=datetime(2026, 4, 21, tzinfo=timezone.utc),
    )
    decision = registry.promote_to_champion("breast", rb.rulebook_version)
    assert decision.promoted is False
    assert "older than the candidate" in decision.reason


def test_promotion_succeeds_with_fresh_vt_pass() -> None:
    registered_at = datetime(2026, 4, 21, tzinfo=timezone.utc)
    gate = StaticGoldGate({"breast": registered_at + timedelta(hours=1)})
    registry = RulebookRegistry(
        store=InMemoryRulebookStore(), gold_gate=gate
    )
    rb = _load_breast_v1()
    registry.register(rb, now=registered_at)
    decision = registry.promote_to_champion(
        "breast",
        rb.rulebook_version,
        now=registered_at + timedelta(hours=2),
    )
    assert decision.promoted is True
    champion = registry.champion("breast")
    assert champion is not None
    assert champion.rulebook_version == rb.rulebook_version
    assert champion.state is RulebookState.CHAMPION


def test_promotion_demotes_prior_champion_and_records_rollback() -> None:
    gate = StaticGoldGate()
    store = InMemoryRulebookStore()
    registry = RulebookRegistry(store=store, gold_gate=gate)

    v0 = _load_breast_v0()
    v1 = _load_breast_v1()
    reg_v0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    reg_v1 = datetime(2026, 4, 21, tzinfo=timezone.utc)
    registry.register(v0, now=reg_v0)
    registry.register(v1, now=reg_v1)
    registry.promote_to_champion(
        "breast", v0.rulebook_version, force=True
    )
    gate.set_pass("breast", reg_v1 + timedelta(hours=1))
    decision = registry.promote_to_champion(
        "breast",
        v1.rulebook_version,
        now=reg_v1 + timedelta(hours=2),
    )
    assert decision.promoted is True
    champion = registry.champion("breast")
    assert champion is not None and champion.rulebook_version == v1.rulebook_version
    assert champion.rollback_target_version == v0.rulebook_version
    prior = registry.get("breast", v0.rulebook_version)
    assert prior is not None and prior.state is RulebookState.DEPRECATED


def test_force_bypasses_gate_and_stamps_audit_note() -> None:
    registry = RulebookRegistry(
        store=InMemoryRulebookStore(), gold_gate=StaticGoldGate()
    )
    rb = _load_breast_v0()
    registry.register(rb)
    decision = registry.promote_to_champion(
        "breast",
        rb.rulebook_version,
        force=True,
    )
    assert decision.promoted is True
    champion = registry.champion("breast")
    assert champion is not None
    assert "[forced]" in champion.notes


def test_rollback_restores_prior_champion() -> None:
    gate = StaticGoldGate()
    registry = RulebookRegistry(
        store=InMemoryRulebookStore(), gold_gate=gate
    )
    v0 = _load_breast_v0()
    v1 = _load_breast_v1()
    registered_v1 = datetime(2026, 4, 21, tzinfo=timezone.utc)
    registry.register(v0)
    registry.register(v1, now=registered_v1)
    registry.promote_to_champion(
        "breast", v0.rulebook_version, force=True
    )
    gate.set_pass("breast", registered_v1 + timedelta(hours=1))
    registry.promote_to_champion(
        "breast", v1.rulebook_version, now=registered_v1 + timedelta(hours=2)
    )
    decision = registry.rollback("breast")
    assert decision.promoted is True
    champion = registry.champion("breast")
    assert champion is not None
    assert champion.rulebook_version == v0.rulebook_version


def test_rollback_no_champion_returns_failure() -> None:
    registry = RulebookRegistry(store=InMemoryRulebookStore())
    decision = registry.rollback("breast")
    assert decision.promoted is False
    assert "no active champion" in decision.reason


def test_promote_unknown_version_returns_failure() -> None:
    registry = RulebookRegistry(
        store=InMemoryRulebookStore(), gold_gate=StaticGoldGate()
    )
    decision = registry.promote_to_champion("breast", "does-not-exist")
    assert decision.promoted is False
    assert "not registered" in decision.reason
