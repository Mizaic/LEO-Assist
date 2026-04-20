"""Phase 2 -- low-confidence DI review.

Generates a human-review report for the 39 DIs that got a fuzzy match
with similarity 0.18-0.30.  For each, lists:
  - the currently proposed Atlas DI (from atlas-id-mapping.csv)
  - top-5 alternative Atlas DI candidates (re-scored with title +
    description + ACs from the Atlas snapshot + on-demand fetch)

After human assignment in phase2_decisions.json (decision: remap |
create | confirm-existing-mapping), re-run phase2_un_di_triage.py
and a follow-up extension to the create flow for these DIs.

Output:
  design-controls/phase8-low-confidence-di-review.md
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path("/Users/robsmith/Documents/github/LEO-AI-CORE")
sys.path.insert(0, str(REPO / "scripts" / "atlas"))
import _mcp_transport as mcp  # noqa: E402
from phase2_un_di_triage import (  # noqa: E402
    _jaccard,
    _norm_text,
    _tokens,
    load_atlas_nodes,
    load_local_di,
)
from difflib import SequenceMatcher

MAPPING_CSV = REPO / "design-controls" / "atlas-id-mapping.csv"
CACHE_PATH = REPO / "scripts" / "atlas" / ".phase2_atlas_full_cache.json"
REVIEW_MD = REPO / "design-controls" / "phase8-low-confidence-di-review.md"


def load_low_confidence_dis() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with MAPPING_CSV.open() as f:
        for row in csv.DictReader(f):
            if (
                row.get("artefact_type") == "DI"
                and row.get("match_type") == "low-confidence"
            ):
                out.append(row)
    return out


def _query_text(local: dict[str, Any]) -> str:
    parts = [local.get("title", ""), local.get("requirement", "")]
    parts.extend(local.get("acceptance_criteria") or [])
    return " ".join(p for p in parts if p)


def _atlas_text(node: dict[str, Any], full: dict[str, Any] | None) -> str:
    parts = [node.get("title", ""), node.get("description", "") or ""]
    if full and "_error" not in full:
        for ac in full.get("acceptance_criteria") or []:
            if isinstance(ac, str):
                parts.append(ac)
            elif isinstance(ac, dict):
                parts.append(ac.get("description") or ac.get("spec") or "")
    return " ".join(p for p in parts if p)


def _composite(local_q: str, atlas_t: str) -> dict[str, float]:
    sm = SequenceMatcher(
        None, _norm_text(local_q).lower(), _norm_text(atlas_t).lower()
    ).ratio()
    jac = _jaccard(_tokens(local_q), _tokens(atlas_t))
    return {"seq": sm, "jac": jac, "max": max(sm, jac)}


def fetch_full(dc_id: str, cache: dict[str, Any]) -> dict[str, Any]:
    """Cache-only lookup. Caller falls back to title+description if missing."""
    val = cache.get(dc_id)
    if val and "_error" not in val:
        return val
    return {"_error": "not in cache"}


def main() -> int:
    rows = load_low_confidence_dis()
    print(f"Loaded {len(rows)} low-confidence DIs from CSV")
    atlas_dis = load_atlas_nodes("design-input")
    cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
    ok_in_cache = sum(1 for v in cache.values() if isinstance(v, dict) and "_error" not in v)
    print(f"Atlas DI cache: {ok_in_cache}/{len(atlas_dis)} entries with ACs")

    out_blocks: list[str] = []
    for i, row in enumerate(rows, start=1):
        lid = row["local_id"]
        proposed = row.get("atlas_id") or ""
        proposed_title = row.get("atlas_title", "")
        sim_old = row.get("similarity", "")
        local = load_local_di(lid)
        if not local:
            out_blocks.append(f"## {lid} -- ERROR local YAML missing")
            continue
        qry = _query_text(local)
        # Stage 1 ranking by snapshot text only
        ranked = sorted(
            atlas_dis,
            key=lambda n: _composite(qry, _atlas_text(n, None))["max"],
            reverse=True,
        )[:15]
        # Stage 2 use cached ACs (fall back to snapshot text if not cached)
        re_ranked: list[tuple[dict[str, Any], dict[str, float]]] = []
        for node in ranked:
            full = fetch_full(node["dcId"], cache)
            text = _atlas_text(node, full)
            re_ranked.append((node, _composite(qry, text)))
        prop_full = fetch_full(proposed, cache) if proposed else None
        prop_score = (
            _composite(
                qry,
                _atlas_text(
                    next(
                        (n for n in atlas_dis if n.get("dcId") == proposed), {}
                    ),
                    prop_full,
                ),
            )
            if proposed
            else {"seq": 0.0, "jac": 0.0, "max": 0.0}
        )
        re_ranked.sort(key=lambda r: r[1]["max"], reverse=True)
        top5 = re_ranked[:5]
        print(f"  [{i}/{len(rows)}] {lid} proposed={proposed} re_score={prop_score['max']:.2f} top1={top5[0][0]['dcId'] if top5 else '-'} ({top5[0][1]['max']:.2f})")

        block = [f"## {lid}"]
        block.append(f"**Local title**: {local.get('title') or '(blank)'}")
        block.append(
            f"**Local requirement**: {(local.get('requirement') or '')[:300]}"
        )
        block.append("")
        block.append(
            f"**Currently proposed**: `{proposed}` -- {proposed_title[:90]} "
            f"(old sim={sim_old}, new max={prop_score['max']:.3f})"
        )
        block.append("")
        block.append("**Top-5 alternatives (after AC fetch)**:")
        block.append("")
        block.append("| dcId | Title | seq | jac | max |")
        block.append("|---|---|---|---|---|")
        for n, s in top5:
            t = n.get("title", "")[:80].replace("|", "\\|")
            block.append(
                f"| {n['dcId']} | {t} | {s['seq']:.3f} | {s['jac']:.3f} | {s['max']:.3f} |"
            )
        block.append("")
        block.append("**DECISION**: _confirm | remap=<dcId> | create | skip_")
        block.append("")
        out_blocks.append("\n".join(block))

    md = ["# Phase 2 -- Low-confidence DI Review", ""]
    md.append(f"Total: {len(rows)}")
    md.append("")
    md.extend(out_blocks)
    REVIEW_MD.write_text("\n".join(md) + "\n")
    print(f"\nWrote: {REVIEW_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
