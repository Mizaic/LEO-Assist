"""Build a human-review SNOMED pack for missed staging forms.

This does not upsert anything. It only prepares a curated shortlist.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = (
    ROOT
    / "scripts"
    / "investigations"
    / "output"
    / "missing_staging_surface_form_snomed.json"
)
OUT = (
    ROOT
    / "scripts"
    / "investigations"
    / "output"
    / "missing_staging_surface_form_snomed_review_pack.json"
)

OVERRIDES: dict[str, dict[str, Any]] = {
    "stage 3a": {
        "recommended_concept_id": "1222802001",
        "recommended_term": "American Joint Committee on Cancer stage IIIA (qualifier value)",
        "confidence": "medium",
        "note": "Generic surface form; use AJCC IIIA as oncology-safe default.",
    },
    "stage i": {
        "recommended_concept_id": "258215001",
        "recommended_term": "Stage 1 (qualifier value)",
        "confidence": "medium",
        "note": "Prefer generic stage qualifier unless source context says lymphoma stage I.",
    },
    "t4n1m1": {
        "recommended_concept_id": "399703000",
        "recommended_term": "Integrated TNM category (observable entity)",
        "confidence": "medium",
        "note": "Composite TNM triplet mapped to integrated TNM category.",
    },
}


def _default_confidence(surface_form: str) -> str:
    sf = surface_form.lower()
    if sf.startswith("pt"):
        return "high"
    if sf.startswith("stage "):
        return "high"
    if sf in {"m0"}:
        return "high"
    return "medium"


def main() -> None:
    rows = json.loads(SRC.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for row in rows:
        sf = str(row.get("surface_form") or "").lower()
        item = {
            "surface_form": row.get("surface_form"),
            "count": row.get("count"),
            "pattern_labels": row.get("pattern_labels") or [],
            "recommended_concept_id": row.get("recommended_concept_id"),
            "recommended_term": row.get("recommended_term"),
            "confidence": _default_confidence(sf),
            "note": "Auto-suggested from terminology search; requires clinician/coder check.",
            "top_candidates": row.get("candidates") or [],
        }
        if sf in OVERRIDES:
            item.update(OVERRIDES[sf])
        out.append(item)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT} ({len(out)} forms)")


if __name__ == "__main__":
    main()
