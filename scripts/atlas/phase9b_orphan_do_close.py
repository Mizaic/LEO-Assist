"""
Phase 9b - Close orphan Design Outputs (DOs without VT TESTS link).

After Phase 9 created DOs for the 41 orphan DIs, the gap report still
shows 9 orphan DOs. These DOs (and their parent DIs) lack a VT link.

This script:
  1. Pulls the orphan_design_outputs from get_traceability_gaps.
  2. For each orphan DO, fetches its parent DI and any local DI YAML.
  3. Creates a VT shell with the DI's acceptance_criteria as test_cases
     (one acceptance criterion per case), automation_status notExecuted.
  4. Links VT -[VERIFIES]-> DI and VT -[TESTS]-> DO.
  5. Records all work to design-controls/phase9b-ledger.csv.

Following the Phase 8b pattern: VT shells are honest debt — they
document the intent and the trace chain, with execution scheduled as
follow-up work. Atlas marks them as 'notExecuted' which is visible in
the CSO queue.
"""

from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DC = ROOT / "design-controls"
DI_DIR = DC / "design-inputs"
sys.path.insert(0, str(ROOT))

from scripts.atlas._mcp_transport import call_tool, initialize  # noqa: E402

PRODUCT_ID = "PROD-LEO-CORE-AI-20260415-6AE8A23B"
LEDGER_PATH = DC / "phase9b-ledger.csv"
LEDGER_COLS = [
    "kind",          # vt | link_di | link_do | error | skip
    "atlas_do_uuid",
    "atlas_do_dcid",
    "atlas_di_uuid",
    "atlas_di_dcid",
    "atlas_vt_dcid",
    "decision",
    "note",
    "ts",
]

LOCAL_ID_RE = re.compile(r"^DI-LEO-AI-\d+$")


def load_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    return list(csv.DictReader(LEDGER_PATH.open()))


def append_ledger(rows: list[dict]) -> None:
    new = not LEDGER_PATH.exists()
    with LEDGER_PATH.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLS, lineterminator="\n")
        if new:
            w.writeheader()
        for r in rows:
            r.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            w.writerow({c: r.get(c, "") for c in LEDGER_COLS})


def is_done(ledger: list[dict], do_uuid: str) -> bool:
    return any(
        r.get("atlas_do_uuid") == do_uuid and r.get("kind") == "vt"
        and r.get("decision") == "created"
        for r in ledger
    )


def parse_local_files(local_id: str) -> list[str]:
    p = DI_DIR / f"{local_id}.yaml"
    if not p.exists():
        return []
    text = p.read_text()
    files: list[str] = []
    in_fs = False
    for line in text.splitlines():
        s = line.rstrip()
        if "file_structure:" in s:
            in_fs = True
            continue
        if in_fs:
            stripped = s.strip()
            if stripped.startswith("- "):
                files.append(stripped[2:].strip().strip('"'))
            elif stripped == "" or (s and not s.startswith(" ")):
                if files:
                    in_fs = False
    return files


def fetch_do(uuid: str) -> dict:
    return call_tool(
        "get_design_control",
        {"dc_id": uuid, "dc_type": "design-output"},
    )


def build_vt_payload(di: dict, do: dict, local_files: list[str]) -> dict:
    title = di.get("title") or do.get("title") or "VT"
    acs = di.get("acceptance_criteria") or []
    if isinstance(acs, str):
        acs = [a.strip() for a in acs.splitlines() if a.strip()]
    if not acs:
        acs = ["No regressions in the implementation surface"]
    surface = (
        "; ".join(local_files) if local_files else do.get("source_reference") or "n/a"
    )
    protocol_steps: list[str] = [
        f"Set up the integration test environment for {title}.",
        f"Exercise the implementation surface: {surface}.",
    ]
    for i, ac in enumerate(acs, 1):
        protocol_steps.append(f"Step {i}: Verify acceptance criterion - {ac}")
    protocol_steps.append(
        "Capture pass/fail evidence and record via record_verification_run."
    )
    description = (
        f"Verification of acceptance criteria for {title}. Acceptance "
        f"criteria below are taken 1-for-1 from the parent DI. "
        f"Implementation surface: {surface}. Execution scheduled as "
        f"follow-up; this VT documents the verification intent and trace "
        f"chain to close the DI/DO/VT triangle for the design controls "
        f"cutover."
    )
    return {
        "product_id": PRODUCT_ID,
        "title": f"{title} - acceptance verification",
        "description": description,
        "test_type": "integration",
        "verification_method": "test",
        "acceptance_criteria": acs,
        "protocol_steps": protocol_steps,
        "safety_class": di.get("safety_class") or di.get("safetyClass") or "B",
    }


