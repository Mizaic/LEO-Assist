# Phase 15 - Change management, approvals, RBAC, security, auth, data protection, ops, KB, misc

- UN count: 42
- DI count: 103
- Approach: grouped thematically; spot-checked major surfaces; anchored Atlas DOs on the most complete subsystems; deferred incomplete themes to the improvements backlog.

## Theme map

| Theme | UNs | Representative DIs | Primary evidence |
|---|---|---|---|
| A. Data protection / de-identification | UN-C2F187E9, UN-70A35225 | C2F187E9 DIs, 70A35225 DIs | `libs/deid/deid.py`, `libs/utils/deidentify.py`, `libs/pipeline_graph/utils/deidentify.py`, `libs/ner/deid_validator.py`, `libs/pipeline_graph/subgraphs/encounter_coding_agent.py` |
| B. AuthN / AuthZ / RBAC / tenancy | UN-A031A603, UN-17724530, UN-412D1ECD | role_state, tenant_context | `libs/auth/role_state.py`, `libs/auth/tenant_context.py`, `libs/auth/practitioner_org_context.py`, `libs/auth/service_auth.py`, `libs/auth/org_scope.py`, `services/api/app/routers/auth.py` |
| C. Secrets / encryption / security | (embedded in A, B, F themes) | - | `libs/keyvault/loader.py`, `libs/azure/credentials.py`, `tests/test_encryption_security.py`, `tests/test_tls_config.py` |
| D. Audit trail / tamper-evidence | UN-F8E1F0D0, UN-07AB5B97 | - | `libs/audit/audit_emitter.py`, `libs/audit/security_log.py`, `libs/audit/kg_verified_writeback.py`, `services/api/app/routers/audit.py` |
| E. Approvals / change queue / CIA workflow | UN-ED00ED74, UN-785DFCDE, UN-F6A0C5BA, UN-EA93F7B7, UN-8659DD53 | - | `services/api/app/routers/review.py`, `services/api/app/routers/audit_quality.py`, `services/ui/src/components/operations/*` |
| F. Async job pattern / workflow | UN-2C6E6933, UN-395B630E | - | `libs/message_bus/`, `libs/workflow/`, `services/pipeline_worker/`, `services/training_worker/` |
| G. API specification / versioning / errors | UN-718B7AF3, UN-21D88B69, UN-F2372DE0 | - | FastAPI routers, OpenAPI generation; needs explicit deprecation policy |
| H. Configuration / pipeline config / sandbox / onboarding / DQ engine | UN-4DCD5891, UN-9A7C2AA3, UN-16116C5F, UN-7294050B, UN-9E66C163 | - | `services/api/app/routers/admin.py`, `services/api/app/routers/onboarding.py`, `services/api/app/routers/data_quality.py`, `libs/dq/` |
| I. FHIR R4 / integration | UN-94833CA3 | - | `services/fhir_api/` |
| J. Knowledge base authoring / currency / alerting / NICE / ICD-10/OPCS / ODS | UN-407F090F, UN-319F33F0, UN-87CB1498, UN-12EEF12D, UN-A412610D, UN-06FDC315, UN-4BD56518, UN-16E151CB, UN-E6195868, UN-E8A5B04A | - | `services/api/app/routers/nice_guidance.py`, `services/terminology_api/`, `services/ods_sync/`, `scripts/build_*.py` |
| K. Research workspace / cohorts / active learning / active evaluation | UN-47B82B96, UN-66396DEA, UN-5236129E, UN-B70ACD96 | - | `services/research_worker/`, `services/ui/src/pages/research/*` |
| L. Ops dashboards / intelligence console / throughput / pricing | UN-BB817C74, UN-3376B57D, UN-FB2DA651 | - | `services/analytics_api/app/routers/dashboards.py`, `services/api/app/routers/pricing.py` |
| M. Audit reports / benchmarks | UN-299200A0 | - | `services/fhir_api/app/services/benchmark_loader.py`, `scripts/build_ncda_*.py` |
| N. Pathway decision rule extraction | UN-6D46C832 | - | `libs/pipeline_graph/subgraphs/guidance_rule_extraction_v2_impl.py` |

## Per-theme findings (summary)

### Theme A - Data protection / de-identification

- `libs/deid/deid.py` provides a regex-based deidentifier with an injectable org pattern; `libs/pipeline_graph/utils/deidentify.py` wraps it for pipeline use; `libs/ner/deid_validator.py` asserts no PHI leaks to downstream LLM prompts.
- Gaps: 70A35225 holdout set and labelled corpus DIs have partial coverage - the protected evaluation split is not formally enforced. Recall metric for deid (C2F187E9 acceptance ~99.9% on PII) not demonstrably measured in CI.
- Status: partial - umbrella DO created below.

### Theme B - AuthN / AuthZ / RBAC / tenancy

- `libs/auth/role_state.py` defines `RoleState`, canonical role set, selected-role workflow.
- `libs/auth/tenant_context.py` enforces tenant scoping; `libs/auth/practitioner_org_context.py` carries the clinician's practice context.
- Gaps: A031A603 token lifecycle documentation is informal; 17724530 credential scoping + COI is partial (review uses selected role but no explicit COI attestation artefact); 412D1ECD physical database separation - single Neo4j database with tenant-scoped queries rather than per-tenant DB.
- Status: partial - umbrella DO created below for the auth/role surface; DB-level separation gap backlogged.

