"""
Phase 9 - Close orphan Design Inputs (DIs without Design Outputs).

The Atlas traceability gap report lists 41 DIs without an IMPLEMENTS link
from any DO. 32 of those have raw "DI-LEO-AI-XXX" titles (a side-effect
of the Phase 2 unmatched-DI creation) and 4 have proper titles. All of
them have a real `requirement` and `acceptance_criteria` in Atlas; they
just lack a paired DO.

This script:
  1. Pulls the orphan list from get_traceability_gaps.
  2. For each orphan DI, fetches its full content from Atlas, then tries
     to match it back to a local DI YAML in design-controls/design-inputs/
     using the title (when it is a local ID like "DI-LEO-AI-009") or via
     atlas-id-mapping.csv reverse lookup.
  3. Creates a DO whose:
        - title is the local YAML's first-line title (or a derived one
          from the requirement when no YAML is found),
        - description summarises the requirement and lists the source
          files from the YAML's `technical_details.file_structure`,
        - source_reference is a semicolon-joined list of those files.
  4. Links DO -[IMPLEMENTS]-> DI.
  5. If the DI's title is the raw local ID, also updates the DI's title
     to the friendly title via update_design_input.

All work is journalled to design-controls/phase9-ledger.csv.
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
from scripts.atlas.product import PRODUCT_ID  # noqa: E402

LEDGER_PATH = DC / "phase9-ledger.csv"
LEDGER_COLS = [
    "kind",  # do | link | di_title_update | error | skip
    "atlas_di_uuid",
    "atlas_di_dcid",
    "local_id",
    "atlas_do_dcid",
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


def is_done(ledger: list[dict], di_uuid: str) -> bool:
    return any(
        r.get("atlas_di_uuid") == di_uuid
        and r.get("kind") == "do"
        and r.get("decision") in {"created", "skipped-already-linked"}
        for r in ledger
    )


def load_atlas_id_to_local() -> dict[str, str]:
    """atlas dcId -> local id (DI only)."""
    out: dict[str, str] = {}
    p = DC / "atlas-id-mapping.csv"
    if not p.exists():
        return out
    for r in csv.DictReader(p.open()):
        if (r.get("artefact_type") or "").upper() != "DI":
            continue
        a = (r.get("atlas_id") or "").strip()
        l = (r.get("local_id") or "").strip()
        if a and l:
            out[a] = l
    return out


def parse_local_yaml(local_id: str) -> dict | None:
    """Return a small dict with title/files/requirement/acs from the YAML."""
    p = DI_DIR / f"{local_id}.yaml"
    if not p.exists():
        return None
    text = p.read_text()
    title_line = ""
    for line in text.splitlines()[:5]:
        s = line.strip()
        if s.startswith("# --") and " -- " in s:
            title_line = s.split(" -- ", 2)[-1].strip()
            break
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
    return {"title": title_line, "files": files}


def fetch_di(uuid: str) -> dict | None:
    try:
        out = call_tool(
            "get_design_control",
            {"dc_id": uuid, "dc_type": "design-input"},
        )
    except Exception as e:
        print(f"  get_design_control failed for {uuid}: {e}")
        return None
    return out.get("designInput") or out


def has_existing_do(uuid: str) -> bool:
    try:
        out = call_tool(
            "get_design_control",
            {"dc_id": uuid, "dc_type": "design-input"},
        )
    except Exception:
        return False
    edges = out.get("edges") or []
    for e in edges:
        if e.get("type") == "IMPLEMENTS" and e.get("target") == uuid:
            return True
    return False


def derive_title(di: dict, local_yaml_title: str | None) -> str:
    if local_yaml_title:
        return local_yaml_title
    cur = di.get("title") or ""
    if cur and not LOCAL_ID_RE.match(cur):
        return cur
    req = di.get("requirement") or di.get("description") or ""
    if not req:
        return f"Implementation of {cur or 'design input'}"
    snippet = req.split(".")[0]
    if len(snippet) > 90:
        snippet = snippet[:87] + "..."
    return snippet


def build_do_payload(di: dict, local_id: str | None, local_yaml: dict | None) -> dict:
    title = derive_title(di, (local_yaml or {}).get("title"))
    files = (local_yaml or {}).get("files") or []
    req = di.get("requirement") or di.get("description") or ""
    desc_parts = [req.strip()]
    if files:
        desc_parts.append("\n\nImplementation files:\n- " + "\n- ".join(files))
    elif local_id:
        desc_parts.append(
            f"\n\nNote: source file list not present in local YAML "
            f"({local_id}); kept for trace continuity. Update the DI's "
            f"description with the implementation paths when known."
        )
    acs = di.get("acceptance_criteria") or []
    if isinstance(acs, str):
        acs = [a.strip() for a in acs.splitlines() if a.strip()]
    payload = {
        "product_id": PRODUCT_ID,
        "title": f"{title} (implementation)",
        "description": "".join(desc_parts),
        "acceptance_criteria": acs or None,
        "output_type": "software",
        "source_reference": "; ".join(files) if files else local_id or "",
        "software_item": local_id or di.get("dcId") or di.get("dc_id") or "",
        "safety_class": di.get("safety_class") or di.get("safetyClass") or "B",
    }
    return {k: v for k, v in payload.items() if v is not None}


def main() -> None:
    print("Phase 9 - close orphan DIs by creating DOs")
    initialize()

    gaps = call_tool("get_traceability_gaps", {"product_id": PRODUCT_ID})
    orphans = gaps.get("orphan_design_inputs") or []
    print(f"  orphan DIs reported by Atlas: {len(orphans)}")
    if not orphans:
        return

    atlas_to_local = load_atlas_id_to_local()
    print(f"  atlas->local DI mappings loaded: {len(atlas_to_local)}")

    for i, orphan in enumerate(orphans, 1):
        ledger = load_ledger()
        uuid = orphan.get("id") or orphan.get("dcId")
        title = orphan.get("title") or ""
        if is_done(ledger, uuid):
            print(f"[{i}/{len(orphans)}] {title} - already closed (ledger)")
            continue
        print(f"\n[{i}/{len(orphans)}] {title}")
        di = fetch_di(uuid)
        if di is None:
            append_ledger(
                [
                    {
                        "kind": "error",
                        "atlas_di_uuid": uuid,
                        "atlas_di_dcid": orphan.get("dcId", ""),
                        "local_id": "",
                        "atlas_do_dcid": "",
                        "decision": "failed",
                        "note": "get_design_control returned none",
                    }
                ]
            )
            continue
        atlas_dcid = di.get("dcId") or di.get("dc_id") or ""

        # Resolve local YAML if title is a local id, else use mapping CSV.
        local_id = ""
        if LOCAL_ID_RE.match(title):
            local_id = title
        else:
            local_id = atlas_to_local.get(atlas_dcid, "")
        local_yaml = parse_local_yaml(local_id) if local_id else None
        if local_yaml:
            print(
                f"  local YAML: {local_id} title='{local_yaml['title']}' "
                f"files={len(local_yaml['files'])}"
            )
        else:
            print(f"  no local YAML resolved (local_id='{local_id}')")

        if has_existing_do(uuid):
            print("  DI already has a DO link in Atlas (race); skipping create")
            append_ledger(
                [
                    {
                        "kind": "do",
                        "atlas_di_uuid": uuid,
                        "atlas_di_dcid": atlas_dcid,
                        "local_id": local_id,
                        "atlas_do_dcid": "",
                        "decision": "skipped-already-linked",
                        "note": "DO already linked at probe time",
                    }
                ]
            )
            continue

        payload = build_do_payload(di, local_id, local_yaml)
        try:
            do_out = call_tool("create_design_output", payload)
        except Exception as e:
            print(f"  create_design_output failed: {e}")
            append_ledger(
                [
                    {
                        "kind": "error",
                        "atlas_di_uuid": uuid,
                        "atlas_di_dcid": atlas_dcid,
                        "local_id": local_id,
                        "atlas_do_dcid": "",
                        "decision": "failed",
                        "note": f"create DO: {str(e)[:200]}",
                    }
                ]
            )
            continue
        do_dcid = do_out.get("dcId") or do_out.get("dc_id") or ""
        do_uuid = do_out.get("id") or ""
        append_ledger(
            [
                {
                    "kind": "do",
                    "atlas_di_uuid": uuid,
                    "atlas_di_dcid": atlas_dcid,
                    "local_id": local_id,
                    "atlas_do_dcid": do_dcid,
                    "decision": "created",
                    "note": payload["title"],
                }
            ]
        )
        try:
            call_tool(
                "link_design_controls",
                {
                    "source_ids": [do_dcid],
                    "target_ids": [atlas_dcid],
                    "relationship": "IMPLEMENTS",
                },
            )
            append_ledger(
                [
                    {
                        "kind": "link",
                        "atlas_di_uuid": uuid,
                        "atlas_di_dcid": atlas_dcid,
                        "local_id": local_id,
                        "atlas_do_dcid": do_dcid,
                        "decision": "created",
                        "note": f"DO {do_dcid} -[IMPLEMENTS]-> DI {atlas_dcid}",
                    }
                ]
            )
        except Exception as e:
            print(f"  link DO->DI failed: {e}")

        # Optional: update DI title if it was raw "DI-LEO-AI-XXX"
        if LOCAL_ID_RE.match(title) and local_yaml and local_yaml.get("title"):
            try:
                call_tool(
                    "update_design_input",
                    {
                        "dc_id": uuid,
                        "title": local_yaml["title"],
                    },
                )
                append_ledger(
                    [
                        {
                            "kind": "di_title_update",
                            "atlas_di_uuid": uuid,
                            "atlas_di_dcid": atlas_dcid,
                            "local_id": local_id,
                            "atlas_do_dcid": "",
                            "decision": "created",
                            "note": f"title -> '{local_yaml['title']}'",
                        }
                    ]
                )
            except Exception as e:
                print(f"  update_design_input title failed: {e}")
        print(f"  DO={do_dcid}")

    print("\nDone.")


if __name__ == "__main__":
    main()
