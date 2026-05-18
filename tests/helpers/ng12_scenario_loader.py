"""Load and validate the three paired NG12 scenario JSON fixtures."""

from __future__ import annotations

import json
import pathlib
from typing import Any

_FIXTURE_DIR = (
    pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "ng12_scenarios"
)


def load_paired_scenarios() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return (gdl_doc, ext_doc, sbr_doc) JSON dict roots."""
    gdl = json.loads((_FIXTURE_DIR / "ng12_guideline_scenarios.json").read_text())
    ext = json.loads((_FIXTURE_DIR / "ng12_extraction_scenarios.json").read_text())
    sbr = json.loads((_FIXTURE_DIR / "ng12_sbar_scenarios.json").read_text())
    return gdl, ext, sbr


_PAIRS_CACHE: list[tuple[dict, dict, dict]] | None = None


def iter_paired_rows() -> list[tuple[dict, dict, dict]]:
    """Align scenarios by numeric suffix on ``id`` (GDL / EXT / SBR)."""
    global _PAIRS_CACHE
    if _PAIRS_CACHE is not None:
        return _PAIRS_CACHE
    gdl, ext, sbr = load_paired_scenarios()
    g_by: dict[str, dict] = {row["id"]: row for row in gdl["scenarios"]}
    e_by: dict[str, dict] = {row["id"]: row for row in ext["scenarios"]}
    s_by: dict[str, dict] = {row["id"]: row for row in sbr["scenarios"]}

    triples: list[tuple[dict, dict, dict]] = []
    for g_id, grow in sorted(g_by.items(), key=lambda kv: kv[0]):
        suffix = g_id.rsplit("-", 1)[-1]
        e_id = f"NG12-EXT-{suffix}"
        s_id = f"NG12-SBR-{suffix}"
        if e_id not in e_by or s_id not in s_by:
            raise ValueError(f"Broken pairing for {g_id}: missing {e_id} or {s_id}")
        triples.append((grow, e_by[e_id], s_by[s_id]))
    _PAIRS_CACHE = triples
    return triples


def validate_fixture_pairing(gdl: dict, ext: dict, sbr: dict) -> None:
    """Raise ``ValueError`` on structural issues (no I/O)."""
    for label, doc in ("gdl", gdl), ("ext", ext), ("sbr", sbr):
        sc = doc.get("scenarios")
        if not isinstance(sc, list) or not sc:
            raise ValueError(f"{label}: scenarios must be a non-empty list")

    g_sc = gdl["scenarios"]
    e_sc = ext["scenarios"]
    s_sc = sbr["scenarios"]
    if not (len(g_sc) == len(e_sc) == len(s_sc)):
        raise ValueError(
            f"scenario count mismatch gdl={len(g_sc)} ext={len(e_sc)} sbr={len(s_sc)}"
        )

    seen: set[str] = set()
    for grow, erow, srow in zip(g_sc, e_sc, s_sc):
        for row in (grow, erow, srow):
            rid = row["id"]
            if rid in seen:
                raise ValueError(f"duplicate scenario id {rid}")
            seen.add(rid)

        gs = grow["id"].rsplit("-", 1)[-1]
        es = erow["id"].rsplit("-", 1)[-1]
        ss = srow["id"].rsplit("-", 1)[-1]
        if not (gs == es == ss):
            raise ValueError(f"suffix mismatch {grow['id']} {erow['id']} {srow['id']}")

        for row, prefix in (grow, "GDL"), (erow, "EXT"), (srow, "SBR"):
            exp = f"NG12-{prefix}-{gs}"
            if row["id"] != exp:
                raise ValueError(f"expected id {exp} got {row['id']}")
            if row["rec_id"] != grow["rec_id"]:
                raise ValueError(f"rec_id mismatch {row['id']} vs {grow['id']}")
            if row["branch_index"] != grow["branch_index"]:
                raise ValueError(f"branch_index mismatch {row['id']} vs {grow['id']}")

        age = grow.get("patient_age")
        if age is not None and not isinstance(age, (int, float)):
            raise ValueError(f"{grow['id']}: patient_age must be numeric")
        codes = grow.get("patient_snomed_codes")
        if not isinstance(codes, list) or not all(isinstance(x, str) for x in codes):
            raise ValueError(f"{grow['id']}: patient_snomed_codes must be string list")
