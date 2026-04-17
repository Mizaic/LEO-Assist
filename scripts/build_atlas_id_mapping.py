"""Build local-to-Atlas ID mapping table.

Loads every local design-controls YAML (UN, DI, DO, VT, VAL) and matches it
against the Atlas traceability matrix snapshot using fuzzy text similarity
on titles plus requirement / description text.

Outputs design-controls/atlas-id-mapping.csv with columns:
    artefact_type, local_id, local_title, atlas_id, atlas_title,
    match_type, similarity, parent_un (Atlas), notes

Run: python3 scripts/build_atlas_id_mapping.py
"""

from __future__ import annotations

import csv
import glob
import json
import os
from difflib import SequenceMatcher
from typing import Any

import yaml

REPO = "/Users/robsmith/Documents/github/LEO-AI-CORE"
ATLAS_MATRIX = (
    "/Users/robsmith/.cursor/projects/"
    "Users-robsmith-Documents-github-LEO-AI-CORE/"
    "agent-tools/e04c1136-be2a-48dc-a30b-731a90163ab8.txt"
)
OUTPUT = f"{REPO}/design-controls/atlas-id-mapping.csv"

EXACT = 0.55
FUZZY = 0.25
LOW_CONFIDENCE = 0.18

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at",
    "by", "with", "is", "are", "be", "been", "shall", "must", "should",
    "system", "user", "users", "need", "needs", "as", "so", "that",
    "their", "this", "from", "into", "via", "any", "all", "when",
    "able", "can", "will", "leo", "ai", "leo-ai", "using", "use",
}


def _norm(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(str(text).lower().split())


def _tokens(text: str | None) -> set[str]:
    norm = _norm(text)
    out: set[str] = set()
    for raw in norm.replace("/", " ").replace("-", " ").split():
        tok = "".join(ch for ch in raw if ch.isalnum())
        if not tok or tok in STOPWORDS or len(tok) < 3:
            continue
        out.add(tok)
    return out


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _sim(a: str, b: str) -> float:
    seq = SequenceMatcher(None, _norm(a), _norm(b)).ratio()
    ovl = _overlap(_tokens(a), _tokens(b))
    return max(seq, ovl)


def _classify(score: float) -> str:
    if score >= EXACT:
        return "exact"
    if score >= FUZZY:
        return "fuzzy"
    if score >= LOW_CONFIDENCE:
        return "low-confidence"
    return "unmatched"


def load_local_yaml(pattern: str) -> list[dict[str, Any]]:
    """Load every YAML matching pattern. Each file may be a list or a dict."""
    items: list[dict[str, Any]] = []
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path) as f:
                doc = yaml.safe_load(f)
        except Exception as exc:
            print(f"WARN: skip {path}: {exc}")
            continue
        if isinstance(doc, list):
            for item in doc:
                if isinstance(item, dict) and "id" in item:
                    item["_source_path"] = path
                    items.append(item)
        elif isinstance(doc, dict) and "id" in doc:
            doc["_source_path"] = path
            items.append(doc)
    return items


def load_atlas_matrix() -> dict[str, list[dict[str, Any]]]:
    """Bucket Atlas nodes by dcType."""
    with open(ATLAS_MATRIX) as f:
        data = json.load(f)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for node in data["nodes"]:
        buckets.setdefault(node["dcType"], []).append(node)
    return buckets


def atlas_un_for_di(di_node: dict[str, Any], links: list[dict[str, Any]],
                    nodes_by_id: dict[str, dict[str, Any]]) -> str:
    """Resolve parent UN ID for an Atlas DI by walking HAS_DESIGN_INPUT."""
    di_id = di_node["id"]
    for link in links:
        if link["relationship"] != "HAS_DESIGN_INPUT":
            continue
        if link["target"] != di_id:
            continue
        src = nodes_by_id.get(link["source"])
        if src and src.get("dcType") == "user-need":
            return src.get("dcId", "")
    return ""


def best_match(query: str, candidates: list[dict[str, Any]],
               atlas_text_fn=None) -> tuple[dict[str, Any] | None, float]:
    """Return the candidate with highest similarity to query.

    By default compares query against the candidate's title + description.
    """
    best: tuple[dict[str, Any] | None, float] = (None, 0.0)
    qn = _norm(query)
    if not qn:
        return best
    for cand in candidates:
        if atlas_text_fn:
            text = atlas_text_fn(cand)
        else:
            text = " ".join(filter(None, [
                cand.get("title", ""),
                cand.get("description", ""),
            ]))
        score = _sim(qn, text)
        if score > best[1]:
            best = (cand, score)
    return best


