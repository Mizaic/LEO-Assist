"""Phase 4 -- Migrate local risks into Atlas with strict de-duplication.

Atlas baseline already contains 159 risks: 94 sourced from prior YAML
migration and 63 sourced from FMEA workshops. Local has 179 R-LEO-AI-*
YAMLs plus 51 FMEA_GAP rows in `MASTER-RISK-LIST-FINAL.csv` that have
no YAML counterpart.

The user's instruction is "do not duplicate risks", so this script
errs strongly toward remap:

  Match precedence (highest first):
    1. EXACT FMEA-ref match. Atlas risks created from FMEA carry
       "FMEA refs: FMEA-NNN" in their description. Every local row
       (YAML AND FMEA_GAP) records the same FMEA refs in the master
       CSV column `Source_FMEA_IDs`. If at least one local FMEA ref
       appears in the Atlas description, we treat it as an EXACT
       match and remap immediately.
    2. Title-only Jaccard >= 0.50 OR combined-text similarity >= 0.55:
       remap.
    3. 0.30 <= score < remap-threshold: REMAP-CONSERVATIVE. We still
       remap (do not duplicate) but flag for review in the ledger so
       a human can confirm.
    4. score < 0.30: CREATE.

Mitigation links: For every successfully resolved local risk we walk
its mitigating DI list (`mitigation_measures[].implemented_by` for YAML
or `Mitigating_DIs` column for CSV rows), translate each local DI to
its Atlas dcId via atlas-id-mapping.csv, and call
`link_design_controls source_ids=[DI dcIds] target_ids=[Risk dcId]
relationship=MITIGATES`.

Outputs:
  - design-controls/phase10-risk-migration.csv / .md
  - design-controls/phase10-risk-mitigates-links.csv (one row per
    successful MITIGATES link batch)
  - scripts/atlas/.phase4_risk_state.json
  - scripts/atlas/.phase4_risk_links_state.json

Usage:
  python3 scripts/atlas/phase4_risk_migrate.py                   # dry-run
  python3 scripts/atlas/phase4_risk_migrate.py --live            # mutate
  python3 scripts/atlas/phase4_risk_migrate.py --live --skip-create
                                                                  # remap only
  python3 scripts/atlas/phase4_risk_migrate.py --filter R-LEO-AI-001
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

REPO = Path("/Users/robsmith/Documents/github/LEO-AI-CORE")
RISK_DIR = REPO / "design-controls" / "risks"
MAPPING_CSV = REPO / "design-controls" / "atlas-id-mapping.csv"
MASTER_CSV = REPO / "design-controls" / "risks" / "MASTER-RISK-LIST-FINAL.csv"
ATLAS_MATRIX = (
    REPO / "design-controls" / "atlas-baseline-2026-04-19" / "traceability-matrix.json"
)
DECISIONS_PATH = REPO / "scripts" / "atlas" / "phase4_decisions.json"

LEDGER_CSV = REPO / "design-controls" / "phase10-risk-migration.csv"
LEDGER_MD = REPO / "design-controls" / "phase10-risk-migration.md"
LINKS_LEDGER = REPO / "design-controls" / "phase10-risk-mitigates-links.csv"
REVIEW_REPORT = REPO / "design-controls" / "phase10-risk-review-band.md"

STATE_PATH = REPO / "scripts" / "atlas" / ".phase4_risk_state.json"
LINKS_STATE_PATH = REPO / "scripts" / "atlas" / ".phase4_risk_links_state.json"

sys.path.insert(0, str(REPO / "scripts" / "atlas"))
import _mcp_transport as mcp  # noqa: E402

PRODUCT_ID = "PROD-LEO-CORE-AI-20260415-6AE8A23B"

# De-duplication thresholds.
#  - At or above REMAP_HARD (or TITLE_REMAP on title alone, or any FMEA
#    exact ref match): auto-remap.
#  - Between REVIEW_BAND_LOW and REMAP_HARD: flagged "review-needed"
#    and DEFAULT to CREATE so we do not silently merge two distinct
#    risks. Manual overrides in phase4_decisions.json can flip a
#    review-needed entry to "remap".
#  - Below REVIEW_BAND_LOW: auto-create.
REMAP_HARD = 0.55
TITLE_REMAP = 0.50
REVIEW_BAND_LOW = 0.40

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "by",
    "with", "is", "are", "be", "been", "shall", "must", "should", "system",
    "as", "so", "that", "their", "this", "from", "into", "via", "any", "all",
    "when", "able", "can", "will", "leo", "ai", "leoai", "using", "use",
    "user", "need", "needs", "have", "has", "not", "than", "then",
    "patient", "data", "could", "may", "would",
}

SEVERITY_MAP = {
    "negligible": 1, "minor": 2, "serious": 3, "critical": 4, "catastrophic": 5,
}
RISK_LEVEL_MAP = {
    "low": "low", "medium": "medium", "high": "high",
    "unacceptable": "unacceptable", "critical": "high",
}
ACCEPTABILITY_MAP = {
    "acceptable": "acceptable",
    "alarp": "alarp",
    "conditionally_acceptable": "alarp",
    "unacceptable": "unacceptable",
}
PROB_MAP = {
    "improbable": 1, "remote": 2, "unlikely": 2, "occasional": 3,
    "probable": 4, "frequent": 5,
}


# -- text helpers -----------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(text: Any) -> str:
    if text is None:
        return ""
    return " ".join(str(text).lower().split())


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for raw in _norm(text).replace("/", " ").replace("-", " ").replace(".", " ").split():
        tok = "".join(ch for ch in raw if ch.isalnum())
        if not tok or tok in STOPWORDS or len(tok) < 3:
            continue
        out.add(tok)
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _sim(a: str, b: str) -> float:
    seq = SequenceMatcher(None, _norm(a), _norm(b)).ratio()
    jac = _jaccard(_tokens(a), _tokens(b))
    return max(seq, jac)


# -- mapping CSV helpers ----------------------------------------------


def load_di_mapping() -> dict[str, str]:
    out: dict[str, str] = {}
    with MAPPING_CSV.open() as f:
        for r in csv.DictReader(f):
            if r.get("artefact_type") != "DI":
                continue
            local = r.get("local_id") or ""
            atlas = r.get("atlas_id") or ""
            if local and atlas:
                out[local] = atlas
    return out


# -- local YAML loader ------------------------------------------------


def _coerce_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [s.strip() for s in re.split(r"[\s,]+", value) if s.strip()]
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return []


def _load_yaml_doc(path: Path, target_id: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    docs = list(yaml.safe_load_all(path.read_text()))
    for doc in docs:
        if not doc:
            continue
        items = doc if isinstance(doc, list) else [doc]
        for item in items:
            if isinstance(item, dict) and item.get("id") == target_id:
                return item
    return None


def load_local_yaml_risk(local_id: str) -> dict[str, Any] | None:
    item = _load_yaml_doc(RISK_DIR / f"{local_id}.yaml", local_id)
    if not item:
        return None
    def _as_dict(v: Any) -> dict[str, Any]:
        return v if isinstance(v, dict) else {}

    hazard = _as_dict(item.get("hazard"))
    harm = _as_dict(item.get("harm"))
    initial = _as_dict(item.get("initial_risk_estimate"))
    residual = _as_dict(item.get("residual_risk_estimate"))
    monitoring = _as_dict(item.get("monitoring"))
    metadata = _as_dict(item.get("metadata"))

    measures = item.get("mitigation_measures") or []
    di_set: set[str] = set()
    vt_set: set[str] = set()
    primary_control_type = ""
    primary_effect = ""
    plan_pieces: list[str] = []
    for m in measures:
        if not isinstance(m, dict):
            continue
        for di in _coerce_str_list(m.get("implemented_by")):
            di_set.add(di)
        for vt in _coerce_str_list(m.get("verified_by")):
            vt_set.add(vt)
        if not primary_control_type and m.get("control_type"):
            primary_control_type = (m.get("control_type") or "").lower().strip()
        if not primary_effect and m.get("effectiveness"):
            primary_effect = (m.get("effectiveness") or "").lower().strip()
        if m.get("description"):
            plan_pieces.append(_norm_text(m["description"]))

    fmea_refs = _coerce_str_list(metadata.get("fmea_refs"))
    return {
        "id": item.get("id"),
        "title": _norm_text(item.get("title") or item.get("id")),
        "hazard_description": _norm_text(hazard.get("description")),
        "hazard_category": (hazard.get("category") or "").lower().strip() or None,
        "hazardous_situation": _norm_text(item.get("hazardous_situation")),
        "harm_description": _norm_text(harm.get("description")),
        "harm_severity": (harm.get("severity") or "").lower().strip() or None,
        "initial_severity": initial.get("severity"),
        "initial_probability": initial.get("probability"),
        "initial_detectability": initial.get("detectability"),
        "initial_risk_score": initial.get("rpn"),
        "residual_severity": residual.get("severity"),
        "residual_probability": residual.get("probability"),
        "residual_detectability": residual.get("detectability"),
        "residual_risk_score": residual.get("rpn"),
        "residual_risk_level": (residual.get("risk_level") or "").lower().strip() or None,
        "residual_acceptability": (residual.get("acceptability") or "").lower().strip() or None,
        "residual_justification": _norm_text(residual.get("justification")),
        "mitigation_plan_description": " || ".join(plan_pieces)[:4000] or None,
        "mitigation_control_type": primary_control_type or None,
        "mitigation_effectiveness": primary_effect or None,
        "monitoring_plan": _norm_text(monitoring.get("monitoring_plan")),
        "monitoring_metrics": _coerce_str_list(monitoring.get("metrics"))[:25] or None,
        "review_frequency": (monitoring.get("review_frequency") or "").lower().strip() or None,
        "identified_by": _norm_text(metadata.get("identified_by")),
        "identified_date": _norm_text(metadata.get("identified_date")),
        "tags": _coerce_str_list(item.get("tags")) or None,
        "status": (metadata.get("status") or "").lower().strip(),
        "safety_class": None,  # YAML risks rarely set this; let server default
        "design_inputs": sorted(di_set),
        "verification_tests": sorted(vt_set),
        "fmea_refs": fmea_refs,
        "source": "yaml",
    }


# -- Master CSV helpers -----------------------------------------------


def load_master_rows() -> list[dict[str, str]]:
    with MASTER_CSV.open() as f:
        return list(csv.DictReader(f))


def _to_int(value: str) -> int | None:
    try:
        v = int(float((value or "").strip()))
        return v if v >= 1 else None
    except (TypeError, ValueError):
        return None


def _coerce_severity(value: str) -> str | None:
    v = (value or "").strip().lower()
    if not v:
        return None
    if v in SEVERITY_MAP:
        return v
    return None


def _coerce_acceptability(value: str) -> str | None:
    v = (value or "").strip().lower()
    if not v:
        return None
    return ACCEPTABILITY_MAP.get(v)


def _coerce_probability_int(value: str) -> int | None:
    v = (value or "").strip().lower()
    if not v:
        return None
    if v.isdigit():
        return _to_int(v)
    if v in PROB_MAP:
        return PROB_MAP[v]
    return None


def load_csv_fmea_gap_risks(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.get("Source") != "FMEA_GAP":
            continue
        ridx = (r.get("Atlas_R_ID") or "").strip()
        title = _norm_text(r.get("Title"))
        if not title:
            continue
        out.append({
            "id": ridx or f"FMEA-GAP-{r.get('Master_ID')}",
            "title": title,
            "hazard_description": _norm_text(r.get("Hazardous_Situation"))[:1000],
            "hazardous_situation": _norm_text(r.get("Hazardous_Situation")),
            "harm_description": _norm_text(r.get("Notes")),
            "harm_severity": _coerce_severity(r.get("Harm_Severity", "")),
            "hazard_category": "software_defect",
            "initial_severity": _to_int(r.get("S")),
            "initial_probability": _to_int(r.get("P")),
            "initial_detectability": _to_int(r.get("D")),
            "initial_risk_score": _to_int(r.get("RPN")),
            "residual_severity": (
                _to_int(r.get("Residual_Severity"))
                or _coerce_probability_int(r.get("Residual_Severity", ""))
                or _to_int(r.get("Revised_S"))
            ),
            "residual_probability": (
                _to_int(r.get("Residual_Probability"))
                or _coerce_probability_int(r.get("Residual_Probability", ""))
                or _to_int(r.get("Revised_P"))
            ),
            "residual_detectability": (
                _to_int(r.get("Residual_Detectability")) or _to_int(r.get("Revised_D"))
            ),
            "residual_risk_score": (
                _to_int(r.get("Residual_RPN")) or _to_int(r.get("Revised_RPN"))
            ),
            "residual_risk_level": None,
            "residual_acceptability": _coerce_acceptability(r.get("Residual_Acceptability", "")),
            "residual_justification": _norm_text(r.get("Notes")),
            "mitigation_plan_description": _norm_text(r.get("Notes"))[:4000] or None,
            "mitigation_control_type": None,
            "mitigation_effectiveness": None,
            "monitoring_plan": None,
            "monitoring_metrics": None,
            "review_frequency": None,
            "identified_by": "FMEA workshop",
            "identified_date": "2026-04-16",
            "tags": _coerce_str_list(r.get("STRIDE_Categories")) or None,
            "status": "analyzed",
            "safety_class": (r.get("Safety_Class") or "").strip().upper() or None,
            "design_inputs": _coerce_str_list(r.get("Mitigating_DIs")),
            "verification_tests": [],
            "fmea_refs": _coerce_str_list(r.get("Source_FMEA_IDs")),
            "source": "fmea_gap",
        })
    return out


def collect_yaml_fmea_refs_from_master(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    """For YAML-backed master rows, capture their declared FMEA refs."""
    out: dict[str, list[str]] = {}
    for r in rows:
        if r.get("Source") not in ("YAML", "YAML+FMEA"):
            continue
        local_id = (r.get("Atlas_R_ID") or "").strip()
        refs = _coerce_str_list(r.get("Source_FMEA_IDs"))
        if local_id and refs:
            out[local_id] = refs
    return out


# -- Atlas baseline loaders -------------------------------------------


def load_atlas_risks() -> list[dict[str, Any]]:
    data = json.loads(ATLAS_MATRIX.read_text())
    return [n for n in data.get("nodes", []) if n.get("dcType") == "risk"]


def index_atlas_by_fmea(atlas: list[dict[str, Any]]) -> dict[str, str]:
    """Return FMEA ref (e.g. 'FMEA-004') -> Atlas dcId."""
    out: dict[str, str] = {}
    for r in atlas:
        desc = r.get("description") or ""
        m = re.search(r"FMEA refs:\s*([A-Z0-9\-,\s]+)", desc)
        if not m:
            continue
        for ref in m.group(1).split(","):
            ref = ref.strip()
            if ref and ref not in out:
                out[ref] = r.get("dcId") or ""
    return out


def best_match_risk(
    local: dict[str, Any], atlas: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, float, float]:
    """Return (atlas_node, combined_score, title_only_score)."""
    title_q = local["title"]
    full_q = " ".join(
        s for s in (
            local["title"],
            local.get("hazard_description") or "",
            local.get("hazardous_situation") or "",
            local.get("harm_description") or "",
        ) if s
    )
    best: tuple[dict[str, Any] | None, float, float] = (None, 0.0, 0.0)
    for n in atlas:
        a_title = n.get("title") or ""
        a_full = " ".join(
            s for s in (a_title, n.get("description") or "") if s
        )
        full_score = _sim(full_q, a_full)
        title_score = _sim(title_q, a_title)
        score = max(full_score, title_score)
        if score > best[1]:
            best = (n, score, title_score)
    return best


# -- state ------------------------------------------------------------


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "started_at": None,
            "updated_at": None,
            "rows": {},
            "created": {},
        }
    return json.loads(path.read_text())


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = _now_iso()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(path)


# -- decision logic ---------------------------------------------------


def decide(
    local: dict[str, Any],
    atlas_node: dict[str, Any] | None,
    score: float,
    title_score: float,
    fmea_match: str | None,
    override: dict[str, Any] | None,
) -> tuple[str, str, str]:
    """Return (decision, atlas_dc_id, note)."""
    if override and override.get("decision"):
        atlas_dc = override.get("atlas_dc_id", "")
        if not atlas_dc and atlas_node:
            atlas_dc = atlas_node.get("dcId", "")
        return override["decision"], atlas_dc, "manual"
    if fmea_match:
        return "remap", fmea_match, "exact FMEA ref"
    if atlas_node and (score >= REMAP_HARD or title_score >= TITLE_REMAP):
        return "remap", atlas_node.get("dcId", ""), "auto >= REMAP_HARD"
    if atlas_node and score >= REVIEW_BAND_LOW:
        # Default to CREATE in review band; the row is flagged so a
        # human can flip it via phase4_decisions.json before live run.
        # Suggestion is recorded in `best_atlas_id` for reporting.
        return (
            "create-review",
            "",
            f"suggest={atlas_node.get('dcId', '')}",
        )
    return "create", "", "auto < 0.40"


# -- create / link helpers --------------------------------------------


def build_create_args(local: dict[str, Any]) -> dict[str, Any]:
    args: dict[str, Any] = {
        "product_id": PRODUCT_ID,
        "title": local["title"][:200] or local["id"],
    }
    desc_pieces = []
    if local.get("source") == "fmea_gap":
        desc_pieces.append(
            f"Source: FMEA_GAP. FMEA refs: {', '.join(local.get('fmea_refs') or [])}."
        )
    elif local.get("source") == "yaml":
        desc_pieces.append(f"Source: YAML ({local['id']}).")
        if local.get("fmea_refs"):
            desc_pieces.append(f"FMEA refs: {', '.join(local['fmea_refs'])}.")
    if local.get("hazard_description"):
        desc_pieces.append("Hazard: " + local["hazard_description"][:600])
    if local.get("hazardous_situation"):
        desc_pieces.append("Situation: " + local["hazardous_situation"][:600])
    args["description"] = (" ".join(desc_pieces))[:4000]

    for k in (
        "hazard_description", "hazardous_situation", "harm_description",
        "hazard_category", "harm_severity",
        "initial_severity", "initial_probability", "initial_detectability",
        "initial_risk_score",
        "residual_severity", "residual_probability", "residual_detectability",
        "residual_risk_score", "residual_risk_level", "residual_acceptability",
        "residual_justification",
        "mitigation_plan_description", "mitigation_control_type",
        "mitigation_effectiveness",
        "monitoring_plan", "monitoring_metrics", "review_frequency",
        "identified_by", "identified_date",
        "tags",
    ):
        v = local.get(k)
        if v not in (None, "", [], {}):
            args[k] = v
    if local.get("safety_class") in ("A", "B", "C"):
        args["safety_class"] = local["safety_class"]
    return args


def link_mitigates(
    atlas_risk_dc: str,
    local: dict[str, Any],
    di_mapping: dict[str, str],
    live: bool,
    state: dict[str, Any],
) -> tuple[int, str, str]:
    """Return (linked_count, result, error)."""
    di_local = local.get("design_inputs") or []
    di_atlas = sorted({di_mapping[d] for d in di_local if d in di_mapping})
    if not di_atlas:
        return 0, "no parent DIs resolved", ""
    cache_key = f"{atlas_risk_dc}<-{','.join(di_atlas)}"
    if cache_key in state["linked"]:
        return len(di_atlas), "cached: already linked", ""
    if not live:
        return len(di_atlas), f"dry-run: would link {len(di_atlas)} DI(s)", ""
    try:
        mcp.call_tool(
            "link_design_controls",
            {
                "source_ids": di_atlas,
                "target_ids": [atlas_risk_dc],
                "relationship": "MITIGATES",
            },
        )
        state["linked"][cache_key] = {"at": _now_iso()}
        return len(di_atlas), f"linked {len(di_atlas)} DI(s)", ""
    except mcp.McpError as e:
        return 0, "link_error", str(e)[:300]


# -- main per-risk processing -----------------------------------------


def process_risk(
    local: dict[str, Any],
    atlas: list[dict[str, Any]],
    fmea_index: dict[str, str],
    di_mapping: dict[str, str],
    live: bool,
    skip_create: bool,
    state: dict[str, Any],
    links_state: dict[str, Any],
    decisions: dict[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "local_id": local["id"], "source": local["source"],
        "atlas_id": "", "decision": "", "best_score": 0.0,
        "title_score": 0.0, "best_atlas_id": "", "best_atlas_title": "",
        "fmea_match": "", "linked_dis": 0, "result": "", "error": "",
    }

    fmea_match: str | None = None
    for ref in local.get("fmea_refs") or []:
        if ref in fmea_index:
            fmea_match = fmea_index[ref]
            row["fmea_match"] = ref
            break

    cand, score, title_score = best_match_risk(local, atlas)
    row["best_score"] = round(score, 3)
    row["title_score"] = round(title_score, 3)
    if cand:
        row["best_atlas_id"] = cand.get("dcId", "")
        row["best_atlas_title"] = (cand.get("title") or "")[:120]

    decision, atlas_dc, note = decide(
        local, cand, score, title_score, fmea_match, decisions.get(local["id"])
    )
    row["decision"] = decision + ("-manual" if note == "manual" else "")
    row["atlas_id"] = atlas_dc

    if decision == "remap":
        row["result"] = f"remap-recorded ({note})"
        if atlas_dc:
            cnt, lr, err = link_mitigates(
                atlas_dc, local, di_mapping, live, links_state
            )
            row["linked_dis"] = cnt
            row["result"] += f" | {lr}"
            if err:
                row["error"] = err
        return row

    if decision == "skip":
        row["result"] = "skipped (manual)"
        return row

    if skip_create:
        row["result"] = "skipped (--skip-create)"
        return row

    if decision == "create-review" and not live:
        row["result"] = (
            f"dry-run: would create (REVIEW: {note}; "
            f"override in phase4_decisions.json to remap)"
        )
        return row
    if not live:
        row["result"] = "dry-run: would create"
        return row

    cached = state["created"].get(local["id"])
    if cached and cached.get("dcId"):
        new_dc = cached["dcId"]
        row["atlas_id"] = new_dc
        row["result"] = f"create-skipped (already exists as {new_dc})"
    else:
        try:
            args = build_create_args(local)
            res = mcp.call_tool("create_risk", args)
        except mcp.McpError as e:
            row["result"] = "create_error"
            row["error"] = str(e)[:600]
            return row
        new_risk = res.get("risk") or res.get("createdRisk") or res
        new_dc = new_risk.get("dcId") or new_risk.get("dc_id") or ""
        new_uuid = new_risk.get("id") or ""
        row["atlas_id"] = new_dc
        if not new_dc:
            row["result"] = "create_error"
            row["error"] = f"unexpected response: {str(res)[:200]}"
            return row
        state["created"][local["id"]] = {"dcId": new_dc, "id": new_uuid}
        row["result"] = "created"

    cnt, lr, err = link_mitigates(new_dc, local, di_mapping, live, links_state)
    row["linked_dis"] = cnt
    row["result"] += f" | {lr}"
    if err:
        row["error"] = err
    return row


# -- ledger output ----------------------------------------------------


def write_ledger(rows: list[dict[str, Any]]) -> None:
    fields = [
        "local_id", "source", "decision", "atlas_id", "best_atlas_id",
        "best_atlas_title", "best_score", "title_score", "fmea_match",
        "linked_dis", "result", "error",
    ]
    with LEDGER_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["decision"]] = counts.get(r["decision"], 0) + 1
    md = ["# Phase 4 -- Risk Migration Ledger", "",
          f"Run at: {_now_iso()}",
          f"Total rows: {len(rows)}", "",
          "## Decision counts", ""]
    for k in sorted(counts):
        md.append(f"- `{k}`: {counts[k]}")
    md += ["", "## Rows", "",
           "| Local | Source | Decision | Atlas | BestAtlas | Score | TitleScore | FMEA | LinkedDIs | Result | Error |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(
            "| "
            + " | ".join(
                str(r.get(k, "")).replace("|", "\\|")
                for k in (
                    "local_id", "source", "decision", "atlas_id",
                    "best_atlas_id",
                    "best_score", "title_score", "fmea_match",
                    "linked_dis", "result", "error",
                )
            )
            + " |"
        )
    LEDGER_MD.write_text("\n".join(md) + "\n")


def write_review_report(rows: list[dict[str, Any]], locals_by_id: dict[str, dict[str, Any]]) -> None:
    band = [r for r in rows if r["decision"] == "create-review"]
    band.sort(key=lambda r: -float(r["best_score"]))
    md = ["# Phase 4 -- Risk Review Band (0.40 <= score < 0.55)", "",
          f"Total candidates needing manual confirmation: {len(band)}",
          "",
          "Default decision: CREATE (do NOT silently merge).",
          "To remap a row to its best-match Atlas risk instead of creating",
          "a new one, add an entry to `scripts/atlas/phase4_decisions.json`",
          'in the form `{\"R-LEO-AI-XXX\": {\"decision\": \"remap\", "atlas_dc_id": "R-XXXXXXXX\"}}`',
          "and re-run with --live.",
          "",
          "| Local ID | Score | Best Atlas | Local Title | Atlas Title |",
          "|---|---|---|---|---|"]
    for r in band:
        local = locals_by_id.get(r["local_id"], {})
        ltitle = (local.get("title") or "")[:160].replace("|", "\\|")
        atitle = (r.get("best_atlas_title") or "")[:120].replace("|", "\\|")
        md.append(
            f"| {r['local_id']} | {r['best_score']} | "
            f"{r.get('best_atlas_id') or '-'} | {ltitle} | {atitle} |"
        )
    REVIEW_REPORT.write_text("\n".join(md) + "\n")


def write_links_ledger(links_state: dict[str, Any]) -> None:
    fields = ["risk_dc_id", "di_dc_ids", "linked_at"]
    with LINKS_LEDGER.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for key, info in sorted(links_state.get("linked", {}).items()):
            risk, dis = key.split("<-", 1)
            w.writerow({"risk_dc_id": risk, "di_dc_ids": dis, "linked_at": info.get("at", "")})


# -- main -------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--skip-create", action="store_true",
                        help="Process remaps + links only, do not create new risks")
    parser.add_argument("--filter", type=str, default="")
    parser.add_argument("--source", choices=("yaml", "fmea_gap", "all"),
                        default="all")
    args = parser.parse_args()

    decisions = (
        json.loads(DECISIONS_PATH.read_text())
        if DECISIONS_PATH.exists() else {}
    )

    print("Loading Atlas snapshot ...")
    atlas = load_atlas_risks()
    fmea_index = index_atlas_by_fmea(atlas)
    print(f"  atlas risks: {len(atlas)}, FMEA-tagged: {len(fmea_index)}")

    print("Loading local risks ...")
    yaml_ids = sorted(p.stem for p in RISK_DIR.glob("R-LEO-AI-*.yaml"))
    locals_list: list[dict[str, Any]] = []
    if args.source in ("yaml", "all"):
        master_rows = load_master_rows()
        yaml_fmea = collect_yaml_fmea_refs_from_master(master_rows)
        for lid in yaml_ids:
            local = load_local_yaml_risk(lid)
            if not local:
                continue
            if not local.get("fmea_refs"):
                local["fmea_refs"] = yaml_fmea.get(lid, [])
            locals_list.append(local)
        print(f"  YAML risks loaded: {sum(1 for x in locals_list if x['source']=='yaml')}")
    if args.source in ("fmea_gap", "all"):
        master_rows = load_master_rows()
        gaps = load_csv_fmea_gap_risks(master_rows)
        locals_list.extend(gaps)
        print(f"  FMEA-gap rows loaded: {len(gaps)}")

    if args.filter:
        locals_list = [
            x for x in locals_list
            if x["id"] == args.filter or x["id"].startswith(args.filter)
        ]
    print(
        f"Total scope: {len(locals_list)} risks "
        f"(live={args.live}, skip_create={args.skip_create})"
    )

    di_mapping = load_di_mapping()
    print(f"  local DI -> Atlas DI mapping: {len(di_mapping)}")

    print("Initialising MCP session ...")
    sid = mcp.initialize()
    print(f"  session: {sid}")

    state = load_state(STATE_PATH)
    if not state.get("started_at"):
        state["started_at"] = _now_iso()
    links_state = load_state(LINKS_STATE_PATH)
    links_state.setdefault("linked", {})
    if not links_state.get("started_at"):
        links_state["started_at"] = _now_iso()

    rows: list[dict[str, Any]] = []
    for idx, local in enumerate(locals_list, start=1):
        cached = state["rows"].get(local["id"])
        if (
            args.live and cached
            and cached.get("result", "").startswith(("created", "create-skipped", "remap"))
        ):
            rows.append(cached)
            continue
        row = process_risk(
            local, atlas, fmea_index, di_mapping, args.live,
            args.skip_create, state, links_state, decisions,
        )
        rows.append(row)
        state["rows"][local["id"]] = row
        save_state(STATE_PATH, state)
        save_state(LINKS_STATE_PATH, links_state)
        print(
            f"  [{idx}/{len(locals_list)}] {local['id']} ({local['source']}): "
            f"{row['decision']} sc={row['best_score']} ts={row['title_score']} "
            f"fmea={row['fmea_match'] or '-'} -> {row['result'][:80]}"
        )
        time.sleep(0.05)

    write_ledger(rows)
    write_links_ledger(links_state)
    locals_by_id = {x["id"]: x for x in locals_list}
    write_review_report(rows, locals_by_id)
    print(f"Wrote ledger:       {LEDGER_CSV}")
    print(f"Wrote review band:  {REVIEW_REPORT}")
    print(f"Wrote links ledger: {LINKS_LEDGER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
