"""Remediate the bad ``ncda_comorbidity_backfill`` DOCUMENTS edges.

Background
----------
On 2026-04-28 21:04-21:06 UTC a one-off deterministic comorbidity
backfill wrote ~1,667 ``(Encounter)-[:DOCUMENTS {domain:'comorbidities',
source:'ncda_comorbidity_backfill'}]->(Situation|Disease)`` edges with
``confidence = 0.95``, ``evidence_start = evidence_end = 0`` and an
``evidence_sentence`` that holds the synonym key (NOT a substring lifted
from the encounter). The matcher used a naive ``low in text_lc`` check
with no word boundaries, no negation handling and no subject detection,
so it tagged things like:

* ``Brother had stroke aged 59`` -> History of cerebrovascular disease
* ``Sister died ... with asthma`` -> History of COPD
* ``Reasons for Request: htn / predm review`` -> History of diabetes
  (matched the ``DM`` substring inside ``predm``)

None of those are patient comorbidities; they are family history,
abbreviations or pre-disease screening. Every edge is also missing real
character offsets, so it is not even reviewable through the normal
audit UI.

This script removes that batch.

Safety
------
Hard-scoped to ``r.source = 'ncda_comorbidity_backfill'``. Refuses to
touch anything else. Default mode is ``--dry-run``; use ``--apply`` to
commit. Always writes a snapshot JSON before deletion so the operation
is reversible by replay.

The upsert helper that wrote these DOCUMENTS edges also fires a
FOREACH that creates property-less ``(Patient)-[:HAS_SITUATION|
HAS_DISORDER|HAS_FINDING]->(Concept)`` edges as a side-effect (the
guard defaults assertion to 'present'). Those patient-level edges have
no ``source`` or ``domain`` property, so they cannot be filtered by
relationship metadata -- but every ``(patient_id, concept_id)`` pair
the bad batch produced is in the snapshot, and the patient sets
exactly match the leftover edges. We delete those patient HAS_* edges
ONLY for pairs in the snapshot.

Finally, any Situation/Disease/Clinical_finding node that the bad
batch created (often as a duplicate label of an already-existing
SnomedConcept) gets garbage-collected once it has zero relationships
left.

Usage
-----
    python scripts/remediate_ncda_comorbidity_backfill.py            # dry run
    python scripts/remediate_ncda_comorbidity_backfill.py --apply    # commit
    python scripts/remediate_ncda_comorbidity_backfill.py --apply --no-gc-orphans
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
)
log = logging.getLogger("remediate_comorbidity_backfill")


BAD_SOURCE = "ncda_comorbidity_backfill"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ncda_comorbidity_backfill_remediation"

# Sanity guards: we expect this many edges (+/- a small drift). Refuse to
# proceed if we see 5x more, which would indicate the source string is
# being reused by something else and our hard scope is no longer safe.
EXPECTED_EDGE_COUNT = 1667
SAFETY_FACTOR = 5


# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------

_Q_COUNT = """
MATCH ()-[r:DOCUMENTS]->()
WHERE r.source = $source
RETURN count(*) AS n,
       min(r.coded_at) AS first_coded_at,
       max(r.coded_at) AS last_coded_at
"""

_Q_SNAPSHOT = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE r.source = $source
RETURN toString(p.id)               AS patient_id,
       toString(e.id)                AS encounter_id,
       toString(e.date)              AS encounter_date,
       toString(c.conceptId)         AS concept_id,
       coalesce(c.name, c.term)      AS concept_name,
       labels(c)                     AS concept_labels,
       coalesce(r.domain, '')        AS domain,
       coalesce(r.source, '')        AS source,
       coalesce(r.evidence_sentence, '') AS evidence_sentence,
       coalesce(r.evidence, '')      AS evidence,
       coalesce(r.confidence, 0.0)   AS confidence,
       coalesce(r.assertion, '')     AS assertion,
       coalesce(r.evidence_start, 0) AS evidence_start,
       coalesce(r.evidence_end, 0)   AS evidence_end,
       toString(r.coded_at)          AS coded_at
ORDER BY coded_at, encounter_id, concept_id
"""

_Q_DELETE = """
MATCH ()-[r:DOCUMENTS]->()
WHERE r.source = $source
WITH r LIMIT $batch
DELETE r
RETURN count(*) AS deleted
"""

