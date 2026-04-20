"""Phase 13a - read-only audit: file <-> Atlas DO traceability.

Builds three artefacts:

  1. compliance/atlas-migration-evidence/phase13a-legacy-to-atlas.csv
     Authoritative legacy_id -> atlas_dcid map combining every ledger.

  2. compliance/atlas-migration-evidence/phase13a-do-source-reference-audit.csv
     For every Atlas DO we know about: dcId, expected source_paths
     (recovered from the pre-deletion local YAMLs and the migration
     ledgers), and the migration phase that wrote it.

  3. compliance/atlas-migration-evidence/phase13a-file-trace-audit.csv
     For every Class B+ source file in libs/ + services/: legacy_ids
     found in file, mapped Atlas DI/DO ids, header_state
     (none / legacy / atlas), bucket_dir, owning_atlas_di, owning_atlas_do.

Plus a markdown summary at phase13a-summary.md.

This script is READ-ONLY. It does not call any mutating Atlas tool.
"""

from __future__ import annotations

import csv
import io
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "compliance" / "atlas-migration-evidence"
PRE_DELETE_SHA = "fd295e7054092dcc8e9258167beff3259c2cf487"

LEGACY_DO_GLOB = "design-controls/design-outputs/DO-LEO-AI-*.yaml"
LEGACY_DI_GLOB = "design-controls/design-inputs/DI-LEO-AI-*.yaml"

ID_RE = re.compile(r"\b((?:DI|DO|UN|VT|VAL|R)-LEO-AI-\d+)\b")
ATLAS_RE = re.compile(r"\b((?:DI|DO|UN|VT|VAL|R)-[A-F0-9]{8})\b")

SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}
EXCLUDE_DIRS = {"node_modules", "__pycache__", ".next", "dist", "build", ".venv"}


def _git_show(sha: str, path: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "show", f"{sha}:{path}"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
        )
        return out.decode("utf-8", errors="ignore")
    except subprocess.CalledProcessError:
        return None


def _git_ls_tree(sha: str, prefix: str) -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", sha, prefix],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
        )
        return [
            line.strip()
            for line in out.decode("utf-8", errors="ignore").splitlines()
            if line.strip()
        ]
    except subprocess.CalledProcessError:
        return []


def load_atlas_id_mapping() -> list[dict]:
    rows: list[dict] = []
    path = EVIDENCE / "atlas-id-mapping.csv"
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("local_id") or not row.get("atlas_id"):
                continue
            rows.append(row)
    return rows


def load_phase8b_ledger() -> list[dict]:
    rows: list[dict] = []
    path = EVIDENCE / "phase8b-ledger.csv"
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def load_phase8a_truly_uncovered() -> list[dict]:
    rows: list[dict] = []
    path = EVIDENCE / "phase8a-truly-uncovered.csv"
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def load_phase9_ledger() -> list[dict]:
    rows: list[dict] = []
    path = EVIDENCE / "phase9-ledger.csv"
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def load_phase9b_ledger() -> list[dict]:
    rows: list[dict] = []
    path = EVIDENCE / "phase9b-ledger.csv"
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def load_phase10_inflight_ledger() -> list[dict]:
    rows: list[dict] = []
    path = EVIDENCE / "phase10-inflight-ledger.csv"
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def load_phase10_risk_migration() -> list[dict]:
    rows: list[dict] = []
    path = EVIDENCE / "phase10-risk-migration.csv"
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def parse_local_yaml(text: str) -> dict | None:
    try:
        docs = list(yaml.safe_load_all(text))
    except yaml.YAMLError:
        return None
    for d in docs:
        if isinstance(d, list) and d and isinstance(d[0], dict):
            return d[0]
        if isinstance(d, dict):
            return d
    return None


def extract_local_di_files(yaml_dict: dict) -> list[str]:
    """Pull file paths out of a local DI YAML."""
    techs = yaml_dict.get("technical_details") or {}
    files = techs.get("file_structure") or []
    if isinstance(files, str):
        files = [files]
    return [str(f).strip() for f in files if str(f).strip()]


