"""Build the Atlas DI inventory CSV from the trace-matrix JSON dump.

Reads the traceability-matrix JSON that get_traceability_matrix wrote to
agent-tools, and emits:
  - design-controls/audits/di-inventory.csv
  - design-controls/audits/un-index.json (UN -> [DI IDs] map)
  - design-controls/audits/atlas-summary.md (batch counts summary)
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AUDITS = REPO / "design-controls" / "audits"
TRACE_JSON = Path(
    "/Users/robsmith/.cursor/projects/"
    "Users-robsmith-Documents-github-LEO-AI-CORE/"
    "agent-tools/c304c425-38c2-4f12-88ba-894790998bc0.txt"
)


def load_trace() -> dict:
    text = TRACE_JSON.read_text(encoding="utf-8")
    return json.loads(text)


def index_nodes(trace: dict) -> dict[str, dict]:
    nodes: dict[str, dict] = {}
    for node in trace.get("nodes", []):
        dc_id = node.get("dcId") or node.get("dc_id")
        if dc_id:
            nodes[dc_id] = node
    return nodes


def build_un_di_map(trace: dict) -> dict[str, list[str]]:
    """Walk the rows block to assemble UN -> [DI IDs]."""
    un_to_dis: dict[str, list[str]] = defaultdict(list)
    for row in trace.get("rows", []):
        un_node = row.get("userNeed") or {}
        un_id = un_node.get("dcId")
        if not un_id or not un_id.startswith("UN-"):
            continue
        dis = row.get("designInputs", []) or []
        for di in dis:
            di_id = di.get("dcId")
            if di_id and di_id.startswith("DI-") and di_id not in un_to_dis[un_id]:
                un_to_dis[un_id].append(di_id)
    return dict(un_to_dis)


def write_un_index(un_to_dis: dict[str, list[str]], nodes: dict[str, dict]) -> None:
    payload = {}
    for un_id, di_list in sorted(un_to_dis.items()):
        un_node = nodes.get(un_id, {})
        payload[un_id] = {
            "title": un_node.get("title", ""),
            "di_count": len(di_list),
            "dis": di_list,
        }
    (AUDITS / "un-index.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _input_type(di_node: dict) -> str:
    return di_node.get("inputType") or di_node.get("input_type") or ""


def _safety_class(di_node: dict) -> str:
    return di_node.get("safetyClass") or di_node.get("safety_class") or ""


def build_di_rows(
    nodes: dict[str, dict], un_to_dis: dict[str, list[str]]
) -> list[dict]:
    di_to_un: dict[str, str] = {}
    for un_id, dis in un_to_dis.items():
        for di_id in dis:
            di_to_un.setdefault(di_id, un_id)

    rows: list[dict] = []
    for dc_id, node in nodes.items():
        if not dc_id.startswith("DI-"):
            continue
        parent_un = di_to_un.get(dc_id, "")
        rows.append(
            {
                "atlas_di_id": dc_id,
                "atlas_di_title": node.get("title", ""),
                "parent_un_id": parent_un,
                "safety_class": _safety_class(node),
                "input_type": _input_type(node),
                "proposed_batch": "",
                "verdict": "",
                "implementation_files": "",
                "proposed_DO_title": "",
                "notes": "",
            }
        )
    rows.sort(key=lambda r: r["atlas_di_id"])
    return rows


def write_di_csv(rows: list[dict]) -> None:
    path = AUDITS / "di-inventory.csv"
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(un_to_dis: dict[str, list[str]], nodes: dict[str, dict]) -> None:
    lines: list[str] = [
        "# Atlas DI inventory summary",
        "",
        f"- Total UNs with DIs: {len(un_to_dis)}",
        f"- Total DIs: {sum(len(v) for v in un_to_dis.values())}",
        "",
        "## UNs sorted by DI count",
        "",
        "| UN ID | DI count | Title |",
        "|---|---|---|",
    ]
    ordered = sorted(un_to_dis.items(), key=lambda kv: -len(kv[1]))
    for un_id, dis in ordered:
        title = nodes.get(un_id, {}).get("title", "")
        if len(title) > 110:
            title = title[:107] + "..."
        lines.append(f"| {un_id} | {len(dis)} | {title} |")
    (AUDITS / "atlas-summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    AUDITS.mkdir(parents=True, exist_ok=True)
    trace = load_trace()
    nodes = index_nodes(trace)
    un_to_dis = build_un_di_map(trace)
    write_un_index(un_to_dis, nodes)
    rows = build_di_rows(nodes, un_to_dis)
    write_di_csv(rows)
    write_summary(un_to_dis, nodes)
    print(
        f"UNs: {len(un_to_dis)} | "
        f"DIs in inventory: {len(rows)} | "
        f"UN->DI edges: {sum(len(v) for v in un_to_dis.values())}"
    )


if __name__ == "__main__":
    main()
