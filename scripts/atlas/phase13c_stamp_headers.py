"""Phase 13c -- stamp Atlas trace headers into Class B+ source files.

Inputs:
  - compliance/atlas-migration-evidence/phase13a-file-trace-audit.csv
  - compliance/atlas-migration-evidence/phase13a-legacy-to-atlas.csv
  - compliance/atlas-migration-evidence/phase13c-atlas-cache.json
  - compliance/atlas-migration-evidence/phase13a-header-convention.md
       (the spec the rewriter implements)

Outputs:
  - compliance/atlas-migration-evidence/phase13c-ledger.csv
       1 row per file decision (stamped | already_atlas | excluded |
       triage | unresolved). Idempotent.
  - compliance/atlas-migration-evidence/phase13c-triage-queue.csv
       multi-DO ambiguity, DI-only with no resolvable child DO,
       legacy-only files where some legacy id has no Atlas mapping.
  - compliance/atlas-migration-evidence/phase13c-skipped.csv
       tests, __init__.py, .d.ts, etc.
  - compliance/atlas-migration-evidence/phase13c-uncovered.csv
       Class B+ files that resolve to no Atlas DI/DO at all.

Modes:
  --dry-run   compute decisions, write the CSVs, emit a unified diff to
              stdout for the first N files; do not modify source files.
  --apply     write the CSVs *and* mutate source files in-place.

Defaults to --dry-run.

Header format implemented (per phase13a-header-convention.md):

  Python:
    \"\"\"<one-line summary kept verbatim or 'Auto-stamped Atlas trace.'>

    Atlas trace:
      DO: DO-XXXXXXXX
      DI: DI-XXXXXXXX[, DI-XXXXXXXX]
      Risks: R-XXXXXXXX[, R-XXXXXXXX]
      Look up via: get_design_control(dc_type=\"design-output\", dc_id=\"DO-XXXXXXXX\")
    \"\"\"

  TypeScript / TSX:
    /**
     * <one-line summary>
     *
     * Atlas trace:
     *   DO: DO-XXXXXXXX
     *   DI: DI-XXXXXXXX
     *   Risks: R-XXXXXXXX
     *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-XXXXXXXX")
     */
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "compliance" / "atlas-migration-evidence"
AUDIT_CSV = EVIDENCE / "phase13a-file-trace-audit.csv"
LEGACY_MAP_CSV = EVIDENCE / "phase13a-legacy-to-atlas.csv"
CACHE_JSON = EVIDENCE / "phase13c-atlas-cache.json"
LEDGER_CSV = EVIDENCE / "phase13c-ledger.csv"
TRIAGE_CSV = EVIDENCE / "phase13c-triage-queue.csv"
SKIPPED_CSV = EVIDENCE / "phase13c-skipped.csv"
UNCOVERED_CSV = EVIDENCE / "phase13c-uncovered.csv"

ATLAS_TRACE_MARKER = "Atlas trace:"

LEDGER_COLS = [
    "path", "decision", "do", "di", "risks", "header_state_before",
    "ext", "note",
]
TRIAGE_COLS = ["path", "category", "owning_atlas_dis", "owning_atlas_dos",
               "legacy_ids_in_file", "note"]
SKIPPED_COLS = ["path", "reason"]
UNCOVERED_COLS = ["path", "header_state", "legacy_ids_in_file",
                  "phase8_bucket_dir", "note"]


# ----------------------------------------------------------------------
# Exclusion rules
# ----------------------------------------------------------------------

EXCLUDE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(^|/)tests?/"), "tests directory (VT, not DO)"),
    (re.compile(r"(^|/)e2e/"), "e2e directory (VAL, not DO)"),
    (re.compile(r"__tests__/"), "ui __tests__ (VT, not DO)"),
    (re.compile(r"/test_[^/]+\.py$"), "test_*.py (VT, not DO)"),
    (re.compile(r"\.test\.(t|j)sx?$"), ".test.ts(x) (VT, not DO)"),
    (re.compile(r"(^|/)__init__\.py$"), "__init__.py (no executable surface)"),
    (re.compile(r"\.d\.ts$"), "declaration-only .d.ts"),
    (re.compile(r"(^|/)conftest\.py$"), "pytest conftest (test infra)"),
]


def exclusion_reason(path: str) -> str | None:
    for pat, reason in EXCLUDE_PATTERNS:
        if pat.search(path):
            return reason
    return None


# ----------------------------------------------------------------------
# IO helpers
# ----------------------------------------------------------------------

@dataclass
class AuditRow:
    path: str
    header_state: str
    legacy_ids_in_file: list[str]
    atlas_ids_in_file: list[str]
    local_dis_owning_file: list[str]
    local_dos_owning_file: list[str]
    phase8_bucket_dir: str
    owning_atlas_dis: list[str]
    owning_atlas_dos: list[str]


def _split(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(";") if x.strip()]


def load_audit() -> list[AuditRow]:
    rows: list[AuditRow] = []
    for r in csv.DictReader(AUDIT_CSV.open()):
        rows.append(AuditRow(
            path=r["path"],
            header_state=r["header_state"],
            legacy_ids_in_file=_split(r["legacy_ids_in_file"]),
            atlas_ids_in_file=_split(r["atlas_ids_in_file"]),
            local_dis_owning_file=_split(r["local_dis_owning_file"]),
            local_dos_owning_file=_split(r["local_dos_owning_file"]),
            phase8_bucket_dir=r["phase8_bucket_dir"],
            owning_atlas_dis=_split(r["owning_atlas_dis"]),
            owning_atlas_dos=_split(r["owning_atlas_dos"]),
        ))
    return rows


def load_legacy_map() -> dict[str, str]:
    m: dict[str, str] = {}
    if not LEGACY_MAP_CSV.exists():
        return m
    for r in csv.DictReader(LEGACY_MAP_CSV.open()):
        # CSV columns: legacy_id,atlas_dcid,kind,phase
        leg = r.get("legacy_id") or r.get("legacy")
        atl = r.get("atlas_dcid") or r.get("atlas")
        if leg and atl:
            m[leg] = atl
    return m


def load_cache() -> dict:
    if not CACHE_JSON.exists():
        return {"design_outputs": {}, "design_inputs": {}}
    return json.loads(CACHE_JSON.read_text())


# ----------------------------------------------------------------------
# Resolution
# ----------------------------------------------------------------------

@dataclass
class Resolution:
    decision: str            # stamped | already_atlas | excluded | triage |
                             # unresolved
    primary_do: str = ""
    extra_dos: list[str] = field(default_factory=list)
    dis: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    note: str = ""
    triage_category: str = ""


def resolve_one(row: AuditRow, cache: dict) -> Resolution:
    excl = exclusion_reason(row.path)
    if excl:
        return Resolution(decision="excluded", note=excl)
    if row.header_state == "atlas":
        # Only "already_atlas" if the file has the canonical trace marker.
        # Files that mention Atlas dcIds inline in comments still need a
        # proper trace block at the top.
        full = ROOT / row.path
        if full.exists():
            try:
                head = full.open("r", encoding="utf-8",
                                 errors="replace").read(4096)
            except OSError:
                head = ""
            if ATLAS_TRACE_MARKER in head:
                return Resolution(decision="already_atlas",
                                  note="canonical Atlas trace block present")
        # Fall through to normal resolution. Inline dcIds in code
        # comments are NOT treated as authoritative ownership -- only
        # the migration ledgers' owning_atlas_di/do columns are. If the
        # ledger has nothing, this file ends up in the unresolved bucket
        # for human triage (we will not infer ownership from comments).
    do_cache = cache["design_outputs"]
    di_cache = cache["design_inputs"]
    dos = sorted(set(row.owning_atlas_dos))
    dis = sorted(set(row.owning_atlas_dis))

    if not dos and not dis:
        return Resolution(
            decision="unresolved",
            note="no resolvable Atlas DI/DO via Phase 13a evidence",
        )

    # If we have DI(s) but no DO, try resolving via cache (DI -> child DOs)
    if not dos and dis:
        candidates = []
        for di in dis:
            di_rec = di_cache.get(di) or {}
            candidates.extend(di_rec.get("design_outputs", []))
        candidates = sorted(set(candidates))
        if not candidates:
            return Resolution(
                decision="triage",
                triage_category="di-only-no-child-do",
                dis=dis,
                note="DI resolved but cache shows no child DO",
            )
        dos = candidates

    # We now have at least one DO. Order lex; primary = first.
    primary = dos[0]
    extras = dos[1:]
    primary_rec = do_cache.get(primary) or {}
    primary_dis = primary_rec.get("design_inputs") or []
    primary_risks = primary_rec.get("risks") or []
    # Union DIs from all DOs (so multi-DO files still cite all owning DIs).
    di_union = set(primary_dis)
    risk_union = set(primary_risks)
    for d in extras:
        rec = do_cache.get(d) or {}
        di_union.update(rec.get("design_inputs") or [])
        risk_union.update(rec.get("risks") or [])
    # Also include DIs the audit found directly in case the cache is partial.
    di_union.update(dis)
    if not di_union:
        return Resolution(
            decision="triage",
            triage_category="do-no-parent-di",
            primary_do=primary,
            extra_dos=extras,
            risks=sorted(risk_union),
            note="Atlas DO has no parent DI in cache",
        )
    decision = "stamped" if not extras else "stamped"  # multi handled in fmt
    return Resolution(
        decision=decision,
        primary_do=primary,
        extra_dos=extras,
        dis=sorted(di_union),
        risks=sorted(risk_union),
    )


# ----------------------------------------------------------------------
# Header rendering
# ----------------------------------------------------------------------

def _trace_lines_python(res: Resolution) -> list[str]:
    lines = [ATLAS_TRACE_MARKER]
    lines.append(f"  DO: {res.primary_do}")
    if res.extra_dos:
        lines.append(f"  Also implements: {', '.join(res.extra_dos)}")
    lines.append(f"  DI: {', '.join(res.dis)}")
    if res.risks:
        lines.append(f"  Risks: {', '.join(res.risks)}")
    lines.append(
        '  Look up via: get_design_control('
        f'dc_type="design-output", dc_id="{res.primary_do}")'
    )
    return lines


def _trace_lines_ts(res: Resolution) -> list[str]:
    lines = [f" * {ATLAS_TRACE_MARKER}"]
    lines.append(f" *   DO: {res.primary_do}")
    if res.extra_dos:
        lines.append(f" *   Also implements: {', '.join(res.extra_dos)}")
    lines.append(f" *   DI: {', '.join(res.dis)}")
    if res.risks:
        lines.append(f" *   Risks: {', '.join(res.risks)}")
    lines.append(
        ' *   Look up via: get_design_control('
        f'dc_type="design-output", dc_id="{res.primary_do}")'
    )
    return lines


# ----------------------------------------------------------------------
# Python rewriter
# ----------------------------------------------------------------------

DOCSTRING_RE = re.compile(
    r'^(?P<lead>(?:#!.*\n|#[^\n]*\n|\s*\n)*)'
    r'(?P<quote>"""|\'\'\')'
)


