"""Remediate the bad ``deterministic_luts_symptom_span`` DOCUMENTS edges.

Background
----------
On 2026-04-27 15:47:18 UTC a one-off batch wrote 167
``(Encounter)-[:DOCUMENTS {source:'deterministic_luts_symptom_span'}]->
(Clinical_finding)`` edges with the same hallucination pattern as the
ncda_comorbidity_backfill: ``evidence_sentence`` holds the canonical
concept name (e.g. ``"lower urinary tract symptoms"``) rather than a
real text snippet, ``evidence_start``/``evidence_end`` are NULL, and 152
of 167 edges have an ``evidence_sentence`` that does not appear anywhere
in the encounter text. Examples include rash consultations, bone-profile
labs, and full-blood-count auto-files all tagged with **Lower urinary
tract symptoms**.

This script removes those 152 edges. The 15 edges where the canonical
phrase IS present in the encounter text are left in place; they may
still be over-eager (template / list hits) but they at least pass the
substring check and warrant separate review.

Like the comorbidity remediation:
* hard-scoped to ``r.source = 'deterministic_luts_symptom_span'``
* additionally requires
  ``NOT toLower(e.text) CONTAINS toLower(r.evidence_sentence)``
* default mode is ``--dry-run``
* always writes a snapshot before deletion
* also cleans up the property-less patient ``HAS_FINDING`` edges that
  the upsert helper's ``FOREACH`` side-effect created
* garbage-collects concept nodes that become orphaned

Usage
-----
    python scripts/remediate_luts_symptom_span_backfill.py            # dry run
    python scripts/remediate_luts_symptom_span_backfill.py --apply    # commit
"""

from __future__ import annotations

import argparse
import json
import logging
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
log = logging.getLogger("remediate_luts_backfill")


BAD_SOURCE = "deterministic_luts_symptom_span"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "luts_symptom_span_remediation"

EXPECTED_BAD_COUNT = 152
SAFETY_FACTOR = 5


# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------

# A "bad" edge: this batch, AND its evidence_sentence is non-empty AND that
# string does not appear in the encounter text (case-insensitive). The same
# filter is applied to count, snapshot, and delete to keep them in lock-step.
_BAD_FILTER = (
    "r.source = $source "
    "AND coalesce(r.evidence_sentence,'') <> '' "
    "AND e.text IS NOT NULL "
    "AND NOT toLower(e.text) CONTAINS toLower(r.evidence_sentence)"
)

_Q_COUNT = f"""
MATCH (e:Encounter)-[r:DOCUMENTS]->()
WHERE {_BAD_FILTER}
RETURN count(*) AS n,
       min(r.coded_at) AS first_coded_at,
       max(r.coded_at) AS last_coded_at
"""

_Q_SNAPSHOT = f"""
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE {_BAD_FILTER}
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
       coalesce(r.evidence_start, -1) AS evidence_start,
       coalesce(r.evidence_end, -1)   AS evidence_end,
       toString(r.coded_at)          AS coded_at,
       substring(e.text, 0, 400)     AS encounter_text_head
ORDER BY coded_at, encounter_id, concept_id
"""

_Q_DELETE = f"""
MATCH (e:Encounter)-[r:DOCUMENTS]->()
WHERE {_BAD_FILTER}
WITH r LIMIT $batch
DELETE r
RETURN count(*) AS deleted
"""

# Patient-level HAS_* cleanup: only for the (patient_id, concept_id) pairs in
# the snapshot and only when the patient edge has zero properties (the
# fingerprint of the FOREACH side-effect).
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


def _coerce_dt(value: Any) -> Any:
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


