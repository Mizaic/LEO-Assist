"""NCDA label audit data layer.

Stage 1 of the NCDA detector plan writes findings about the reviewed
EpisodeOfCare label set. Findings flow into a Neo4j :NCDALabelAudit node
keyed by (patient_id, episode_id, encounter_id, finding_type) so reviewer
actions in the Stage 9b audit tile can update them in place.

The Stage 2 tidy migration BLOCKS on any open finding with severity='high'.
The Stage 11 nightly job reads dismissed/resolved rows to grow training data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Literal

FindingType = Literal[
    "role_mismatch",
    "out_of_sequence",
    "multiple_anchors_per_role",
    "wrong_site",
    "llm_relabel_suggestion",
]
Severity = Literal["high", "medium", "low", "info"]
AuditStatus = Literal["open", "dismissed", "resolved", "applied"]


@dataclass(frozen=True)
class AuditFinding:
    """One audit finding row.

    Attributes:
        patient_id: Patient identifier.
        episode_id: Reviewed EpisodeOfCare id (or None for orphan-encounter).
        encounter_id: Encounter id the finding pertains to.
        current_milestone: The milestone_type the encounter is currently
            tagged with (e.g. 'referral_sent', 'diagnosis_confirmed').
        suggested_role: Canonical NCDA role the curator/LLM proposes.
        suggested_outcome: Outcome attribute when suggested_role == 'dx'.
        finding_type: Which deterministic check or LLM pass produced this.
        severity: Blocking ('high'), strongly-recommended-fix ('medium'),
            informational ('low'), or audit-trail-only ('info').
        rationale: Human-readable explanation for the curator.
        supporting_quote: A short quote from encounter text that motivates
            the suggestion (used for review-tile UX).
        encounter_date: Date stamped on the Encounter node.
        entry_date: Date the encounter was actually entered (from flags),
            distinct from encounter_date when the entry was back-dated.
        status: Workflow state.
        created_at: Audit-row creation timestamp (UTC iso8601).
    """

    patient_id: str
    encounter_id: str
    finding_type: FindingType
    severity: Severity
    rationale: str
    episode_id: str | None = None
    current_milestone: str | None = None
    suggested_role: str | None = None
    suggested_outcome: str | None = None
    supporting_quote: str | None = None
    encounter_date: str | None = None
    entry_date: str | None = None
    status: AuditStatus = "open"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


_MERGE_QUERY = """
MERGE (a:NCDALabelAudit {
    patient_id: $patient_id,
    encounter_id: $encounter_id,
    finding_type: $finding_type,
    episode_id: coalesce($episode_id, '__none__')
})
ON CREATE SET
    a.severity = $severity,
    a.current_milestone = $current_milestone,
    a.suggested_role = $suggested_role,
    a.suggested_outcome = $suggested_outcome,
    a.rationale = $rationale,
    a.supporting_quote = $supporting_quote,
    a.encounter_date = $encounter_date,
    a.entry_date = $entry_date,
    a.status = $status,
    a.created_at = $created_at,
    a.updated_at = $created_at
ON MATCH SET
    a.severity = $severity,
    a.suggested_role = coalesce($suggested_role, a.suggested_role),
    a.suggested_outcome = coalesce($suggested_outcome, a.suggested_outcome),
    a.rationale = $rationale,
    a.supporting_quote = coalesce($supporting_quote, a.supporting_quote),
    a.updated_at = $created_at
"""


def upsert_findings(session, findings: Iterable[AuditFinding]) -> int:
    """Idempotently write findings to Neo4j; returns count written."""
    n = 0
    for finding in findings:
        session.run(
            _MERGE_QUERY,
            patient_id=finding.patient_id,
            encounter_id=finding.encounter_id,
            finding_type=finding.finding_type,
            episode_id=finding.episode_id,
            severity=finding.severity,
            current_milestone=finding.current_milestone,
            suggested_role=finding.suggested_role,
            suggested_outcome=finding.suggested_outcome,
            rationale=finding.rationale,
            supporting_quote=finding.supporting_quote,
            encounter_date=finding.encounter_date,
            entry_date=finding.entry_date,
            status=finding.status,
            created_at=finding.created_at,
        )
        n += 1
    return n


_OPEN_HIGH_QUERY = """
MATCH (a:NCDALabelAudit)
WHERE a.status = 'open' AND a.severity = 'high'
RETURN count(a) AS n
"""


def open_high_severity_count(session) -> int:
    """Return count of open, high-severity findings (Stage 2 gate)."""
    row = session.run(_OPEN_HIGH_QUERY).single()
    return int(row["n"]) if row else 0


_LIST_QUERY = """
MATCH (a:NCDALabelAudit)
WHERE ($status IS NULL OR a.status = $status)
  AND ($severity IS NULL OR a.severity = $severity)
RETURN
    a.patient_id AS patient_id,
    a.episode_id AS episode_id,
    a.encounter_id AS encounter_id,
    a.current_milestone AS current_milestone,
    a.suggested_role AS suggested_role,
    a.suggested_outcome AS suggested_outcome,
    a.finding_type AS finding_type,
    a.severity AS severity,
    a.rationale AS rationale,
    a.supporting_quote AS supporting_quote,
    a.status AS status,
    a.created_at AS created_at,
    a.updated_at AS updated_at
ORDER BY a.severity DESC, a.created_at ASC
LIMIT $limit
"""


def list_findings(
    session,
    *,
    status: AuditStatus | None = None,
    severity: Severity | None = None,
    limit: int = 500,
) -> list[dict]:
    """List audit findings, newest-first within severity bucket."""
    rows = session.run(_LIST_QUERY, status=status, severity=severity, limit=limit)
    return [dict(r) for r in rows]


_UPDATE_STATUS_QUERY = """
MATCH (a:NCDALabelAudit {
    patient_id: $patient_id,
    encounter_id: $encounter_id,
    finding_type: $finding_type,
    episode_id: coalesce($episode_id, '__none__')
})
SET a.status = $new_status,
    a.updated_at = $updated_at,
    a.reviewer = $reviewer,
    a.reviewer_action = $reviewer_action
RETURN a.patient_id AS patient_id, a.status AS status
"""


def update_finding_status(
    session,
    *,
    patient_id: str,
    encounter_id: str,
    finding_type: FindingType,
    new_status: AuditStatus,
    reviewer: str,
    reviewer_action: str,
    episode_id: str | None = None,
) -> bool:
    """Reviewer-driven status update (Stage 9b audit tile actions)."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row = session.run(
        _UPDATE_STATUS_QUERY,
        patient_id=patient_id,
        encounter_id=encounter_id,
        finding_type=finding_type,
        episode_id=episode_id,
        new_status=new_status,
        updated_at=now,
        reviewer=reviewer,
        reviewer_action=reviewer_action,
    ).single()
    return row is not None
