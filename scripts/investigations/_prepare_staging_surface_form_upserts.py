"""Prepare TNM-aware surface-form upsert preview for staging terms.

Reads missed staging forms and emits a deterministic mapping preview using
the descendant set of SNOMED concept 399566009.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MISSED_FILE = (
    ROOT / "scripts" / "investigations" / "output" / "staging_surface_form_scan.json"
)
DESC_FILE = (
    ROOT / "scripts" / "investigations" / "output" / "descendants_399566009.json"
)
OUT_FILE = (
    ROOT
    / "scripts"
    / "investigations"
    / "output"
    / "staging_surface_form_upserts_preview.json"
)

_TNM_TRIPLET_RE = re.compile(
    r"\b([cpyr]?t[0-4](?:[a-c])?)\s*([cpyr]?n[0-3](?:[a-c])?)\s*([cpyr]?m[0-1](?:[a-c])?)\b",
    re.IGNORECASE,
)
_T_RE = re.compile(r"^[cpyr]?t[0-4](?:[a-c])?$", re.IGNORECASE)
_N_RE = re.compile(r"^[cpyr]?n[0-3](?:[a-c])?$", re.IGNORECASE)
_M_RE = re.compile(r"^[cpyr]?m[0-1](?:[a-c])?$", re.IGNORECASE)


def _desc_map() -> dict[str, str]:
    rows = json.loads(DESC_FILE.read_text(encoding="utf-8"))
    out = {str(r["concept_id"]): str(r["preferred_term"]) for r in rows}
    out.setdefault(
        "399566009", "Tumor-node-metastasis (TNM) category (observable entity)"
    )
    return out


def _pick_concept(surface_form: str) -> str:
    sf = surface_form.strip().lower()
    if _TNM_TRIPLET_RE.search(sf):
        return "399703000"  # Integrated TNM category
    if _T_RE.fullmatch(sf):
        if sf.startswith("p"):
            return "384625004"  # pT category
        if sf.startswith("c"):
            return "399504009"  # cT category
        return "78873005"  # T category
    if _N_RE.fullmatch(sf):
        if sf.startswith("p"):
            return "371494008"  # pN category
        if sf.startswith("c"):
            return "399534004"  # cN category
        return "277206009"  # N category
    if _M_RE.fullmatch(sf):
        if sf.startswith("p"):
            return "371497001"  # pM category
        if sf.startswith("c"):
            return "399387003"  # cM category
        return "277208005"  # M category
    if sf.startswith("stage "):
        return "399566009"  # TNM category (generic fallback)
    return "399566009"


def _split_triplet(surface_form: str) -> list[str]:
    m = _TNM_TRIPLET_RE.search(surface_form)
    if not m:
        return []
    return [m.group(1).upper(), m.group(2).upper(), m.group(3).upper()]


def main() -> None:
    desc = _desc_map()
    missed = json.loads(MISSED_FILE.read_text(encoding="utf-8")).get("missed") or []
    out: list[dict[str, Any]] = []
    compiled: dict[str, dict[str, Any]] = {}
    for row in missed:
        sf = str(row.get("surface_form") or "").strip()
        if not sf:
            continue
        concept_id = _pick_concept(sf)
        split_forms = _split_triplet(sf)
        out.append(
            {
                "surface_form": sf,
                "count": int(row.get("count") or 0),
                "pattern_labels": row.get("pattern_labels") or [],
                "recommended_concept_id": concept_id,
                "recommended_term": desc.get(concept_id, ""),
                "split_surface_forms": split_forms,
                "split_mappings": [
                    {
                        "surface_form": part,
                        "concept_id": _pick_concept(part),
                        "term": desc.get(_pick_concept(part), ""),
                    }
                    for part in split_forms
                ],
            }
        )
        key = sf.lower()
        compiled[key] = {
            "surface_form": sf,
            "concept_id": concept_id,
            "term": desc.get(concept_id, ""),
        }
        for part in split_forms:
            pid = _pick_concept(part)
            compiled.setdefault(
                part.lower(),
                {
                    "surface_form": part,
                    "concept_id": pid,
                    "term": desc.get(pid, ""),
                },
            )

    OUT_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    compiled_out = OUT_FILE.with_name("staging_surface_form_upserts_compiled.json")
    compiled_out.write_text(
        json.dumps(
            sorted(compiled.values(), key=lambda r: r["surface_form"].lower()),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT_FILE} ({len(out)} rows)")
    print(f"Wrote {compiled_out} ({len(compiled)} unique surface forms)")


if __name__ == "__main__":
    main()