def extract_local_do_files(yaml_dict: dict) -> list[str]:
    """Pull file paths out of a local DO YAML (multiple shapes)."""
    files: list[str] = []
    impl = yaml_dict.get("implementation") or {}
    artefacts = impl.get("artifacts") or []
    for a in artefacts:
        if isinstance(a, dict):
            loc = a.get("location") or a.get("path") or ""
            if loc:
                files.append(str(loc).strip())
    techs = impl.get("technical_details") or {}
    fs = techs.get("file_structure") or []
    if isinstance(fs, str):
        fs = [fs]
    files.extend(str(f).strip() for f in fs if str(f).strip())
    if "source_paths" in yaml_dict:
        sp = yaml_dict["source_paths"] or []
        if isinstance(sp, str):
            sp = [sp]
        files.extend(str(f).strip() for f in sp if str(f).strip())
    return list(dict.fromkeys(files))


def extract_local_di_links(yaml_dict: dict) -> list[str]:
    """Local DOs reference parent DIs via traceability.design_inputs."""
    trace = yaml_dict.get("traceability") or {}
    dis = trace.get("design_inputs") or trace.get("design_input") or []
    if isinstance(dis, str):
        dis = [dis]
    return [str(d).strip() for d in dis if str(d).strip()]


def build_legacy_to_atlas() -> tuple[dict[str, str], list[dict]]:
    """Returns (legacy_id -> atlas_dcid, audit_rows)."""
    mapping: dict[str, str] = {}
    audit: list[dict] = []

    for r in load_atlas_id_mapping():
        local = r["local_id"]
        atlas = r["atlas_id"]
        if not atlas:
            continue
        mapping[local] = atlas
        audit.append({
            "legacy_id": local,
            "atlas_dcid": atlas,
            "kind": r.get("artefact_type", ""),
            "source_ledger": "atlas-id-mapping.csv",
            "phase": "0-3",
            "decision": r.get("match_type", ""),
        })

    for r in load_phase10_risk_migration():
        local = r["local_id"]
        atlas = r["atlas_id"]
        if not atlas:
            continue
        mapping[local] = atlas
        audit.append({
            "legacy_id": local,
            "atlas_dcid": atlas,
            "kind": "R",
            "source_ledger": "phase10-risk-migration.csv",
            "phase": "4",
            "decision": r.get("decision", ""),
        })

    for r in load_phase10_inflight_ledger():
        local = r.get("local_id", "")
        atlas = r.get("atlas_dcid", "")
        if not local or not atlas:
            continue
        kind_map = {
            "user_need": "UN", "design_input": "DI", "design_output": "DO",
            "verification_test": "VT", "validation_test": "VAL", "risk": "R",
        }
        mapping[local] = atlas
        audit.append({
            "legacy_id": local,
            "atlas_dcid": atlas,
            "kind": kind_map.get(r.get("kind", ""), r.get("kind", "")),
            "source_ledger": "phase10-inflight-ledger.csv",
            "phase": "10",
            "decision": r.get("decision", ""),
        })

    for r in load_phase9_ledger():
        local = r.get("local_id", "")
        atlas_do = r.get("atlas_do_dcid", "")
        atlas_di = r.get("atlas_di_dcid", "")
        kind = r.get("kind", "")
        if kind == "do" and local and atlas_do:
            mapping[local] = atlas_do
            audit.append({
                "legacy_id": local,
                "atlas_dcid": atlas_do,
                "kind": "DO",
                "source_ledger": "phase9-ledger.csv",
                "phase": "9a",
                "decision": r.get("decision", ""),
            })
        if kind == "di_title_update" and local and atlas_di:
            if local not in mapping:
                mapping[local] = atlas_di
                audit.append({
                    "legacy_id": local,
                    "atlas_dcid": atlas_di,
                    "kind": "DI",
                    "source_ledger": "phase9-ledger.csv",
                    "phase": "9a",
                    "decision": r.get("decision", ""),
                })

    return mapping, audit