# Delete the patient-level HAS_* edge created as a FOREACH side-effect of the
# bad backfill. We hard-scope to (patient_id, concept_id) pairs that exist in
# the snapshot to avoid clobbering legitimate patient-level codings.
_Q_DELETE_PATIENT_EDGE = """
UNWIND $pairs AS pair
MATCH (p:Patient)-[r]->(c)
WHERE toString(p.id) = pair.patient_id
  AND toString(c.conceptId) = pair.concept_id
  AND type(r) IN ['HAS_SITUATION','HAS_DISORDER','HAS_FINDING','HAS_CONCEPT','HAS_DISEASE']
  AND coalesce(r.source, '') = ''
  AND coalesce(r.domain, '') = ''
  AND size(keys(properties(r))) = 0
DELETE r
RETURN count(r) AS deleted
"""

# Per-node orphan check + delete. We iterate over ALL nodes that share each
# conceptId so duplicate :Situation labels left behind by the bad batch are
# also collected, not just the first row.
_Q_FIND_NODES_FOR_CONCEPT = """
MATCH (c)
WHERE toString(c.conceptId) = $concept_id
  AND any(lbl IN labels(c) WHERE lbl IN [
      'Situation','Disease','Clinical_finding','Observable_entity','SnomedConcept'
  ])
RETURN id(c) AS internal_id, labels(c) AS labels, c.name AS name
"""

_Q_NODE_ORPHAN_STATUS = """
MATCH (c) WHERE id(c) = $internal_id
OPTIONAL MATCH (c)-[r]-()
RETURN count(r) AS rel_count
"""

_Q_DELETE_NODE_BY_ID = """
MATCH (c) WHERE id(c) = $internal_id AND NOT (c)-[]-()
DELETE c
RETURN count(c) AS deleted
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_concept: dict[str, dict[str, Any]] = {}
    patients: set[str] = set()
    encounters: set[str] = set()
    for row in rows:
        cid = str(row.get("concept_id") or "")
        name = str(row.get("concept_name") or "")
        ev = str(row.get("evidence_sentence") or "")
        bucket = by_concept.setdefault(
            cid,
            {
                "concept_id": cid,
                "concept_name": name,
                "evidence_synonym": ev,
                "n_edges": 0,
                "patients": set(),
            },
        )
        bucket["n_edges"] += 1
        bucket["patients"].add(str(row.get("patient_id") or ""))
        patients.add(str(row.get("patient_id") or ""))
        encounters.add(str(row.get("encounter_id") or ""))

    by_concept_list = sorted(
        (
            {
                "concept_id": v["concept_id"],
                "concept_name": v["concept_name"],
                "evidence_synonym": v["evidence_synonym"],
                "n_edges": v["n_edges"],
                "n_patients": len(v["patients"]),
            }
            for v in by_concept.values()
        ),
        key=lambda d: d["n_edges"],
        reverse=True,
    )

    return {
        "total_edges": len(rows),
        "n_patients": len(patients),
        "n_encounters": len(encounters),
        "by_concept": by_concept_list,
    }


def _write_snapshot(
    output_dir: Path,
    rows: list[dict[str, Any]],
    counts: dict[str, Any],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_dir / "snapshot.jsonl"
    summary_path = output_dir / "summary.json"

    with snapshot_path.open("w", encoding="utf-8") as f:
        for row in rows:
            safe = {k: _coerce_dt(v) for k, v in row.items()}
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")

    summary = {
        "remediation": "ncda_comorbidity_backfill",
        "scope": {"r.source": BAD_SOURCE},
        "snapshot_taken_at": _now_stamp(),
        "neo4j_counts_at_snapshot": counts,
        "summary": _summarise(rows),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return snapshot_path, summary_path


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _coerce_dt(value: Any) -> Any:
    """Cast Neo4j DateTime / Date types to ISO strings for JSON output."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    iso = getattr(value, "iso_format", None)
    if callable(iso):
        try:
            return iso()
        except Exception:  # noqa: BLE001
            pass
    return str(value)


def step_count(client: PatientGraphClient) -> dict[str, Any]:
    rows = client.run(_Q_COUNT, source=BAD_SOURCE)
    if not rows:
        return {"n": 0, "first_coded_at": None, "last_coded_at": None}
    r = rows[0]
    return {
        "n": int(r.get("n") or 0),
        "first_coded_at": _coerce_dt(r.get("first_coded_at")),
        "last_coded_at": _coerce_dt(r.get("last_coded_at")),
    }