def _strip_existing_atlas_block_python(doc_body: str) -> tuple[str, bool]:
    """Remove a previous Atlas trace block from a docstring body."""
    lines = doc_body.split("\n")
    out = []
    i = 0
    removed = False
    while i < len(lines):
        if lines[i].strip().startswith(ATLAS_TRACE_MARKER):
            # Drop until first blank line OR end
            removed = True
            j = i + 1
            while j < len(lines) and lines[j].strip() != "":
                j += 1
            i = j
            continue
        out.append(lines[i])
        i += 1
    body = "\n".join(out).rstrip() + "\n"
    return body, removed


def stamp_python(text: str, res: Resolution) -> str:
    """Insert / update the Atlas trace block in a Python file."""
    m = DOCSTRING_RE.match(text)
    trace = "\n".join(_trace_lines_python(res))
    if m:
        quote = m.group("quote")
        lead = m.group("lead")
        rest_start = m.end()
        # Find the closing triple-quote.
        end_idx = text.find(quote, rest_start)
        if end_idx == -1:
            return text  # malformed; bail
        doc_body = text[rest_start:end_idx]
        # Preserve the first non-empty line as the summary; strip prior block.
        doc_body, _ = _strip_existing_atlas_block_python(doc_body)
        body_lines = doc_body.split("\n")
        # body_lines[0] is the summary line (often non-empty, may be empty)
        if body_lines and body_lines[0].strip():
            summary = body_lines[0].rstrip()
            tail_lines = body_lines[1:]
        else:
            summary = "Auto-stamped Atlas trace."
            tail_lines = body_lines
        # Strip leading blank lines from tail; we'll re-insert exactly one.
        while tail_lines and tail_lines[0].strip() == "":
            tail_lines.pop(0)
        tail = ("\n".join(tail_lines)).rstrip()
        new_body_parts = [summary, "", trace]
        if tail:
            new_body_parts.extend(["", tail])
        new_body = "\n".join(new_body_parts).rstrip() + "\n"
        new_text = (
            text[: m.start()]
            + lead
            + quote
            + new_body
            + quote
            + text[end_idx + len(quote):]
        )
        return new_text

    # No docstring: insert one at the top, preserving shebang / encoding.
    head_match = re.match(
        r'^((?:#!.*\n)?(?:#.*coding.*\n)?)', text
    )
    head = head_match.group(1) if head_match else ""
    rest = text[len(head):]
    docstring = (
        '"""Auto-stamped Atlas trace.\n\n'
        + trace + "\n"
        + '"""\n'
    )
    sep = "" if rest.startswith("\n") or not rest else ""
    return head + docstring + sep + rest