def local_un_text(item: dict[str, Any]) -> str:
    return " ".join(filter(None, [
        item.get("title", ""),
        item.get("description", ""),
    ]))


def local_di_text(item: dict[str, Any]) -> str:
    return " ".join(filter(None, [
        item.get("title") or "",
        item.get("requirement", "") or "",
    ]))


def local_do_text(item: dict[str, Any]) -> str:
    spec = item.get("specification", {}) or {}
    return " ".join(filter(None, [
        spec.get("title") or item.get("title") or "",
        spec.get("description") or "",
    ]))


def local_vt_text(item: dict[str, Any]) -> str:
    meta = item.get("metadata", {}) or {}
    return " ".join(filter(None, [
        meta.get("title") or item.get("title") or "",
        meta.get("description") or "",
    ]))


def local_val_text(item: dict[str, Any]) -> str:
    meta = item.get("metadata", {}) or {}
    return " ".join(filter(None, [
        meta.get("title") or item.get("title") or "",
        meta.get("description") or "",
    ]))


def emit_row(rows: list[dict[str, str]], artefact: str, local: dict[str, Any],
             local_title: str, atlas: dict[str, Any] | None,
             score: float, parent_un: str = "", notes: str = "") -> None:
    rows.append({
        "artefact_type": artefact,
        "local_id": local.get("id", ""),
        "local_title": (local_title or "")[:160],
        "atlas_id": (atlas or {}).get("dcId", ""),
        "atlas_title": ((atlas or {}).get("title", "") or "")[:160],
        "match_type": _classify(score),
        "similarity": f"{score:.3f}",
        "parent_un_atlas": parent_un,
        "notes": notes,
    })


def map_uns(local: list[dict[str, Any]], atlas: list[dict[str, Any]],
            rows: list[dict[str, str]]) -> dict[str, str]:
    """Greedy 1:1 assignment of local UNs to Atlas UNs by global best score."""
    pairs: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for item in local:
        query = local_un_text(item)
        for cand in atlas:
            text = cand.get("title", "") + " " + cand.get("description", "")
            pairs.append((_sim(query, text), item, cand))
    pairs.sort(key=lambda x: x[0], reverse=True)
    used_local: set[str] = set()
    used_atlas: set[str] = set()
    matches: dict[str, tuple[dict[str, Any], dict[str, Any], float]] = {}
    for score, item, cand in pairs:
        if item["id"] in used_local or cand["dcId"] in used_atlas:
            continue
        if score < LOW_CONFIDENCE:
            continue
        matches[item["id"]] = (item, cand, score)
        used_local.add(item["id"])
        used_atlas.add(cand["dcId"])
    mapping: dict[str, str] = {}
    for item in local:
        title = item.get("title", "") or ""
        if item["id"] in matches:
            _, cand, score = matches[item["id"]]
            mapping[item["id"]] = cand["dcId"]
            emit_row(rows, "UN", item, title, cand, score)
        else:
            emit_row(rows, "UN", item, title, None, 0.0,
                     notes="local UN with no Atlas counterpart - "
                           "below confidence threshold")
    return mapping


