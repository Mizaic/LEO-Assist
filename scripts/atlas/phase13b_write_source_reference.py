"""Phase 13b - write source_reference onto every Atlas DO we have evidence for.

Inputs (from Phase 13a):
  - compliance/atlas-migration-evidence/phase13a-do-source-reference-audit.csv
  - compliance/atlas-migration-evidence/phase13a-legacy-to-atlas.csv

Outputs:
  - compliance/atlas-migration-evidence/phase13b-ledger.csv
  - compliance/atlas-migration-evidence/phase13b-review-queue.csv
  - compliance/atlas-migration-evidence/phase13b-atlas-do-index.csv

Behaviour:
  1. Build the live Atlas DO index via get_traceability_matrix.
  2. Compute the union: dcIds in the matrix vs dcIds in the 13a audit.
  3. For each DO in the 13a audit with >= 1 file path, call
     update_design_output(source_reference="<paths> [phase13b]").
     The trailing "[phase13b]" tag makes any subsequent edit detectable.
  4. For each DO in the 13a audit with 0 file paths, append to the
     review queue with note `ledger evidence but no file paths`.
  5. For each Atlas DO that is NOT in the 13a audit, append to the
     review queue with note `no ledger evidence; likely Phase 2 stub`.

Idempotent: every action is journalled to phase13b-ledger.csv. A
re-run skips DOs whose ledger row says decision=updated or skipped.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(Path(__file__).parent))
from _mcp_transport import McpError, call_tool, initialize  # noqa: E402
from product import PRODUCT_ID  # noqa: E402

EVIDENCE = ROOT / "compliance" / "atlas-migration-evidence"
AUDIT_CSV = EVIDENCE / "phase13a-do-source-reference-audit.csv"
LEDGER_CSV = EVIDENCE / "phase13b-ledger.csv"
REVIEW_CSV = EVIDENCE / "phase13b-review-queue.csv"
INDEX_CSV = EVIDENCE / "phase13b-atlas-do-index.csv"

LEDGER_COLS = [
    "kind",  # update | skip | review | error
    "atlas_dcid",
    "decision",  # updated | already_phase13b | no_evidence | not_in_audit
    "source_path_count",
    "note",
    "ts",
]
REVIEW_COLS = [
    "atlas_dcid",
    "category",  # ledger-but-no-paths | not-in-audit
    "title",
    "note",
]

PHASE13B_TAG = "[phase13b]"
MAX_FIELD = 4000  # safety bound on source_reference length


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_ledger() -> list[dict]:
    if not LEDGER_CSV.exists():
        return []
    with LEDGER_CSV.open(newline="") as f:
        return list(csv.DictReader(f))


def append_ledger(rows: list[dict]) -> None:
    is_new = not LEDGER_CSV.exists()
    with LEDGER_CSV.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLS)
        if is_new:
            w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in LEDGER_COLS})


def write_review(rows: list[dict]) -> None:
    with REVIEW_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in REVIEW_COLS})


def write_index(rows: list[dict]) -> None:
    with INDEX_CSV.open("w", newline="") as f:
        cols = ["atlas_dcid", "title", "in_phase13a_audit"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def load_audit() -> list[dict]:
    with AUDIT_CSV.open(newline="") as f:
        return list(csv.DictReader(f))


def list_atlas_dos() -> list[dict]:
    """Return [{atlas_dcid, title}, ...] for every DO in Atlas."""
    matrix = call_tool("get_traceability_matrix", {"product_id": PRODUCT_ID})
    rows: dict[str, dict] = {}

    def collect(node: object) -> None:
        if isinstance(node, dict):
            dc_id = node.get("dcId") or node.get("dc_id")
            dc_type = node.get("dcType") or node.get("dc_type") or ""
            if (
                dc_id
                and isinstance(dc_id, str)
                and dc_id.startswith("DO-")
                and len(dc_id) <= 16
            ):
                title = node.get("title", "")
                if dc_type in ("", "design-output", "designOutput") or "DO" in dc_id:
                    rows.setdefault(dc_id, {"atlas_dcid": dc_id, "title": title})
            for v in node.values():
                collect(v)
        elif isinstance(node, list):
            for v in node:
                collect(v)

    collect(matrix)
    return sorted(rows.values(), key=lambda r: r["atlas_dcid"])


def build_source_reference(paths_str: str) -> str:
    """Format a source_reference string with a trailing [phase13b] tag."""
    paths = [p.strip() for p in paths_str.split(";") if p.strip()]
    paths = sorted(set(paths))
    body = "; ".join(paths)
    tag = f" {PHASE13B_TAG}"
    if len(body) + len(tag) > MAX_FIELD:
        body = body[: MAX_FIELD - len(tag) - 4] + "..."
    return body + tag


def update_one(dcid: str, source_reference: str) -> tuple[str, str]:
    """Returns (decision, note)."""
    try:
        out = call_tool(
            "update_design_output",
            {"dc_id": dcid, "source_reference": source_reference},
        )
    except McpError as e:
        return "error", str(e)[:300]
    err = (out or {}).get("error")
    if err:
        return "error", str(err)[:300]
    return "updated", "ok"


def main() -> int:
    print("Phase 13b - write Atlas DO source_reference from 13a evidence")
    initialize()

    print("[1/4] Pulling live Atlas DO index ...")
    atlas_dos = list_atlas_dos()
    print(f"  -> {len(atlas_dos)} DOs in Atlas")

    audit = load_audit()
    audit_by_dcid: dict[str, dict] = {r["atlas_dcid"]: r for r in audit}
    print(f"  -> {len(audit)} DOs in 13a audit")

    in_audit = set(audit_by_dcid)
    in_atlas = {r["atlas_dcid"] for r in atlas_dos}
    print(
        f"  -> overlap: {len(in_audit & in_atlas)}; "
        f"in atlas but not in audit: {len(in_atlas - in_audit)}; "
        f"in audit but not in atlas: {len(in_audit - in_atlas)}"
    )

    write_index(
        [
            {
                "atlas_dcid": d["atlas_dcid"],
                "title": d["title"],
                "in_phase13a_audit": "1" if d["atlas_dcid"] in in_audit else "0",
            }
            for d in atlas_dos
        ]
    )

    ledger = load_ledger()
    done_dcids = {
        r["atlas_dcid"]
        for r in ledger
        if r.get("decision")
        in {"updated", "already_phase13b", "no_evidence", "not_in_audit"}
    }
    print(f"  -> {len(done_dcids)} DOs already in ledger; resuming after them")

    print("[2/4] Updating DOs that have file evidence ...")
    review_rows: list[dict] = []
    new_ledger: list[dict] = []
    updates = 0
    skips = 0
    errors = 0
    for r in audit:
        dcid = r["atlas_dcid"]
        if dcid in done_dcids:
            continue
        path_count = int(r.get("expected_source_path_count", "0") or 0)
        if path_count == 0:
            review_rows.append(
                {
                    "atlas_dcid": dcid,
                    "category": "ledger-but-no-paths",
                    "title": "",
                    "note": (
                        f"phases_with_evidence={r.get('phases_with_evidence', '')}; "
                        f"legacy_ids={r.get('legacy_ids', '')}"
                    ),
                }
            )
            new_ledger.append(
                {
                    "kind": "review",
                    "atlas_dcid": dcid,
                    "decision": "no_evidence",
                    "source_path_count": "0",
                    "note": "ledger evidence but no file paths",
                    "ts": _now(),
                }
            )
            skips += 1
            continue
        body = build_source_reference(r["expected_source_paths"])
        decision, note = update_one(dcid, body)
        if decision == "updated":
            updates += 1
            new_ledger.append(
                {
                    "kind": "update",
                    "atlas_dcid": dcid,
                    "decision": "updated",
                    "source_path_count": str(path_count),
                    "note": (
                        f"phases={r.get('phases_with_evidence', '')}; "
                        f"legacy={r.get('legacy_ids', '')}"
                    ),
                    "ts": _now(),
                }
            )
        else:
            errors += 1
            new_ledger.append(
                {
                    "kind": "error",
                    "atlas_dcid": dcid,
                    "decision": "error",
                    "source_path_count": str(path_count),
                    "note": note,
                    "ts": _now(),
                }
            )
        if (updates + errors + skips) % 25 == 0:
            append_ledger(new_ledger)
            new_ledger = []
            print(f"  ... progress: updates={updates} skips={skips} errors={errors}")

    if new_ledger:
        append_ledger(new_ledger)

    print("[3/4] Building review queue for DOs not in 13a audit ...")
    only_in_atlas = sorted(in_atlas - in_audit)
    title_by_dcid = {d["atlas_dcid"]: d["title"] for d in atlas_dos}
    final_review: list[dict] = []
    for r in review_rows:
        final_review.append(r)
    new_ledger = []
    for dcid in only_in_atlas:
        already = any(
            row.get("atlas_dcid") == dcid and row.get("decision") == "not_in_audit"
            for row in ledger
        )
        if already:
            continue
        final_review.append(
            {
                "atlas_dcid": dcid,
                "category": "not-in-audit",
                "title": title_by_dcid.get(dcid, ""),
                "note": "no ledger evidence; likely Phase 2 stub",
            }
        )
        new_ledger.append(
            {
                "kind": "review",
                "atlas_dcid": dcid,
                "decision": "not_in_audit",
                "source_path_count": "0",
                "note": "no ledger evidence; likely Phase 2 stub",
                "ts": _now(),
            }
        )
    if new_ledger:
        append_ledger(new_ledger)
    write_review(final_review)

    print("[4/4] Done.")
    print(f"  updates: {updates}")
    print(f"  skips (no file evidence): {skips}")
    print(f"  errors: {errors}")
    print(f"  review queue rows: {len(final_review)}")
    print(f"  ledger: {LEDGER_CSV}")
    print(f"  review: {REVIEW_CSV}")
    print(f"  index:  {INDEX_CSV}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