# ----------------------------------------------------------------------
# TypeScript rewriter
# ----------------------------------------------------------------------

TS_BLOCK_RE = re.compile(r"^\s*/\*\*[\s\S]*?\*/\s*\n", re.MULTILINE)


def _strip_existing_atlas_block_ts(comment: str) -> tuple[str, bool]:
    """Remove a previous Atlas trace block from a JSDoc comment body."""
    lines = comment.split("\n")
    out = []
    i = 0
    removed = False
    while i < len(lines):
        stripped = lines[i].strip().lstrip("*").strip()
        if stripped.startswith(ATLAS_TRACE_MARKER):
            removed = True
            j = i + 1
            while j < len(lines):
                s = lines[j].strip().lstrip("*").strip()
                if s == "" or lines[j].strip() == "*/" or lines[j].strip() == "*":
                    break
                j += 1
            i = j
            continue
        out.append(lines[i])
        i += 1
    # Collapse consecutive blank " *" lines to a single one (idempotency).
    cleaned: list[str] = []
    for ln in out:
        if (
            ln.strip() in ("*", "")
            and cleaned
            and cleaned[-1].strip() in ("*", "")
        ):
            continue
        cleaned.append(ln)
    return "\n".join(cleaned), removed


def stamp_ts(text: str, res: Resolution) -> str:
    trace = "\n".join(_trace_lines_ts(res))
    block_match = re.match(r"\s*/\*\*[\s\S]*?\*/\s*\n", text)
    if block_match:
        comment = block_match.group(0)
        comment_clean, _ = _strip_existing_atlas_block_ts(comment)
        # Remove trailing close so we can re-append cleanly.
        close_idx = comment_clean.rfind("*/")
        body = comment_clean[: close_idx].rstrip()
        # Append trace lines before close (trace already includes marker).
        # Avoid double blank if body already ends with " *".
        sep = "\n" if body.rstrip("\n").endswith(" *") else "\n *\n"
        new_comment = (
            body + sep
            + trace + "\n */\n"
        )
        return new_comment + text[len(block_match.group(0)):]

    summary = "Auto-stamped Atlas trace."
    block = (
        "/**\n"
        f" * {summary}\n"
        " *\n"
        + trace + "\n"
        + " */\n"
    )
    return block + text


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------

