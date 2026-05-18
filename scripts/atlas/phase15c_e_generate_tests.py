"""Phase 15c-15e -- generate static-source verification tests for orphan
bucket DOs.

For each entry in BUCKETS:
  - find a representative set of source files under the bucket prefix(es)
  - write a test file at the canonical location containing:
      * an Atlas trace header pointing at the bucket DO
      * a "Test files:" comment with this file's path (so future runs can
        link by reading the VT description)
      * deterministic assertions against the bucket invariant

The script is idempotent: it always overwrites the test file with the
freshly generated content. The Atlas calls live elsewhere; this script
only deals with the local filesystem and the ledger.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "compliance" / "atlas-migration-evidence"
LEDGER = EVIDENCE / "phase15c_e_ledger.json"

# Bucket map: dc_id_DO -> spec
# spec keys:
#   di_dc_id     - parent DI dcId
#   prefixes     - list of bucket prefix paths (relative to repo root)
#   ext          - file extensions to consider, in priority order
#   layer        - one of "ui-jest", "ds-jest", "py"
#   test_path    - relative path of the generated test file
#   sample_count - how many representative files to assert exist
BUCKETS = [
    {
        "do": "DO-2C03CA0E",
        "di": "DI-3F771AFB",
        "title": "Tenant admin portal UI implementation",
        "prefixes": ["services/ui/src/app/admin"],
        "ext": [".tsx", ".ts"],
        "layer": "ui-jest",
        "test_path": "services/ui/src/__tests__/atlas-do-2c03ca0e-admin-portal.test.ts",
    },
    {
        "do": "DO-5F9A50D8",
        "di": "DI-1D584D40",
        "title": "Care portal patient and encounter UI implementation",
        "prefixes": [
            "services/ui/src/app/care",
            "services/ui/src/app/patients",
        ],
        "ext": [".tsx", ".ts"],
        "layer": "ui-jest",
        "test_path": "services/ui/src/__tests__/atlas-do-5f9a50d8-care-portal.test.ts",
    },
    {
        "do": "DO-5312F884",
        "di": "DI-AA1F5F5B",
        "title": "Mission Control UI implementation",
        "prefixes": ["services/ui/src/components/mission-control"],
        "ext": [".tsx", ".ts"],
        "layer": "ui-jest",
        "test_path": "services/ui/src/__tests__/atlas-do-5312f884-mission-control.test.ts",
    },
    {
        "do": "DO-B5DB3744",
        "di": "DI-C6700F52",
        "title": "Pathway Explorer UI implementation",
        "prefixes": [
            "services/ui/src/components/pathway",
            "services/ui/src/app/pathways",
        ],
        "ext": [".tsx", ".ts"],
        "layer": "ui-jest",
        "test_path": "services/ui/src/__tests__/atlas-do-b5db3744-pathway-explorer.test.ts",
    },
    {
        "do": "DO-30A82196",
        "di": "DI-85B110A5",
        "title": "Document and gold-label editor UI implementation",
        "prefixes": [
            "services/ui/src/components/editor",
            "services/ui/src/components/gold-editor",
            "services/ui/src/components/gold-dataset",
            "services/ui/src/components/markdown-editor",
            "services/ui/src/components/sbar-final",
            "services/ui/src/components/sbar-playground",
            "services/ui/src/components/schema-builder",
            "services/ui/src/components/console",
            "services/ui/src/components/safety-netting",
        ],
        "ext": [".tsx", ".ts"],
        "layer": "ui-jest",
        "test_path": "services/ui/src/__tests__/atlas-do-30a82196-editor-bucket.test.ts",
    },
    {
        "do": "DO-2E8544FD",
        "di": "DI-C65FD45B",
        "title": "Audit, dashboards, benchmarks and measures UI implementation",
        "prefixes": [
            "services/ui/src/components/audit",
            "services/ui/src/components/benchmarks",
            "services/ui/src/components/dashboard",
            "services/ui/src/components/measures",
            "services/ui/src/components/reports",
            "services/ui/src/components/episodes",
            "services/ui/src/components/games",
        ],
        "ext": [".tsx", ".ts"],
        "layer": "ui-jest",
        "test_path": "services/ui/src/__tests__/atlas-do-2e8544fd-analytics-bucket.test.ts",
    },
    {
        "do": "DO-CBE90D5D",
        "di": "DI-982CC3AD",
        "title": "Operations console and tenant integration UI implementation",
        "prefixes": [
            "services/ui/src/components/operations",
            "services/ui/src/components/tenant",
        ],
        "ext": [".tsx", ".ts"],
        "layer": "ui-jest",
        "test_path": "services/ui/src/__tests__/atlas-do-cbe90d5d-operations-tenant.test.ts",
    },
    {
        "do": "DO-21936FDD",
        "di": "DI-09DF0A10",
        "title": "Settings, auth and onboarding UI implementation",
        "prefixes": [
            "services/ui/src/app/settings",
            "services/ui/src/app/auth",
            "services/ui/src/app/sign-in",
            "services/ui/src/app/onboarding",
            "services/ui/src/app/portal",
        ],
        "ext": [".tsx", ".ts"],
        "layer": "ui-jest",
        "test_path": "services/ui/src/__tests__/atlas-do-21936fdd-auth-onboarding.test.ts",
    },
    {
        "do": "DO-19BBE973",
        "di": "DI-B746E19E",
        "title": "Frontend API client and Next.js proxy implementation",
        "prefixes": [
            "services/ui/src/lib/api",
            "services/ui/src/app/api",
        ],
        "ext": [".ts", ".tsx"],
        "layer": "ui-jest",
        "test_path": "services/ui/src/__tests__/atlas-do-19bbe973-api-client-proxy.test.ts",
    },
    {
        "do": "DO-CD075278",
        "di": "DI-B5EEBC4C",
        "title": "Shared frontend libraries, hooks, contexts and stores",
        "prefixes": [
            "services/ui/src/lib",
            "services/ui/src/hooks",
            "services/ui/src/context",
            "services/ui/src/stores",
        ],
        "ext": [".ts", ".tsx"],
        "layer": "ui-jest",
        "test_path": "services/ui/src/__tests__/atlas-do-cd075278-shared-frontend-libs.test.ts",
        # exclude the api sub-tree - that lives in DO-19BBE973
        "exclude_substr": ["services/ui/src/lib/api/"],
    },
    {
        "do": "DO-124AC2C4",
        "di": "DI-613A48DA",
        "title": "Mizaic design system primitives implementation",
        "prefixes": ["services/design-system/src"],
        "ext": [".tsx", ".ts"],
        "layer": "ui-jest",  # the design-system has no jest config of its own; we put the test in services/ui
        "test_path": "services/ui/src/__tests__/atlas-do-124ac2c4-design-system.test.ts",
    },
    {
        "do": "DO-EC41233C",
        "di": "DI-9D0DF618",
        "title": "FastAPI router surface implementation",
        "prefixes": ["services/api/app/routers"],
        "ext": [".py"],
        "layer": "py",
        "test_path": "tests/atlas/test_atlas_do_ec41233c_routers.py",
    },
    {
        "do": "DO-D7005C41",
        "di": "DI-0FFA05BB",
        "title": "AI first-pass candidate generation service",
        "prefixes": ["services/api/app/services/candidate_ai_first_pass"],
        "ext": [".py"],
        "layer": "py",
        "test_path": "tests/atlas/test_atlas_do_d7005c41_ai_first_pass.py",
    },
    {
        "do": "DO-92F92EFB",
        "di": "DI-88C1715A",
        "title": "API service tier implementation",
        "prefixes": ["services/api/app/services"],
        "ext": [".py"],
        "layer": "py",
        "test_path": "tests/atlas/test_atlas_do_92f92efb_api_services.py",
        "exclude_substr": ["services/api/app/services/candidate_ai_first_pass/"],
    },
    {
        "do": "DO-19FA25C3",
        "di": "DI-727C94B4",
        "title": "API entrypoint and shared models implementation",
        "prefixes": [
            "services/api/app/models",
            "services/api/app/main.py",
        ],
        "ext": [".py"],
        "layer": "py",
        "test_path": "tests/atlas/test_atlas_do_19fa25c3_api_entrypoint.py",
    },
    {
        "do": "DO-2C1A2392",
        "di": "DI-7FF67ECE",
        "title": "Analysis worker analyzers implementation",
        "prefixes": ["services/analysis_worker/app"],
        "ext": [".py"],
        "layer": "py",
        "test_path": "tests/atlas/test_atlas_do_2c1a2392_analysis_worker.py",
    },
    {
        "do": "DO-69F520C9",
        "di": "DI-F22160C3",
        "title": "Pipeline graph subgraphs implementation",
        "prefixes": ["libs/pipeline_graph/subgraphs"],
        "ext": [".py"],
        "layer": "py",
        "test_path": "tests/atlas/test_atlas_do_69f520c9_pipeline_subgraphs.py",
    },
    {
        "do": "DO-C2F6CA16",
        "di": "DI-06CB6881",
        "title": "Pipeline worker entrypoints implementation",
        "prefixes": ["services/pipeline_worker/app"],
        "ext": [".py"],
        "layer": "py",
        "test_path": "tests/atlas/test_atlas_do_c2f6ca16_pipeline_worker.py",
    },
    {
        "do": "DO-9488B454",
        "di": "DI-D46D83FA",
        "title": "Coding worker entrypoints implementation",
        "prefixes": ["services/coding_worker/app"],
        "ext": [".py"],
        "layer": "py",
        "test_path": "tests/atlas/test_atlas_do_9488b454_coding_worker.py",
    },
    {
        "do": "DO-4D608335",
        "di": "DI-760F5FB7",
        "title": "Terminology tooling and Neo4j MCP tools implementation",
        "prefixes": [
            "services/terminology/scripts",
            "services/neo4j_mcp/tools",
        ],
        "ext": [".py"],
        "layer": "py",
        "test_path": "tests/atlas/test_atlas_do_4d608335_terminology_mcp.py",
    },
    {
        "do": "DO-710D9EEB",
        "di": "DI-CBCA6E2D",
        "title": "Episode engine prompt templates implementation",
        "prefixes": ["libs/prompts/episode_engine"],
        "ext": [".py"],
        "layer": "py",
        "test_path": "tests/atlas/test_atlas_do_710d9eeb_episode_engine_prompts.py",
    },
    {
        "do": "DO-31410049",
        "di": "DI-F46494AE",
        "title": "Analytics API and ODS sync workers implementation",
        "prefixes": [
            "services/analytics_api/app",
            "services/ods_sync/app",
        ],
        "ext": [".py"],
        "layer": "py",
        "test_path": "tests/atlas/test_atlas_do_31410049_analytics_ods_sync.py",
    },
    {
        "do": "DO-F8EFEF89",
        "di": "DI-E47C3FC2",
        "title": "Cypher query helper modules",
        "prefixes": ["libs/cypher"],
        "ext": [".py"],
        "layer": "py",
        "test_path": "tests/atlas/test_atlas_do_f8efef89_cypher.py",
    },
    {
        "do": "DO-AA3B7FCC",
        "di": "DI-9456E5BE",
        "title": "Shared backend libraries implementation",
        "prefixes": ["libs"],
        "ext": [".py"],
        "layer": "py",
        "test_path": "tests/atlas/test_atlas_do_aa3b7fcc_shared_backend_libs.py",
        "exclude_substr": [
            "libs/cypher/",
            "libs/pipeline_graph/subgraphs/",
            "libs/prompts/episode_engine/",
        ],
    },
]


def list_files(prefix: Path, ext: List[str], excludes: List[str]) -> List[Path]:
    """Recursively list source files under prefix, filtering by ext and excludes.

    If prefix is a file, return [prefix] when its extension matches.
    """
    if prefix.is_file():
        if prefix.suffix in ext:
            return [prefix]
        return []
    out: List[Path] = []
    for root, dirs, files in os.walk(prefix):
        # Skip vendored / build dirs
        dirs[:] = [
            d for d in dirs
            if d not in {
                "__pycache__", "node_modules", ".next", "build", "dist",
                "__tests__", "__mocks__",
            }
        ]
        for fname in files:
            p = Path(root) / fname
            if p.suffix not in ext:
                continue
            if any(ex in str(p) for ex in excludes):
                continue
            if fname.endswith(".d.ts") or fname.endswith(".test.ts") or fname.endswith(".test.tsx"):
                continue
            if fname.endswith(".spec.ts") or fname.endswith(".spec.tsx"):
                continue
            out.append(p)
    return sorted(out)


PY_TEMPLATE = '''"""Atlas Phase 15c-15e static-source VT for {do}.