def build_do_source_reference_records(
    legacy_to_atlas: dict[str, str],
) -> list[dict]:
    """Recover what files each Atlas DO covers, from every available source."""
    records: dict[str, dict] = {}

    def upsert(atlas_dcid: str, files: list[str], legacy_id: str, phase: str):
        if not atlas_dcid:
            return
        rec = records.setdefault(atlas_dcid, {
            "atlas_dcid": atlas_dcid,
            "legacy_ids": set(),
            "expected_source_paths": set(),
            "phases_with_evidence": set(),
        })
        if legacy_id:
            rec["legacy_ids"].add(legacy_id)
        for f in files:
            if f:
                rec["expected_source_paths"].add(f)
        rec["phases_with_evidence"].add(phase)

    legacy_do_files = _git_ls_tree(PRE_DELETE_SHA, "design-controls/design-outputs/")
    print(f"  Phase 0-3: probing {len(legacy_do_files)} local DO YAMLs...")
    for path in legacy_do_files:
        text = _git_show(PRE_DELETE_SHA, path)
        if not text:
            continue
        d = parse_local_yaml(text)
        if not d:
            continue
        local_id = d.get("id") or Path(path).stem
        atlas_do = legacy_to_atlas.get(local_id, "")
        files = extract_local_do_files(d)
        if not files:
            di_links = extract_local_di_links(d)
            for di_local in di_links:
                di_path = (
                    f"design-controls/design-inputs/{di_local}.yaml"
                )
                di_text = _git_show(PRE_DELETE_SHA, di_path)
                if not di_text:
                    continue
                di_yaml = parse_local_yaml(di_text)
                if not di_yaml:
                    continue
                files.extend(extract_local_di_files(di_yaml))
        upsert(atlas_do, files, local_id, "0-3 (local DO YAML)")

    legacy_di_files = _git_ls_tree(PRE_DELETE_SHA, "design-controls/design-inputs/")
    print(f"  Phase 0-3: probing {len(legacy_di_files)} local DI YAMLs...")
    for path in legacy_di_files:
        text = _git_show(PRE_DELETE_SHA, path)
        if not text:
            continue
        d = parse_local_yaml(text)
        if not d:
            continue
        local_di = d.get("id") or Path(path).stem
        atlas_di = legacy_to_atlas.get(local_di, "")
        if not atlas_di:
            continue
        files = extract_local_di_files(d)
        if not files:
            continue

    print("  Phase 8b: parsing reverse-discovery ledger ...")
    p8b = load_phase8b_ledger()
    p8a = load_phase8a_truly_uncovered()
    bucket_files: dict[str, list[str]] = defaultdict(list)
    for r in p8a:
        bucket = r.get("service", "").strip()
        path = r.get("path", "").strip()
        if bucket and path:
            bucket_files[bucket].append(path)
    for r in p8b:
        if r.get("kind") != "do" or r.get("decision") != "created":
            continue
        bucket = r.get("bucket", "").strip()
        atlas_dcid = r.get("atlas_id", "").strip()
        if not atlas_dcid:
            continue
        files = bucket_files.get(bucket, [])
        upsert(atlas_dcid, files, "", "8b (reverse-discovery bucket)")

    print("  Phase 9a: parsing orphan-DI-close ledger ...")
    for r in load_phase9_ledger():
        if r.get("kind") != "do":
            continue
        atlas_dcid = r.get("atlas_do_dcid", "")
        local_di = r.get("local_id", "")
        if not atlas_dcid or not local_di:
            continue
        di_path = f"design-controls/design-inputs/{local_di}.yaml"
        text = _git_show(PRE_DELETE_SHA, di_path)
        if not text:
            continue
        di_yaml = parse_local_yaml(text)
        files = extract_local_di_files(di_yaml) if di_yaml else []
        upsert(atlas_dcid, files, local_di, "9a (DO created from local DI)")

    print("  Phase 10: parsing in-flight ledger ...")
    for r in load_phase10_inflight_ledger():
        if r.get("kind") != "design_output":
            continue
        atlas_dcid = r.get("atlas_dcid", "")
        local_id = r.get("local_id", "")
        if not atlas_dcid or not local_id:
            continue
        do_path = f"design-controls/design-outputs/{local_id}.yaml"
        text = _git_show(PRE_DELETE_SHA, do_path)
        if not text:
            text = _git_show("HEAD", do_path)
        if not text:
            continue
        do_yaml = parse_local_yaml(text)
        files = extract_local_do_files(do_yaml) if do_yaml else []
        upsert(atlas_dcid, files, local_id, "10 (in-flight DO)")

    out: list[dict] = []
    for atlas_dcid, rec in records.items():
        out.append({
            "atlas_dcid": atlas_dcid,
            "legacy_ids": ";".join(sorted(rec["legacy_ids"])),
            "expected_source_path_count": len(rec["expected_source_paths"]),
            "expected_source_paths": ";".join(sorted(rec["expected_source_paths"])),
            "phases_with_evidence": ";".join(sorted(rec["phases_with_evidence"])),
        })
    out.sort(key=lambda r: r["atlas_dcid"])
    return out