def _summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_concept: dict[str, dict[str, Any]] = {}
    patients: set[str] = set()
    encounters: set[str] = set()
    for row in rows:
        cid = str(row.get("concept_id") or "")
        bucket = by_concept.setdefault(
            cid,
            {
                "concept_id": cid,
                "concept_name": str(row.get("concept_name") or ""),
                "evidence_synonym": str(row.get("evidence_sentence") or ""),
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
        "remediation": "luts_symptom_span_backfill",
        "scope": {
            "r.source": BAD_SOURCE,
            "filter": "evidence_sentence non-empty AND not present in encounter text",
        },
        "snapshot_taken_at": _now_stamp(),
        "neo4j_counts_at_snapshot": counts,
        "summary": _summarise(rows),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return snapshot_path, summary_path


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
    log.info("snapshotting bad LUTS edges ...")
    rows = client.run(_Q_SNAPSHOT, source=BAD_SOURCE)
    counts = step_count(client)
    snapshot_path, summary_path = _write_snapshot(output_dir, rows, counts)
    log.info("snapshot     -> %s (%d rows)", snapshot_path, len(rows))
    log.info("summary      -> %s", summary_path)
    return snapshot_path, summary_path, counts


def step_delete_edges(client: PatientGraphClient, *, batch: int = 500) -> int:
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
        description=(
            "Delete the 152 hallucinated edges from the "
            "deterministic_luts_symptom_span batch."
        )
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes to Neo4j (default is dry-run snapshot only).",
    )
    p.add_argument(
        "--no-gc-orphans",
        action="store_true",
        help="Skip orphan Clinical_finding/SnomedConcept node garbage collection.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for snapshot/summary output (timestamped subfolder).",
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
            f"Required when bad edge count exceeds {SAFETY_FACTOR * EXPECTED_BAD_COUNT}."
        ),
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    apply = bool(args.apply)
    mode = "APPLY" if apply else "DRY-RUN"
    log.info("=== luts_symptom_span backfill remediation -- %s ===", mode)

    run_dir = args.output_dir / _now_stamp()
    log.info("run output -> %s", run_dir)

    client = PatientGraphClient()
    try:
        counts = step_count(client)
        n = counts["n"]
        log.info(
            "found %d bad edges (source=%r, evidence_sentence not in text). "
            "first=%s last=%s",
            n,
            BAD_SOURCE,
            counts["first_coded_at"],
            counts["last_coded_at"],
        )

        if n == 0:
            log.info("nothing to do.")
            return 0

        if n > EXPECTED_BAD_COUNT * SAFETY_FACTOR and not args.ack_larger_than_expected:
            log.error(
                "bad edge count %d exceeds %dx the expected baseline %d. "
                "Refusing to proceed without --ack-larger-than-expected.",
                n,
                SAFETY_FACTOR,
                EXPECTED_BAD_COUNT,
            )
            return 2

        snapshot_path, summary_path, _ = step_snapshot(client, run_dir)

        if not apply:
            with snapshot_path.open("r", encoding="utf-8") as f:
                preview_rows = [json.loads(line) for line in f if line.strip()]
            n_pairs = len({(r["patient_id"], r["concept_id"]) for r in preview_rows})
            log.info(
                "[DRY-RUN] would delete %d DOCUMENTS edges, then check "
                "%d (patient, concept) HAS_* pairs (only those whose r is "
                "property-less), then GC any concept node now orphaned.",
                n,
                n_pairs,
            )
            log.info("re-run with --apply to commit.")
            return 0

        with snapshot_path.open("r", encoding="utf-8") as f:
            snapshot_rows = [json.loads(line) for line in f if line.strip()]

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

        final = step_count(client)
        log.info("final count of bad edges remaining: %d", final["n"])

        def _safe_rel(path: Path) -> str:
            abs_path = path if path.is_absolute() else (Path.cwd() / path).resolve()
            try:
                return str(abs_path.relative_to(ROOT))
            except ValueError:
                return str(abs_path)

        report = {
            "remediation": "luts_symptom_span_backfill",
            "applied_at": _now_stamp(),
            "n_documents_edges_deleted": n_edges_deleted,
            "patient_edge_cleanup": patient_result,
            "n_bad_edges_remaining": final["n"],
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
                "expected zero bad edges after delete, found %d", final["n"]
            )
            return 3
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