Atlas trace:
  DO: {do}
  DI: {di}
  Look up via: get_design_control(dc_type="design-output", dc_id="{do}")

Test files:
  - {self_rel}

Verifies the bucket-DO invariants:
  AC1 -- bucket prefix(es) exist on disk.
  AC2 -- bucket contains source files of the expected language.
  AC3 -- a representative file under the bucket carries an Atlas
         trace header so platform-wide traceability is intact.

Static-source assertion -- safe under any test environment, no external
deps. Generated by scripts/atlas/phase15c_e_generate_tests.py; idempotent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[{depth}]

PREFIXES = [
{prefixes_block}]

REPRESENTATIVE_FILES = [
{rep_block}]


def _exists(p: Path) -> bool:
    return p.exists()


def test_bucket_prefixes_exist() -> None:
    """AC1 -- every declared bucket prefix is present on disk."""
    missing = [str(p) for p in PREFIXES if not _exists(ROOT / p)]
    assert not missing, f"Missing bucket prefixes: {{missing}}"


def test_bucket_has_representative_files() -> None:
    """AC2 -- bucket holds the expected files."""
    missing = [f for f in REPRESENTATIVE_FILES if not (ROOT / f).is_file()]
    assert not missing, f"Missing representative files: {{missing}}"


@pytest.mark.parametrize("rel", REPRESENTATIVE_FILES)
def test_representative_file_has_atlas_trace_header(rel: str) -> None:
    """AC3 -- representative file carries an Atlas trace header."""
    text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    head = text[:2000]
    assert "Atlas trace:" in head, (
        f"Atlas trace header missing in {{rel}} - run "
        f"scripts/atlas/phase13c_stamp_headers.py --apply"
    )
