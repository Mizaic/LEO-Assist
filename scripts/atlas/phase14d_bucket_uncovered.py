"""Phase 14d-i -- bucket the 603 uncovered files into ~25 DO-sized clusters.

Uses a deterministic prefix-based router (see BUCKETS) so re-running
produces the same plan. Output: phase14d-bucket-plan.csv.

Each bucket carries enough metadata for Phase 14d-ii to mint UN/DI/DO
without further human input.
"""

from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "compliance" / "atlas-migration-evidence"
UNCOVERED = EVIDENCE / "phase13c-uncovered.csv"
PLAN = EVIDENCE / "phase14d-bucket-plan.csv"


# Each bucket is (id, title, capability_summary, [path-prefix or regex matchers]).
# Order matters: earlier rules win.
#
# A special bucket whose `bucket_id` starts with `existing-DO-` skips DO
# creation in Phase 14d-ii: the suffix is the Atlas dcId of an existing DO
# that already owns the rest of the capability. The phase14d-ii script
# will only update the source_reference and stamp headers.
BUCKETS: list[tuple[str, str, str, list[str | re.Pattern]]] = [
    # ---- Special case: file belongs to an existing Atlas DO ----
    ("existing-DO-77A48DBC",
     "ConceptMap CRUD service (extends existing DO-77A48DBC)",
     "Sibling of valueset_service.py / coding_resolver.py / conceptmap "
     "router; implements the ConceptMap CRUD + $translate service for "
     "the FHIR R4B terminology surface.",
     ["services/terminology_api/app/services/conceptmap_service.py"]),


    # ---- UI ----
    ("ui-admin-portal",
     "Tenant admin portal UI",
     "Pages and components under /admin/* that let tenant admins configure "
     "users, model settings, knowledge libraries, content guardrails and "
     "monitoring dashboards.",
     ["services/ui/src/app/admin/"]),

    ("ui-care-portal",
     "Care portal patient and encounter UI",
     "Patient-facing care portal pages: encounter list, patient timeline, "
     "patient profile and the case-list shell.",
     [
         "services/ui/src/app/care/",
         "services/ui/src/app/patients/",
         "services/ui/src/components/EncounterList.tsx",
         "services/ui/src/components/PatientList.tsx",
         "services/ui/src/components/PatientTimeline.tsx",
     ]),

    ("ui-mission-control",
     "Mission Control UI",
     "Encounter Mission Control surface used by clinicians to review live "
     "AI output, trigger batch recoding, and watch pipeline state.",
     ["services/ui/src/components/mission-control/"]),

    ("ui-pathway-explorer",
     "Pathway Explorer UI",
     "Pathway Explorer pages and visualisations: pathway map, milestone "
     "list, escalation rule editor, pathway risk overlay.",
     [
         "services/ui/src/components/pathway/",
         "services/ui/src/app/pathways/",
         "services/ui/src/lib/pathwayRisk.ts",
     ]),

    ("ui-document-editor",
     "Document and gold-label editor UI",
     "Editor surface for SBAR, gold labels, schema-builder, markdown, "
     "context rules, and entity correction tooling used by clinical "
     "reviewers and label authors.",
     [
         "services/ui/src/components/editor/",
         "services/ui/src/components/gold-editor/",
         "services/ui/src/components/gold-dataset/",
         "services/ui/src/components/markdown-editor/",
         "services/ui/src/components/sbar-final/",
         "services/ui/src/components/sbar-playground/",
         "services/ui/src/components/schema-builder/",
         "services/ui/src/components/console/",
         "services/ui/src/components/safety-netting/",
         "services/ui/src/components/AreaIntro.tsx",
         "services/ui/src/components/AssertionChip.tsx",
         "services/ui/src/components/CodedLinksSection.tsx",
         "services/ui/src/components/CorrectionsLog.tsx",
         "services/ui/src/components/ManualEntityBanner.tsx",
         "services/ui/src/components/NerAnnotation",
         "services/ui/src/lib/nerAnnotation.tsx",
     ]),

    ("ui-audit-and-analytics",
     "Audit, dashboards, benchmarks and measures UI",
     "Visual analytics surfaces: audit trail viewer, dashboards, "
     "benchmarks, QOF/SBAR measures, episode timeline, reports and "
     "training games.",
     [
         "services/ui/src/components/audit/",
         "services/ui/src/components/benchmarks/",
         "services/ui/src/app/benchmarks/",
         "services/ui/src/app/audit/",
         "services/ui/src/components/dashboard/",
         "services/ui/src/components/measures/",
         "services/ui/src/app/measures/",
         "services/ui/src/components/reports/",
         "services/ui/src/app/reports/",
         "services/ui/src/components/episodes/",
         "services/ui/src/components/games/",
         "services/ui/src/app/games/",
         "services/ui/src/app/cohorts/",
     ]),

    ("ui-operations-and-tenant",
     "Operations console and tenant integration UI",
     "Cross-cutting operations console, mail outbox, tenant integration "
     "(Entra) UI, and operator-facing tooling.",
     [
         "services/ui/src/components/operations/",
         "services/ui/src/components/tenant/",
         "services/ui/src/app/operations/",
         "services/ui/src/app/tenant/",
         "services/ui/src/app/mail/",
     ]),

    ("ui-settings-and-auth",
     "Settings, auth and onboarding UI",
     "Login, sign-in, onboarding, settings, portal landing page, and the "
     "shared chrome that frames every authenticated page.",
     [
         "services/ui/src/app/settings/",
         "services/ui/src/app/auth/",
         "services/ui/src/app/sign-in/",
         "services/ui/src/app/onboarding/",
         "services/ui/src/app/portal/",
         "services/ui/src/app/pipeline/",
         "services/ui/src/app/gold-dataset/",
         "services/ui/src/app/page.tsx",
     ]),

    ("ui-frontend-api-client",
     "Frontend API client and Next.js proxy routes",
     "Typed API client used by the UI to talk to backend services, plus "
     "the Next.js /api proxy routes that broker session-aware traffic to "
     "internal services.",
     [
         "services/ui/src/lib/api/",
         "services/ui/src/app/api/",
         "services/ui/src/proxy.ts",
     ]),

    ("ui-shared-utilities",
     "Shared frontend libraries, hooks, contexts and stores",
     "Cross-cutting frontend code: hooks, React contexts, Zustand stores, "
     "shared lib helpers (formatting, sorting, NHS number, charts, role), "
     "and the auth/unauthorized screen wrappers used by every route.",
     [
         "services/ui/src/hooks/",
         "services/ui/src/context/",
         "services/ui/src/stores/",
         "services/ui/src/components/ui/",
         "services/ui/src/components/AuthProviderWrapper.tsx",
         "services/ui/src/components/UnauthorizedScreen.tsx",
         "services/ui/src/lib/",
         "services/ui/src/__mocks__/",
     ]),

    ("design-system",
     "Mizaic design system primitives",
     "Reusable design-system primitives (motion provider, layout, "
     "tokens, typography, primitives) used across every product surface.",
     ["services/design-system/src/"]),

    # ---- Backend services/api ----
    ("api-routers",
     "FastAPI router surface for /api/*",
     "All FastAPI router modules under services/api/app/routers/* that "
     "expose the public API contract consumed by the UI and external "
     "callers.",
     ["services/api/app/routers/"]),

    ("api-services-ai-first-pass",
     "AI-first-pass candidate generation service",
     "Service tier under services/api/app/services/candidate_ai_first_pass/ "
     "that runs the AI-first-pass candidate generation, scoring, and "
     "review-queue handling.",
     ["services/api/app/services/candidate_ai_first_pass/"]),

    ("api-services",
     "API service tier",
     "Service modules under services/api/app/services/* that implement "
     "the business logic invoked by the FastAPI routers (training, "
     "context reconciliation, label verification, mail, sync, etc).",
     ["services/api/app/services/"]),

    ("api-models-and-main",
     "API entrypoint and shared models",
     "FastAPI entry-point and shared Pydantic / Neo4j contracts used by "
     "every router and service.",
     [
         "services/api/app/main.py",
         "services/api/app/models/",
     ]),

    # ---- Workers and pipeline ----
    ("analysis-worker",
     "Analysis worker analyzers",
     "Analyzer modules consumed by the analysis worker: anchor detection, "
     "episode builder, cancer-site site resolution, classifier glue, etc.",
     ["services/analysis_worker/app/"]),

    ("pipeline-graph-subgraphs",
     "Pipeline graph subgraphs",
     "LangGraph subgraph definitions and helpers under "
     "libs/pipeline_graph/subgraphs/ that wire together the runtime "
     "extraction pipeline.",
     ["libs/pipeline_graph/subgraphs/"]),

    ("pipeline-worker",
     "Pipeline worker entrypoints",
     "Pipeline worker bootstrap and dispatch modules in "
     "services/pipeline_worker/app/.",
     ["services/pipeline_worker/app/"]),

    ("coding-worker",
     "Coding worker entrypoints",
     "Coding worker bootstrap and dispatch modules in "
     "services/coding_worker/app/.",
     ["services/coding_worker/app/"]),

    ("terminology-tools",
     "Terminology tooling and neo4j MCP tools",
     "Terminology import/maintenance scripts and the neo4j MCP tool "
     "modules used by the read-only Cypher MCP server.",
     [
         "services/terminology/scripts/",
         "services/neo4j_mcp/tools/",
     ]),

    ("prompts-episode-engine",
     "Episode engine prompt templates",
     "Prompt templates in libs/prompts/episode_engine/ that the episode "
     "engine uses to drive its LLM steps.",
     ["libs/prompts/episode_engine/"]),

    ("analytics-and-ods-sync",
     "Analytics API and ODS sync workers",
     "Small worker / API surfaces for the analytics API and ODS sync "
     "scheduler.",
     [
         "services/analytics_api/app/",
         "services/ods_sync/app/",
     ]),

    # ---- libs catch-alls ----
    ("libs-cypher-helpers",
     "Cypher query helper modules",
     "All Cypher query builders under libs/cypher/* that centralise the "
     "graph queries used by services and workers.",
     ["libs/cypher/"]),

    ("libs-shared-utilities",
     "Shared backend libraries",
     "Shared backend Python libraries: auth/role helpers, episode "
     "lifecycle, llm_client, exclusion_detector, key vault loader, and "
     "other cross-service utilities.",
     ["libs/"]),  # catch-all, runs last
]