def build_file_to_di_map_from_local() -> dict[str, set[str]]:
    """Walk the pre-deletion local DI YAMLs to map each file path to the local DI ids."""
    f2di: dict[str, set[str]] = defaultdict(set)
    for path in _git_ls_tree(PRE_DELETE_SHA, "design-controls/design-inputs/"):
        text = _git_show(PRE_DELETE_SHA, path)
        if not text:
            continue
        d = parse_local_yaml(text)
        if not d:
            continue
        local_di = d.get("id") or Path(path).stem
        for f in extract_local_di_files(d):
            f2di[f.lstrip("./")].add(local_di)
    return f2di


def build_file_to_do_map_from_local() -> dict[str, set[str]]:
    """Walk the pre-deletion local DO YAMLs to map each file path to the local DO ids."""
    f2do: dict[str, set[str]] = defaultdict(set)
    for path in _git_ls_tree(PRE_DELETE_SHA, "design-controls/design-outputs/"):
        text = _git_show(PRE_DELETE_SHA, path)
        if not text:
            continue
        d = parse_local_yaml(text)
        if not d:
            continue
        local_do = d.get("id") or Path(path).stem
        for f in extract_local_do_files(d):
            f2do[f.lstrip("./")].add(local_do)
    return f2do


def build_file_to_p8b_bucket() -> dict[str, tuple[str, str, str]]:
    """File path -> (bucket, atlas_di_dcid, atlas_do_dcid) from Phase 8 ledgers."""
    bucket_files: dict[str, list[str]] = defaultdict(list)
    for r in load_phase8a_truly_uncovered():
        bucket = r.get("service", "").strip()
        path = r.get("path", "").strip()
        if bucket and path:
            bucket_files[bucket].append(path)
    bucket_di: dict[str, str] = {}
    bucket_do: dict[str, str] = {}
    for r in load_phase8b_ledger():
        if r.get("decision") != "created":
            continue
        bucket = r.get("bucket", "").strip()
        atlas_dcid = r.get("atlas_id", "").strip()
        if not bucket or not atlas_dcid:
            continue
        if r.get("kind") == "di":
            bucket_di[bucket] = atlas_dcid
        elif r.get("kind") == "do":
            bucket_do[bucket] = atlas_dcid
    f2bucket: dict[str, tuple[str, str, str]] = {}
    for bucket, files in bucket_files.items():
        for f in files:
            f2bucket[f.lstrip("./")] = (
                bucket,
                bucket_di.get(bucket, ""),
                bucket_do.get(bucket, ""),
            )
    return f2bucket


def iter_source_files() -> list[str]:
    out: list[str] = []
    for top in ("libs", "services"):
        top_dir = ROOT / top
        if not top_dir.exists():
            continue
        for p in top_dir.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in SOURCE_EXTS:
                continue
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            rel = p.relative_to(ROOT).as_posix()
            out.append(rel)
    return sorted(out)


def scan_file_for_ids(path: str) -> tuple[set[str], set[str]]:
    """Return (legacy_ids_in_file, atlas_ids_in_file)."""
    try:
        text = (ROOT / path).read_text(errors="ignore")
    except Exception:
        return set(), set()
    legacy = {m.group(1) for m in ID_RE.finditer(text)}
    atlas = {m.group(1) for m in ATLAS_RE.finditer(text)}
    return legacy, atlas