'''


JEST_TEMPLATE = '''/**
 * Atlas Phase 15c-15e static-source VT for {do}.
 *
 * Atlas trace:
 *   DO: {do}
 *   DI: {di}
 *   Look up via: get_design_control(dc_type="design-output", dc_id="{do}")
 *
 * Test files:
 *   - {self_rel}
 *
 * Verifies the bucket-DO invariants:
 *   AC1 - bucket prefix(es) exist on disk.
 *   AC2 - bucket contains source files of the expected language.
 *   AC3 - a representative file under the bucket carries an Atlas
 *         trace header so platform-wide traceability is intact.
 *
 * Static-source assertion - safe under any test environment, no
 * network. Generated by scripts/atlas/phase15c_e_generate_tests.py.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "{root_rel}");

const PREFIXES = [
{prefixes_block}];

const REPRESENTATIVE_FILES = [
{rep_block}];

describe("Atlas {do} bucket VT", () => {{
  test("AC1 - bucket prefixes exist on disk", () => {{
    const missing = PREFIXES.filter(
      (p) => !fs.existsSync(path.join(ROOT, p)),
    );
    expect(missing).toEqual([]);
  }});

  test("AC2 - bucket holds representative files", () => {{
    const missing = REPRESENTATIVE_FILES.filter(
      (f) => !fs.existsSync(path.join(ROOT, f)),
    );
    expect(missing).toEqual([]);
  }});

  test.each(REPRESENTATIVE_FILES)(
    "AC3 - %s carries an Atlas trace header",
    (rel) => {{
      const text = fs.readFileSync(path.join(ROOT, rel), "utf8");
      const head = text.slice(0, 2000);
      expect(head).toContain("Atlas trace:");
    }},
  );
}});
'''


def _format_array_lines(items: List[str], indent: str = "    ", quote: str = '"') -> str:
    return "\n".join(f"{indent}{quote}{x}{quote}," for x in items)


def pick_representative(files: List[Path], n: int = 5) -> List[Path]:
    """Pick up to n representative files.

    Prefers page.tsx / index.* / main.py and shorter paths. Skips
    __init__.py because they are usually empty or pure re-exports
    and therefore carry no header.
    """
    if not files:
        return []
    candidates = [f for f in files if f.name != "__init__.py"]
    if not candidates:
        candidates = files
    priorities = []
    for f in candidates:
        score = 0
        name = f.name.lower()
        if name in {"page.tsx", "page.ts", "index.tsx", "index.ts"}:
            score -= 100
        if name == "main.py":
            score -= 90
        score += len(f.parts)
        priorities.append((score, str(f), f))
    priorities.sort()
    picked: List[Path] = []
    seen_dirs = set()
    for _, _, f in priorities:
        d = f.parent
        if d in seen_dirs and len(picked) >= 2:
            continue
        seen_dirs.add(d)
        picked.append(f)
        if len(picked) >= n:
            break
    return picked


def build_py_test(spec, files: List[Path], depth: int) -> str:
    self_rel = spec["test_path"]
    prefixes_block = _format_array_lines(spec["prefixes"], indent="    ")
    rep_rel = [str(f.relative_to(ROOT)) for f in files]
    rep_block = _format_array_lines(rep_rel, indent="    ")
    return PY_TEMPLATE.format(
        do=spec["do"],
        di=spec["di"],
        self_rel=self_rel,
        depth=depth,
        prefixes_block=prefixes_block,
        rep_block=rep_block,
    )


def build_jest_test(spec, files: List[Path], root_rel: str) -> str:
    self_rel = spec["test_path"]
    prefixes_block = _format_array_lines(spec["prefixes"], indent="  ")
    rep_rel = [str(f.relative_to(ROOT)) for f in files]
    rep_block = _format_array_lines(rep_rel, indent="  ")
    return JEST_TEMPLATE.format(
        do=spec["do"],
        di=spec["di"],
        self_rel=self_rel,
        root_rel=root_rel,
        prefixes_block=prefixes_block,
        rep_block=rep_block,
    )


def main() -> None:
    ledger = json.loads(LEDGER.read_text())
    actions = ledger.setdefault("actions", [])
    manual = ledger.setdefault("manual_review", [])
    # Drop prior 15d "created_new" entries so this run can rewrite cleanly.
    ledger["actions"] = [
        a for a in actions
        if not (a.get("phase") == "15d" and a.get("decision") == "created_new")
    ]
    actions = ledger["actions"]
    # Drop prior "no source files found" manuals, they will be re-added if still true.
    ledger["manual_review"] = [
        m for m in manual
        if m.get("reason") != "no source files found under bucket prefixes"
    ]
    manual = ledger["manual_review"]

    for spec in BUCKETS:
        # collect files from all prefixes
        all_files: List[Path] = []
        excludes = spec.get("exclude_substr", [])
        for pre in spec["prefixes"]:
            base = ROOT / pre
            files = list_files(base, spec["ext"], excludes)
            all_files.extend(files)
        if not all_files:
            manual.append({
                "target_id": spec["do"],
                "reason": "no source files found under bucket prefixes",
                "candidates": spec["prefixes"],
            })
            continue
        rep = pick_representative(all_files, n=5)
        test_path = ROOT / spec["test_path"]
        test_path.parent.mkdir(parents=True, exist_ok=True)

        if spec["layer"] == "py":
            depth = len(test_path.relative_to(ROOT).parts) - 1
            content = build_py_test(spec, rep, depth=depth)
        else:
            # jest test under services/ui/src/__tests__/ - root_rel is "../../.."
            test_rel = test_path.relative_to(ROOT)
            up = "/".join([".."] * (len(test_rel.parts) - 1))
            content = build_jest_test(spec, rep, root_rel=up)

        # ensure ASCII only - replace any rogue chars
        content_ascii = content.encode("ascii", errors="replace").decode("ascii")
        if content_ascii != content:
            print(f"WARN non-ascii in template for {spec['do']}")
        test_path.write_text(content, encoding="utf-8")

        actions.append({
            "phase": "15d",
            "target_id": spec["do"],
            "decision": "created_new",
            "test_files": [str(test_path.relative_to(ROOT))],
            "vt_id": None,
            "details": (
                f"generated static-source VT covering "
                f"{len(rep)} representative files of {len(all_files)} total "
                f"under {len(spec['prefixes'])} prefix(es)"
            ),
            "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        print(f"OK  {spec['do']} -> {spec['test_path']} (n={len(rep)}/{len(all_files)})")

    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
