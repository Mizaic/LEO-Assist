"""Replay one real referral through the production pipeline for review.

Reuses the exact production path a clinician's "reprocess this document"
click takes (`libs.patient_document_runs.service.start_document_run`), so
the loop observes genuine pipeline behaviour: real chunk resolution with
legacy-id backfill, the real `referral-received` bus message, the real
DurableStepRunner steps, and the real Assessment write-back. Nothing about
extraction, guideline evaluation or SBAR is re-implemented here.

Atlas trace:
  DO: DO-92F92EFB (reset), DO-5D3EA371 (document run), DO-3A70C3DD (lab pipeline)
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5D3EA371")

Usage:
    python scripts/replay_referral.py --referral-id 000049823847
    python scripts/replay_referral.py --referral-id 000049823847 --timeout-s 900
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402
from libs.neo4j_client.client import PatientGraphClient  # noqa: E402
from libs.patient_document_runs.chunk_resolver import (  # noqa: E402
    resolve_pipeline_chunks,
)
from libs.patient_document_runs.service import (  # noqa: E402
    DocumentRunError,
    start_document_run,
)
from libs.validation_lab.pipeline import (  # noqa: E402
    list_stage_progress,
    poll_run_status,
    read_real_outputs,
)
from app.services.reset_service import (  # noqa: E402
    reset_patient,
    reset_referral_draft_assessments,
)

_DEFAULT_TENANT_FALLBACK = "replay-referral"
_TERMINAL_STATUSES = {"completed", "failed"}

_FIND_PATIENT_FOR_REFERRAL = """
MATCH (rr:ReferralRequest {id: $referral_id})-[:FOR_PATIENT]->(p:Patient)
RETURN toString(p.id) AS patient_id,
       coalesce(rr.reason, '') AS reason,
       coalesce(rr.clinicType, '') AS clinic_type,
       coalesce(rr.specialty, '') AS specialty
LIMIT 1
"""

_FIND_REFERRAL_DOCUMENTS = """
MATCH (rr:ReferralRequest {id: $referral_id})-[:HAS_DOCUMENT]->(dr:DocumentReference)
OPTIONAL MATCH (dr)-[:HAS_CHUNK]->(c:Chunk)
WITH dr, count(c) AS chunk_count
RETURN toString(dr.id) AS document_reference_id,
       coalesce(dr.title, '') AS title,
       chunk_count
ORDER BY chunk_count DESC
"""

_LIST_CHUNK_DOCUMENTS = """
UNWIND $chunk_ids AS cid
MATCH (c:Chunk {id: cid})
OPTIONAL MATCH (c)-[r:DOCUMENTS]->(s)
RETURN c.id AS chunk_id,
       toString(s.conceptId) AS concept_id,
       labels(s) AS concept_labels,
       coalesce(s.name, '') AS term,
       r.assertion AS assertion_prop,
       r.context AS context_json,
       r.confidence AS confidence,
       coalesce(r.evidence, '') AS evidence,
       r.evidence_sentence AS evidence_sentence,
       r.value AS value,
       r.unit AS unit
