"""Phase 14d-ii -- mint UN/DI/DO triplets for every bucket.

Inputs:
  compliance/atlas-migration-evidence/phase14d-bucket-plan.csv
  scripts/atlas/phase14d_metadata.py  (BUCKET_META, SPECIAL_DO_PARENTS)

Outputs:
  compliance/atlas-migration-evidence/phase14d-create-ledger.csv
  compliance/atlas-migration-evidence/phase14d-bucket-ids.json
       { bucket_id: { "un": "UN-...", "di": "DI-...", "do": "DO-...",
                       "additional_dis": [...] } }

For every regular bucket (Class B+):
  1. create_user_need
  2. create_design_input
  3. link_design_controls(UN -> DI, HAS_DESIGN_INPUT)
  4. create_design_output (with source_reference = bucket file paths
     plus a [phase14d] tag)
  5. link_design_controls(DO -> DI, IMPLEMENTS)

For specials (existing-DO-<dcid>):
  1. update_design_output to merge bucket files into source_reference
  2. record the existing DO and its known parent DIs in bucket-ids.json

Idempotent: every Atlas write is recorded in the ledger and skipped on
re-run.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from _mcp_transport import McpError, call_tool, initialize  # noqa: E402
from phase14d_metadata import (  # noqa: E402
    BUCKET_META,
    PRODUCT_ID,
    SPECIAL_DO_PARENTS,
)

EVIDENCE = ROOT / "compliance" / "atlas-migration-evidence"
PLAN = EVIDENCE / "phase14d-bucket-plan.csv"
LEDGER = EVIDENCE / "phase14d-create-ledger.csv"
BUCKET_IDS = EVIDENCE / "phase14d-bucket-ids.json"

PHASE14D_TAG = "[phase14d]"
MAX_FIELD = 4000

LEDGER_COLS = ["operation", "bucket", "subject", "result", "note"]


# ---------------------------------------------------------------------
# Ledger helpers
# ---------------------------------------------------------------------

def _ledger_rows() -> list[dict]:
    if not LEDGER.exists():
        return []
    return list(csv.DictReader(LEDGER.open()))


def _append_ledger(row: dict) -> None:
    new = not LEDGER.exists()
    with LEDGER.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLS)
        if new:
            w.writeheader()
        w.writerow({c: row.get(c, "") for c in LEDGER_COLS})


def _resume(operation: str, bucket: str, subject: str = "") -> str | None:
    for r in _ledger_rows():
        if (
            r["operation"] == operation
            and r["bucket"] == bucket
            and (subject == "" or r["subject"] == subject)
            and r["result"] in ("created", "ok", "linked")
        ):
            return r["note"]
    return None


def _safe(name: str, args: dict, bucket: str, subject: str) -> dict | None:
    try:
        out = call_tool(name, args)
    except McpError as e:
        _append_ledger({"operation": name, "bucket": bucket,
                        "subject": subject, "result": "error",
                        "note": str(e)[:300]})
        print(f"  ! {name}({bucket}/{subject}): {str(e)[:160]}")
        return None
    err = (out or {}).get("error")
    if err:
        _append_ledger({"operation": name, "bucket": bucket,
                        "subject": subject, "result": "error",
                        "note": str(err)[:300]})
        print(f"  ! {name}({bucket}/{subject}): {str(err)[:160]}")
        return None
    return out


# ---------------------------------------------------------------------
# Plan loading
# ---------------------------------------------------------------------

def load_plan() -> dict[str, list[str]]:
    by_bucket: dict[str, list[str]] = defaultdict(list)
    for r in csv.DictReader(PLAN.open()):
        by_bucket[r["bucket_id"]].append(r["file_path"])
    for k in by_bucket:
        by_bucket[k] = sorted(set(by_bucket[k]))
    return dict(by_bucket)


def build_source_reference(paths: list[str]) -> str:
    body = "; ".join(sorted(set(paths)))
    tag = f" {PHASE14D_TAG}"
    if len(body) + len(tag) > MAX_FIELD:
        body = body[: MAX_FIELD - len(tag) - 4] + "..."
    return body + tag


# ---------------------------------------------------------------------
# Bucket processors
# ---------------------------------------------------------------------

def _extract_id(out: dict | None, *paths: tuple[str, ...]) -> str | None:
    """Walk an Atlas response for the first non-empty id at any of the
    paths."""
    if not out:
        return None
    for path in paths:
        cur = out
        ok = True
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok and isinstance(cur, str) and cur:
            return cur
    return None


def process_regular_bucket(
    bucket_id: str, paths: list[str], ids_out: dict
) -> None:
    meta = BUCKET_META.get(bucket_id)
    if not meta:
        print(f"  ! {bucket_id}: no metadata in BUCKET_META; skipping")
        return
    print(f"\n[bucket] {bucket_id} ({len(paths)} files)")

    # 1. Create UN
    un_id = _resume("create_user_need", bucket_id)
    if not un_id:
        out = _safe("create_user_need",
                    {"product_id": PRODUCT_ID, **meta["un"]},
                    bucket_id, meta["un"]["title"])
        un_id = _extract_id(out,
                            ("dcId",), ("dc_id",),
                            ("userNeed", "dcId"),
                            ("userNeed", "dc_id"))
        if un_id:
            _append_ledger({"operation": "create_user_need",
                            "bucket": bucket_id,
                            "subject": meta["un"]["title"],
                            "result": "created", "note": un_id})
            print(f"  UN: {un_id}")
    else:
        print(f"  UN (resumed): {un_id}")

    # 2. Create DI
    di_id = _resume("create_design_input", bucket_id)
    if not di_id:
        out = _safe("create_design_input",
                    {"product_id": PRODUCT_ID, **meta["di"]},
                    bucket_id, meta["di"]["title"])
        di_id = _extract_id(out,
                            ("dcId",), ("dc_id",),
                            ("designInput", "dcId"),
                            ("designInput", "dc_id"))
        if di_id:
            _append_ledger({"operation": "create_design_input",
                            "bucket": bucket_id,
                            "subject": meta["di"]["title"],
                            "result": "created", "note": di_id})
            print(f"  DI: {di_id}")
    else:
        print(f"  DI (resumed): {di_id}")

    # 3. Link UN -> DI
    if un_id and di_id and not _resume("link_un_di", bucket_id):
        out = _safe("link_design_controls",
                    {"source_ids": [un_id], "target_ids": [di_id],
                     "relationship": "HAS_DESIGN_INPUT"},
                    bucket_id, f"{un_id}->{di_id}")
        if out is not None:
            _append_ledger({"operation": "link_un_di",
                            "bucket": bucket_id,
                            "subject": f"{un_id}->{di_id}",
                            "result": "linked",
                            "note": "HAS_DESIGN_INPUT"})
            print(f"  link UN->DI ok")

    # 4. Create DO
    do_id = _resume("create_design_output", bucket_id)
    if not do_id:
        do_args = {
            "product_id": PRODUCT_ID,
            **meta["do"],
            "source_reference": build_source_reference(paths),
        }
        out = _safe("create_design_output", do_args,
                    bucket_id, meta["do"]["title"])
        do_id = _extract_id(out,
                            ("dcId",), ("dc_id",),
                            ("designOutput", "dcId"),
                            ("designOutput", "dc_id"))
        if do_id:
            _append_ledger({"operation": "create_design_output",
                            "bucket": bucket_id,
                            "subject": meta["do"]["title"],
                            "result": "created", "note": do_id})
            print(f"  DO: {do_id}  (src_ref: {len(paths)} paths)")
    else:
        print(f"  DO (resumed): {do_id}")

    # 5. Link DO -> DI
    if do_id and di_id and not _resume("link_do_di", bucket_id):
        out = _safe("link_design_controls",
                    {"source_ids": [do_id], "target_ids": [di_id],
                     "relationship": "IMPLEMENTS"},
                    bucket_id, f"{do_id}->{di_id}")
        if out is not None:
            _append_ledger({"operation": "link_do_di",
                            "bucket": bucket_id,
                            "subject": f"{do_id}->{di_id}",
                            "result": "linked",
                            "note": "IMPLEMENTS"})
            print(f"  link DO->DI ok")

    if un_id and di_id and do_id:
        ids_out[bucket_id] = {
            "un": un_id, "di": di_id, "do": do_id,
            "additional_dis": [], "files": paths,
        }


def process_special_bucket(
    bucket_id: str, paths: list[str], ids_out: dict
) -> None:
    """existing-DO-<dcid>: only update source_reference."""
    raw = bucket_id[len("existing-DO-"):]
    do_id = raw if raw.startswith("DO-") else f"DO-{raw}"
    parents = SPECIAL_DO_PARENTS.get(do_id, [])
    print(f"\n[special] {bucket_id} -> {do_id} ({len(paths)} files; "
          f"parent DIs: {parents})")

    if not _resume("update_existing_do_src", bucket_id):
        # Fetch current source_reference, merge with bucket paths.
        try:
            out = call_tool(
                "get_design_control",
                {"dc_id": do_id, "dc_type": "design-output"},
            )
            do = out.get("designOutput", {}) or {}
            current = (do.get("source_reference") or "").strip()
        except McpError as e:
            print(f"  ! could not read current src_ref: {str(e)[:120]}")
            current = ""
        for tag in (PHASE14D_TAG, "[phase13b]", "[phase14c]"):
            current = current.replace(tag, "")
        current_paths = [p.strip() for p in current.split(";") if p.strip()]
        merged = sorted(set(current_paths) | set(paths))
        new_value = build_source_reference(merged)
        out = _safe("update_design_output",
                    {"dc_id": do_id, "source_reference": new_value},
                    bucket_id, do_id)
        if out is not None:
            _append_ledger({"operation": "update_existing_do_src",
                            "bucket": bucket_id,
                            "subject": do_id,
                            "result": "ok",
                            "note": f"merged to {len(merged)} paths"})
            print(f"  src_ref ok ({len(merged)} paths)")

    ids_out[bucket_id] = {
        "un": "", "di": parents[0] if parents else "", "do": do_id,
        "additional_dis": parents[1:], "files": paths,
    }


def main() -> int:
    initialize()
    by_bucket = load_plan()
    print(f"Plan has {len(by_bucket)} buckets")

    ids_out: dict = {}
    if BUCKET_IDS.exists():
        try:
            ids_out = json.loads(BUCKET_IDS.read_text())
        except Exception:
            ids_out = {}

    for bucket_id, paths in by_bucket.items():
        if bucket_id == "unbucketed":
            continue
        if bucket_id.startswith("existing-DO-"):
            process_special_bucket(bucket_id, paths, ids_out)
        else:
            process_regular_bucket(bucket_id, paths, ids_out)
        BUCKET_IDS.write_text(
            json.dumps(ids_out, indent=2, sort_keys=True) + "\n"
        )

    print("\nDone.")
    print(f"  ledger:     {LEDGER}")
    print(f"  bucket-ids: {BUCKET_IDS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
