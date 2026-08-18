"""Stamp Atlas trace headers onto Class B+ files missing them.

Routes each missing file to an owning DO via (in order):
  1. Exact path ownership from known Atlas Validation Lab DOs
  2. Path-prefix buckets (phase14d + a few post-14d packages)
  3. Same-directory sibling with a canonical DO: line
  4. libs/ catch-all DO-AA3B7FCC

Reuses the Phase 13c Python / TypeScript rewriters so the header
format stays identical. Defaults to dry-run; pass --apply to write.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "atlas"))

from check_atlas_trace_headers import (  # noqa: E402
    ROOT as CHECK_ROOT,
    has_trace,
    iter_candidates,
    load_allow_list,
    load_triage_list,
)
from phase13c_stamp_headers import (  # noqa: E402
    Resolution,
    load_cache,
    stamp_python,
    stamp_ts,
)

assert CHECK_ROOT == ROOT

EVIDENCE = ROOT / "compliance" / "atlas-migration-evidence"
CACHE_JSON = EVIDENCE / "phase13c-atlas-cache.json"
BUCKET_IDS = EVIDENCE / "phase14d-bucket-ids.json"

DO_RE = re.compile(r"DO:\s*(DO-[0-9A-Fa-f]{8})")
DI_RE = re.compile(r"DI:\s*([^\n*]+)")
RISK_RE = re.compile(r"Risks:\s*([^\n*]+)")

# Exact path -> (DO, [DI, ...]) from Atlas source_reference / IMPLEMENTS.
EXACT_OWNERS: dict[str, tuple[str, list[str]]] = {}


def _exact(do: str, dis: list[str], paths: list[str]) -> None:
    for p in paths:
        EXACT_OWNERS[p] = (do, dis)


_exact(
    "DO-3A70C3DD",
    ["DI-724CD8A5"],
    [
        "libs/validation_lab/models.py",
        "libs/validation_lab/scaffold.py",
        "libs/validation_lab/service.py",
        "libs/validation_lab/pipeline.py",
        "libs/validation_lab/gold.py",
        "libs/validation_lab/reset.py",
        "libs/cypher/validation_lab_queries.py",
        "services/api/app/routers/validation_lab.py",
    ],
)
_exact(
    "DO-158BE606",
    ["DI-2289D095"],
    [
        "services/ui/src/app/admin/validation-lab/page.tsx",
        "services/ui/src/app/admin/validation-lab/CreatePatientWizard.tsx",
        "services/ui/src/app/admin/validation-lab/WizardPmhEncounterSteps.tsx",
        "services/ui/src/app/admin/validation-lab/useCreatePatientWizard.ts",
        "services/ui/src/app/admin/validation-lab/labApi.ts",
        "services/ui/src/app/admin/validation-lab/labRun.ts",
        "services/ui/src/app/admin/validation-lab/SnomedConceptPicker.tsx",
        "services/ui/src/app/admin/validation-lab/terminology.ts",
        "services/ui/src/app/admin/validation-lab/LabCasesPanel.tsx",
        "services/ui/src/app/admin/validation-lab/TestPatientRolodex.tsx",
        "services/ui/src/app/admin/validation-lab/TestPatientRolodexFilters.tsx",
        "services/ui/src/app/admin/validation-lab/TestPatientCard.tsx",
        "services/ui/src/app/admin/validation-lab/testPatientSelection.ts",
        "services/ui/src/components/sbar-final/LeoSbarHost.tsx",
    ],
)
_exact(
    "DO-A0ADDB38",
    ["DI-EB716E68"],
    [
        "libs/prompts/validation_lab_brainstorm_v1.py",
        "libs/validation_lab/brainstorm.py",
        "libs/validation_lab/brainstorm_tools.py",
        "libs/validation_lab/scenario_patch.py",
        "libs/validation_lab/scenario_catalog.py",
        "libs/validation_lab/equity_taxonomy.py",
        "libs/validation_lab/rule_grounded_eval.py",
        "services/api/app/routers/validation_lab_brainstorm.py",
        "services/ui/src/app/admin/validation-lab/ScenarioBrainstormDrawer.tsx",
        "services/ui/src/app/admin/validation-lab/"
        "ScenarioBrainstormVariantsStep.tsx",
        "services/ui/src/app/admin/validation-lab/scenarioVariants.ts",
        "services/ui/src/app/admin/validation-lab/caseCardMeta.ts",
    ],
)
_exact(
    "DO-7E9AD55B",
    ["DI-DA60AC55"],
    [
        "libs/ner/context_rule_catalog.py",
        "libs/pipeline/ignore_phrase_catalog.py",
        "services/ui/src/app/admin/context-rules/ContextAddDialog.tsx",
        "services/ui/src/app/admin/context-rules/categoryCopy.ts",
        "services/ui/src/app/admin/context-rules/types.ts",
        "services/ui/src/app/admin/context-rules/useContextRulesPage.ts",
        "services/ui/src/app/admin/guard-rules/GuardEditorPanel.tsx",
        "services/ui/src/app/admin/guard-rules/guardFamilyCopy.ts",
        "services/ui/src/app/admin/guard-rules/guardWorkedExamples.ts",
        "services/ui/src/app/admin/guard-rules/humanizePattern.ts",
        "services/ui/src/app/admin/guard-rules/types.ts",
        "services/ui/src/app/admin/guard-rules/useGuardRulesPage.ts",
    ],
)
_exact(
    "DO-15449C6E",
    ["DI-0F9542BF"],
    [
        "libs/ner/context_engine.py",
    ],
)
_exact(
    "DO-47454249",
    ["DI-E5FEF0AE"],
    [
        "services/design-system/src/brand/LeoLoader.tsx",
        "services/design-system/src/brand/LeoLogo.tsx",
        "services/design-system/src/brand/LeoSplash.tsx",
        "services/design-system/src/brand/index.ts",
    ],
)
_exact(
    "DO-E981C7B1",
    ["DI-D6E5F94E"],
    [
        "libs/validation_lab/pmh_verbalisation.py",
        "libs/validation_lab/epr_scaffold.py",
        "libs/validation_lab/gp_consult.py",
        "libs/validation_lab/ag_pipeline.py",
        "libs/validation_lab/ag_scaffold.py",
        "libs/validation_lab/referral_identity.py",
        "libs/cypher/pmh_verbalisation_queries.py",
        "services/ui/src/app/admin/validation-lab/WizardAgThreadSteps.tsx",
        "services/ui/src/app/admin/validation-lab/WizardGpConsultStep.tsx",
    ],
)

# Prefix -> (DO, [DI]) -- most specific first. Catch-all last.
PREFIX_OWNERS: list[tuple[str, str, list[str]]] = [
    ("services/ui/src/app/admin/validation-lab/", "DO-158BE606", ["DI-2289D095"]),
    ("libs/validation_lab/", "DO-3A70C3DD", ["DI-724CD8A5"]),
    ("services/ui/src/app/admin/", "DO-2C03CA0E", ["DI-3F771AFB"]),
    ("services/ui/src/components/patients/", "DO-5F9A50D8", ["DI-1D584D40"]),
    ("services/ui/src/app/patients/", "DO-5F9A50D8", ["DI-1D584D40"]),
    ("services/ui/src/app/care/", "DO-5F9A50D8", ["DI-1D584D40"]),
    ("services/ui/src/components/mission-control/", "DO-5312F884", ["DI-AA1F5F5B"]),
    ("services/ui/src/components/pathway/", "DO-B5DB3744", ["DI-C6700F52"]),
    ("services/ui/src/app/pathways/", "DO-B5DB3744", ["DI-C6700F52"]),
    ("services/ui/src/components/operations/", "DO-CBE90D5D", ["DI-982CC3AD"]),
    ("services/ui/src/app/operations/", "DO-CBE90D5D", ["DI-982CC3AD"]),
    ("services/ui/src/components/audit/", "DO-2E8544FD", ["DI-C65FD45B"]),
    ("services/ui/src/components/dashboard/", "DO-2E8544FD", ["DI-C65FD45B"]),
    ("services/ui/src/app/api/", "DO-19BBE973", ["DI-B746E19E"]),
    ("services/ui/src/lib/", "DO-CD075278", ["DI-B5EEBC4C"]),
    ("services/ui/src/hooks/", "DO-CD075278", ["DI-B5EEBC4C"]),
    ("services/ui/src/components/", "DO-30A82196", ["DI-85B110A5"]),
    ("services/ui/src/", "DO-CD075278", ["DI-B5EEBC4C"]),
    ("services/api/app/routers/", "DO-EC41233C", ["DI-9D0DF618"]),
    ("services/api/app/services/", "DO-92F92EFB", ["DI-88C1715A"]),
    ("services/api/app/", "DO-19FA25C3", ["DI-727C94B4"]),
    ("services/analysis_worker/app/", "DO-2C1A2392", ["DI-7FF67ECE"]),
    ("services/pipeline_worker/app/", "DO-C2F6CA16", ["DI-06CB6881"]),
    ("services/training_worker/app/", "DO-9488B454", ["DI-D46D83FA"]),
    ("services/analytics_api/app/", "DO-31410049", ["DI-F46494AE"]),
    ("services/terminology_api/app/", "DO-77A48DBC", ["DI-4746A178"]),
    ("services/widget-sdk/", "DO-5C88CA8F", ["DI-A1206416"]),
    ("libs/cypher/", "DO-F8EFEF89", ["DI-E47C3FC2"]),
    ("libs/prompts/", "DO-BEFC4C67", ["DI-85AB13D7"]),
    ("libs/pipeline_graph/", "DO-69F520C9", ["DI-F22160C3"]),
    ("libs/ner/", "DO-8EF2EC20", ["DI-2F963FC6"]),
    ("libs/pipeline/", "DO-728930A1", ["DI-B5C78811"]),
    ("libs/cohort_annotation/", "DO-AA3B7FCC", ["DI-9456E5BE"]),
    ("libs/referral_simulator/", "DO-AA3B7FCC", ["DI-9456E5BE"]),
    ("libs/", "DO-AA3B7FCC", ["DI-9456E5BE"]),
]


def list_missing() -> list[str]:
    allow = load_allow_list()
    triage = load_triage_list()
    out: list[str] = []
    for p in iter_candidates():
        rel = str(p.relative_to(ROOT))
        if rel in allow or rel in triage:
            continue
        if not has_trace(p):
            out.append(rel)
    return out


def extract_trace(path: Path) -> tuple[str, list[str], list[str]] | None:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return None
    do_m = DO_RE.search(head)
    if not do_m:
        return None
    di_m = DI_RE.search(head)
    risk_m = RISK_RE.search(head)
    dis = []
    if di_m:
        dis = [x.strip() for x in di_m.group(1).split(",") if x.strip()]
        dis = [d for d in dis if d.startswith("DI-")]
    risks = []
    if risk_m:
        risks = [x.strip() for x in risk_m.group(1).split(",") if x.strip()]
        risks = [r for r in risks if r.startswith("R-")]
    return do_m.group(1).upper(), dis, risks


def sibling_owner(rel: str, stamped_by_dir: dict[str, list]) -> tuple[str, list[str], list[str]] | None:
    cur = Path(rel).parent
    while True:
        key = str(cur)
        if key in ("", ".") or key in ("libs", "services"):
            return None
        hits = stamped_by_dir.get(key) or []
        if hits:
            counts = Counter(h[0] for h in hits)
            best_do = counts.most_common(1)[0][0]
            sample = next(h for h in hits if h[0] == best_do)
            return sample
        parts = key.split("/")
        if len(parts) <= 2 and parts[0] in ("libs", "services"):
            return None
        cur = cur.parent


def load_bucket_fallback() -> dict[str, tuple[str, list[str]]]:
    if not BUCKET_IDS.exists():
        return {}
    raw = json.loads(BUCKET_IDS.read_text())
    out: dict[str, tuple[str, list[str]]] = {}
    for _bid, v in raw.items():
        do = v["do"]
        if not do.startswith("DO-"):
            do = "DO-" + do
        di = v.get("di") or ""
        dis = [di] if di.startswith("DI-") else []
        for extra in v.get("additional_dis") or []:
            if str(extra).startswith("DI-"):
                dis.append(str(extra))
        for path in v.get("files") or []:
            out[path] = (do, dis)
    return out


def resolve_owner(
    rel: str,
    stamped_by_dir: dict[str, list],
    bucket_paths: dict[str, tuple[str, list[str]]],
    cache: dict,
) -> Resolution | None:
    if rel in EXACT_OWNERS:
        do, dis = EXACT_OWNERS[rel]
        return Resolution(decision="stamped", primary_do=do, dis=list(dis))

    if rel in bucket_paths:
        do, dis = bucket_paths[rel]
        return _with_cache(do, dis, cache)

    for prefix, do, dis in PREFIX_OWNERS:
        if rel.startswith(prefix) or rel == prefix.rstrip("/"):
            return _with_cache(do, list(dis), cache)

    sib = sibling_owner(rel, stamped_by_dir)
    if sib:
        do, dis, risks = sib
        return Resolution(
            decision="stamped", primary_do=do, dis=list(dis), risks=list(risks)
        )
    return None


def _with_cache(do: str, dis: list[str], cache: dict) -> Resolution:
    rec = (cache.get("design_outputs") or {}).get(do) or {}
    cached_dis = list(rec.get("design_inputs") or [])
    risks = list(rec.get("risks") or [])
    merged = sorted(set(dis + [d for d in cached_dis if str(d).startswith("DI-")]))
    if not merged:
        merged = list(dis)
    return Resolution(decision="stamped", primary_do=do, dis=merged, risks=risks)


def ensure_cache_entries(cache: dict) -> None:
    dos = cache.setdefault("design_outputs", {})
    extras = {
        "DO-3A70C3DD": ["DI-724CD8A5"],
        "DO-158BE606": ["DI-2289D095"],
        "DO-A0ADDB38": ["DI-EB716E68"],
        "DO-E981C7B1": ["DI-D6E5F94E"],
        "DO-5C88CA8F": ["DI-A1206416"],
        "DO-728930A1": ["DI-B5C78811"],
        "DO-7E9AD55B": ["DI-DA60AC55"],
        "DO-15449C6E": ["DI-0F9542BF"],
        "DO-47454249": ["DI-E5FEF0AE"],
    }
    for do, dis in extras.items():
        if do not in dos:
            dos[do] = {
                "dcId": do,
                "title": "stamp_untraced_class_b synthetic cache",
                "design_inputs": dis,
                "design_outputs": [],
                "risks": [],
            }


def stamp_one(rel: str, res: Resolution) -> bool:
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        new = stamp_python(text, res)
    else:
        new = stamp_ts(text, res)
    if new == text:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def build_sibling_index() -> dict[str, list]:
    by_dir: dict[str, list] = defaultdict(list)
    for p in iter_candidates():
        rel = str(p.relative_to(ROOT))
        if not has_trace(p):
            continue
        extracted = extract_trace(p)
        if not extracted:
            continue
        by_dir[str(p.parent.relative_to(ROOT))].append(extracted)
    return by_dir


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    missing = list_missing()
    print(f"Missing Atlas trace headers: {len(missing)}")
    cache = load_cache()
    ensure_cache_entries(cache)
    stamped_by_dir = build_sibling_index()
    bucket_paths = load_bucket_fallback()

    resolved: list[tuple[str, Resolution]] = []
    unresolved: list[str] = []
    for rel in missing:
        res = resolve_owner(rel, stamped_by_dir, bucket_paths, cache)
        if res and res.primary_do and res.dis:
            resolved.append((rel, res))
        else:
            unresolved.append(rel)

    print(f"Resolved:   {len(resolved)}")
    print(f"Unresolved: {len(unresolved)}")
    if unresolved:
        print("Unresolved files:")
        for u in unresolved[:40]:
            print(f"  {u}")
        if len(unresolved) > 40:
            print(f"  ... and {len(unresolved) - 40} more")

    do_counts = Counter(r.primary_do for _, r in resolved)
    print("DO distribution:")
    for do, n in do_counts.most_common(30):
        print(f"  {n:4d} {do}")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to write headers.")
        return 1 if unresolved else 0

    changed = 0
    for rel, res in resolved:
        if stamp_one(rel, res):
            changed += 1
    CACHE_JSON.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    print(f"Stamped {changed} files.")
    if unresolved:
        print("ERROR: unresolved files remain; add to allow-list or extend routers.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
