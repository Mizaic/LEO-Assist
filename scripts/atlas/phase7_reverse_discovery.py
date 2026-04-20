"""
Phase 7 - Reverse Traceability Discovery (read-only).

Builds:
  1. Implementation manifest from services/, libs/, scripts/, services/ui/src/.
  2. Atlas covered-path index from local DO YAMLs (whose locations are
     mapped to Atlas DOs via phase9/atlas-id-mapping CSVs and the
     bidirectional traceability we already established).
  3. Per-service uncovered-paths report with size and risk-pattern hits.
  4. Candidate-risk report (pattern-sweep) with similarity score against
     existing Atlas risks (de-dup at >= 0.75).

No mutations. All outputs are markdown/csv files in design-controls/.
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DC = ROOT / "design-controls"
ATLAS_BASELINE = DC / "atlas-baseline-2026-04-19" / "traceability-matrix.json"

OUT_MANIFEST = DC / "phase7-implementation-manifest.csv"
OUT_GAPS_MD = DC / "phase7-reverse-traceability-gaps.md"
OUT_GAPS_CSV = DC / "phase7-reverse-traceability-gaps.csv"
OUT_RISKS_MD = DC / "phase7-candidate-risks.md"
OUT_RISKS_CSV = DC / "phase7-candidate-risks.csv"

SCAN_ROOTS = [
    ("services", "*.py"),
    ("libs", "*.py"),
    ("scripts", "*.py"),
    ("services/ui/src", "*.ts"),
    ("services/ui/src", "*.tsx"),
]

EXCLUDE_PATH_PARTS = {
    "__pycache__",
    "node_modules",
    ".next",
    ".git",
    "build",
    "dist",
}

EXCLUDE_FILE_PATTERNS = [
    re.compile(r".*__init__\.py$"),
    re.compile(r".*\.test\.(ts|tsx)$"),
    re.compile(r".*\.spec\.(ts|tsx)$"),
    re.compile(r"^test_.*\.py$"),
    re.compile(r".*_test\.py$"),
    re.compile(r".*conftest\.py$"),
    re.compile(r".*\.d\.ts$"),
]

# Files to exclude from the risk-pattern sweep only (still in coverage report).
RISK_SCAN_EXCLUDE = [
    re.compile(r"^scripts/atlas/phase\d.*\.py$"),
    re.compile(r"^scripts/atlas/_.*\.py$"),
]

# A line is considered "regex/test scaffolding" and skipped from pattern hits.
_LINE_NOISE = re.compile(r"re\.compile|^\s*r['\"]|^\s*['\"][^'\"]*\\s\*=")

TEST_DIR_PARTS = {"tests", "__tests__", "e2e"}

RISK_PATTERNS: list[tuple[str, str, str]] = [
    (
        "raw_phi_logging",
        r"(logger|logging)\.(info|warning|error|debug)\([^)]{0,200}"
        r"(nhs_number|patient[_-]?id|encounter[_-]?text|document[_-]?text|"
        r"patient_name)",
        "Patient identifier or clinical text appears inside a logger call - "
        "potential PHI leak via application logs",
    ),
    (
        "auth_bypass",
        r"(skip|disable|bypass)[_-]?auth|allow_unauthenticated|"
        r"verify_token\s*=\s*False",
        "Auth bypass / disabled token verification",
    ),
    (
        "hardcoded_secret",
        r"(api[_-]?key|secret|token|password)\s*=\s*['\"][A-Za-z0-9_\-/+=]{16,}['\"]",
        "Possible hardcoded secret literal in source",
    ),
    (
        "missing_org_scope",
        r"MATCH\s*\(\s*\w*\s*:\s*Patient\s*\)(?![^\n]{0,200}org_id)",
        "Cypher MATCH on Patient without org_id filter on same line",
    ),
    (
        "raw_llm_passthrough",
        r"return\s+(llm_response|response)\.text|"
        r"\.write_back\([^)]*llm_raw|"
        r"auto_code\s*=\s*True",
        "Raw LLM output written back without HITL gate",
    ),
    (
        "weak_tls",
        r"verify\s*=\s*False|ssl_verify\s*=\s*False|InsecureRequestWarning",
        "TLS verification disabled in HTTPS / Bolt client",
    ),
    (
        "broad_except_silent",
        r"except\s+Exception\s*:\s*\n\s*pass\b",
        "Bare except: pass - silent failure mode",
    ),
    (
        "subprocess_shell",
        r"subprocess\.(run|Popen|call|check_output)\([^)]*shell\s*=\s*True",
        "Shell injection risk via subprocess(..., shell=True)",
    ),
    (
        "yaml_load_unsafe",
        r"yaml\.load\((?![^)]*Loader\s*=\s*yaml\.SafeLoader)",
        "Unsafe yaml.load (deserialisation risk)",
    ),
    (
        "eval_or_exec",
        r"\beval\s*\(|\bexec\s*\(",
        "eval()/exec() usage - arbitrary code execution risk",
    ),
    (
        "deid_bypass",
        r"deid\s*=\s*False|skip_deid|raw_text\s*=\s*True",
        "De-identification bypass before LLM call",
    ),
    (
        "audit_skip",
        r"skip_audit|audit_disabled|audit\s*=\s*False",
        "Audit logging disabled",
    ),
]


def is_excluded(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE_PATH_PARTS:
        return True
    if parts & TEST_DIR_PARTS:
        return True
    name = path.name
    return any(p.match(name) for p in EXCLUDE_FILE_PATTERNS)


def build_manifest() -> list[dict]:
    seen: set[Path] = set()
    rows: list[dict] = []
    for sub, pattern in SCAN_ROOTS:
        base = ROOT / sub
        if not base.exists():
            continue
        for f in base.rglob(pattern):
            if not f.is_file() or f in seen:
                continue
            rel = f.relative_to(ROOT)
            if is_excluded(rel):
                continue
            seen.add(f)
            try:
                loc = sum(1 for _ in f.read_text(errors="ignore").splitlines())
            except Exception:
                loc = 0
            rows.append(
                {
                    "path": str(rel),
                    "service": _service_bucket(rel),
                    "loc": loc,
                }
            )
    rows.sort(key=lambda r: r["path"])
    return rows


def _service_bucket(rel: Path) -> str:
    parts = rel.parts
    if parts[0] == "services" and len(parts) >= 2:
        return f"services/{parts[1]}"
    if parts[0] == "libs" and len(parts) >= 2:
        return f"libs/{parts[1]}"
    if parts[0] == "scripts":
        return "scripts"
    return parts[0]


def _class_for_bucket(bucket: str) -> str:
    """Heuristic safety-class hint for the per-service bucket.

    Per design-controls-first.mdc proportionality gate:
      - scripts/ = internal tooling -> Class A (DI/DO only if new capability)
      - everything else (services/, libs/) ships in product -> Class B+
    """
    if bucket == "scripts":
        return "A"
    return "B+"


def _yaml_locations(yaml_path: Path) -> list[str]:
    """Cheap YAML reader pulling location: lines under artifacts:.

    Avoids the pyyaml dependency in this script.
    """
    locations: list[str] = []
    in_artifacts = False
    artifact_indent = -1
    try:
        text = yaml_path.read_text()
    except Exception:
        return locations
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        if stripped.startswith("artifacts:"):
            in_artifacts = True
            artifact_indent = indent
            continue
        if in_artifacts and indent <= artifact_indent and stripped.endswith(":"):
            in_artifacts = False
        if in_artifacts and stripped.startswith("location:"):
            val = stripped.split(":", 1)[1].strip().strip("\"'")
            if val:
                locations.append(val)
        if (
            stripped.startswith("file_structure:")
            or stripped.startswith("source_paths:")
            or stripped.startswith("test_file_paths:")
        ):
            in_artifacts = True
            artifact_indent = indent
            continue
        if (
            in_artifacts
            and stripped.startswith("- ")
            and not stripped.startswith("- artifact_type")
        ):
            val = stripped[2:].strip().strip("\"'")
            if val and not val.endswith(":") and "/" in val:
                locations.append(val)
    return locations


_FILE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml", ".sql", ".cypher", ".md"}


def build_covered_paths() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return (file_coverage, dir_coverage).

    A path is covered ONLY if it matches a file_coverage entry exactly OR
    one of its ancestors appears in dir_coverage. Files referenced by a DI/DO
    do NOT cover their parent directory; only explicit directory references
    do (path ending with '/' or with no recognised file extension).
    """
    file_coverage: dict[str, set[str]] = defaultdict(set)
    dir_coverage: dict[str, set[str]] = defaultdict(set)
    for sub in ("design-outputs", "design-inputs", "verification-tests"):
        d = DC / sub
        if not d.exists():
            continue
        for yf in d.glob("*.yaml"):
            artefact_id = yf.stem
            for loc in _yaml_locations(yf):
                norm = loc.lstrip("./").rstrip()
                if not norm:
                    continue
                p = Path(norm)
                ext = p.suffix.lower()
                if ext in _FILE_EXTS:
                    file_coverage[norm].add(artefact_id)
                else:
                    # Treat as directory reference
                    key = norm.rstrip("/") + "/"
                    dir_coverage[key].add(artefact_id)
    return file_coverage, dir_coverage


