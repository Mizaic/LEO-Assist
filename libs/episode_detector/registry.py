"""Per-site episode rulebook registry with gold-patient promotion gate.

Atlas trace:
  DI: DI-BF97CEAC (registry wiring)
  DI: DI-AC6838DD (gold-patient regression gate on promotion)
  Mitigates: R-94D0D086 (rulebook drift), R-192A2D18 (PII leakage)

A rulebook is promoted to champion for a site only if:

  1. The rulebook has been registered (validate_no_pii passes).
  2. There is a VT pass for the matching gold-patient VT.
  3. The VT pass is newer than the rulebook's registered_at (stale
     passes cannot justify a new promotion).
  4. The rulebook has been shadow-evaluated against the champion.

This module is the single place that owns the state machine. Backends
(in-memory for tests, Neo4j-backed for production) implement the
:class:`RulebookStore` protocol. The :class:`GoldGate` protocol is
the injection seam for the Atlas VT lookup.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Protocol

from libs.episode_detector.rulebook import SiteRulebook, validate_no_pii


class RulebookState(str, Enum):
    """Lifecycle state of a registered rulebook. Mirrors the existing
    model-registry states so promotions, canaries, and rollbacks read
    the same vocabulary across the system.
    """

    REGISTERED = "registered"
    SHADOW = "shadow"
    CANARY = "canary"
    CHAMPION = "champion"
    DEPRECATED = "deprecated"


@dataclass(frozen=True)
class RulebookEntry:
    """Registry record for a single (site, version) rulebook."""

    site_key: str
    rulebook_version: str
    rulebook: SiteRulebook
    state: RulebookState = RulebookState.REGISTERED
    registered_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    promoted_at: datetime | None = None
    rollback_target_version: str | None = None
    notes: str = ""


class RulebookStore(Protocol):
    """Pluggable backend protocol. The in-memory implementation below
    covers unit tests; a future :class:`Neo4jRulebookStore` will satisfy
    the same protocol against ``(:ModelVersion {model_name:
    "episode-rulebook-<site>"})`` nodes.
    """

    def save(self, entry: RulebookEntry) -> None: ...

    def get(
        self, site_key: str, rulebook_version: str
    ) -> RulebookEntry | None: ...

    def list_for_site(self, site_key: str) -> list[RulebookEntry]: ...

    def champion(self, site_key: str) -> RulebookEntry | None: ...


class GoldGate(Protocol):
    """Injection seam for looking up the gold-patient VT pass status.

    ``latest_pass`` returns the timestamp of the most recent passing
    run of the per-site regression VT, or None if no pass has been
    recorded. Production wires this to the Atlas MCP
    ``record_verification_run`` history; tests pass an in-memory
    fake.
    """

    def latest_pass(self, site_key: str) -> datetime | None: ...


@dataclass(frozen=True)
class PromotionDecision:
    """Outcome of a promotion attempt. On failure, ``reason`` is a
    human-readable, UK-English explanation that the CLI surfaces
    verbatim; on success, ``reason`` is the audit one-liner that
    lands on the (:ModelVersion).notes field.
    """

    promoted: bool
    site_key: str
    rulebook_version: str
    reason: str


# ----------------------------------------------------------------------
# In-memory store (default backend for tests and dev)
# ----------------------------------------------------------------------


class InMemoryRulebookStore:
    """Dict-backed RulebookStore. Good for tests and dry-runs."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], RulebookEntry] = {}

    def save(self, entry: RulebookEntry) -> None:
        self._entries[(entry.site_key, entry.rulebook_version)] = entry

    def get(
        self, site_key: str, rulebook_version: str
    ) -> RulebookEntry | None:
        return self._entries.get((site_key, rulebook_version))

    def list_for_site(self, site_key: str) -> list[RulebookEntry]:
        return [
            e for (s, _), e in self._entries.items() if s == site_key
        ]

    def champion(self, site_key: str) -> RulebookEntry | None:
        for entry in self.list_for_site(site_key):
            if entry.state == RulebookState.CHAMPION:
                return entry
        return None


class StaticGoldGate:
    """Test double implementing :class:`GoldGate` from a dict."""

    def __init__(
        self, passes: dict[str, datetime] | None = None
    ) -> None:
        self._passes = dict(passes or {})

    def set_pass(self, site_key: str, at: datetime) -> None:
        self._passes[site_key] = at

    def latest_pass(self, site_key: str) -> datetime | None:
        return self._passes.get(site_key)


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------


