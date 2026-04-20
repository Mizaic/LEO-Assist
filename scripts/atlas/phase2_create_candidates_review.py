"""Phase 2 -- create-candidate human review.

For each local UN/DI flagged as 'create' by phase2_un_di_triage, list the
top-10 Atlas candidates by several scoring strategies so a human (or the
agent) can confirm 'really new' vs 'late-bind to existing'.

The Atlas snapshot lacks acceptance_criteria, so we ALSO fetch Atlas ACs
per top-30 candidate (cached) and re-score with AC-aware text.

Output:
  design-controls/phase8-create-candidates-review.md
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path("/Users/robsmith/Documents/github/LEO-AI-CORE")
sys.path.insert(0, str(REPO / "scripts" / "atlas"))
import _mcp_transport as mcp  # noqa: E402
from phase2_un_di_triage import (  # noqa: E402
    HUMAN_REVIEW_THRESHOLD,
    REMAP_THRESHOLD,
    _jaccard,
    _norm_text,
    _sim,
    _tokens,
    load_atlas_nodes,
    load_local_di,
    load_local_un,
    parse_gap_section,
)
from difflib import SequenceMatcher

CACHE_PATH = REPO / "scripts" / "atlas" / ".phase2_atlas_full_cache.json"
REVIEW_MD = REPO / "design-controls" / "phase8-create-candidates-review.md"

CREATE_UNS_LOWER_BOUND = HUMAN_REVIEW_THRESHOLD  # < 0.40 = create or human-review


def _query_text(local: dict[str, Any], kind: str) -> str:
    parts = [local.get("title", "")]
    if kind == "UN":
        parts.append(local.get("description", ""))
    else:
        parts.append(local.get("requirement", ""))
    parts.extend(local.get("acceptance_criteria") or [])
    return " ".join(p for p in parts if p)


def _atlas_text(node: dict[str, Any], full: dict[str, Any] | None) -> str:
    parts = [node.get("title", ""), node.get("description", "") or ""]
    if full:
        # acceptance_criteria comes back as list-of-strings or dicts
        for ac in full.get("acceptance_criteria") or []:
            if isinstance(ac, str):
                parts.append(ac)
            elif isinstance(ac, dict):
                parts.append(ac.get("description") or ac.get("spec") or "")
    return " ".join(p for p in parts if p)


def _composite_score(local_q: str, atlas_t: str) -> dict[str, float]:
    sm = SequenceMatcher(None, _norm_text(local_q).lower(),
                         _norm_text(atlas_t).lower()).ratio()
    jac = _jaccard(_tokens(local_q), _tokens(atlas_t))
    return {"seq": sm, "jac": jac, "max": max(sm, jac)}


def fetch_atlas_full(dc_id: str, cache: dict[str, Any]) -> dict[str, Any] | None:
    if dc_id in cache:
        return cache[dc_id]
    try:
        res = mcp.call_tool("get_design_control", {"dc_id": dc_id})
    except mcp.McpError as e:
        cache[dc_id] = {"_error": str(e)[:120]}
        return cache[dc_id]
    # response may wrap in userNeed/designInput
    inner = (
        res.get("userNeed")
        or res.get("user_need")
        or res.get("designInput")
        or res.get("design_input")
        or res
    )
    cache[dc_id] = inner
    return inner


def review_local(local_id: str, kind: str, atlas_nodes: list[dict[str, Any]],
                 cache: dict[str, Any]) -> dict[str, Any]:
    if kind == "UN":
        local = load_local_un(local_id)
    else:
        local = load_local_di(local_id)
    if not local:
        return {"local_id": local_id, "error": "yaml missing"}

    qry = _query_text(local, kind)

    # Stage 1: rank by snapshot text
    ranked: list[tuple[dict[str, Any], dict[str, float]]] = []
    for n in atlas_nodes:
        text = _atlas_text(n, None)
        ranked.append((n, _composite_score(qry, text)))
    ranked.sort(key=lambda r: r[1]["max"], reverse=True)
    top30 = ranked[:30]

    # Stage 2: fetch ACs for top-30 and re-score
    re_ranked: list[tuple[dict[str, Any], dict[str, float]]] = []
    for node, _ in top30:
        full = fetch_atlas_full(node["dcId"], cache)
        text = _atlas_text(node, full if isinstance(full, dict) and "_error" not in full else None)
        re_ranked.append((node, _composite_score(qry, text)))
        # be polite to MCP
        time.sleep(0.05)
    re_ranked.sort(key=lambda r: r[1]["max"], reverse=True)
    top10 = re_ranked[:10]

    return {
        "local_id": local_id,
        "kind": kind,
        "local_title": local.get("title", ""),
        "local_summary": (local.get("description") or local.get("requirement", ""))[:200],
        "candidates": [
            {
                "dcId": n["dcId"],
                "title": n.get("title", ""),
                "desc": (n.get("description") or "")[:160],
                "seq": round(s["seq"], 3),
                "jac": round(s["jac"], 3),
                "max": round(s["max"], 3),
            }
            for n, s in top10
        ],
    }


def load_cache() -> dict[str, Any]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache: dict[str, Any]) -> None:
    CACHE_PATH.write_text(json.dumps(cache, sort_keys=True, indent=2))


def find_create_candidates() -> tuple[list[str], list[str]]:
    """Re-run triage logic offline to identify 'create' candidates."""
    from phase2_un_di_triage import best_match
    un_creates: list[str] = []
    di_creates: list[str] = []

    atlas_uns = load_atlas_nodes("user-need")
    atlas_dis = load_atlas_nodes("design-input")

    for lid in parse_gap_section("UN"):
        loc = load_local_un(lid)
        if not loc:
            continue
        q = " ".join(filter(None, [loc["title"], loc["description"]]))
        _, score = best_match(q, atlas_uns)
        if score < HUMAN_REVIEW_THRESHOLD:
            un_creates.append(lid)

    for lid in parse_gap_section("DI"):
        loc = load_local_di(lid)
        if not loc:
            continue
        q = " ".join(filter(None, [loc["title"], loc["requirement"]]))
        _, score = best_match(q, atlas_dis)
        if score < HUMAN_REVIEW_THRESHOLD:
            di_creates.append(lid)
    return un_creates, di_creates


def main() -> int:
    print("Identifying 'create' candidates from Phase 2 dry-run ...")
    un_creates, di_creates = find_create_candidates()
    print(f"  UN creates: {len(un_creates)}  DI creates: {len(di_creates)}")
    print(f"  UNs: {un_creates}")
    print(f"  DIs: {di_creates}")

    print("\nInitialising MCP session ...")
    mcp.initialize()

    print("\nLoading Atlas snapshot ...")
    atlas_uns = load_atlas_nodes("user-need")
    atlas_dis = load_atlas_nodes("design-input")
    cache = load_cache()

    reports: list[dict[str, Any]] = []
    for i, lid in enumerate(un_creates, start=1):
        print(f"  UN {i}/{len(un_creates)} {lid} ...")
        reports.append(review_local(lid, "UN", atlas_uns, cache))
        save_cache(cache)
    for i, lid in enumerate(di_creates, start=1):
        print(f"  DI {i}/{len(di_creates)} {lid} ...")
        reports.append(review_local(lid, "DI", atlas_dis, cache))
        save_cache(cache)

    md = ["# Phase 2 -- Create-Candidate Human Review", ""]
    md.append(f"Total local items needing review: {len(reports)}")
    md.append("")
    md.append("For each 'create' candidate, the top-10 Atlas candidates "
              "(re-scored after fetching Atlas ACs) are listed.  ")
    md.append("Assign one of: REMAP -> <atlas dc_id>  |  CREATE  |  SKIP")
    md.append("")
    for r in reports:
        if "error" in r:
            md.append(f"## {r['local_id']} -- ERROR {r['error']}")
            continue
        md.append(f"## {r['kind']} {r['local_id']}")
        md.append(f"**Title**: {r['local_title']}")
        md.append("")
        md.append(f"**Summary**: {r['local_summary']}")
        md.append("")
        md.append("| Atlas DC | Title | seq | jac | max |")
        md.append("|---|---|---|---|---|")
        for c in r["candidates"]:
            t = c["title"][:80].replace("|", "\\|")
            md.append(f"| {c['dcId']} | {t} | {c['seq']} | {c['jac']} | {c['max']} |")
        md.append("")
        md.append("**DECISION**: _to fill_")
        md.append("")
    REVIEW_MD.write_text("\n".join(md) + "\n")
    print(f"\nWrote: {REVIEW_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
