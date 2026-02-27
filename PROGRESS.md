# Production Consolidation - Implementation Progress

**Plan reference:** `.cursor/plans/production_consolidation_comprehensive_4818e9d4.plan.md`

## Workstream Status

| WS | Name | Status | Notes |
|----|------|--------|-------|
| A | Mono-repo scaffold + Docker + Auth + shared libs | DONE | Committed |
| B | Terminology API | DONE | Committed |
| C | Coding Worker | DONE | Committed |
| D | Analysis Worker | DONE | Committed |
| E | FHIR API + Analytics API | DONE | Committed |
| F | Frontend | DONE | Committed |
| G | Quality + IEC 62304 | DONE | Committed |

## WS-A: Mono-repo Scaffold (DONE)

### Completed
- [x] Directory structure: `libs/`, `infra/`, new service directories
- [x] `libs/auth/` - Azure AD JWT validation, TenantContext (from VRB)
- [x] `libs/neo4j-client/` - PatientGraphClient, KnowledgeGraphClient with retry (from PCA)
- [x] `libs/llm-client/` - LLM cache, Bedrock+Azure fallback, token tracking (from auditor_2)
- [x] `libs/message-bus/` - Azure Service Bus adapter + in-memory adapter (from auditor_2)
- [x] `libs/domain-config/` - Domain registry loading from Knowledge Graph ValueSets
- [x] `docker-compose.yml` - Full 7-service + 3-infra compose file
- [x] `infra/dockerfiles/` - Dockerfiles for all 7 services
- [x] Service skeletons: terminology-api, coding-worker, analysis-worker, fhir-api, analytics-api
- [x] `.env.example` - Full environment variable template
- [x] `start.ps1` - Local development startup script
- [x] Multi-tenancy indexes on Neo4j schema

## WS-B: Terminology API (DONE)

### Completed
- [x] `services/terminology-api/app/main.py` - FastAPI app with search, resolve, writeback, valueset, conceptmap routers
- [x] `services/terminology-api/app/queries/` - Cypher queries for terminology, valueset, conceptmap
- [x] `services/terminology-api/app/services/coding_resolver.py` - Hybrid SNOMED resolution (exact+fulltext+vector, score fusion)
- [x] `services/terminology-api/app/services/writeback_service.py` - Terminology writeback/learning loop
- [x] `services/terminology-api/app/services/valueset_service.py` - FHIR ValueSet CRUD + $expand
- [x] `services/terminology-api/app/services/conceptmap_service.py` - FHIR ConceptMap CRUD + $translate
- [x] `services/terminology-api/app/routers/` - HTTP endpoints for all operations

## WS-C: Coding Worker (DONE)

### Completed
- [x] `services/coding-worker/app/main.py` - Service Bus consumer, subscribes to coding-jobs queue
- [x] `services/coding-worker/app/pipeline/pipeline_service.py` - Two-phase pipeline (LLM extract -> Terminology API resolve)
- [x] `services/coding-worker/app/pipeline/llm_extractor.py` - Bedrock converse API clinical term extraction
- [x] `services/coding-worker/app/pipeline/sentence_splitter.py` - Regex + optional PyRuSH splitting
- [x] `services/coding-worker/app/services/job_handler.py` - Job orchestration with progress publishing
- [x] `services/coding-worker/app/services/progress_publisher.py` - Redis-based progress events

## WS-D: Analysis Worker (DONE)

### Completed
- [x] `services/analysis-worker/app/main.py` - Service Bus consumer, subscribes to analysis-jobs queue
- [x] `services/analysis-worker/app/services/job_handler.py` - Full analysis pipeline orchestration
- [x] `services/analysis-worker/app/analyzers/anchor_detector.py` - Referral/diagnosis/treatment anchor detection
- [x] `services/analysis-worker/app/analyzers/episode_builder.py` - Episode construction + consolidation
- [x] `services/analysis-worker/app/analyzers/safety_net_detector.py` - Clinical safety signal detection
- [x] `services/analysis-worker/app/analyzers/abnormal_results.py` - Abnormal test result tracking
- [x] `services/analysis-worker/app/analyzers/kpi_calculator.py` - KPI computation (wait times, consultation counts)

## WS-E: FHIR API + Analytics API (DONE)

### FHIR API
- [x] `services/fhir-api/app/main.py` - FastAPI app with Measure, MeasureReport, Library, Device routers
- [x] `services/fhir-api/app/services/measure_service.py` - Measure CRUD + $evaluate-measure (Cypher execution)
- [x] `services/fhir-api/app/services/library_service.py` - Library CRUD (Cypher storage with hash)
- [x] `services/fhir-api/app/routers/` - Measure, MeasureReport, Library, Device HTTP endpoints