def step_snapshot(
    client: PatientGraphClient, output_dir: Path
) -> tuple[Path, Path, dict[str, Any]]:
    log.info("snapshotting edges with source = %r ...", BAD_SOURCE)
    rows = client.run(_Q_SNAPSHOT, source=BAD_SOURCE)
    counts = step_count(client)
    snapshot_path, summary_path = _write_snapshot(output_dir, rows, counts)
    log.info("snapshot     -> %s (%d rows)", snapshot_path, len(rows))
    log.info("summary      -> %s", summary_path)
    return snapshot_path, summary_path, counts


def step_delete_edges(
    client: PatientGraphClient, *, batch: int = 500
) -> int:
    total = 0
    while True:
        rows = client.run(_Q_DELETE, source=BAD_SOURCE, batch=batch)
        deleted = int(rows[0].get("deleted") or 0) if rows else 0
        total += deleted
        log.info("deleted %d edges (running total %d)", deleted, total)
        if deleted < batch:
            break
    return total


def step_delete_patient_edges(
    client: PatientGraphClient,
    snapshot_rows: list[dict[str, Any]],
    *,
    batch: int = 500,
) -> dict[str, int]:
    """Delete property-less HAS_* edges that mirror the bad batch's pairs."""
    pairs = sorted(
        {
            (str(r["patient_id"]), str(r["concept_id"]))
            for r in snapshot_rows
            if r.get("patient_id") and r.get("concept_id")
        }
    )
    log.info("checking %d (patient, concept) pairs for stray HAS_* edges", len(pairs))
    total_deleted = 0
    for i in range(0, len(pairs), batch):
        chunk = [
            {"patient_id": pid, "concept_id": cid}
            for pid, cid in pairs[i : i + batch]
        ]
        rows = client.run(_Q_DELETE_PATIENT_EDGE, pairs=chunk)
        deleted = int(rows[0].get("deleted") or 0) if rows else 0
        total_deleted += deleted
    log.info("patient HAS_* edges deleted: %d", total_deleted)
    return {"checked_pairs": len(pairs), "deleted": total_deleted}