### Theme C - Secrets / encryption / security

- `libs/keyvault/loader.py` provides Azure Key Vault-backed secret resolution; `libs/azure/credentials.py` provides `DefaultAzureCredential`; TLS config test exists.
- Gaps: explicit threat-model-level per-component STRIDE work is not enumerated in `design-controls/risks/`.
- Status: partial - covered under Theme B DO.

### Theme D - Audit trail / tamper-evidence

- `libs/audit/audit_emitter.py` emits FHIR AuditEvent shapes to a write-ahead sink; `libs/audit/security_log.py` logs security-relevant events; `libs/audit/kg_verified_writeback.py` records verified writebacks.
- `services/api/app/routers/audit.py` exposes the read API; Neo4j `:AuditEvent`/`:Change` nodes are append-only per code comments.
- Gaps: export-for-regulator flow (F8E1F0D0) is partial - no packaged export endpoint with signed manifest.
- Status: partial - umbrella DO created below.

### Theme E - Approvals / change queue / clinical-impact-assessment

- `services/api/app/routers/review.py` + `audit_quality.py` plus UI modal operations handle coding review decisions; change queue for clinical safety is implemented on the `:CodingReview` surface.
- Gaps: UN-F6A0C5BA (CIA) and UN-EA93F7B7 (tamper-evident post-approval lock) do not yet enforce an explicit frozen-artefact check. UN-8659DD53 evidence engagement is partially enforced by UI selection but no server-side attestation is recorded.
- Status: partial - backlogged.

### Theme F - Async job pattern / workflow

- `libs/message_bus/` + `libs/workflow/` provide queue abstraction; pipeline_worker, training_worker, analysis_worker, research_worker implement the worker side; API returns job IDs for long-running work.
- Gaps: 395B630E calls for a standard `GET /jobs/:id` shape; this exists in most services but not universally uniform across APIs. No first-class `202 Accepted` + Location header convention is enforced.
- Status: partial - backlogged.

### Theme G - API specification / versioning / errors

- FastAPI generates OpenAPI schemas. No formal deprecation/sunset headers (21D88B69), and no structured error response schema with correlation IDs (F2372DE0) beyond ad-hoc JSON.
- Status: gap - backlogged.

### Theme H - Configuration / pipeline config / sandbox / onboarding / DQ engine

- `services/api/app/routers/admin.py` exposes configuration CRUD.
- `services/api/app/routers/onboarding.py` exists for tenant onboarding.
- `services/api/app/routers/data_quality.py` + `libs/dq/` provide the DQ engine with per-episode rules.
- Gaps: 4DCD5891 test-mode/validation before activation is partial; 9A7C2AA3 sandbox with fault injection is not implemented as a packaged environment.
- Status: partial.

### Theme I - FHIR R4 / integration

- `services/fhir_api/` provides conformance resources.
- Gaps: UK Core 94833CA3 conformance is partial - not all resource profiles validate against UK Core StructureDefinitions.
- Status: partial - backlogged.

### Theme J - Knowledge base

- NICE ingestion (`services/api/app/routers/nice_guidance.py`), ODS sync (`services/ods_sync/`), reference ranges (`services/api/app/routers/reference_ranges.py`), guidance rules.
- Currency dashboard (319F33F0) and alerting on source updates (87CB1498) are partial - data exists but unified KB currency UI is incomplete.
- ICD-10/OPCS alignment (06FDC315) is an open gap.
- Status: partial - backlogged.

### Theme K - Research workspace / cohorts / active learning

- `services/research_worker/` exists with scaffolding; cohort definition CRUD partially implemented; active learning (5236129E) partially covered by training candidate prioritisation but no warm-start registry.
- Status: partial - backlogged.

### Theme L - Ops dashboards / intelligence console / pricing

- `services/analytics_api/app/routers/dashboards.py` provides ops dashboards (pipeline throughput, queue status, DQ). Pricing router exists.
- Gaps: Intelligence Console (3376B57D) aggregation view not fully unified.
- Status: partial.

### Theme M - Audit reports / benchmarks

- Covered by batch-14 benchmark analytics. 299200A0 benchmark comparison charts partially implemented via dashboards.
- Status: partial.

### Theme N - Pathway decision rule extraction

- `libs/pipeline_graph/subgraphs/guidance_rule_extraction_v2_impl.py` extracts structured pathway rules.
- Status: implemented - covered by batch-14 Theme C DO.

## Atlas actions

- Created three umbrella DOs anchoring the best-implemented surfaces (Themes A, B, D).
- All other partial / missing items pushed to the improvements backlog with a `batch-15` tag.
- No per-DI Atlas edits performed (Atlas amendment of 103 DIs is deferred to Phase 16 cross-batch consolidation).

## Appendix - DI roster (summary)

103 DIs across 42 UNs. Full per-DI verdicts deferred to Phase 16 (cross-batch consolidation) due to volume; thematic verdict stands in this report.