def map_dis(local: list[dict[str, Any]], atlas: list[dict[str, Any]],
            un_mapping: dict[str, str], links: list[dict[str, Any]],
            nodes_by_id: dict[str, dict[str, Any]],
            rows: list[dict[str, str]]) -> dict[str, str]:
    """Map local DIs to Atlas DIs preferring matches under the same parent UN."""
    di_parent: dict[str, str] = {
        cand["dcId"]: atlas_un_for_di(cand, links, nodes_by_id)
        for cand in atlas
    }
    pairs: list[tuple[float, dict[str, Any], dict[str, Any], bool]] = []
    for item in local:
        query = local_di_text(item)
        derived = item.get("derived_from") or []
        atlas_un_ids = {un_mapping[u] for u in derived if u in un_mapping}
        for cand in atlas:
            text = cand.get("title", "") + " " + cand.get("description", "")
            same_parent = (
                bool(atlas_un_ids) and di_parent.get(cand["dcId"]) in atlas_un_ids
            )
            score = _sim(query, text)
            if same_parent:
                score = min(1.0, score + 0.10)
            pairs.append((score, item, cand, same_parent))
    pairs.sort(key=lambda x: x[0], reverse=True)
    used_local: set[str] = set()
    used_atlas: set[str] = set()
    matches: dict[str, tuple[dict[str, Any], dict[str, Any], float]] = {}
    for score, item, cand, _ in pairs:
        if item["id"] in used_local or cand["dcId"] in used_atlas:
            continue
        if score < LOW_CONFIDENCE:
            continue
        matches[item["id"]] = (item, cand, score)
        used_local.add(item["id"])
        used_atlas.add(cand["dcId"])
    mapping: dict[str, str] = {}
    for item in local:
        local_title = item.get("title") or item.get("requirement", "") or ""
        if item["id"] in matches:
            _, cand, score = matches[item["id"]]
            mapping[item["id"]] = cand["dcId"]
            emit_row(rows, "DI", item, local_title, cand, score,
                     parent_un=di_parent.get(cand["dcId"], ""))
        else:
            emit_row(rows, "DI", item, local_title, None, 0.0,
                     notes="local DI with no Atlas counterpart - "
                           "candidate to create")
    return mapping


def map_dos_and_vts(local: list[dict[str, Any]],
                    artefact_type: str,
                    text_fn,
                    di_mapping: dict[str, str],
                    rows: list[dict[str, str]]) -> None:
    """Local DOs/VTs are migrated to Atlas. Emit one row per local artefact."""
    for item in local:
        if artefact_type == "DO":
            spec = item.get("specification", {}) or {}
            short = spec.get("title") or item.get("title", "") or ""
        else:
            meta = item.get("metadata", {}) or {}
            short = meta.get("title") or item.get("title", "") or ""
        _ = text_fn(item)
        trace = item.get("traceability", {}) or {}
        local_dis = trace.get("design_inputs", []) or []
        atlas_dis = [di_mapping[d] for d in local_dis if d in di_mapping]
        unmatched_dis = [d for d in local_dis if d not in di_mapping]
        notes = "MIGRATE: create new fine-grained Atlas " + artefact_type
        if atlas_dis:
            notes += f"; trace to Atlas DIs {','.join(atlas_dis)}"
        if unmatched_dis:
            notes += f"; UNMATCHED local DIs {','.join(unmatched_dis)}"
        emit_row(rows, artefact_type, item, short, None, 0.0,
                 parent_un="", notes=notes)


def map_vals(local: list[dict[str, Any]], atlas: list[dict[str, Any]],
             rows: list[dict[str, str]]) -> None:
    """Greedy 1:1 assignment of local VALs to Atlas VALs."""
    pairs: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for item in local:
        query = local_val_text(item)
        for cand in atlas:
            text = cand.get("title", "") + " " + cand.get("description", "")
            pairs.append((_sim(query, text), item, cand))
    pairs.sort(key=lambda x: x[0], reverse=True)
    used_local: set[str] = set()
    used_atlas: set[str] = set()
    matches: dict[str, tuple[dict[str, Any], dict[str, Any], float]] = {}
    for score, item, cand in pairs:
        if item["id"] in used_local or cand["dcId"] in used_atlas:
            continue
        if score < LOW_CONFIDENCE:
            continue
        matches[item["id"]] = (item, cand, score)
        used_local.add(item["id"])
        used_atlas.add(cand["dcId"])
    for item in local:
        meta = item.get("metadata", {}) or {}
        local_title = meta.get("title") or item.get("title", "") or ""
        if item["id"] in matches:
            _, cand, score = matches[item["id"]]
            emit_row(rows, "VAL", item, local_title, cand, score,
                     notes="cross-check AC and update Atlas")
        else:
            emit_row(rows, "VAL", item, local_title, None, 0.0,
                     notes="MIGRATE: create new Atlas VAL")


