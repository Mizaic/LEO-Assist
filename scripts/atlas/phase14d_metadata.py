"""Phase 14d-ii metadata: UN/DI/DO content for each bucket.

For every bucket in phase14d-bucket-plan.csv (excluding `existing-DO-*`
specials and `unbucketed`) we mint:

  - 1 User Need (UN)
  - 1 Design Input (DI)
  - 1 Design Output (DO)
  - link UN -> DI (HAS_DESIGN_INPUT)
  - link DO -> DI (IMPLEMENTS)
  - set DO source_reference to the bucketed file paths

Specials starting with `existing-DO-<dcid>` reuse the existing DO and
only update its source_reference to merge in the new files.
"""

from product import PRODUCT_ID  # noqa: E402,F401

# Default safety class for every bucket. Override per bucket if needed.
DEFAULT_SAFETY_CLASS = "B"


def _ui_un(area: str, who: str, what: str, why: str) -> dict:
    return {
        "title": f"{area} surface for {who}",
        "description": (f"As {who}, I need {what} so that {why}."),
        "stakeholder_types": (
            ["Clinician", "Clinical Safety Officer"]
            if "clinician" in who.lower() or "review" in who.lower()
            else ["Clinician", "Developer"]
        ),
        "rationale": (
            f"The {area} surface is the primary touch-point for the "
            "intended-use workflow it serves; explicit traceability lets "
            "us localise risks, verification tests, and validation "
            "evidence to one design output instead of guessing across "
            "the codebase."
        ),
        "acceptance_criteria": [
            "All files under the bucket prefix are listed in the DO "
            "source_reference.",
            "Every file in the bucket carries the canonical Atlas trace "
            "header pointing at this DO.",
            "The DO is reachable from a UN and parented by a DI in " "Atlas.",
        ],
        "priority": "MUST",
        "safety_class": DEFAULT_SAFETY_CLASS,
    }


def _di(title: str, requirement: str, criteria: list[str]) -> dict:
    return {
        "title": title,
        "description": requirement,
        "rationale": (
            "Establishes a single named requirement that the bucketed "
            "implementation files must satisfy, so verification tests "
            "can target one DI instead of dozens of micro-DIs."
        ),
        "input_type": "functional",
        "verification_method": "test",
        "acceptance_criteria": criteria,
        "safety_class": DEFAULT_SAFETY_CLASS,
    }


def _do(title: str, description: str) -> dict:
    return {
        "title": title,
        "description": description,
        "output_type": "software",
        "safety_class": DEFAULT_SAFETY_CLASS,
    }


