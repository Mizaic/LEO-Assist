"""Promote reviewer-confirmed locks to the :GoldLabel corpus.

A successful ``apply_with_lock`` call in the Reconcile Pathway flow is
the strongest training signal we have: a clinician or QA lead has
manually confirmed an entity (coded link, assertion, or a whole
episode) and stamped a HumanReconciliation audit event on it. This
module turns that signal into a permanent training row by routing the
reviewer's view of the encounter through the same DE-ID gate as the
existing audit-verified writeback.

Design choices:

  - The promoter is invoked from the API layer (router) AFTER
    ``apply_with_lock`` returns, NOT from inside lock_service. The
    lock and its audit event are the source of truth; the GoldLabel
    is a derived artefact that should not block a successful lock if
    the writeback fails (telemetry-only failure mode).
  - Encounter text and coded rows are passed in via an
    ``EncounterContext`` so the promoter does not depend on a
    Neo4j-shaped reader. Routers fetch the context with the existing
    ``PatientGraphClient`` helpers.
  - Episode-level locks promote one GoldLabel per encounter that
    IS_PART_OF the episode, keyed by ``encounter_id`` so downstream
    deduplication is straightforward.

Atlas trace:
  DI: DI-C424BB44 (VerificationLock cross-entity primitive)
  VT: VT-96455BC1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from libs.audit.kg_verified_writeback import (
    RECONCILE_PATHWAY_SOURCE,
    write_audit_verified_to_kg,
)
from libs.locks import VerificationLock

logger = logging.getLogger(__name__)


# Entity types this promoter knows how to translate into GoldLabels.
# Episode-level locks fan out to per-encounter rows; coded_link and
# assertion locks emit one row each. is_part_of_edge and encounter
# locks are intentionally NOT promoted on their own -- the edge lock
# is satisfied by the rebuild guard, and a bare encounter lock without
# a coded entity has no training-shaped payload.
_PROMOTABLE_ENTITY_TYPES = {"coded_link", "assertion", "episode"}


@dataclass(frozen=True)
class EncounterContext:
    """Reviewer-visible view of one encounter for gold-label promotion.

    ``raw_encounter_text`` MAY contain PHI -- the writeback layer
    de-identifies it before persistence. ``coded_rows`` follows the
    same shape as the audit prefilter: each row contributes one
    canonical entity (text, label, span, assertion).
    """

    encounter_id: str
    raw_encounter_text: str
    coded_rows: list[dict[str, Any]] = field(default_factory=list)


def promote_lock_to_gold(
    *,
    lock: VerificationLock,
    encounter_contexts: list[EncounterContext],
    quality_score: float = 0.95,
) -> dict[str, Any]:
    """Promote a successful lock to one or more GoldLabel rows.

    For coded_link and assertion locks the caller passes a single
    encounter context (the one the lock targets). For episode locks
    the caller passes every encounter that IS_PART_OF the episode --
    each becomes its own GoldLabel keyed by ``encounter_id``.

    The function never raises on writeback failure: it returns a
    summary that the router can log and forward to telemetry. The
    underlying lock is unaffected because ``apply_with_lock`` has
    already committed.
    """

    summary: dict[str, Any] = {
        "lock_id": lock.lock_id,
        "entity_type": lock.entity_type,
        "entity_id": lock.entity_id,
        "promoted": 0,
        "skipped": 0,
        "errors": [],
    }

    if lock.entity_type not in _PROMOTABLE_ENTITY_TYPES:
        summary["skipped"] = 1
        summary["errors"].append(f"entity_type {lock.entity_type!r} is not promotable")
        return summary

    if lock.entity_type in {"coded_link", "assertion"} and len(encounter_contexts) != 1:
        summary["skipped"] = 1
        summary["errors"].append(
            "coded_link/assertion lock requires exactly one encounter context"
        )
        return summary

    for ctx in encounter_contexts:
        if not ctx.encounter_id:
            summary["skipped"] += 1
            summary["errors"].append("encounter context missing encounter_id")
            continue
        try:
            result = write_audit_verified_to_kg(
                raw_encounter_text=ctx.raw_encounter_text,
                coded_rows=ctx.coded_rows,
                quality_score=float(quality_score),
                verified_by=lock.locked_by,
                assessment=f"reconcile_pathway:{lock.entity_type}",
                source=RECONCILE_PATHWAY_SOURCE,
            )
        except Exception as exc:  # noqa: BLE001 -- non-fatal
            logger.exception(
                "reconcile_promoter: writeback failed for encounter %s",
                ctx.encounter_id,
            )
            summary["errors"].append(
                f"encounter {ctx.encounter_id}: {type(exc).__name__}: {exc}"
            )
            summary["skipped"] += 1
            continue

        if result.get("written"):
            summary["promoted"] += 1
        else:
            summary["skipped"] += 1
            for err in result.get("errors", []):
                summary["errors"].append(f"encounter {ctx.encounter_id}: {err}")

    return summary