def main() -> None:
    print("Loading local YAMLs...")
    local_uns = load_local_yaml(f"{REPO}/design-controls/user-needs/UN-LEO-AI-*.yaml")
    local_dis = load_local_yaml(f"{REPO}/design-controls/design-inputs/DI-LEO-AI-*.yaml")
    local_dos = load_local_yaml(f"{REPO}/design-controls/design-outputs/DO-LEO-AI-*.yaml")
    local_vts = load_local_yaml(f"{REPO}/design-controls/verification-tests/VT-LEO-AI-*.yaml")
    local_vals = load_local_yaml(f"{REPO}/design-controls/validation-tests/VAL-LEO-AI-*.yaml")
    print(f"  UNs={len(local_uns)} DIs={len(local_dis)} DOs={len(local_dos)} "
          f"VTs={len(local_vts)} VALs={len(local_vals)}")

    print("Loading Atlas matrix...")
    with open(ATLAS_MATRIX) as f:
        data = json.load(f)
    nodes_by_id = {n["id"]: n for n in data["nodes"]}
    links = data["links"]
    atlas_uns = [n for n in data["nodes"] if n["dcType"] == "user-need"]
    atlas_dis = [n for n in data["nodes"] if n["dcType"] == "design-input"]
    atlas_vals = [n for n in data["nodes"] if n["dcType"] == "validation-test"]
    print(f"  Atlas UNs={len(atlas_uns)} DIs={len(atlas_dis)} VALs={len(atlas_vals)}")

    rows: list[dict[str, str]] = []
    print("Matching UNs...")
    un_map = map_uns(local_uns, atlas_uns, rows)
    print(f"  matched {len(un_map)}/{len(local_uns)}")

    print("Matching DIs...")
    di_map = map_dis(local_dis, atlas_dis, un_map, links, nodes_by_id, rows)
    print(f"  matched {len(di_map)}/{len(local_dis)}")

    print("Recording DOs (migrate-only)...")
    map_dos_and_vts(local_dos, "DO", local_do_text, di_map, rows)
    print("Recording VTs (migrate-only)...")
    map_dos_and_vts(local_vts, "VT", local_vt_text, di_map, rows)
    print("Matching VALs...")
    map_vals(local_vals, atlas_vals, rows)

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "artefact_type", "local_id", "local_title", "atlas_id",
            "atlas_title", "match_type", "similarity",
            "parent_un_atlas", "notes",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT}")

    cats = ["exact", "fuzzy", "low-confidence", "unmatched"]
    overall = {c: 0 for c in cats}
    by_type: dict[str, dict[str, int]] = {}
    for row in rows:
        atype = row["artefact_type"]
        mtype = row["match_type"]
        by_type.setdefault(atype, {c: 0 for c in cats})
        by_type[atype][mtype] = by_type[atype].get(mtype, 0) + 1
        overall[mtype] = overall.get(mtype, 0) + 1

    print("\nSummary by artefact type:")
    for atype, counts in sorted(by_type.items()):
        total = sum(counts.values())
        print(
            f"  {atype}: total={total} exact={counts['exact']} "
            f"fuzzy={counts['fuzzy']} low-conf={counts['low-confidence']} "
            f"unmatched={counts['unmatched']}"
        )
    print(f"Overall: {overall}")

    gaps_path = f"{REPO}/design-controls/atlas-id-mapping-gaps.md"
    with open(gaps_path, "w") as f:
        f.write("# Atlas-Local Mapping Gaps\n\n")
        f.write(
            "Auto-generated by `scripts/build_atlas_id_mapping.py`. "
            "Source: `design-controls/atlas-id-mapping.csv`.\n\n"
        )
        for atype in sorted(by_type):
            counts = by_type[atype]
            total = sum(counts.values())
            f.write(f"## {atype} (total {total})\n\n")
            f.write(
                f"- exact: {counts['exact']}\n"
                f"- fuzzy: {counts['fuzzy']}\n"
                f"- low-confidence (manual review): "
                f"{counts['low-confidence']}\n"
                f"- unmatched (candidate to create / migrate): "
                f"{counts['unmatched']}\n\n"
            )
            unmatched_ids = [
                r["local_id"]
                for r in rows
                if r["artefact_type"] == atype
                and r["match_type"] == "unmatched"
            ]
            if unmatched_ids:
                f.write("Unmatched local IDs:\n\n")
                for lid in unmatched_ids:
                    f.write(f"- {lid}\n")
                f.write("\n")
    print(f"Wrote gaps summary to {gaps_path}")


if __name__ == "__main__":
    main()