def assign_bucket(path: str) -> str:
    for bucket_id, _title, _cap, matchers in BUCKETS:
        for m in matchers:
            if isinstance(m, re.Pattern):
                if m.search(path):
                    return bucket_id
            elif path == m or path.startswith(m):
                return bucket_id
    return "unbucketed"


def main() -> int:
    rows = list(csv.DictReader(UNCOVERED.open()))
    print(f"Uncovered files: {len(rows)}")

    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        b = assign_bucket(r["path"])
        grouped[b].append(r)

    plan_rows: list[dict] = []
    for bucket_id, title, capability, _matchers in BUCKETS:
        files = sorted(f["path"] for f in grouped.get(bucket_id, []))
        for path in files:
            plan_rows.append({
                "bucket_id": bucket_id,
                "bucket_title": title,
                "bucket_capability": capability,
                "file_path": path,
                "file_count_for_bucket": str(len(files)),
            })

    # Append unbucketed for visibility (should be 0 once rules are tight).
    unbucketed = sorted(f["path"] for f in grouped.get("unbucketed", []))
    for path in unbucketed:
        plan_rows.append({
            "bucket_id": "unbucketed",
            "bucket_title": "(uncategorised - hand triage)",
            "bucket_capability": "Files that did not match any prefix; please review.",
            "file_path": path,
            "file_count_for_bucket": str(len(unbucketed)),
        })

    PLAN.write_text("")
    with PLAN.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "bucket_id", "bucket_title", "bucket_capability",
            "file_path", "file_count_for_bucket",
        ])
        w.writeheader()
        w.writerows(plan_rows)

    print(f"\nPlan written to {PLAN}")
    print(f"Buckets:")
    for bucket_id, title, _cap, _matchers in BUCKETS:
        n = len(grouped.get(bucket_id, []))
        if n:
            print(f"  {n:4d}  {bucket_id:30s}  {title}")
    if unbucketed:
        print(f"\n  UNBUCKETED ({len(unbucketed)}):")
        for p in unbucketed:
            print(f"    - {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
