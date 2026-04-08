"""Find candidate SNOMED concepts for missed staging surface forms.

Input:
  scripts/investigations/output/staging_surface_form_scan.json

Output:
  scripts/investigations/output/missing_staging_surface_form_snomed.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.terminology import TERMINOLOGY_SEARCH

load_keyvault_secrets()

INPUT_FILE = (
    ROOT / "scripts" / "investigations" / "output" / "staging_surface_form_scan.json"
)
OUTPUT_FILE = (
    ROOT
    / "scripts"
    / "investigations"
    / "output"
    / "missing_staging_surface_form_snomed.json"
)


_GOOD_TAGS = {"tumor staging", "qualifier value", "observable entity", "finding"}


def _fallback_term(surface_form: str, labels: list[str]) -> str:
    sf = surface_form.lower().strip()
    if "tnm_triplet" in labels:
        return f"TNM {sf}"
    if "tnm_t_component" in labels:
        return f"T category {sf}"
    if "tnm_n_component" in labels:
        return f"N category {sf}"
    if "tnm_m_component" in labels:
        return f"M category {sf}"
    if sf.startswith("stage "):
        return sf
    return sf


def _query(kg: KnowledgeGraphClient, text: str, limit: int = 8) -> list[dict[str, Any]]:
    return kg.run(TERMINOLOGY_SEARCH, q=text, limit=limit) or []


def _score_candidate(
    row: dict[str, Any],
    surface_form: str,
    labels: list[str],
) -> float:
    term = str(row.get("term") or "").lower()
    tag = str(row.get("semantic_tag") or "").lower()
    sf = surface_form.lower()
    score = float(row.get("score") or 0.0)
    if tag in _GOOD_TAGS:
        score += 3.0
    if "tumor-node-metastasis" in term or "tnm" in term:
        score += 3.5
    if "american joint committee on cancer" in term or "union for international cancer control" in term:
        score += 2.0
    if sf in term:
        score += 1.0
    if "generic_stage_token" in labels and "stage" in term:
        score += 1.0
    if any(lbl.startswith("tnm_") for lbl in labels) and (
        "category" in term or "tnm" in term or "stage" in term
    ):
        score += 1.0
    return score


def _sort_candidates(
    rows: list[dict[str, Any]], surface_form: str, labels: list[str]
) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: _score_candidate(row, surface_form, labels),
        reverse=True,
    )


def _is_relevant(row: dict[str, Any], surface_form: str, labels: list[str]) -> bool:
    term = str(row.get("term") or "").lower()
    sf = surface_form.lower().strip()
    if any(lbl.startswith("tnm_") for lbl in labels):
        if "category" in term and ("tnm" in term or " t category" in term or " n category" in term or " m category" in term):
            return True
        if re.fullmatch(r"p?t[0-4][a-c]?", sf):
            token = sf.replace("pt", "t")
            return bool(re.search(rf"\b[cpyr]?{re.escape(token)}\b", term))
        if re.fullmatch(r"n[0-3][a-c]?", sf):
            return bool(re.search(rf"\b[cpyr]?{re.escape(sf)}\b", term))
        if re.fullmatch(r"m[0-1][a-c]?", sf):
            return bool(re.search(rf"\b[cpyr]?{re.escape(sf)}\b", term))
        if "tnm_triplet" in labels:
            return "tnm" in term
        return "tnm" in term
    if "generic_stage_token" in labels:
        if not sf.startswith("stage "):
            return "stage" in term
        suffix = sf.replace("stage ", "").strip()
        return "stage" in term and suffix in term
    return sf in term


def _seed_queries(surface_form: str, labels: list[str]) -> list[str]:
    sf = surface_form.lower().strip()
    out = [sf]
    up = sf.upper()
    if re.fullmatch(r"p?t[0-4][a-c]?", sf):
        out.extend(
            [
                f"Union for International Cancer Control {up}",
                f"American Joint Committee on Cancer {up}",
                f"{up} qualifier value",
                "T category",
            ]
        )
    elif re.fullmatch(r"n[0-3][a-c]?", sf):
        out.extend(
            [
                f"Union for International Cancer Control {up}",
                f"American Joint Committee on Cancer {up}",
                f"{up} qualifier value",
                "N category",
            ]
        )
    elif re.fullmatch(r"m[0-1][a-c]?", sf):
        out.extend(
            [
                f"Union for International Cancer Control {up}",
                f"American Joint Committee on Cancer {up}",
                f"{up} qualifier value",
                "M category",
            ]
        )
    elif "tnm_triplet" in labels:
        out.extend(["Integrated TNM category", "TNM stage grouping", "TNM category"])
    elif sf.startswith("stage "):
        roman = sf.replace("stage ", "stage ").upper().replace("  ", " ")
        out.extend([roman, sf.replace("stage ", "clinical stage ")])
    else:
        out.append(_fallback_term(sf, labels))
    deduped: list[str] = []
    seen: set[str] = set()
    for q in out:
        key = q.lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(q)
    return deduped


def _to_result_row(miss: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    best = candidates[0] if candidates else {}
    return {
        "surface_form": miss.get("surface_form"),
        "count": miss.get("count"),
        "pattern_labels": miss.get("pattern_labels") or [],
        "recommended_concept_id": best.get("snomed_concept_id"),
        "recommended_term": best.get("term"),
        "recommended_semantic_tag": best.get("semantic_tag"),
        "candidates": [
            {
                "concept_id": c.get("snomed_concept_id"),
                "term": c.get("term"),
                "semantic_tag": c.get("semantic_tag"),
                "score": c.get("score"),
            }
            for c in candidates
        ],
    }


def main() -> None:
    data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    misses = data.get("missed") or []
    kg = KnowledgeGraphClient()
    try:
        out: list[dict[str, Any]] = []
        for miss in misses:
            sf = str(miss.get("surface_form") or "").strip()
            labels = list(miss.get("pattern_labels") or [])
            if not sf:
                continue
            merged: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for q in _seed_queries(sf, labels):
                rows = _query(kg, q, limit=8)
                for row in rows:
                    cid = str(row.get("snomed_concept_id") or "")
                    if not cid or cid in seen_ids:
                        continue
                    if not _is_relevant(row, sf, labels):
                        continue
                    seen_ids.add(cid)
                    merged.append(row)
            ranked = _sort_candidates(merged, sf, labels)
            out.append(_to_result_row(miss, ranked[:8]))
    finally:
        kg.close()

    OUTPUT_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE} ({len(out)} forms)")


if __name__ == "__main__":
    main()