def step_gc_orphan_nodes(
    client: PatientGraphClient, candidate_concept_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Per-node orphan GC -- iterates every node sharing each conceptId."""
    deleted: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for cid in candidate_concept_ids:
        nodes = client.run(_Q_FIND_NODES_FOR_CONCEPT, concept_id=cid)
        for node in nodes:
            internal_id = node.get("internal_id")
            if internal_id is None:
                continue
            status_rows = client.run(_Q_NODE_ORPHAN_STATUS, internal_id=internal_id)
            rel_count = (
                int(status_rows[0].get("rel_count") or 0) if status_rows else 0
            )
            entry = {
                "concept_id": cid,
                "internal_id": int(internal_id),
                "labels": list(node.get("labels") or []),
                "name": node.get("name"),
                "rel_count": rel_count,
            }
            if rel_count == 0:
                d = client.run(_Q_DELETE_NODE_BY_ID, internal_id=internal_id)
                n_deleted = int(d[0].get("deleted") or 0) if d else 0
                if n_deleted:
                    deleted.append(entry)
                    continue
            kept.append(entry)
    return {"deleted": deleted, "kept": kept}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Remediate the bad ncda_comorbidity_backfill DOCUMENTS edges."
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes to Neo4j (default is dry-run snapshot only).",
    )
    p.add_argument(
        "--no-gc-orphans",
        action="store_true",
        help="Skip orphan Situation/Disease node garbage collection.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "Directory to write snapshot/summary into. "
            "A timestamped subfolder is created underneath."
        ),
    )
    p.add_argument(
        "--batch",
        type=int,
        default=500,
        help="Delete batch size (default 500).",
    )
    p.add_argument(
        "--ack-larger-than-expected",
        action="store_true",
        help=(
            f"Bypass the {SAFETY_FACTOR}x safety guard. "
            f"Required when edge count exceeds {SAFETY_FACTOR * EXPECTED_EDGE_COUNT}."
        ),
    )
    p.add_argument(
        "--from-snapshot",
        type=Path,
        help=(
            "Resume from an existing snapshot.jsonl produced by an earlier run. "
            "Skips the DOCUMENTS-edge delete step and proceeds to clean up "
            "patient-level HAS_* edges + orphan nodes. Use after a partial "
            "remediation when only the FOREACH side-effect cleanup is left."
        ),
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    apply = bool(args.apply)
    mode = "APPLY" if apply else "DRY-RUN"
    log.info("=== ncda_comorbidity_backfill remediation -- %s ===", mode)

    run_dir = args.output_dir / _now_stamp()
    log.info("run output -> %s", run_dir)

    client = PatientGraphClient()
    try:
        counts = step_count(client)
        n = counts["n"]
        log.info(
            "found %d edges with source=%r (first=%s, last=%s)",
            n,
            BAD_SOURCE,
            counts["first_coded_at"],
            counts["last_coded_at"],
        )

        if args.from_snapshot:
            snapshot_path = args.from_snapshot
            if not snapshot_path.exists():
                log.error("snapshot file not found: %s", snapshot_path)
                return 2
            summary_path = snapshot_path.with_name("summary.json")
            log.info("resume mode: using snapshot %s", snapshot_path)
        elif n == 0:
            log.info("nothing to do.")
            return 0
        else:
            if n > EXPECTED_EDGE_COUNT * SAFETY_FACTOR and not args.ack_larger_than_expected:
                log.error(
                    "edge count %d exceeds %dx the expected baseline %d. "
                    "Refusing to proceed without --ack-larger-than-expected.",
                    n,
                    SAFETY_FACTOR,
                    EXPECTED_EDGE_COUNT,
                )
                return 2
            snapshot_path, summary_path, _ = step_snapshot(client, run_dir)

        if not apply:
            with snapshot_path.open("r", encoding="utf-8") as f:
                preview_rows = [json.loads(line) for line in f if line.strip()]
            n_pairs = len({(r["patient_id"], r["concept_id"]) for r in preview_rows})
            log.info(
                "[DRY-RUN] would delete %d DOCUMENTS edges, then "
                "%d (patient, concept) HAS_* pairs (only those whose r is "
                "property-less), then GC any concept node now orphaned.",
                n,
                n_pairs,
            )
            log.info("re-run with --apply to commit.")
            return 0

        # Load the snapshot once for downstream steps that need (pid, cid) pairs.
        with snapshot_path.open("r", encoding="utf-8") as f:
            snapshot_rows = [json.loads(line) for line in f if line.strip()]

        if args.from_snapshot:
            log.info("resume mode: skipping DOCUMENTS edge delete step")
            n_edges_deleted = 0
        else:
            log.info("deleting DOCUMENTS edges in batches of %d ...", args.batch)
            n_edges_deleted = step_delete_edges(client, batch=args.batch)
            log.info("DOCUMENTS edges deleted: %d", n_edges_deleted)

        log.info("deleting stray patient-level HAS_* edges (FOREACH side-effect) ...")
        patient_result = step_delete_patient_edges(
            client, snapshot_rows, batch=args.batch
        )

        gc_result: dict[str, Any] = {"skipped": True}
        if not args.no_gc_orphans:
            candidate_ids = sorted(
                {r["concept_id"] for r in snapshot_rows if r.get("concept_id")}
            )
            log.info(
                "garbage-collecting orphan nodes for %d concept ids ...",
                len(candidate_ids),
            )
            gc_result = step_gc_orphan_nodes(client, candidate_ids)
            log.info(
                "orphan node GC -> deleted=%d kept=%d",
                len(gc_result.get("deleted") or []),
                len(gc_result.get("kept") or []),
            )

        # Final state
        final = step_count(client)
        log.info("final count of source=%r edges: %d", BAD_SOURCE, final["n"])

        def _safe_rel(path: Path) -> str:
            abs_path = path if path.is_absolute() else (Path.cwd() / path).resolve()
            try:
                return str(abs_path.relative_to(ROOT))
            except ValueError:
                return str(abs_path)

        report = {
            "remediation": "ncda_comorbidity_backfill",
            "applied_at": _now_stamp(),
            "resumed_from_snapshot": bool(args.from_snapshot),
            "n_documents_edges_deleted": n_edges_deleted,
            "patient_edge_cleanup": patient_result,
            "n_documents_edges_remaining_with_source": final["n"],
            "orphan_node_gc": gc_result,
            "snapshot_jsonl": _safe_rel(snapshot_path),
            "summary_json": _safe_rel(summary_path),
        }
        (run_dir / "apply_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log.info("apply report -> %s", run_dir / "apply_report.json")

        if final["n"] != 0:
            log.error(
                "expected zero edges with source=%r after delete, found %d",
                BAD_SOURCE,
                final["n"],
            )
            return 3

        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