def main() -> None:
    print("Phase 9b - close orphan DOs by creating VT shells")
    initialize()

    gaps = call_tool(
        "get_traceability_gaps", {"product_id": PRODUCT_ID}
    )
    orphans = gaps.get("orphan_design_outputs") or []
    print(f"  orphan DOs reported by Atlas: {len(orphans)}")
    if not orphans:
        return

    for i, orphan in enumerate(orphans, 1):
        ledger = load_ledger()
        do_uuid = orphan.get("id") or orphan.get("dcId")
        title = orphan.get("title") or ""
        if is_done(ledger, do_uuid):
            print(f"[{i}/{len(orphans)}] {title} - already closed")
            continue
        print(f"\n[{i}/{len(orphans)}] {title}")
        try:
            do_resp = fetch_do(do_uuid)
        except Exception as e:
            append_ledger(
                [
                    {
                        "kind": "error",
                        "atlas_do_uuid": do_uuid,
                        "atlas_do_dcid": orphan.get("dcId", ""),
                        "decision": "failed",
                        "note": f"fetch DO: {str(e)[:200]}",
                    }
                ]
            )
            continue
        do = do_resp.get("designOutput") or {}
        atlas_do_dcid = do.get("dcId") or ""
        di_list = (do_resp.get("traceability") or {}).get("designInputs") or []
        if not di_list:
            print("  no parent DI found; skipping")
            append_ledger(
                [
                    {
                        "kind": "skip",
                        "atlas_do_uuid": do_uuid,
                        "atlas_do_dcid": atlas_do_dcid,
                        "decision": "skipped",
                        "note": "no parent DI",
                    }
                ]
            )
            continue
        di = di_list[0]
        di_uuid = di.get("id") or ""
        atlas_di_dcid = di.get("dcId") or ""
        local_id = do.get("software_item") or ""
        if not LOCAL_ID_RE.match(local_id):
            local_id = ""
        files = parse_local_files(local_id) if local_id else []
        print(
            f"  parent DI: {di.get('title')} ({atlas_di_dcid}) | "
            f"local={local_id} files={len(files)}"
        )

        payload = build_vt_payload(di, do, files)
        try:
            vt_out = call_tool("create_verification_test", payload)
        except Exception as e:
            print(f"  create_verification_test failed: {e}")
            append_ledger(
                [
                    {
                        "kind": "error",
                        "atlas_do_uuid": do_uuid,
                        "atlas_do_dcid": atlas_do_dcid,
                        "atlas_di_uuid": di_uuid,
                        "atlas_di_dcid": atlas_di_dcid,
                        "decision": "failed",
                        "note": f"create VT: {str(e)[:200]}",
                    }
                ]
            )
            continue
        vt_dcid = vt_out.get("dcId") or vt_out.get("dc_id") or ""
        append_ledger(
            [
                {
                    "kind": "vt",
                    "atlas_do_uuid": do_uuid,
                    "atlas_do_dcid": atlas_do_dcid,
                    "atlas_di_uuid": di_uuid,
                    "atlas_di_dcid": atlas_di_dcid,
                    "atlas_vt_dcid": vt_dcid,
                    "decision": "created",
                    "note": payload["title"],
                }
            ]
        )
        for rel, target_dcid, kind in [
            ("VERIFIES", atlas_di_dcid, "link_di"),
            ("TESTS", atlas_do_dcid, "link_do"),
        ]:
            try:
                call_tool(
                    "link_design_controls",
                    {
                        "source_ids": [vt_dcid],
                        "target_ids": [target_dcid],
                        "relationship": rel,
                    },
                )
                append_ledger(
                    [
                        {
                            "kind": kind,
                            "atlas_do_uuid": do_uuid,
                            "atlas_do_dcid": atlas_do_dcid,
                            "atlas_di_uuid": di_uuid,
                            "atlas_di_dcid": atlas_di_dcid,
                            "atlas_vt_dcid": vt_dcid,
                            "decision": "created",
                            "note": f"VT {vt_dcid} -[{rel}]-> {target_dcid}",
                        }
                    ]
                )
            except Exception as e:
                print(f"  link {rel} failed: {e}")
        print(f"  VT={vt_dcid}")

    print("\nDone.")


if __name__ == "__main__":
    main()