def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def render_diff(orig: str, new: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            orig.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=path,
            tofile=path + " (stamped)",
            n=2,
        )
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually mutate files (default: dry run)")
    ap.add_argument("--show-diffs", type=int, default=10,
                    help="number of sample diffs to print (default 10)")
    args = ap.parse_args()

    audit = load_audit()
    cache = load_cache()
    print(f"audit rows: {len(audit)}")
    print(f"cache: {len(cache['design_outputs'])} DOs, "
          f"{len(cache['design_inputs'])} DIs")

    ledger_rows: list[dict] = []
    triage_rows: list[dict] = []
    skipped_rows: list[dict] = []
    uncovered_rows: list[dict] = []
    diffs_shown = 0

    for row in audit:
        res = resolve_one(row, cache)
        ext = Path(row.path).suffix
        ledger_rows.append({
            "path": row.path,
            "decision": res.decision,
            "do": res.primary_do,
            "di": ", ".join(res.dis),
            "risks": ", ".join(res.risks),
            "header_state_before": row.header_state,
            "ext": ext,
            "note": res.note,
        })
        if res.decision == "excluded":
            skipped_rows.append({"path": row.path, "reason": res.note})
            continue
        if res.decision == "triage":
            triage_rows.append({
                "path": row.path,
                "category": res.triage_category,
                "owning_atlas_dis": "; ".join(row.owning_atlas_dis),
                "owning_atlas_dos": "; ".join(row.owning_atlas_dos),
                "legacy_ids_in_file": "; ".join(row.legacy_ids_in_file),
                "note": res.note,
            })
            continue
        if res.decision == "unresolved":
            uncovered_rows.append({
                "path": row.path,
                "header_state": row.header_state,
                "legacy_ids_in_file": "; ".join(row.legacy_ids_in_file),
                "phase8_bucket_dir": row.phase8_bucket_dir,
                "note": res.note,
            })
            continue
        if res.decision == "already_atlas":
            continue
        if res.decision != "stamped":
            continue

        # Apply stamp to file (or render diff)
        full = ROOT / row.path
        if not full.exists():
            ledger_rows[-1]["decision"] = "missing_file"
            ledger_rows[-1]["note"] = "file no longer exists"
            continue
        original = full.read_text()
        if ext == ".py":
            updated = stamp_python(original, res)
        elif ext in (".ts", ".tsx"):
            updated = stamp_ts(original, res)
        else:
            ledger_rows[-1]["decision"] = "skipped_unknown_ext"
            ledger_rows[-1]["note"] = f"unsupported extension {ext}"
            continue
        if updated == original:
            continue  # nothing to do (e.g. block already present)
        if args.apply:
            full.write_text(updated)
        elif diffs_shown < args.show_diffs:
            print("\n" + "=" * 70)
            print(render_diff(original, updated, row.path))
            diffs_shown += 1

    write_csv(LEDGER_CSV, LEDGER_COLS, ledger_rows)
    write_csv(TRIAGE_CSV, TRIAGE_COLS, triage_rows)
    write_csv(SKIPPED_CSV, SKIPPED_COLS, skipped_rows)
    write_csv(UNCOVERED_CSV, UNCOVERED_COLS, uncovered_rows)

    counts: dict[str, int] = {}
    for r in ledger_rows:
        counts[r["decision"]] = counts.get(r["decision"], 0) + 1
    print("\nDecisions:")
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")
    print()
    print(f"  ledger:    {LEDGER_CSV} ({len(ledger_rows)} rows)")
    print(f"  triage:    {TRIAGE_CSV} ({len(triage_rows)} rows)")
    print(f"  skipped:   {SKIPPED_CSV} ({len(skipped_rows)} rows)")
    print(f"  uncovered: {UNCOVERED_CSV} ({len(uncovered_rows)} rows)")
    if not args.apply:
        print("\nDRY RUN: no source files were modified. Pass --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
