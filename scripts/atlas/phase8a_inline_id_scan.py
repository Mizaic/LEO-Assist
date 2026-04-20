"""
Phase 8a - Inline ID Claim Scan (read-only).

Many files in the 144 Class B+ uncovered set actually reference a local
DI/DO/R/VT/UN ID in their docstring or comments (e.g. "See DI-LEO-AI-129").
They are flagged as uncovered only because the DI's file_structure field
never listed them.

This script:
  1. Walks the same Class B+ uncovered set computed by Phase 7
     (read from `phase7-reverse-traceability-gaps.csv`).
  2. Greps each file for inline `DI-LEO-AI-NNN`, `DO-LEO-AI-NNN`,
     `R-LEO-AI-NNN`, `VT-LEO-AI-NNN`, `UN-LEO-AI-NNN` references.
  3. Resolves each local ID to its Atlas dcId via
     `atlas-id-mapping.csv`.
  4. Writes:
       phase8a-inline-claims.csv  -- one row per (file, local_id, atlas_id)
       phase8a-truly-uncovered.csv -- file paths with no claim of any kind
       phase8a-summary.md          -- human report

No Atlas mutations.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DC = ROOT / "design-controls"

GAPS_CSV = DC / "phase7-reverse-traceability-gaps.csv"
MAPPING_CSV = DC / "atlas-id-mapping.csv"

OUT_CLAIMS = DC / "phase8a-inline-claims.csv"
OUT_NO_CLAIM = DC / "phase8a-truly-uncovered.csv"
OUT_SUMMARY = DC / "phase8a-summary.md"

ID_REGEX = re.compile(r"\b(DI|DO|R|VT|UN|VAL)-LEO-AI-\d+\b")


def load_mapping() -> dict[str, dict[str, str]]:
    """local_id -> {artefact_type, atlas_id, atlas_title, similarity, match_type}."""
    out: dict[str, dict[str, str]] = {}
    if not MAPPING_CSV.exists():
        return out
    for row in csv.DictReader(MAPPING_CSV.open()):
        lid = (row.get("local_id") or "").strip()
        if not lid:
            continue
        out[lid] = {
            "artefact_type": row.get("artefact_type", ""),
            "atlas_id": row.get("atlas_id", ""),
            "atlas_title": row.get("atlas_title", ""),
            "similarity": row.get("similarity", ""),
            "match_type": row.get("match_type", ""),
        }
    return out


def load_class_bplus_paths() -> list[dict[str, str]]:
    rows = []
    for r in csv.DictReader(GAPS_CSV.open()):
        if r.get("service") == "scripts":
            continue
        rows.append(r)
    return rows


def scan_file(path: Path) -> set[str]:
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return set()
    return {m.group(0) for m in ID_REGEX.finditer(text)}


def main() -> None:
    mapping = load_mapping()
    print(f"Loaded {len(mapping)} local-id -> atlas-id mappings")

    paths = load_class_bplus_paths()
    print(f"Class B+ uncovered files to scan: {len(paths)}")

    claim_rows: list[dict[str, str]] = []
    no_claim_rows: list[dict[str, str]] = []
    file_to_ids: dict[str, set[str]] = {}

    for p in paths:
        full = ROOT / p["path"]
        ids = scan_file(full)
        file_to_ids[p["path"]] = ids
        if not ids:
            no_claim_rows.append(p)
            continue
        for local_id in sorted(ids):
            m = mapping.get(local_id, {})
            claim_rows.append(
                {
                    "service": p["service"],
                    "path": p["path"],
                    "loc": p["loc"],
                    "local_id": local_id,
                    "artefact_type": m.get("artefact_type", "?"),
                    "atlas_id": m.get("atlas_id", ""),
                    "atlas_title": m.get("atlas_title", ""),
                    "match_type": m.get("match_type", ""),
                    "similarity": m.get("similarity", ""),
                }
            )

    _write_csv(
        OUT_CLAIMS,
        claim_rows,
        [
            "service",
            "path",
            "loc",
            "local_id",
            "artefact_type",
            "atlas_id",
            "atlas_title",
            "match_type",
            "similarity",
        ],
    )
    _write_csv(OUT_NO_CLAIM, no_claim_rows, ["service", "path", "loc"])

    files_with_claim = sum(1 for ids in file_to_ids.values() if ids)
    files_with_resolved = sum(
        1
        for ids in file_to_ids.values()
        if any(mapping.get(i, {}).get("atlas_id") for i in ids)
    )
    files_no_claim = len(no_claim_rows)

    by_artefact = defaultdict(int)
    by_resolved = defaultdict(int)
    for r in claim_rows:
        by_artefact[r["artefact_type"] or "?"] += 1
        if r["atlas_id"]:
            by_resolved[r["artefact_type"] or "?"] += 1

    md = ["# Phase 8a - Inline ID Claim Scan\n\n"]
    md.append(
        "Class B+ uncovered files were grepped for `DI-LEO-AI-NNN` / "
        "`DO-LEO-AI-NNN` / `R-LEO-AI-NNN` / `VT-LEO-AI-NNN` / `UN-LEO-AI-NNN` "
        "references in source. Each match was resolved to its Atlas dcId via "
        "`atlas-id-mapping.csv`.\n\n"
    )
    md.append("## Headline\n\n")
    md.append(f"- Scanned files: **{len(paths)}**\n")
    md.append(
        f"- Files with at least one inline ID claim: **{files_with_claim}** "
        f"({files_with_claim * 100 / max(len(paths), 1):.0f}%)\n"
    )
    md.append(
        f"- Files whose claims resolved to >= 1 Atlas artefact: "
        f"**{files_with_resolved}** ({files_with_resolved * 100 / max(len(paths), 1):.0f}%)\n"
    )
    md.append(
        f"- Files with NO inline claim (truly uncovered, candidates for new DIs): "
        f"**{files_no_claim}**\n\n"
    )
    md.append("## Claims by artefact type\n\n")
    md.append("| Artefact type | Total claims | Resolved to Atlas |\n")
    md.append("|---|---|---|\n")
    for k in sorted(by_artefact):
        md.append(f"| `{k}` | {by_artefact[k]} | {by_resolved.get(k, 0)} |\n")
    md.append("\n")

    md.append("## Truly-uncovered files by service (next: bucket into new DIs)\n\n")
    by_svc = defaultdict(list)
    for p in no_claim_rows:
        by_svc[p["service"]].append(p)
    md.append("| Service | Files | LoC |\n")
    md.append("|---|---|---|\n")
    grand_files = grand_loc = 0
    for svc in sorted(by_svc):
        n = len(by_svc[svc])
        loc = sum(int(r["loc"]) for r in by_svc[svc])
        grand_files += n
        grand_loc += loc
        md.append(f"| `{svc}` | {n} | {loc} |\n")
    md.append(f"| **TOTAL** | **{grand_files}** | **{grand_loc}** |\n\n")

    md.append("## Detail of truly-uncovered files\n\n")
    for svc in sorted(by_svc):
        md.append(f"### {svc}\n\n")
        for p in sorted(by_svc[svc], key=lambda r: -int(r["loc"])):
            md.append(f"- `{p['path']}` ({p['loc']} loc)\n")
        md.append("\n")

    OUT_SUMMARY.write_text("".join(md))
    print(f"  wrote {OUT_CLAIMS.name}: {len(claim_rows)} claim rows")
    print(f"  wrote {OUT_NO_CLAIM.name}: {len(no_claim_rows)} truly-uncovered files")
    print(f"  wrote {OUT_SUMMARY.name}")


def _write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    import io

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in cols})
    path.write_text(buf.getvalue())


if __name__ == "__main__":
    main()
