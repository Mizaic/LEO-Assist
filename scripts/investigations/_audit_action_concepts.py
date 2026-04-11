"""Audit action concepts from NG12 dry run using full terminology API.

For each action term:
  1. Resolve via the live resolver (text similarity + surface forms)
  2. For the top candidate, fetch /descendants and /related
  3. Use all candidates to decide if the current mapping is the best choice
  4. Print a recommended surface form fix where the current code is wrong

Usage:
    python scripts/investigations/_audit_action_concepts.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import requests

BASE = "http://localhost:8001/terminology"
TIMEOUT = 60


# ------------------------------------------------------------------ #
# Terminology API helpers                                              #
# ------------------------------------------------------------------ #


def resolve(terms: list[str], top_k: int = 8) -> dict[str, list[dict]]:
    r = requests.post(
        f"{BASE}/resolve", json={"terms": terms, "top_k": top_k}, timeout=TIMEOUT
    )
    r.raise_for_status()
    return r.json().get("results", {})


def search(q: str, tag: str | None = None, limit: int = 20) -> list[dict]:
    params: dict[str, Any] = {"q": q, "limit": limit}
    if tag:
        params["semantic_tag"] = tag
    r = requests.get(f"{BASE}/search", params=params, timeout=TIMEOUT)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json()


def descendants(
    concept_id: str, depth: int = 3, tag: str | None = None, limit: int = 100
) -> list[dict]:
    params: dict[str, Any] = {"depth": depth, "limit": limit}
    if tag:
        params["semantic_tag"] = tag
    r = requests.get(
        f"{BASE}/concepts/{concept_id}/descendants", params=params, timeout=TIMEOUT
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json()


def related(concept_id: str) -> dict:
    r = requests.get(f"{BASE}/concepts/{concept_id}/related", timeout=TIMEOUT)
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------ #
# Action terms to audit (from NG12 recommendations)                   #
# ------------------------------------------------------------------ #

# (action_text, current_code_from_dry_run, expected_tag)
ACTIONS = [
    # Upper GI
    ("direct access upper gastrointestinal endoscopy", "880451000000106", "procedure"),
    ("upper gastrointestinal endoscopy", "880451000000106", "procedure"),
    ("OGD", None, "procedure"),
    ("gastroscopy", None, "procedure"),
    # Lower GI
    ("direct access colonoscopy", "73761001", "procedure"),
    ("colonoscopy", "73761001", "procedure"),
    ("flexible sigmoidoscopy", None, "procedure"),
    ("CT colonography", None, "procedure"),
    # Imaging
    ("urgent chest X-ray", "399208008", "procedure"),
    ("urgent direct access CT scan", "116152004", "procedure"),
    ("CT scan of the chest abdomen and pelvis", None, "procedure"),
    ("urgent CT abdomen and pelvis", None, "procedure"),
    # Referrals (spot check a few)
    ("fast track referral for suspected lung cancer", "276491000000101", "procedure"),
    (
        "fast track referral for suspected colorectal cancer",
        "276401000000108",
        "procedure",
    ),
    # Haematology
    ("full blood count", None, "procedure"),
    ("blood film", None, "procedure"),
    ("serum protein electrophoresis", None, "procedure"),
    # Other investigations
    ("urine dipstick", None, "procedure"),
    ("faecal occult blood test", None, "procedure"),
    ("PSA test", None, "procedure"),
    ("CA125", None, "procedure"),
    ("urgent ultrasound", None, "procedure"),
    ("chest X-ray", "399208008", "procedure"),
]


def _tag(concept: dict) -> str:
    term = concept.get("snomed_term") or concept.get("term") or ""
    if "(" in term and ")" in term:
        return term.rsplit("(", 1)[-1].rstrip(")")
    return concept.get("semantic_tag") or "?"


def _is_bad_tag(term_str: str) -> bool:
    """True if the concept is a management/education/record type, not a procedure."""
    bad_prefixes = (
        "management of",
        "education about",
        "provision of",
        "care plan",
        "record artifact",
        "qualifier value",
        "situation",
        "finding",
        "disorder",
        "substance",
        "body structure",
        "organism",
        "occupation",
    )
    low = term_str.lower()
    return any(low.startswith(p) or f"({p})" in low for p in bad_prefixes)


def _score_candidate(c: dict, target_tag: str) -> float:
    """Score a candidate for how good it is as an action concept."""
    term = c.get("snomed_term") or c.get("term") or ""
    tag = _tag(c)
    score = c.get("score", 0.0)
    if tag == target_tag:
        score *= 1.5
    if _is_bad_tag(term):
        score *= 0.1
    return score


def _best_from_list(candidates: list[dict], target_tag: str) -> dict | None:
    if not candidates:
        return None
    scored = sorted(
        candidates, key=lambda c: _score_candidate(c, target_tag), reverse=True
    )
    return scored[0]


def audit_action(action_text: str, current_id: str | None, target_tag: str) -> dict:
    """Run full hierarchy-aware audit for one action term."""
    result: dict[str, Any] = {
        "action_text": action_text,
        "current_id": current_id,
        "resolver_top": None,
        "search_top": None,
        "hierarchy_candidates": [],
        "related_procedures": [],
        "recommendation": None,
        "flag": "OK",
    }

    # -- Step 1: Resolve via the live resolver -------------------------
    resolved = resolve([action_text]).get(action_text, [])
    if resolved:
        top = resolved[0]
        result["resolver_top"] = {
            "id": top.get("snomed_concept_id"),
            "term": top.get("snomed_term", "")[:70],
            "score": top.get("score"),
        }

    # -- Step 2: Fulltext search with semantic_tag filter --------------
    searched = search(action_text, tag=target_tag, limit=10)
    if searched:
        s_top = searched[0]
        result["search_top"] = {
            "id": s_top.get("snomed_concept_id") or s_top.get("id"),
            "term": (s_top.get("snomed_term") or s_top.get("term") or "")[:70],
            "score": s_top.get("score"),
        }

    # -- Step 3: Traverse hierarchy from resolver top concept ----------
    resolver_id = result["resolver_top"]["id"] if result["resolver_top"] else None
    if resolver_id:
        # Get descendants (find more specific procedures)
        desc = descendants(resolver_id, depth=3, tag=target_tag, limit=50)
        if desc:
            result["hierarchy_candidates"].extend(
                {
                    "id": d.get("snomed_concept_id"),
                    "term": (d.get("term") or "")[:70],
                    "via": "descendant",
                }
                for d in desc[:10]
            )

        # Get related concepts (find associated procedures)
        rel = related(resolver_id)
        if rel:
            for rel_type in (
                "component_of_procedures",
                "has_components",
                "interpreted_by_findings",
            ):
                for item in (rel.get(rel_type) or [])[:5]:
                    result["related_procedures"].append(
                        {
                            "id": item.get("id"),
                            "term": (item.get("fsn") or "")[:70],
                            "rel": rel_type,
                        }
                    )

    # -- Step 4: Recommend the best concept ----------------------------
    all_candidates = []
    if resolved:
        all_candidates.extend(resolved[:5])
    if searched:
        # Normalise search result shape to match resolver shape
        for s in searched[:5]:
            all_candidates.append(
                {
                    "snomed_concept_id": s.get("snomed_concept_id") or s.get("id"),
                    "snomed_term": s.get("snomed_term") or s.get("term") or "",
                    "score": s.get("score", 0.5),
                }
            )

    best = _best_from_list(all_candidates, target_tag)
    if best:
        result["recommendation"] = {
            "id": best.get("snomed_concept_id"),
            "term": (best.get("snomed_term") or "")[:70],
        }

    # -- Step 5: Flag problems -----------------------------------------
    resolver_term = (result["resolver_top"] or {}).get("term", "")
    if _is_bad_tag(resolver_term):
        result["flag"] = "WRONG_TYPE"
    elif (
        current_id
        and result["recommendation"]
        and result["recommendation"]["id"] != current_id
    ):
        result["flag"] = "BETTER_AVAILABLE"

    return result


# ------------------------------------------------------------------ #
# Main                                                                 #
# ------------------------------------------------------------------ #


def main() -> None:
    print("Auditing NG12 action concepts via terminology API hierarchy traversal")
    print("=" * 70)

    fixes_needed: list[dict] = []

    for action_text, current_id, target_tag in ACTIONS:
        print(f"\n  Auditing: {action_text!r}")
        try:
            r = audit_action(action_text, current_id, target_tag)
        except Exception as exc:
            print(f"    ERROR: {exc}")
            continue

        res_top = r["resolver_top"] or {}
        rec = r["recommendation"] or {}

        print(
            f"    Resolver top : {res_top.get('id')} | "
            f"{res_top.get('term', '?')[:55]} | score={res_top.get('score')}"
        )
        print(
            f"    Search top   : {(r['search_top'] or {}).get('id')} | "
            f"{(r['search_top'] or {}).get('term', '?')[:55]}"
        )
        if r["hierarchy_candidates"]:
            print("    Hierarchy children (top 3):")
            for h in r["hierarchy_candidates"][:3]:
                print(f"      {h['id']} | {h['term'][:55]}")
        if r["related_procedures"]:
            print("    Related procedures (top 3):")
            for rp in r["related_procedures"][:3]:
                print(f"      {rp['id']} | {rp['term'][:55]} [{rp['rel']}]")

        flag = r["flag"]
        if flag != "OK":
            print(f"    *** FLAG: {flag}")
            print(f"    Recommendation: {rec.get('id')} | {rec.get('term', '?')[:55]}")
            fixes_needed.append(
                {
                    "action_text": action_text,
                    "current_id": current_id,
                    "flag": flag,
                    "recommended_id": rec.get("id"),
                    "recommended_term": rec.get("term"),
                    "resolver_top_id": res_top.get("id"),
                    "resolver_top_term": res_top.get("term"),
                    "hierarchy_candidates": r["hierarchy_candidates"][:5],
                }
            )

    print("\n" + "=" * 70)
    print(f"SUMMARY: {len(fixes_needed)} action(s) need attention")
    print("=" * 70)
    for f in fixes_needed:
        print(f"\n  [{f['flag']}] {f['action_text']!r}")
        print(f"    Current   : {f['current_id']} | {f['resolver_top_term']}")
        print(f"    Recommend : {f['recommended_id']} | {f['recommended_term']}")

    # Write JSON for the fix script to consume
    out = Path(__file__).parent / "action_concept_audit.json"
    out.write_text(
        json.dumps(fixes_needed, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    print(f"\nFull audit written to: {out}")


if __name__ == "__main__":
    main()