def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in cols})
    path.write_text(buf.getvalue())


def main() -> int:
    print("Phase 13a - read-only file <-> Atlas DO trace audit")
    print(f"Repo: {ROOT}")
    print()

    print("[1/5] Building legacy_id -> Atlas dcId map ...")
    legacy_to_atlas, audit_rows = build_legacy_to_atlas()
    write_csv(
        EVIDENCE / "phase13a-legacy-to-atlas.csv",
        audit_rows,
        ["legacy_id", "atlas_dcid", "kind", "source_ledger", "phase", "decision"],
    )
    print(f"  -> {len(legacy_to_atlas)} legacy ids mapped to Atlas dcIds")
    print()

    print("[2/5] Recovering DO source_reference evidence "
          "from pre-deletion YAMLs + ledgers ...")
    do_records = build_do_source_reference_records(legacy_to_atlas)
    write_csv(
        EVIDENCE / "phase13a-do-source-reference-audit.csv",
        do_records,
        [
            "atlas_dcid",
            "legacy_ids",
            "expected_source_path_count",
            "expected_source_paths",
            "phases_with_evidence",
        ],
    )
    do_with_files = sum(
        1 for r in do_records if int(r["expected_source_path_count"]) > 0
    )
    print(f"  -> {len(do_records)} Atlas DOs with recoverable evidence "
          f"({do_with_files} have file paths, "
          f"{len(do_records) - do_with_files} do not)")
    print()

    print("[3/5] Building file -> local DI/DO map from pre-deletion git ...")
    f2di_local = build_file_to_di_map_from_local()
    f2do_local = build_file_to_do_map_from_local()
    print(f"  -> {len(f2di_local)} files cited by local DIs; "
          f"{len(f2do_local)} files cited by local DOs")
    print()

    print("[4/5] Building file -> Phase 8 bucket map ...")
    f2bucket = build_file_to_p8b_bucket()
    print(f"  -> {len(f2bucket)} files covered by Phase 8 buckets")
    print()

    print("[5/5] Walking Class B+ source files ...")
    files = iter_source_files()
    print(f"  -> {len(files)} files to classify")
    rows: list[dict] = []
    counts = defaultdict(int)
    for f in files:
        legacy_in_file, atlas_in_file = scan_file_for_ids(f)
        if atlas_in_file:
            header_state = "atlas"
        elif legacy_in_file:
            header_state = "legacy"
        else:
            header_state = "none"
        counts[header_state] += 1
        local_dis = f2di_local.get(f, set())
        local_dos = f2do_local.get(f, set())
        bucket_info = f2bucket.get(f)
        bucket_di = bucket_info[1] if bucket_info else ""
        bucket_do = bucket_info[2] if bucket_info else ""
        bucket_dir = bucket_info[0] if bucket_info else ""
        owning_atlas_dis = {
            legacy_to_atlas[d] for d in local_dis
            if d in legacy_to_atlas
        }
        if bucket_di:
            owning_atlas_dis.add(bucket_di)
        owning_atlas_dos = {
            legacy_to_atlas[d] for d in local_dos
            if d in legacy_to_atlas
        }
        if bucket_do:
            owning_atlas_dos.add(bucket_do)
        if owning_atlas_dis or owning_atlas_dos:
            counts["resolved_to_atlas"] += 1
        else:
            counts["unresolvable"] += 1
        rows.append({
            "path": f,
            "header_state": header_state,
            "legacy_ids_in_file": ";".join(sorted(legacy_in_file)),
            "atlas_ids_in_file": ";".join(sorted(atlas_in_file)),
            "local_dis_owning_file": ";".join(sorted(local_dis)),
            "local_dos_owning_file": ";".join(sorted(local_dos)),
            "phase8_bucket_dir": bucket_dir,
            "owning_atlas_dis": ";".join(sorted(owning_atlas_dis)),
            "owning_atlas_dos": ";".join(sorted(owning_atlas_dos)),
        })
    write_csv(
        EVIDENCE / "phase13a-file-trace-audit.csv",
        rows,
        [
            "path",
            "header_state",
            "legacy_ids_in_file",
            "atlas_ids_in_file",
            "local_dis_owning_file",
            "local_dos_owning_file",
            "phase8_bucket_dir",
            "owning_atlas_dis",
            "owning_atlas_dos",
        ],
    )
    print()
    print("== summary ==")
    for k in sorted(counts):
        print(f"  {k:20s} {counts[k]}")
    print()

    summary = EVIDENCE / "phase13a-summary.md"
    summary.write_text(_render_summary(legacy_to_atlas, do_records, rows, counts))
    print(f"  -> wrote {summary}")
    return 0