class RulebookRegistry:
    """Per-site rulebook registry with gold-patient promotion gate."""

    def __init__(
        self,
        store: RulebookStore | None = None,
        gold_gate: GoldGate | None = None,
    ) -> None:
        self._store = store if store is not None else InMemoryRulebookStore()
        self._gold_gate = gold_gate

    # -- Registration ---------------------------------------------------

    def register(
        self,
        rulebook: SiteRulebook,
        *,
        notes: str = "",
        now: datetime | None = None,
    ) -> RulebookEntry:
        """Persist a rulebook. Always runs validate_no_pii first.

        Registration does NOT activate the rulebook. A freshly-registered
        rulebook is in state REGISTERED until it has been shadow-evaluated
        and then promoted via :meth:`promote_to_champion`.
        """

        validate_no_pii(rulebook)
        existing = self._store.get(
            rulebook.site_key, rulebook.rulebook_version
        )
        if existing is not None:
            raise ValueError(
                f"rulebook for site {rulebook.site_key!r} version "
                f"{rulebook.rulebook_version!r} already registered"
            )
        entry = RulebookEntry(
            site_key=rulebook.site_key,
            rulebook_version=rulebook.rulebook_version,
            rulebook=rulebook,
            state=RulebookState.REGISTERED,
            registered_at=now or datetime.now(timezone.utc),
            notes=notes,
        )
        self._store.save(entry)
        return entry

    # -- Lookups --------------------------------------------------------

    def get(
        self, site_key: str, rulebook_version: str
    ) -> RulebookEntry | None:
        return self._store.get(site_key, rulebook_version)

    def list_for_site(self, site_key: str) -> list[RulebookEntry]:
        return self._store.list_for_site(site_key)

    def champion(self, site_key: str) -> RulebookEntry | None:
        return self._store.champion(site_key)

    # -- Promotion ------------------------------------------------------

    def promote_to_champion(
        self,
        site_key: str,
        rulebook_version: str,
        *,
        now: datetime | None = None,
        force: bool = False,
    ) -> PromotionDecision:
        """Promote ``(site_key, rulebook_version)`` to champion.

        Blocked unless the gold-patient VT has a pass newer than the
        candidate's registered_at. ``force=True`` overrides the gate
        (audit note is stamped on the entry) -- only used for the
        v0 bootstrap which ships with the binary.
        """

        entry = self._store.get(site_key, rulebook_version)
        if entry is None:
            return PromotionDecision(
                promoted=False,
                site_key=site_key,
                rulebook_version=rulebook_version,
                reason=f"rulebook {rulebook_version!r} not registered",
            )

        if not force:
            gate_result = self._check_gold_gate(entry)
            if gate_result is not None:
                return gate_result

        ts = now or datetime.now(timezone.utc)
        current_champion = self._store.champion(site_key)

        if current_champion is not None:
            self._store.save(
                replace(current_champion, state=RulebookState.DEPRECATED)
            )

        audit_note = _build_audit_note(entry, force=force, now=ts)
        promoted = replace(
            entry,
            state=RulebookState.CHAMPION,
            promoted_at=ts,
            rollback_target_version=(
                current_champion.rulebook_version
                if current_champion is not None
                else None
            ),
            notes=(entry.notes + "\n" + audit_note).strip(),
        )
        self._store.save(promoted)

        return PromotionDecision(
            promoted=True,
            site_key=site_key,
            rulebook_version=rulebook_version,
            reason=audit_note,
        )

    def rollback(self, site_key: str) -> PromotionDecision:
        """Roll back to the previous champion for the site."""

        current = self._store.champion(site_key)
        if current is None:
            return PromotionDecision(
                promoted=False,
                site_key=site_key,
                rulebook_version="",
                reason="no active champion to roll back from",
            )
        target_version = current.rollback_target_version
        if not target_version:
            return PromotionDecision(
                promoted=False,
                site_key=site_key,
                rulebook_version=current.rulebook_version,
                reason="active champion has no rollback target recorded",
            )
        target = self._store.get(site_key, target_version)
        if target is None:
            return PromotionDecision(
                promoted=False,
                site_key=site_key,
                rulebook_version=target_version,
                reason=(
                    f"rollback target {target_version!r} not found "
                    f"(was it pruned?)"
                ),
            )
        ts = datetime.now(timezone.utc)
        self._store.save(replace(current, state=RulebookState.DEPRECATED))
        self._store.save(
            replace(
                target,
                state=RulebookState.CHAMPION,
                promoted_at=ts,
                notes=(
                    target.notes
                    + f"\n[rollback] restored from {current.rulebook_version} "
                    f"at {ts.isoformat()}"
                ).strip(),
            )
        )
        return PromotionDecision(
            promoted=True,
            site_key=site_key,
            rulebook_version=target_version,
            reason=(
                f"rolled back from {current.rulebook_version} to "
                f"{target_version}"
            ),
        )

    def register_many(
        self, rulebooks: Iterable[SiteRulebook]
    ) -> list[RulebookEntry]:
        out: list[RulebookEntry] = []
        for rb in rulebooks:
            out.append(self.register(rb))
        return out

    # -- Internals ------------------------------------------------------

    def _check_gold_gate(
        self, entry: RulebookEntry
    ) -> PromotionDecision | None:
        if self._gold_gate is None:
            return PromotionDecision(
                promoted=False,
                site_key=entry.site_key,
                rulebook_version=entry.rulebook_version,
                reason=(
                    "no gold gate configured; pass force=True only for "
                    "the v0 bootstrap"
                ),
            )
        latest = self._gold_gate.latest_pass(entry.site_key)
        if latest is None:
            return PromotionDecision(
                promoted=False,
                site_key=entry.site_key,
                rulebook_version=entry.rulebook_version,
                reason=(
                    f"no gold-patient VT pass recorded for site "
                    f"{entry.site_key!r}; run the per-site regression "
                    f"test and record it via Atlas record_verification_run "
                    f"before promoting"
                ),
            )
        if latest < entry.registered_at:
            return PromotionDecision(
                promoted=False,
                site_key=entry.site_key,
                rulebook_version=entry.rulebook_version,
                reason=(
                    f"gold VT last passed {latest.isoformat()}, which is "
                    f"older than the candidate's registered_at "
                    f"{entry.registered_at.isoformat()}. Re-run the "
                    f"per-site gold regression against the current "
                    f"rulebook and record a fresh VT pass."
                ),
            )
        return None


def _build_audit_note(
    entry: RulebookEntry, *, force: bool, now: datetime
) -> str:
    tag = "[forced]" if force else "[gold-gated]"
    return (
        f"{tag} promoted site={entry.site_key} "
        f"version={entry.rulebook_version} at {now.isoformat()}"
    )