# Per-bucket metadata. Keys match BUCKETS in phase14d_bucket_uncovered.py.
BUCKET_META: dict[str, dict] = {
    # ---- UI ----
    "ui-admin-portal": {
        "un": _ui_un(
            "Tenant admin portal",
            "a tenant administrator",
            "a single self-service portal under /admin/* for users, "
            "model settings, knowledge libraries, content guardrails, "
            "and platform monitoring",
            "I can perform routine joiner/mover/leaver and configuration "
            "changes without raising tickets to Mizaic engineering",
        ),
        "di": _di(
            "Admin portal SHALL expose self-service tenant configuration",
            "The /admin/* portal shall expose pages and components that "
            "let an authorised tenant administrator manage users, model "
            "configurations, knowledge libraries, content guardrails, "
            "and platform health from one navigation surface.",
            [
                "Every /admin/* page renders inside the standard "
                "authenticated chrome.",
                "Each admin sub-area is reachable via the admin "
                "navigation tree without page reloads.",
                "Admin actions surface clear success / failure feedback "
                "and respect tenant-scoped role checks.",
            ],
        ),
        "do": _do(
            "Tenant admin portal UI implementation",
            "Pages and components under services/ui/src/app/admin/* "
            "that implement the tenant administrator self-service "
            "portal: users, model configs, knowledge libraries, "
            "guidance, monitoring dashboards, and onboarding flows.",
        ),
    },
    "ui-care-portal": {
        "un": _ui_un(
            "Care portal",
            "a clinician or oncology data nurse",
            "a patient-centric portal that lists encounters, surfaces "
            "patient timelines, and links into the document review "
            "surfaces",
            "I can navigate from a patient list to the right encounter "
            "and document in two clicks",
        ),
        "di": _di(
            "Care portal SHALL provide patient and encounter navigation",
            "The /care/* and /patients/* portal shall list patients, "
            "show patient timelines, and link from any encounter into "
            "the encounter Mission Control and document review "
            "surfaces.",
            [
                "Patient list paginates and filters server-side.",
                "Patient timeline shows encounters in reverse "
                "chronological order with clinical metadata.",
                "Encounter rows link directly into Mission Control.",
            ],
        ),
        "do": _do(
            "Care portal patient and encounter UI implementation",
            "Pages under services/ui/src/app/care/* and "
            "services/ui/src/app/patients/* plus the patient/encounter "
            "list and timeline components that drive the care portal.",
        ),
    },
    "ui-mission-control": {
        "un": _ui_un(
            "Encounter Mission Control",
            "a clinical reviewer",
            "a single workspace per encounter that shows live AI output, "
            "pipeline state, and lets me trigger a batch recode",
            "I can supervise the AI's work on each encounter from one "
            "place instead of navigating between tools",
        ),
        "di": _di(
            "Mission Control SHALL co-locate AI output, state, and actions",
            "The Mission Control surface shall show live AI output, "
            "pipeline state, and reviewer-triggered actions (Ask LEO, "
            "batch recode, escalate) for a single encounter.",
            [
                "Live pipeline events appear without manual refresh.",
                "Reviewer actions complete optimistically and reconcile "
                "against the server response.",
                "Escalation entry points are present for every " "reviewable artefact.",
            ],
        ),
        "do": _do(
            "Mission Control UI implementation",
            "Components under services/ui/src/components/mission-control/* "
            "implementing the per-encounter Mission Control workspace.",
        ),
    },
    "ui-pathway-explorer": {
        "un": _ui_un(
            "Pathway Explorer",
            "a clinical safety lead",
            "a visual explorer for patient pathways, milestones, "
            "escalation rules, and pathway risk overlays",
            "I can localise where a pathway breaks down and edit the "
            "underlying escalation rules without leaving the UI",
        ),
        "di": _di(
            "Pathway Explorer SHALL visualise pathways and edit rules",
            "The Pathway Explorer shall render pathway maps, milestone "
            "lists, escalation-rule editors, and pathway risk overlays "
            "for the configured cancer pathway taxonomy.",
            [
                "Pathway map reflects the latest published pathway " "definition.",
                "Escalation rule edits round-trip through the API and "
                "appear in the next render.",
                "Pathway risk overlay differentiates priority bands "
                "visually and via accessible labels.",
            ],
        ),
        "do": _do(
            "Pathway Explorer UI implementation",
            "Components under services/ui/src/components/pathway/*, "
            "pages under /pathways/*, and the pathwayRisk helper module "
            "that together render the Pathway Explorer surface.",
        ),
    },
    "ui-document-editor": {
        "un": _ui_un(
            "Document and gold-label editor",
            "a clinical reviewer or label author",
            "an editor surface for SBAR, gold labels, schema-builder, "
            "markdown notes, context rules, and entity correction",
            "I can review and correct AI extraction in one place and "
            "drive training datasets from the same surface",
        ),
        "di": _di(
            "Editor SHALL support clinical review and gold-label authoring",
            "The editor surface shall render documents with entity "
            "highlights, allow corrections, support gold-label authoring "
            "with schema validation, and expose context-rule and "
            "safety-netting tooling.",
            [
                "Edits dispatch the correct mutation and refresh local " "state.",
                "Schema-builder catches invalid gold-label shapes "
                "before submission.",
                "Safety-netting overlays render any safety-critical "
                "context flags inline.",
            ],
        ),
        "do": _do(
            "Document and gold-label editor UI implementation",
            "Components under services/ui/src/components/{editor, "
            "gold-editor, gold-dataset, markdown-editor, sbar-final, "
            "sbar-playground, schema-builder, console, safety-netting}/* "
            "and standalone editor utilities.",
        ),
    },
    "ui-audit-and-analytics": {
        "un": _ui_un(
            "Audit, dashboards and benchmarks",
            "a quality assurance lead",
            "visual analytics surfaces (audit trail, dashboards, "
            "benchmarks, QOF/SBAR measures, episode timeline, reports, "
            "training games)",
            "I can monitor pipeline quality and clinical performance "
            "without exporting data to a separate BI tool",
        ),
        "di": _di(
            "Analytics SHALL render audit, benchmark, and measure surfaces",
            "The analytics surface shall render the audit trail, "
            "dashboards, QOF/SBAR measure breakdowns, benchmarks, "
            "episode timelines, training games, and report exports.",
            [
                "Charts respect the global date filter context.",
                "Benchmarks load lazily and degrade gracefully on slow " "tenants.",
                "Reports export to the documented file shapes (CSV, "
                "PDF) without losing column metadata.",
            ],
        ),
        "do": _do(
            "Audit, dashboards, benchmarks and measures UI implementation",
            "Components and pages under services/ui/src/components/{audit, "
            "benchmarks, dashboard, measures, reports, episodes, games}/* "
            "and the matching pages under /benchmarks, /audit, /games, "
            "/cohorts, /reports, /measures.",
        ),
    },
    "ui-operations-and-tenant": {
        "un": _ui_un(
            "Operations console and tenant integration",
            "a platform operator",
            "a cross-cutting operations console plus tenant integration "
            "tooling for Entra group/user binding and mail outbox "
            "review",
            "I can manage tenant-side configuration and platform "
            "operations without shell access",
        ),
        "di": _di(
            "Ops UI SHALL expose console, mail outbox, and tenant integration",
            "The operations UI shall expose the operations console for "
            "training/review queues, the mail outbox viewer, and the "
            "tenant integration controls (Entra group binding, user "
            "picker).",
            [
                "Console actions reach the right backend endpoint and "
                "surface the resulting state change.",
                "Mail outbox viewer paginates and filters by status.",
                "Entra integration controls respect the OBO scope and "
                "audit every mutation.",
            ],
        ),
        "do": _do(
            "Operations console and tenant integration UI implementation",
            "Components under services/ui/src/components/{operations, "
            "tenant}/*, the operations / tenant / mail pages, and the "
            "Entra integration components.",
        ),
    },
    "ui-settings-and-auth": {
        "un": _ui_un(
            "Settings, auth and onboarding",
            "any authenticated user",
            "settings, sign-in, onboarding, portal landing page, and "
            "the chrome that frames every authenticated page",
            "I get a consistent entry experience and can manage my "
            "preferences without leaving the product",
        ),
        "di": _di(
            "Auth and settings SHALL provide consistent shell and onboarding",
            "The settings, auth, sign-in, onboarding and portal pages "
            "shall present a consistent shell, enforce role-based "
            "redirects, and let a user complete onboarding and update "
            "personal settings.",
            [
                "Sign-in flows complete via the configured Entra app.",
                "Onboarding only shows for users without a tenant role.",
                "Settings changes persist server-side and survive a " "reload.",
            ],
        ),
        "do": _do(
            "Settings, auth and onboarding UI implementation",
            "Pages under services/ui/src/app/{settings, auth, sign-in, "
            "onboarding, portal, page.tsx, pipeline, gold-dataset}/* "
            "implementing the auth, settings, and onboarding shell.",
        ),
    },
    "ui-frontend-api-client": {
        "un": _ui_un(
            "Frontend API client and proxy",
            "a frontend developer",
            "a typed API client and a Next.js /api proxy that brokers "
            "session-aware traffic to internal services",
            "the UI talks to one well-typed surface and we can rotate "
            "service endpoints without touching every component",
        ),
        "di": _di(
            "Frontend SHALL use a typed API client and proxy backend traffic",
            "The frontend shall use a typed API client (services/ui/src/"
            "lib/api/*) and route all backend traffic through the "
            "Next.js /api/* proxy so cookies, OBO tokens, and audit "
            "headers stay server-side.",
            [
                "All UI components consume the typed client (no raw "
                "fetch to internal services).",
                "/api proxy routes attach session and audit headers "
                "before forwarding.",
                "Errors are normalised into the typed Result shape "
                "before returning to the UI.",
            ],
        ),
        "do": _do(
            "Frontend API client and Next.js proxy implementation",
            "Modules under services/ui/src/lib/api/*, the Next.js "
            "/api/* proxy routes, and the proxy.ts entry-point.",
        ),
    },
    "ui-shared-utilities": {
        "un": _ui_un(
            "Shared frontend utilities",
            "a frontend developer",
            "shared hooks, contexts, stores, helper libraries (NHS "
            "number, sorting, charts, role state), and the auth/"
            "unauthorized screens",
            "I do not duplicate cross-cutting logic across components "
            "and the user sees consistent behaviour",
        ),
        "di": _di(
            "Frontend SHALL share cross-cutting utilities via libs/contexts/hooks",
            "Cross-cutting frontend logic shall live in shared "
            "lib/contexts/hooks/stores modules under "
            "services/ui/src/{lib, hooks, context, stores}/* with one "
            "canonical implementation per concern.",
            [
                "Hooks follow the use* naming convention and are " "test-covered.",
                "Contexts expose typed providers; consumers use the "
                "context type, not its primitives.",
                "Lib helpers are pure functions with deterministic "
                "outputs for given inputs.",
            ],
        ),
        "do": _do(
            "Shared frontend libraries, hooks, contexts and stores",
            "Modules under services/ui/src/{lib, hooks, context, "
            "stores, components/ui, __mocks__}/* plus the proxy.ts and "
            "AuthProviderWrapper / UnauthorizedScreen components.",
        ),
    },
    "design-system": {
        "un": _ui_un(
            "Design system",
            "a frontend developer",
            "a reusable design-system layer (motion provider, layout, "
            "tokens, typography, primitives) shared across every "
            "product surface",
            "the visual language stays consistent and accessibility "
            "fixes propagate everywhere",
        ),
        "di": _di(
            "Design system SHALL provide reusable primitives and tokens",
            "services/design-system/src shall expose motion, layout, "
            "typography, colour tokens, and primitives consumed by "
            "every product UI surface, with no product-specific "
            "logic.",
            [
                "Primitives have stable public APIs and tested "
                "accessibility behaviour.",
                "Tokens are the single source of truth for colour, "
                "spacing, typography.",
                "Motion provider centralises animation timings and "
                "respects reduced-motion preferences.",
            ],
        ),
        "do": _do(
            "Mizaic design system primitives implementation",
            "All modules under services/design-system/src/* providing "
            "the shared design-system primitives, tokens, and motion "
            "provider.",
        ),
    },
    # ---- Backend services/api ----
    "api-routers": {
        "un": _ui_un(
            "FastAPI router surface",
            "an integrating service or the UI",
            "a stable FastAPI router surface that exposes audited, "
            "tenant-scoped endpoints for every product capability",
            "the UI and external callers have one documented contract "
            "to integrate against",
        ),
        "di": _di(
            "API SHALL expose tenant-scoped routers for every capability",
            "The FastAPI app under services/api/app/routers/* shall "
            "expose one router per capability area (admin, audit, "
            "events, exports, model configs, sbar, terminology, "
            "training, etc) with tenant-scoped, audited endpoints.",
            [
                "Every router enforces the standard auth dependency.",
                "Every mutating endpoint emits an audit event.",
                "Routers are versioned via path prefix and " "documented in OpenAPI.",
            ],
        ),
        "do": _do(
            "FastAPI router surface implementation",
            "All FastAPI router modules under "
            "services/api/app/routers/* that expose the API contract "
            "consumed by the UI and external callers.",
        ),
    },
    "api-services-ai-first-pass": {
        "un": _ui_un(
            "AI first-pass candidate generation",
            "the coding worker pipeline",
            "a service that generates candidate codes for an "
            "encounter using an AI first pass, scores them, and "
            "places them on the review queue",
            "human reviewers see ranked, deduplicated candidates "
            "instead of raw model output",
        ),
        "di": _di(
            "AI first-pass SHALL generate, score, and queue candidate codes",
            "services/api/app/services/candidate_ai_first_pass/* shall "
            "generate candidate codes, score them, deduplicate by "
            "concept identity, and place them on the review queue with "
            "the correct provenance.",
            [
                "Candidate generation is deterministic given the same "
                "input and model version.",
                "Scoring exposes per-candidate confidence the UI can " "render.",
                "Review queue entries carry provenance back to the "
                "originating document and span.",
            ],
        ),
        "do": _do(
            "AI first-pass candidate generation service",
            "Modules under "
            "services/api/app/services/candidate_ai_first_pass/* that "
            "implement candidate generation, scoring, and review-queue "
            "handling for the AI first pass.",
        ),
    },
    "api-services": {
        "un": _ui_un(
            "API service tier",
            "a FastAPI router",
            "a service tier that implements training, context "
            "reconciliation, label verification, mail, sync, and "
            "tenant seeding business logic",
            "routers stay thin and orchestration logic is unit-tested " "and reusable",
        ),
        "di": _di(
            "API service tier SHALL implement business logic outside routers",
            "services/api/app/services/* shall implement the business "
            "logic invoked by FastAPI routers (training creation, "
            "label verification, context reconciliation, mail, sync, "
            "tenant seeding, model config seeding, etc) and shall not "
            "depend on the router layer.",
            [
                "Service modules are importable without starting the " "FastAPI app.",
                "Each service has a clear public function signature "
                "with typed inputs/outputs.",
                "Side effects (DB writes, HTTP calls) are isolated "
                "behind explicit dependencies.",
            ],
        ),
        "do": _do(
            "API service tier implementation",
            "Service modules under services/api/app/services/* "
            "(excluding the candidate_ai_first_pass sub-tree) that "
            "implement the business logic invoked by the FastAPI "
            "routers.",
        ),
    },
    "api-models-and-main": {
        "un": _ui_un(
            "API entrypoint and shared models",
            "every API consumer",
            "a single FastAPI entry-point that wires routers, auth, "
            "logging, and CORS, plus shared Pydantic and Neo4j "
            "contracts used by every router and service",
            "the API behaves consistently and consumers can rely on "
            "stable shared schemas",
        ),
        "di": _di(
            "API SHALL share one entrypoint and one schema contract",
            "services/api/app/main.py shall be the single FastAPI "
            "entry-point; services/api/app/models/* shall hold the "
            "shared Pydantic and Neo4j contracts used across routers "
            "and services.",
            [
                "main.py wires every router, the standard middleware, "
                "and observability hooks.",
                "Contracts in models/* are imported by both routers " "and services.",
                "Schema changes are backwards-compatible or versioned.",
            ],
        ),
        "do": _do(
            "API entrypoint and shared models implementation",
            "services/api/app/main.py and the shared Pydantic / Neo4j "
            "contract modules under services/api/app/models/*.",
        ),
    },
    # ---- Workers / pipeline / libs ----
    "analysis-worker": {
        "un": _ui_un(
            "Analysis worker analyzers",
            "the pipeline worker",
            "a set of analyzers (anchor detection, episode builder, "
            "site resolution, classifier glue) that turn extracted "
            "entities into structured episodes",
            "downstream consumers see deterministic, auditable "
            "episodes instead of raw extraction events",
        ),
        "di": _di(
            "Analysis worker SHALL turn extractions into structured episodes",
            "services/analysis_worker/app/* shall provide deterministic "
            "analyzer modules (anchor detection, episode builder, site "
            "resolution, classifier glue) that turn extracted entities "
            "into structured episodes consumed by the rest of the "
            "platform.",
            [
                "Each analyzer is pure given its inputs (no global " "mutable state).",
                "The episode builder dispatch is deterministic per "
                "site and document.",
                "Analyzers expose explicit fail-open / fail-closed " "behaviour.",
            ],
        ),
        "do": _do(
            "Analysis worker analyzers implementation",
            "Analyzer modules under services/analysis_worker/app/* "
            "that consume extracted entities and produce structured "
            "episodes.",
        ),
    },
    "pipeline-graph-subgraphs": {
        "un": _ui_un(
            "Pipeline graph subgraphs",
            "the pipeline orchestrator",
            "LangGraph subgraph definitions and helpers that compose "
            "the runtime extraction pipeline",
            "we can iterate on individual pipeline phases without "
            "rewriting the whole orchestrator",
        ),
        "di": _di(
            "Pipeline shall be composed from named LangGraph subgraphs",
            "libs/pipeline_graph/subgraphs/* shall provide the "
            "LangGraph subgraph definitions and shared helpers that "
            "compose the runtime extraction pipeline.",
            [
                "Each subgraph is independently importable and " "testable.",
                "Shared helpers do not import from individual "
                "subgraphs (no circular dependencies).",
                "Subgraph wiring is configuration-driven where " "feasible.",
            ],
        ),
        "do": _do(
            "Pipeline graph subgraphs implementation",
            "Modules under libs/pipeline_graph/subgraphs/* defining "
            "the LangGraph subgraphs that compose the runtime "
            "extraction pipeline.",
        ),
    },
    "pipeline-worker": {
        "un": _ui_un(
            "Pipeline worker entrypoints",
            "the platform scheduler",
            "a pipeline worker bootstrap that subscribes to work, "
            "dispatches it to the right pipeline graph, and reports "
            "telemetry",
            "the platform processes documents reliably with one " "audited entry point",
        ),
        "di": _di(
            "Pipeline worker SHALL bootstrap and dispatch work reliably",
            "services/pipeline_worker/app/* shall bootstrap the worker, "
            "subscribe to the work queue, dispatch each document to "
            "the right pipeline graph, and emit telemetry.",
            [
                "Worker startup logs the active model and graph " "version.",
                "Failed dispatches are retried with bounded backoff.",
                "Telemetry events distinguish success, retryable "
                "failure, and terminal failure.",
            ],
        ),
        "do": _do(
            "Pipeline worker entrypoints implementation",
            "Modules under services/pipeline_worker/app/* implementing "
            "the worker bootstrap and dispatch loop.",
        ),
    },
    "coding-worker": {
        "un": _ui_un(
            "Coding worker entrypoints",
            "the platform scheduler",
            "a coding worker bootstrap that runs the coding pipeline "
            "for incoming documents",
            "encounters get coded reliably with one audited worker",
        ),
        "di": _di(
            "Coding worker SHALL bootstrap and run the coding pipeline",
            "services/coding_worker/app/* shall bootstrap the coding "
            "worker, subscribe to the coding work queue, run the "
            "coding pipeline for each document, and emit telemetry.",
            [
                "Worker startup logs the coding pipeline version.",
                "Each document is coded exactly once unless explicitly " "re-queued.",
                "Telemetry mirrors the pipeline worker schema for " "consistency.",
            ],
        ),
        "do": _do(
            "Coding worker entrypoints implementation",
            "Modules under services/coding_worker/app/* implementing "
            "the coding worker bootstrap and dispatch loop.",
        ),
    },
    "terminology-tools": {
        "un": _ui_un(
            "Terminology tooling and Neo4j MCP tools",
            "a terminology engineer or platform operator",
            "tooling for terminology import / maintenance and the "
            "read-only Neo4j MCP tools used by Cursor agents",
            "I can keep terminology fresh and let agents query Neo4j "
            "safely without DBA access",
        ),
        "di": _di(
            "Terminology tools SHALL provide import/maintenance + safe MCP read",
            "services/terminology/scripts/* shall provide the tooling "
            "for terminology import and maintenance; "
            "services/neo4j_mcp/tools/* shall expose the read-only "
            "Neo4j MCP tools used by Cursor agents.",
            [
                "Maintenance scripts are idempotent and " "resume-safe.",
                "MCP tools are read-only and reject mutating " "Cypher.",
                "Both surfaces emit structured logs the platform " "can audit.",
            ],
        ),
        "do": _do(
            "Terminology tooling and Neo4j MCP tools implementation",
            "Scripts under services/terminology/scripts/* and the "
            "Neo4j MCP tool modules under services/neo4j_mcp/tools/*.",
        ),
    },
    "prompts-episode-engine": {
        "un": _ui_un(
            "Episode engine prompts",
            "the episode engine maintainer",
            "versioned prompt templates for the episode engine LLM " "steps",
            "we can iterate on episode-engine prompts under change "
            "control without scattering them across the codebase",
        ),
        "di": _di(
            "Episode engine prompts SHALL live under one versioned module",
            "libs/prompts/episode_engine/* shall hold the prompt "
            "templates the episode engine uses to drive its LLM "
            "steps, with explicit versioning.",
            [
                "Prompts are pure Python data with no runtime " "dependencies.",
                "Each prompt has a stable identifier referenced by " "the engine.",
                "Prompt changes are reviewable via diff in pull " "requests.",
            ],
        ),
        "do": _do(
            "Episode engine prompt templates implementation",
            "Prompt modules under libs/prompts/episode_engine/* "
            "consumed by the episode engine LLM steps.",
        ),
    },
    "analytics-and-ods-sync": {
        "un": _ui_un(
            "Analytics API and ODS sync",
            "a quality assurance lead",
            "an analytics API and an ODS sync scheduler that keep "
            "external reference data fresh",
            "analytics surfaces stay accurate and the platform "
            "reflects the latest organisational data",
        ),
        "di": _di(
            "Analytics + ODS sync SHALL provide read API and scheduled sync",
            "services/analytics_api/app/* shall expose the analytics "
            "read API; services/ods_sync/app/* shall implement the "
            "scheduled ODS reference data sync.",
            [
                "Analytics API endpoints are paginated and filterable " "by date.",
                "ODS sync runs on a schedule and records its last " "successful run.",
                "Both services log structured events the platform " "can audit.",
            ],
        ),
        "do": _do(
            "Analytics API and ODS sync workers implementation",
            "Modules under services/analytics_api/app/* and "
            "services/ods_sync/app/* implementing the analytics read "
            "API and scheduled ODS sync.",
        ),
    },
    "libs-cypher-helpers": {
        "un": _ui_un(
            "Cypher query helpers",
            "every backend service that talks to Neo4j",
            "a centralised library of Cypher query builders so the "
            "graph contract lives in one place",
            "graph schema changes propagate via one library, not via "
            "scattered inline Cypher",
        ),
        "di": _di(
            "Backend services SHALL use libs/cypher/* for graph queries",
            "libs/cypher/* shall hold the Cypher query builders used "
            "by every backend service. Services shall not embed "
            "ad-hoc Cypher inline.",
            [
                "Each query builder returns parameterised Cypher (no "
                "string interpolation of values).",
                "Every query is unit-tested against the canonical " "graph schema.",
                "Renames at the schema level are made in libs/cypher "
                "first, then propagated.",
            ],
        ),
        "do": _do(
            "Cypher query helper modules",
            "Cypher query builders under libs/cypher/* used by every "
            "backend service that talks to Neo4j.",
        ),
    },
    "libs-shared-utilities": {
        "un": _ui_un(
            "Shared backend libraries",
            "every backend service",
            "shared backend Python libraries for auth/role helpers, "
            "episode lifecycle, llm_client, exclusion_detector, key "
            "vault loader, and other cross-service utilities",
            "we do not duplicate cross-cutting logic across services",
        ),
        "di": _di(
            "Backend services SHALL share cross-cutting code via libs/*",
            "Cross-cutting backend logic shall live in libs/* with "
            "one canonical module per concern (auth, episodes, "
            "llm_client, key vault loader, exclusion_detector, "
            "domains, etc).",
            [
                "Each shared module has a focused public surface.",
                "Imports flow from libs/* into services/*, never the " "other way.",
                "Mocks for shared modules live in tests/, not in " "production code.",
            ],
        ),
        "do": _do(
            "Shared backend libraries implementation",
            "Backend Python libraries under libs/* (excluding "
            "libs/cypher/*, libs/pipeline_graph/subgraphs/*, and "
            "libs/prompts/episode_engine/* which are owned by "
            "dedicated DOs).",
        ),
    },
}


# Specials: existing-DO-<dcid>. Phase 14d-ii consults SPECIAL_DO_PARENTS to
# learn the DI(s) to attach in the file headers; no new UN/DI/DO needed.
SPECIAL_DO_PARENTS: dict[str, list[str]] = {
    "DO-77A48DBC": ["DI-4746A178", "DI-B7FEA996", "DI-F8634363"],
}
