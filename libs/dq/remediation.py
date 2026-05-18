"""Safe graph mutation tools -- all operations default to dry_run=True.

Atlas trace:
  DO: DO-0998FAF5
  Also implements: DO-86800C9B
  DI: DI-FC80B65A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0998FAF5")

IMPORTANT: Never call with dry_run=False unless the caller has reviewed the
dry-run preview and explicitly confirmed the operation.
"""

from __future__ import annotations

import logging
from typing import Any

from libs.dq._models import RemediationResult

logger = logging.getLogger(__name__)

# Cypher: preview (count only)
_PATIENT_PREVIEW_Q = """
MATCH (p:Patient {id: $patient_id})
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter)
OPTIONAL MATCH (p)-[:HAS_EPISODE]->(ep:EpisodeOfCare)
OPTIONAL MATCH (enc)-[d:DOCUMENTS]->()
RETURN count(DISTINCT enc) AS enc_count,
       count(DISTINCT ep) AS ep_count,
       count(DISTINCT d) AS doc_count
"""

# Cypher: actual delete
_PATIENT_DELETE_Q = """
MATCH (p:Patient {id: $patient_id})
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter)
OPTIONAL MATCH (enc)-[d:DOCUMENTS]->()
OPTIONAL MATCH (p)-[:HAS_EPISODE]->(ep:EpisodeOfCare)
DETACH DELETE d, enc, ep, p
RETURN count(*) AS deleted
"""

_EPISODES_PREVIEW_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ($status IS NULL OR ep.status = $status)
  AND ($site IS NULL OR ep.cancer_type = $site)
  AND (NOT $unreviewed_only OR ep.reviewed_at IS NULL)
RETURN count(ep) AS ep_count
"""

_EPISODES_DELETE_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ($status IS NULL OR ep.status = $status)
  AND ($site IS NULL OR ep.cancer_type = $site)
  AND (NOT $unreviewed_only OR ep.reviewed_at IS NULL)
DETACH DELETE ep
RETURN count(*) AS deleted
"""

_ASSERTION_PREVIEW_Q = """
MATCH (enc:Encounter {id: $encounter_id})-[d:DOCUMENTS]->()
WHERE d.assertion = $old_assertion
RETURN count(d) AS edge_count
"""

_ASSERTION_FIX_Q = """
MATCH (enc:Encounter {id: $encounter_id})-[d:DOCUMENTS]->()
WHERE d.assertion = $old_assertion
SET d.assertion = $new_assertion,
    d.dq_fixed_at = datetime()
RETURN count(d) AS updated
"""


def delete_patient(
    patient_id: str, client: Any, dry_run: bool = True
) -> RemediationResult:
    """Delete a patient subtree. Always dry_run=True unless explicitly set."""
    from libs.neo4j_client.client import run_with_retry

    preview = run_with_retry(client, _PATIENT_PREVIEW_Q, patient_id=patient_id)
    counts = preview[0] if preview else {}
    enc = int(counts.get("enc_count") or 0)
    ep = int(counts.get("ep_count") or 0)
    doc = int(counts.get("doc_count") or 0)
    total = enc + ep + doc + 1  # +1 for Patient node

    if dry_run:
        return RemediationResult(
            operation="delete_patient",
            dry_run=True,
            affected_count=total,
            affected_items=[
                {
                    "patient_id": patient_id,
                    "encounters": enc,
                    "episodes": ep,
                    "documents": doc,
                }
            ],
            message=f"DRY RUN: would delete {total} nodes/edges for patient {patient_id}",
        )

    logger.warning("Deleting patient %s from graph", patient_id)
    run_with_retry(client, _PATIENT_DELETE_Q, patient_id=patient_id)
    return RemediationResult(
        operation="delete_patient",
        dry_run=False,
        affected_count=total,
        affected_items=[{"patient_id": patient_id}],
        message=f"Deleted patient {patient_id} and {total} related nodes/edges",
    )


def delete_episodes(
    client: Any,
    status: str | None = None,
    site: str | None = None,
    *,
    unreviewed_only: bool = False,
    dry_run: bool = True,
) -> RemediationResult:
    """Delete episodes matching filters. Always dry_run=True by default.

    When ``unreviewed_only`` is True, only episodes with no curator sign-off
    (``reviewed_at IS NULL``) are matched; see ``libs.episodes.lifecycle.is_reviewed``.

    Combinable filters: optional ``status`` / ``site`` (cancer_type) with
    ``unreviewed_only`` to narrow the delete set.
    """
    from libs.neo4j_client.client import run_with_retry

    preview = run_with_retry(
        client,
        _EPISODES_PREVIEW_Q,
        status=status,
        site=site,
        unreviewed_only=unreviewed_only,
    )
    ep_count = int((preview[0] or {}).get("ep_count") or 0) if preview else 0

    if dry_run:
        return RemediationResult(
            operation="delete_episodes",
            dry_run=True,
            affected_count=ep_count,
            affected_items=[
                {
                    "status_filter": status,
                    "site_filter": site,
                    "unreviewed_only": unreviewed_only,
                }
            ],
            message=f"DRY RUN: would delete {ep_count} episodes",
        )

    logger.warning(
        "Deleting episodes status=%s site=%s unreviewed_only=%s",
        status,
        site,
        unreviewed_only,
    )
    run_with_retry(
        client,
        _EPISODES_DELETE_Q,
        status=status,
        site=site,
        unreviewed_only=unreviewed_only,
    )
    return RemediationResult(
        operation="delete_episodes",
        dry_run=False,
        affected_count=ep_count,
        affected_items=[
            {
                "status_filter": status,
                "site_filter": site,
                "unreviewed_only": unreviewed_only,
            }
        ],
        message=f"Deleted {ep_count} episodes",
    )


def fix_assertions(
    encounter_id: str,
    old_assertion: str,
    new_assertion: str,
    client: Any,
    dry_run: bool = True,
) -> RemediationResult:
    """Change assertion on DOCUMENTS edges for an encounter."""
    from libs.neo4j_client.client import run_with_retry

    preview = run_with_retry(
        client,
        _ASSERTION_PREVIEW_Q,
        encounter_id=encounter_id,
        old_assertion=old_assertion,
    )
    edge_count = int((preview[0] or {}).get("edge_count") or 0) if preview else 0

    if dry_run:
        return RemediationResult(
            operation="fix_assertions",
            dry_run=True,
            affected_count=edge_count,
            affected_items=[
                {
                    "encounter_id": encounter_id,
                    "old": old_assertion,
                    "new": new_assertion,
                }
            ],
            message=(
                f"DRY RUN: would change {edge_count} edges "
                f"from '{old_assertion}' to '{new_assertion}' "
                f"on encounter {encounter_id}"
            ),
        )

    run_with_retry(
        client,
        _ASSERTION_FIX_Q,
        encounter_id=encounter_id,
        old_assertion=old_assertion,
        new_assertion=new_assertion,
    )
    return RemediationResult(
        operation="fix_assertions",
        dry_run=False,
        affected_count=edge_count,
        affected_items=[
            {
                "encounter_id": encounter_id,
                "old": old_assertion,
                "new": new_assertion,
            }
        ],
        message=(
            f"Updated {edge_count} DOCUMENTS edges " f"on encounter {encounter_id}"
        ),
    )