ORDER BY c.id, r.confidence DESC
"""


class ReplayError(Exception):
    """Raised when a referral cannot be replayed as requested."""


@dataclass
class ReferralTarget:
    referral_id: str
    patient_id: str
    reason: str
    clinic_type: str
    specialty: str
    document_reference_id: str
    document_title: str


def _resolve_referral_target(client: PatientGraphClient, referral_id: str) -> ReferralTarget:
    patient_rows = client.run(_FIND_PATIENT_FOR_REFERRAL, referral_id=referral_id)
    if not patient_rows:
        raise ReplayError(f"No ReferralRequest {referral_id!r} with a FOR_PATIENT patient.")
    patient_row = patient_rows[0]

    doc_rows = client.run(_FIND_REFERRAL_DOCUMENTS, referral_id=referral_id)
    if not doc_rows:
        raise ReplayError(
            f"Referral {referral_id!r} has no HAS_DOCUMENT DocumentReference at all."
        )
    best = doc_rows[0]
    if int(best.get("chunk_count") or 0) == 0:
        raise ReplayError(
            f"Referral {referral_id!r}'s best document {best.get('document_reference_id')!r} "
            "has zero chunks (upstream ingestion never chunked it). Not replayable yet."
        )

    return ReferralTarget(
        referral_id=referral_id,
        patient_id=str(patient_row["patient_id"]),
        reason=str(patient_row.get("reason") or ""),
        clinic_type=str(patient_row.get("clinic_type") or ""),
        specialty=str(patient_row.get("specialty") or ""),
        document_reference_id=str(best["document_reference_id"]),
        document_title=str(best.get("title") or ""),
    )


def _reset_for_replay(
    client: PatientGraphClient, target: ReferralTarget
) -> dict[str, Any]:
    with client.session() as session:
        patient_reset = reset_patient(target.patient_id, session)
        draft_reset = reset_referral_draft_assessments(target.referral_id, session)
    return {"patient_reset": patient_reset, "draft_reset": draft_reset}


def _start_run(
    client: PatientGraphClient,
    target: ReferralTarget,
    resolved_chunk_ids: list[str],
    *,
    plan_id: str,
    tenant_fallback: str,
) -> str:
    result = start_document_run(
        client,
        patient_id=target.patient_id,
        document_reference_id=target.document_reference_id,
        chunk_ids=resolved_chunk_ids,
        plan_id=plan_id,
        requested_by="replay_referral.py",
        tenant_fallback=tenant_fallback,
    )
    if result.status == "failed":
        raise ReplayError(f"start_document_run failed to enqueue: {result.error_message}")
    return result.run_id


def _poll_until_terminal(
    client: PatientGraphClient,
    run_id: str,
    *,
    timeout_s: int,
    poll_interval_s: int,
) -> dict[str, Any]:
    started = time.time()
    status_row: dict[str, str] = {"status": "queued", "assessment_id": ""}
    while time.time() - started < timeout_s:
        status_row = poll_run_status(client, run_id)
        stages = list_stage_progress(client, run_id)
        elapsed = int(time.time() - started)
        print(
            f"  [{elapsed:>4}s] status={status_row['status']:<10} "
            f"stages={[(s['step_id'], s['status']) for s in stages]}"
        )
        if status_row["status"] in _TERMINAL_STATUSES:
            return {"status_row": status_row, "stage_progress": stages}
        time.sleep(poll_interval_s)
    return {"status_row": status_row, "stage_progress": list_stage_progress(client, run_id)}


def _resolve_assertion(row: dict[str, Any]) -> str | None:
    """Runtime DOCUMENTS writes only set `assertion` inside the JSON-encoded
    `context` property, not as a top-level relationship property (confirmed
    against a real GY22/LGI5 replay: `r.assertion` was always null while
    `r.context` carried '{"assertion": "possible", ...}'). Prefer context,
    fall back to the top-level property for any write path that does set it.
    """
    context_json = row.get("context_json")
    if isinstance(context_json, str) and context_json.strip():
        try:
            parsed = json.loads(context_json)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and parsed.get("assertion"):
            return str(parsed["assertion"])
    return row.get("assertion_prop")


def _chunk_documents(client: PatientGraphClient, chunk_ids: list[str]) -> dict[str, list[dict]]:
    rows = client.run(_LIST_CHUNK_DOCUMENTS, chunk_ids=chunk_ids)
    by_chunk: dict[str, list[dict]] = {cid: [] for cid in chunk_ids}
    for row in rows:
        if not row.get("concept_id"):
            continue
        by_chunk.setdefault(str(row["chunk_id"]), []).append(
            {
                "concept_id": row["concept_id"],
                "concept_labels": row.get("concept_labels") or [],
                "term": row.get("term") or "",
                "assertion": _resolve_assertion(row),
                "confidence": row.get("confidence"),
                "evidence": row.get("evidence") or "",
                "evidence_sentence": row.get("evidence_sentence") or "",
                "value": row.get("value"),
                "unit": row.get("unit"),
            }
        )
    return by_chunk


def replay_referral(
    *,
    referral_id: str,
    plan_id: str,
    tenant_fallback: str,
    timeout_s: int,
    poll_interval_s: int,
) -> dict[str, Any]:
    client = PatientGraphClient()
    target = _resolve_referral_target(client, referral_id)
    print(f"Resolved referral {referral_id} -> patient {target.patient_id}")
    print(f"  reason: {target.reason[:120]!r}")
    print(f"  document: {target.document_reference_id} ({target.document_title!r})")

    resolved = resolve_pipeline_chunks(
        client,
        document_reference_id=target.document_reference_id,
        referral_id=target.referral_id,
        backfill_legacy_ids=True,
    )
    if not resolved.chunks:
        raise ReplayError(
            f"resolve_pipeline_chunks found no chunks for {target.document_reference_id!r} "
            f"(resolution={resolved.resolution!r})."
        )
    print(f"  chunks: {len(resolved.chunks)} (resolution={resolved.resolution})")

    reset_result = _reset_for_replay(client, target)
    print(
        f"  reset: patient_links_deleted={reset_result['patient_reset'].get('links_deleted')} "
        f"draft_assessments_deleted={reset_result['draft_reset'].get('draft_assessments_deleted')}"
    )

    chunk_ids = [str(c["id"]) for c in resolved.chunks]
    try:
        run_id = _start_run(
            client,
            target,
            chunk_ids,
            plan_id=plan_id,
            tenant_fallback=tenant_fallback,
        )
    except DocumentRunError as exc:
        raise ReplayError(f"start_document_run rejected the replay: {exc}") from exc
    print(f"  run_id={run_id}")

    poll_result = _poll_until_terminal(
        client, run_id, timeout_s=timeout_s, poll_interval_s=poll_interval_s
    )
    status_row = poll_result["status_row"]
    assessment_id = status_row.get("assessment_id") or ""
    outputs = read_real_outputs(client, assessment_id) if assessment_id else None

    entities_by_chunk = _chunk_documents(client, chunk_ids)
    chunks_bundle = [
        {
            "chunk_id": c["id"],
            "ordinal": c["ordinal"],
            "text": c["text"],
            "documented_concepts": entities_by_chunk.get(c["id"], []),
        }
        for c in resolved.chunks
    ]

    return {
        "referral": {
            "referral_id": target.referral_id,
            "patient_id": target.patient_id,
            "reason": target.reason,
            "clinic_type": target.clinic_type,
            "specialty": target.specialty,
            "document_reference_id": target.document_reference_id,
            "chunk_resolution": resolved.resolution,
        },
        "reset": reset_result,
        "run": {
            "run_id": run_id,
            "status": status_row.get("status"),
            "assessment_id": assessment_id or None,
            "stage_progress": poll_result["stage_progress"],
        },
        "chunks": chunks_bundle,
        "assessment": outputs.to_dict() if outputs is not None else None,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--referral-id", required=True)
    parser.add_argument("--plan-id", default="pd-referral-assessment")
    parser.add_argument("--tenant-fallback", default=_DEFAULT_TENANT_FALLBACK)
    parser.add_argument("--timeout-s", type=int, default=600)
    parser.add_argument("--poll-interval-s", type=int, default=5)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    load_dotenv(ROOT / "secrets" / ".env.config", override=False)
    load_dotenv(ROOT / "secrets" / ".env", override=False)
    load_keyvault_secrets()

    try:
        bundle = replay_referral(
            referral_id=args.referral_id,
            plan_id=args.plan_id,
            tenant_fallback=args.tenant_fallback,
            timeout_s=args.timeout_s,
            poll_interval_s=args.poll_interval_s,
        )
    except ReplayError as exc:
        print(f"REPLAY FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output) if args.output else (
        ROOT
        / "artifacts"
        / "replay"
        / args.referral_id
        / f"{bundle['run']['run_id']}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(bundle, indent=2, default=str))
    print(f"\nReview bundle written to {output_path}")
    print(f"Final status: {bundle['run']['status']}")


if __name__ == "__main__":
    main()