def is_covered(
    path: str,
    file_coverage: dict[str, set[str]],
    dir_coverage: dict[str, set[str]],
) -> tuple[bool, set[str]]:
    if path in file_coverage:
        return True, file_coverage[path]
    p = Path(path)
    while p.parent != Path("."):
        key = str(p.parent) + "/"
        if key in dir_coverage:
            return True, dir_coverage[key]
        p = p.parent
    return False, set()


def scan_risk_patterns(file_path: Path, rel_path: str) -> list[tuple[str, int, str]]:
    """Return list of (pattern_id, line_number, snippet) hits.

    Implements two extra checks beyond a flat regex match:
      * Skip lines that look like regex literal scaffolding so the discovery
        script's own patterns don't count.
      * For ``missing_org_scope``, look for ``org_id`` within a 12-line window
        before/after the ``MATCH (Patient)`` and only flag when none is found.
    """
    hits: list[tuple[str, int, str]] = []
    if any(p.match(rel_path) for p in RISK_SCAN_EXCLUDE):
        return hits
    try:
        text = file_path.read_text(errors="ignore")
    except Exception:
        return hits
    lines = text.splitlines()
    for pid, regex, _desc in RISK_PATTERNS:
        try:
            cre = re.compile(regex, re.IGNORECASE)
        except re.error:
            continue
        for ln, line in enumerate(lines, 1):
            if not cre.search(line):
                continue
            if _LINE_NOISE.search(line):
                continue
            if pid == "missing_org_scope":
                window = "\n".join(lines[max(0, ln - 12) : ln + 12]).lower()
                if "org_id" in window or "$org_id" in window:
                    continue
            snippet = line.strip()[:180]
            hits.append((pid, ln, snippet))
            if len(hits) > 200:
                return hits
    return hits


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]{4,}", text.lower())}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_atlas_risks() -> list[dict]:
    if not ATLAS_BASELINE.exists():
        return []
    matrix = json.loads(ATLAS_BASELINE.read_text())
    return [n for n in matrix.get("nodes", []) if n.get("dcType") == "risk"]