def _render_summary(
    legacy_to_atlas: dict[str, str],
    do_records: list[dict],
    file_rows: list[dict],
    counts: dict[str, int],
) -> str:
    by_state = {
        "atlas": counts.get("atlas", 0),
        "legacy": counts.get("legacy", 0),
        "none": counts.get("none", 0),
    }
    total = sum(by_state.values()) or 1
    do_total = len(do_records)
    do_with_files = sum(
        1 for r in do_records if int(r["expected_source_path_count"]) > 0
    )
    return (
        "# Phase 13a - file <-> Atlas DO trace audit (read-only)\n\n"
        "## Inputs\n\n"
        f"- {len(legacy_to_atlas)} legacy ids resolved to Atlas dcIds\n"
        "- Pre-deletion local YAMLs read from "
        f"git SHA `{PRE_DELETE_SHA}`\n"
        "- Migration ledgers in `compliance/atlas-migration-evidence/`\n\n"
        "## Forward (file -> Atlas DO)\n\n"
        f"Class B+ source files scanned: **{total}** "
        "(under `libs/` and `services/`, excluding tests)\n\n"
        "| Header state | Files | Share |\n"
        "|---|---:|---:|\n"
        f"| `atlas` (Atlas-format dcId in file) | {by_state['atlas']} | "
        f"{by_state['atlas'] / total * 100:.1f}% |\n"
        f"| `legacy` (only `*-LEO-AI-N` ids in file) | "
        f"{by_state['legacy']} | "
        f"{by_state['legacy'] / total * 100:.1f}% |\n"
        f"| `none` (no design-control reference at all) | "
        f"{by_state['none']} | "
        f"{by_state['none'] / total * 100:.1f}% |\n\n"
        f"Resolvable to at least one Atlas DI/DO via the migration ledgers: "
        f"**{counts.get('resolved_to_atlas', 0)}** files. "
        f"Cannot resolve from any ledger: "
        f"**{counts.get('unresolvable', 0)}** files. "
        "(The unresolvable bucket is the population that needs new Atlas "
        "design controls or a per-file triage in Phase 13c.)\n\n"
        "## Reverse (Atlas DO -> file)\n\n"
        f"Atlas DOs we have evidence for: **{do_total}** "
        f"(out of 252 total in Atlas, per `get_design_control_stats`).\n\n"
        f"- DOs with recoverable file paths: {do_with_files}\n"
        f"- DOs with no recoverable file paths in our ledgers: "
        f"{do_total - do_with_files}\n\n"
        "**Atlas API gap:** `get_design_control` does not return "
        "`source_reference` even though `create_design_output` and "
        "`update_design_output` accept it. We cannot read back the values "
        "we wrote; the audit therefore reconstructs expected values from "
        "(a) pre-deletion local YAMLs, and (b) the Phase 8b bucket ledger. "
        "Phase 13b will rewrite `source_reference` from this CSV "
        "(using `update_design_output`) so the field is the canonical, "
        "current truth.\n\n"
        "## Output files\n\n"
        "- `phase13a-legacy-to-atlas.csv` - full legacy_id -> atlas_dcid table\n"
        "- `phase13a-do-source-reference-audit.csv` - per-DO file evidence\n"
        "- `phase13a-file-trace-audit.csv` - per-file trace state\n"
    )


if __name__ == "__main__":
    sys.exit(main())