### Analytics API
- [x] `services/analytics-api/app/main.py` - FastAPI app with dashboards, IMD, CCI, benchmarks routers
- [x] `services/analytics-api/app/routers/dashboards.py` - Episode summary, timeline, safety-net alerts
- [x] `services/analytics-api/app/routers/imd.py` - UK IMD 2019 postcode lookup + patient enrichment
- [x] `services/analytics-api/app/routers/cci.py` - Charlson Comorbidity Index scoring
- [x] `services/analytics-api/app/routers/benchmarks.py` - KPI benchmarks, peer comparison, trends

## WS-F: Frontend (DONE)

### Auth
- [x] `src/lib/auth.ts` - NextAuth v5 config with Microsoft Entra ID (Azure AD)
- [x] `src/app/api/auth/[...nextauth]/route.ts` - NextAuth API route handler
- [x] `src/components/SessionProviderWrapper.tsx` - Session provider wrapper
- [x] Updated `layout.tsx` with SessionProvider
- [x] Landing page with sign-in flow

### Navigation
- [x] Updated `AppShell.tsx` - 6 nav items: Dashboard, Patients, Episodes, CSS Alerts, Reports, Pipeline
- [x] User avatar + sign-out in drawer

### Dashboard
- [x] `src/app/dashboard/page.tsx` - Summary stats, episode/KPI/CSS overview
- [x] `src/components/dashboard/KPICards.tsx` - KPI metrics with NHS targets
- [x] `src/components/dashboard/EpisodesByTypeChart.tsx` - Recharts bar chart
- [x] `src/components/dashboard/SafetyNetAlertsSummary.tsx` - Alert severity list

### Episodes
- [x] `src/app/episodes/page.tsx` - Episode list + timeline detail view
- [x] `src/components/episodes/EpisodeList.tsx` - Searchable episode cards
- [x] `src/components/episodes/EpisodeTimelineView.tsx` - Milestone stepper with gap detection

### CSS Alerts
- [x] `src/app/css/page.tsx` - Full safety-net alert table with severity counts, type breakdown

### Reports / Visual Report Builder
- [x] `src/app/reports/page.tsx` - Report list from FHIR Measures
- [x] `src/app/reports/builder/page.tsx` - Report builder page
- [x] `src/components/reports/ReportBuilder.tsx` - Canvas with add/remove/reorder elements
- [x] `src/components/reports/ElementPalette.tsx` - 7 element types (heading, text, KPI, chart, measure, table, divider)
- [x] `src/components/reports/ElementRenderer.tsx` - Inline editing for heading/text, placeholder rendering for charts/tables

### API Client
- [x] `src/lib/analyticsApi.ts` - Typed API client for Analytics API + FHIR API endpoints

### Dependencies Added
- next-auth@beta (Azure AD/Entra ID)
- recharts (charts)
- zustand (state management)

## WS-G: Quality + IEC 62304 (DONE)

### Gold Data Improvements
- [x] Updated `export_service.py` - Fine-grained NER labels (semantic_tag per entity) and context flags (negation, uncertainty, historical, subject, temporality) now exported alongside entity spans

### Ported Services
- [x] `services/api/app/services/fix_analyzer.py` - Fix Analyzer (from VRB) - analyzes HITL corrections, proposes knowledge-layer fixes
- [x] `services/analysis-worker/app/analyzers/quality_checker.py` - Quality Checker (from VRB) - duration outliers, missing milestones, NHS targets, low confidence, temporal anomalies, unactioned safety-net alerts, coding contradictions

### Test Consolidation
- [x] `tests/conftest.py` - Shared fixtures with mocked Neo4j and environment
- [x] `tests/test_terminology_api.py` - Coding resolver, writeback, ValueSet tests
- [x] `tests/test_fhir_api.py` - Measure CRUD + evaluation, Library CRUD tests
- [x] `tests/test_analytics_api.py` - CCI scoring, IMD validation, benchmark tests
- [x] `tests/test_quality_checker.py` - Quality checker + export improvements tests
- [x] `tests/test_shared_libs.py` - LLM cache, message bus, auth library tests

### IEC 62304 Design Controls
- [x] Updated `DC-SOUP-001-soup-list.md` - Added 8 new Python packages (httpx, redis, azure-servicebus, openai, langchain-*, PyJWT), 3 new frontend packages (next-auth, recharts, zustand), updated infrastructure section (Neo4j Aura, Azure Redis, Service Bus, Azure AD, AWS Bedrock, Azure OpenAI)
- [x] Updated `DC-TM-001-traceability-matrix.md` - Added 35 new requirements across 9 categories: Terminology API (4), Coding Worker (5), Analysis Worker (6), FHIR API (5), Analytics API (4), Auth (3), Frontend (5), Fix Analyzer (1), Message Bus (2). Total requirements: 38 -> 73