def best_risk_match(text: str, atlas_risks: list[dict]) -> tuple[float, dict | None]:
    toks = _tokens(text)
    best = (0.0, None)
    for r in atlas_risks:
        title = r.get("title") or ""
        desc = r.get("description") or ""
        ratio = SequenceMatcher(None, text.lower(), (title + " " + desc).lower()).ratio()
        jac = _jaccard(toks, _tokens(title + " " + desc))
        score = max(ratio * 0.6 + jac * 0.4, ratio, jac)
        if score > best[0]:
            best = (score, r)
    return best


def main() -> None:
    print("Phase 7 - reverse-traceability discovery starting...")
    manifest = build_manifest()
    print(f"  manifest: {len(manifest)} source files")
    file_coverage, dir_coverage = build_covered_paths()
    print(
        f"  covered files: {len(file_coverage)}, "
        f"covered directories: {len(dir_coverage)}"
    )
    atlas_risks = load_atlas_risks()
    print(f"  atlas risks (for de-dup): {len(atlas_risks)}")

    # ----- per-service gap report -----
    per_service = defaultdict(lambda: {"files": [], "uncovered": []})
    for row in manifest:
        bucket = row["service"]
        per_service[bucket]["files"].append(row)
        covered, owners = is_covered(row["path"], file_coverage, dir_coverage)
        if not covered:
            per_service[bucket]["uncovered"].append(row)

    OUT_MANIFEST.write_text(_csv(manifest, ["path", "service", "loc"]))
    print(f"  wrote {OUT_MANIFEST.name}")

    gap_rows: list[dict] = []
    for bucket in sorted(per_service):
        for f in per_service[bucket]["uncovered"]:
            gap_rows.append(
                {
                    "service": bucket,
                    "path": f["path"],
                    "loc": f["loc"],
                }
            )
    OUT_GAPS_CSV.write_text(_csv(gap_rows, ["service", "path", "loc"]))

    md = ["# Phase 7 - Reverse Traceability Gaps\n\n"]
    md.append(
        "Implementation files in the repo with no DI/DO/VT YAML referencing them. "
        "Sorted by service bucket. Coverage is computed file-level then directory-level "
        "(a DI/DO that references a directory covers everything below it).\n\n"
        "**Safety-class hint** uses the proportionality gate from "
        "`design-controls-first.mdc`:\n"
        "- `scripts/` -> Class A (internal tooling; DI/DO only if a new capability)\n"
        "- everything else -> Class B+ (full DI/DO/VT chain required)\n\n"
        "Phase 8 will create UN/DI/DO/VT entries for the **Class B+ uncovered** "
        "set; Class A scripts are listed for awareness only.\n\n"
    )
    md.append("## Summary by service\n\n")
    md.append("| Service bucket | Class | Files total | Uncovered | LoC uncovered |\n")
    md.append("|---|---|---|---|---|\n")
    summary = []
    for bucket in sorted(per_service):
        total = len(per_service[bucket]["files"])
        unc = len(per_service[bucket]["uncovered"])
        loc_unc = sum(f["loc"] for f in per_service[bucket]["uncovered"])
        cls = _class_for_bucket(bucket)
        summary.append((bucket, cls, total, unc, loc_unc))
        md.append(f"| `{bucket}` | {cls} | {total} | {unc} | {loc_unc} |\n")
    total_total = sum(s[2] for s in summary)
    total_unc = sum(s[3] for s in summary)
    total_loc = sum(s[4] for s in summary)
    bplus_unc = sum(s[3] for s in summary if s[1] == "B+")
    bplus_loc = sum(s[4] for s in summary if s[1] == "B+")
    md.append(
        f"| **TOTAL** |  | **{total_total}** | **{total_unc}** "
        f"({total_unc * 100 / max(total_total, 1):.0f}%) | **{total_loc}** |\n"
    )
    md.append(
        f"| **CLASS B+ TOTAL** |  |  | **{bplus_unc}** | **{bplus_loc}** |\n\n"
    )
    md.append("## Class B+ uncovered files (Phase 8 candidates)\n\n")
    for bucket in sorted(per_service):
        if _class_for_bucket(bucket) != "B+":
            continue
        unc = per_service[bucket]["uncovered"]
        if not unc:
            continue
        md.append(f"### {bucket}\n\n")
        for f in sorted(unc, key=lambda r: -r["loc"]):
            md.append(f"- `{f['path']}` ({f['loc']} loc)\n")
        md.append("\n")
    md.append("## Class A uncovered files (`scripts/`, informational)\n\n")
    for bucket in sorted(per_service):
        if _class_for_bucket(bucket) != "A":
            continue
        unc = per_service[bucket]["uncovered"]
        if not unc:
            continue
        md.append(f"<details><summary>{bucket} ({len(unc)} files)</summary>\n\n")
        for f in sorted(unc, key=lambda r: -r["loc"])[:50]:
            md.append(f"- `{f['path']}` ({f['loc']} loc)\n")
        if len(unc) > 50:
            md.append(f"- _... {len(unc) - 50} more omitted_\n")
        md.append("\n</details>\n\n")
    OUT_GAPS_MD.write_text("".join(md))
    print(
        f"  wrote {OUT_GAPS_MD.name}: {total_unc}/{total_total} files uncovered "
        f"({total_loc} loc); Class B+ uncovered: {bplus_unc} files / {bplus_loc} loc"
    )

    # ----- candidate-risk pattern sweep -----
    print("Scanning for risk patterns across uncovered files...")
    candidate_rows: list[dict] = []
    for bucket in sorted(per_service):
        for f in per_service[bucket]["uncovered"]:
            hits = scan_risk_patterns(ROOT / f["path"], f["path"])
            for pid, ln, snippet in hits:
                desc = next(d for p, _, d in RISK_PATTERNS if p == pid)
                # candidate risk text = "<pattern desc> at <path>:<ln>"
                candidate_text = f"{desc} ({f['path']}:{ln})"
                score, atlas_match = best_risk_match(desc, atlas_risks)
                candidate_rows.append(
                    {
                        "service": bucket,
                        "path": f["path"],
                        "line": ln,
                        "pattern": pid,
                        "description": desc,
                        "snippet": snippet,
                        "best_atlas_id": atlas_match.get("dcId", "") if atlas_match else "",
                        "best_atlas_title": atlas_match.get("title", "") if atlas_match else "",
                        "best_score": f"{score:.3f}",
                        "dedupe_decision": (
                            "skip-already-covered" if score >= 0.75 else "candidate-create"
                        ),
                    }
                )

    OUT_RISKS_CSV.write_text(
        _csv(
            candidate_rows,
            [
                "service",
                "path",
                "line",
                "pattern",
                "description",
                "snippet",
                "best_atlas_id",
                "best_atlas_title",
                "best_score",
                "dedupe_decision",
            ],
        )
    )

    rmd = ["# Phase 7 - Candidate Risks (pattern sweep)\n\n"]
    rmd.append(
        "Risk-relevant code patterns detected in uncovered files. Each row is "
        "compared against the existing Atlas risk corpus (159 risks at the "
        "baseline snapshot). Hits with similarity >= 0.75 are pre-flagged as "
        "skip-already-covered; the rest are candidate-create and will be "
        "re-probed against live Atlas in Phase 8 before any creation.\n\n"
    )
    by_pattern: dict[str, list] = defaultdict(list)
    for r in candidate_rows:
        by_pattern[r["pattern"]].append(r)
    rmd.append("| Pattern | Hits | Skip (>=0.75) | Candidate-create |\n")
    rmd.append("|---|---|---|---|\n")
    for pid in sorted(by_pattern):
        rows = by_pattern[pid]
        skip = sum(1 for r in rows if r["dedupe_decision"] == "skip-already-covered")
        create = sum(1 for r in rows if r["dedupe_decision"] == "candidate-create")
        rmd.append(f"| `{pid}` | {len(rows)} | {skip} | {create} |\n")
    rmd.append(f"| **TOTAL** | **{len(candidate_rows)}** | **"
               f"{sum(1 for r in candidate_rows if r['dedupe_decision']=='skip-already-covered')}** | **"
               f"{sum(1 for r in candidate_rows if r['dedupe_decision']=='candidate-create')}** |\n\n")

    rmd.append("## Top candidate-create hits per pattern (max 25 each)\n\n")
    for pid in sorted(by_pattern):
        rows = [r for r in by_pattern[pid] if r["dedupe_decision"] == "candidate-create"]
        if not rows:
            continue
        rmd.append(f"### `{pid}` -- {next(d for p, _, d in RISK_PATTERNS if p == pid)}\n\n")
        for r in rows[:25]:
            rmd.append(
                f"- `{r['path']}:{r['line']}` (best Atlas: "
                f"{r['best_atlas_id'] or 'none'} score {r['best_score']})\n"
                f"  - `{r['snippet']}`\n"
            )
        if len(rows) > 25:
            rmd.append(f"- _... {len(rows) - 25} more hits omitted_\n")
        rmd.append("\n")

    OUT_RISKS_MD.write_text("".join(rmd))
    print(f"  wrote {OUT_RISKS_MD.name}: {len(candidate_rows)} pattern hits")
    print("Phase 7 discovery done.")


def _csv(rows: list[dict], cols: list[str]) -> str:
    import io

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in cols})
    return buf.getvalue()


if __name__ == "__main__":
    main()
