# Traceability Matrix

| Field            | Value                                               |
| ---------------- | --------------------------------------------------- |
| Document ID      | DC-TM-001                                           |
| Version          | 1.0.0                                               |
| Status           | Draft                                               |
| Date             | 2026-02-25                                          |
| Standard         | IEC 62304:2006+A1:2015                               |
| Classification   | QMS - Design Controls                               |

---

## 1. Purpose

This document traces software requirements (DC-SRS-001) to design elements, implementation, and verification activities, demonstrating that all requirements are addressed and tested.

---

## 2. Requirement -> Design -> Implementation -> Verification

### 2.1 Training Pipeline

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-TP-001 | Extract clinical entities via LLM | 03-detail 6 | llm_extractor.py | test_v3_llm_extractor.py (18 tests) | ST-TP-001 |
| FR-TP-002 | Sentence splitting via PyRuSH | 03-detail 6 | sentence_splitter.py | -- | ST-TP-001 |
| FR-TP-003 | Deduplicate repeated text lines | 03-detail 6 | sentence_splitter.deduplicate_lines() | -- | ST-TP-001 |
| FR-TP-004 | Hybrid SNOMED resolution | 03-detail 3.2 | coding_resolver.py | test_v3_coding_resolver.py (5 tests) | ST-TP-001 |
| FR-TP-005 | LLM disambiguation | 03-detail 6 | disambiguator.py | test_v3_disambiguator.py (3 tests) | ST-TP-001 |
| FR-TP-006 | Validation checks | 03-detail 6 | pipeline_service.py (validate_encounter_payload) | -- | ST-TP-001 |
| FR-TP-007 | Persist to Patient graph | 03-detail 3.1 | pipeline_service._persist() | -- | ST-TP-001 |
| FR-TP-008 | Hard fail on LLM failure | 03-detail 9 | llm_extractor.py (ExtractionError) | test_v3_llm_extractor.test_disabled_extractor_raises | ST-TP-003 |
| FR-TP-009 | Concurrent processing | 03-detail 10 | pipeline_service.py (ThreadPoolExecutor) | -- | ST-TP-001 |
| FR-TP-010 | SSE progress events | 03-detail 2.1 | pipeline_service._emit() | -- | ST-TP-001 |
| FR-TP-011 | Unified post-processing stack (9 layers) shared between training and runtime pipelines | DI-LEO-AI-050 | libs/pipeline/post_processing.py | test_post_processing_pipeline.py (13 tests), test_pipeline_parity.py (9 tests) | -- |
| FR-TP-012 | Hardened post-processing: sentence-window scoping for lab-value guard and scope guard, narrowed scope guard regexes, removed "discussed" ConText rule, multi-pass ConText deduplication, refuted disorder verdict, narrowed situation normalisation, INJECTION_GUARD on _VERIFY_SYSTEM | DI-LEO-AI-044, DI-LEO-AI-048, DI-LEO-AI-005 | libs/pipeline/post_processing.py, libs/ner/lab_value_guard.py, libs/ner/scope_guard.py, libs/ner/context_engine.py, libs/ner/context_detector.py, libs/ner/observable_post_processor.py, libs/ner/post_processor_rules.py, libs/llm_client/disorder_verifier.py, libs/llm_client/escalation.py | test_lab_value_guard.py, test_scope_guard.py, test_context_detector.py, test_escalation.py, test_post_processing_pipeline.py, test_pipeline_parity.py | -- |
| FR-TP-013 | Semantic tag cross-validation: unbiased terminology resolve, top-3 candidate tag comparison against entity label, auto-reclassification for high-confidence mismatches, HITL flagging with suggested_label and tag_mismatch_delta for medium-confidence mismatches | DI-LEO-AI-053 | label_verifier.py (_cross_check_semantic_tag, _check_terminology_coding), coding_review_queries.py, ReviewCard.tsx, ReviewSection.tsx, CodingReviewCasesModal.tsx | test_semantic_tag_cross_validation.py (23 tests), test_hitl_tier_integration.py (38 tests) | -- |

### 2.2 HITL Review

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-HR-001 | Present ReviewTasks | 03-detail 3.5 | review_service.py, neo4j_store.py | -- | ST-HR-001 |
| FR-HR-002 | Approve/edit/reject/escalate | 03-detail 3.5 | review_service.decide() | -- | ST-HR-002 to ST-HR-004 |
| FR-HR-003 | Record Approval node | 03-detail 1.5 | neo4j_store.append_approval() | -- | ST-HR-002 |
| FR-HR-004 | Record Change node | 03-detail 1.5 | neo4j_store.append_change() | -- | ST-HR-003 |
| FR-HR-005 | No output without human approval | DC-IU-001 6.2 | approval_status workflow; sync only processes 'approved' | -- | ST-HR-002, ST-GS-001 |

### 2.3 Gold Sync

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-GS-001 | Sync approved to DOCUMENTS | 03-detail 3.3 | sync_service.py | test_sync_service.py (3 tests) | ST-GS-001 |
| FR-GS-002 | Delete before create | 03-detail 5.6 | sync_service.py (DELETE_ENCOUNTER_DOCUMENTS) | test_sync_service.test_sync_creates_links_from_gold | ST-GS-001 |
| FR-GS-003 | Only approved synced | 03-detail 5.4 | list_approved_candidates_for_patient() | test_sync_service.test_sync_no_approved_gold | ST-GS-002 |

### 2.4 Terminology Writeback

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-TW-001 | Write SurfaceForm nodes | 03-detail 3.4 | terminology_writeback_service.py | test_terminology_writeback_service.py (8 tests) | ST-GS-001, ST-GS-003 |
| FR-TW-002 | Normalise surface forms | 03-detail 3.4 | _normalize() | test_terminology_writeback_service.TestNormalize (3 tests) | ST-GS-003 |
| FR-TW-003 | Auto trigger + standalone | 03-detail 2.4 | patients.py (sync-gold), terminology.py (writeback) | -- | ST-GS-001, ST-GS-003 |
| FR-TW-004 | Resolver uses SurfaceForm | 03-detail 3.2 | coding_resolver.py | test_v3_coding_resolver.py | ST-GS-004 |

### 2.5 Reset

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-RS-001 | Remove DOCUMENTS | 03-detail 5.2 | reset_service.py | test_reset_service.py (3 tests) | ST-RS-001 |
| FR-RS-002 | Preserve Patient/Encounter | 03-detail 5.2 | RESET_PATIENT_DOCUMENTS query | test_reset_service.py | ST-RS-001 |
| FR-RS-003 | Remove Patient->semantic | 03-detail 5.3 | RESET_PATIENT_DIRECT_SEMANTIC query | test_reset_service.py | ST-RS-001 |
| FR-RS-004 | Reset review queue | 03-detail 5.7 | reset_review_queue_service.py | test_reset_review_queue_service.py (2 tests) | ST-RS-002 |

### 2.6 MedSpaCy

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-MT-001 | Export gold to JSONL | 03-detail 3.7 | export_service.py | -- | ST-MT-001 |
| FR-MT-002 | Training script | 06-plan 2.3 | scripts/train_medspacy.py | -- | ST-MT-001 |
| FR-MT-003 | Configurable training | 06-plan 2.3 | argparse in train_medspacy.py | -- | -- |
| FR-MI-001 | Run inference | 03-detail 3.6 | inference_service.py | -- | ST-MI-002 |
| FR-MI-002 | Graceful no-model | 03-detail 3.6 | inference_service._load_model() | -- | ST-MI-001 |
| FR-MI-003 | dry_run mode | 06-plan 3.1 | inference_service.infer_encounter() | -- | ST-MI-002 |

### 2.7 LLM Usage

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-LU-001 | Track token counts | 03-detail 1.2 | llm_usage.py | test_v3_llm_usage.py (12 tests) | ST-TP-004 |
| FR-LU-002 | Estimate cost | 03-detail 8 | LLMCostConfig | test_v3_llm_usage.TestLLMCostConfig (2 tests) | ST-TP-004 |
| FR-LU-003 | Persist on candidate | 03-detail 5.1 | pipeline_service._build_candidate() | -- | ST-TP-004 |

### 2.8 Data Governance

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-DG-001 | No patient data in Coding graph | 01-purpose 10 | Schema split; PatientGraphClient for HITL | -- | ST-DG-001 |
| FR-DG-002 | HITL data in Patient graph | 02-arch 2.3 | PATIENT_SCHEMA_CONSTRAINTS | -- | ST-DG-001 |
| FR-DG-003 | Coding graph read-only (except SurfaceForm) | 02-arch 2.4 | CodingGraphClient docstring; writeback only | -- | ST-DG-002 |

### 2.9 Terminology API (New — consolidated from PCA + VRB)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-TA-001 | Hybrid SNOMED resolution (exact + fulltext + vector) | Plan WS-B | terminology-api/services/coding_resolver.py | test_terminology_api.py (3 tests) | ST-TA-001 |
| FR-TA-002 | Terminology writeback (learning loop) | Plan WS-B | terminology-api/services/writeback_service.py | test_terminology_api.py (1 test) | ST-TA-002 |
| FR-TA-003 | FHIR ValueSet CRUD + $expand | Plan WS-B | terminology-api/services/valueset_service.py | test_terminology_api.py (2 tests) | ST-TA-003 |
| FR-TA-004 | FHIR ConceptMap CRUD + $translate | Plan WS-B | terminology-api/services/conceptmap_service.py | -- | ST-TA-004 |

### 2.10 Coding Worker (New — from PCA pipeline + auditor_2 patterns)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-CW-001 | Service Bus consumer for coding jobs | Plan WS-C | coding-worker/app/main.py | -- | ST-CW-001 |
| FR-CW-002 | Two-phase pipeline (LLM extract -> unified post-processing -> Terminology resolve) | Plan WS-C | coding-worker/app/pipeline/pipeline_service.py, libs/pipeline/post_processing.py | test_post_processing_pipeline.py, test_pipeline_parity.py | ST-CW-001 |
| FR-CW-003 | LLM response caching | Plan WS-C | libs/llm-client/cache.py | test_shared_libs.py (3 tests) | -- |
| FR-CW-004 | LLM fallback (Bedrock -> Azure OpenAI) | Plan WS-C | libs/llm-client/providers.py | -- | ST-CW-002 |
| FR-CW-005 | Redis progress streaming | Plan WS-C | coding-worker/app/services/progress_publisher.py | -- | -- |

### 2.11 Analysis Worker (New — from VRB + auditor_2)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-AW-001 | Anchor detection (referral, diagnosis, treatment) | Plan WS-D | analysis-worker/app/analyzers/anchor_detector.py | -- | ST-AW-001 |
| FR-AW-002 | Episode building + consolidation | Plan WS-D | analysis-worker/app/analyzers/episode_builder.py | -- | ST-AW-001 |
| FR-AW-003 | Clinical safety signal detection | Plan WS-D | analysis-worker/app/analyzers/safety_net_detector.py | -- | ST-AW-002 |
| FR-AW-004 | Abnormal results tracking | Plan WS-D | analysis-worker/app/analyzers/abnormal_results.py | -- | ST-AW-003 |
| FR-AW-005 | KPI calculation (wait times, consultation counts) | Plan WS-D | analysis-worker/app/analyzers/kpi_calculator.py | -- | ST-AW-004 |
| FR-AW-006 | Quality checks (outliers, milestones, NHS targets, contradictions) | Plan WS-G | analysis-worker/app/analyzers/quality_checker.py | test_quality_checker.py (3 tests) | ST-AW-005 |

### 2.12 FHIR API (New — from VRB)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-FA-001 | FHIR Measure CRUD | Plan WS-E | fhir-api/app/services/measure_service.py | test_fhir_api.py (4 tests) | ST-FA-001 |
| FR-FA-002 | $evaluate-measure (Library Cypher execution) | Plan WS-E | fhir-api/app/services/measure_service.py | -- | ST-FA-002 |
| FR-FA-003 | FHIR Library CRUD | Plan WS-E | fhir-api/app/services/library_service.py | test_fhir_api.py (2 tests) | ST-FA-003 |
| FR-FA-004 | FHIR Device CRUD (agent config) | Plan WS-E | fhir-api/app/routers/device.py | -- | -- |
| FR-FA-005 | FHIR MeasureReport CRUD | Plan WS-E | fhir-api/app/routers/measure_report.py | -- | -- |

### 2.13 Analytics API (New — from auditor_2 + VRB)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-AN-001 | Dashboard aggregation endpoints | Plan WS-E | analytics-api/app/routers/dashboards.py | -- | ST-AN-001 |
| FR-AN-002 | UK IMD data retrieval + patient enrichment | Plan WS-E | analytics-api/app/routers/imd.py | test_analytics_api.py (1 test) | ST-AN-002 |
| FR-AN-003 | Charlson Comorbidity Index scoring | Plan WS-E | analytics-api/app/routers/cci.py | test_analytics_api.py (2 tests) | ST-AN-003 |
| FR-AN-004 | KPI benchmarks + peer comparison | Plan WS-E | analytics-api/app/routers/benchmarks.py | test_analytics_api.py (1 test) | ST-AN-004 |

### 2.14 Authentication & Multi-tenancy (New — from VRB)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-AU-001 | Azure AD JWT validation | Plan WS-A | libs/auth/tenant_context.py | test_shared_libs.py (1 test) | ST-AU-001 |
| FR-AU-002 | TenantContext extraction | Plan WS-A | libs/auth/tenant_context.py | test_shared_libs.py (1 test) | ST-AU-001 |
| FR-AU-003 | Multi-tenancy indexes on Patient Graph | Plan WS-A | neo4j_schema.py (PATIENT_SCHEMA_CONSTRAINTS) | -- | ST-AU-002 |

### 2.15 Frontend — Production UI (New — from PCA + VRB)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-UI-001 | Azure AD sign-in flow | Plan WS-F | lib/auth.ts, SessionProviderWrapper.tsx | -- | ST-UI-001 |
| FR-UI-002 | Dashboard with episode/KPI/safety-net summary | Plan WS-F | app/dashboard/page.tsx | -- | ST-UI-002 |
| FR-UI-003 | Episode timeline with milestones | Plan WS-F | components/episodes/EpisodeTimelineView.tsx | -- | ST-UI-003 |
| FR-UI-004 | safety-net alerts table | Plan WS-F | app/css/page.tsx | -- | ST-UI-004 |
| FR-UI-005 | Visual report builder (FHIR Measure-backed) | Plan WS-F | components/reports/ReportBuilder.tsx | -- | ST-UI-005 |

### 2.16 Fix Analyzer (New — from VRB)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-FX-001 | Analyze corrections and propose knowledge-layer fixes | Plan WS-G | services/api/app/services/fix_analyzer.py | -- | ST-FX-001 |

### 2.17 Message Bus (New — from auditor_2)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-MB-001 | Azure Service Bus adapter | Plan WS-A | libs/message-bus/azure_adapter.py | -- | ST-MB-001 |
| FR-MB-002 | In-memory adapter for local dev | Plan WS-A | libs/message-bus/in_memory_adapter.py | test_shared_libs.py (2 tests) | -- |

### 2.18 Agentic Training Label Auditor (New — DI-LEO-AI-054)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-AUD-001 | Two-pass audit: Opus pass 1 (no tools), Haiku+tools pass 2 for SNOMED needs_review | DI-LEO-AI-054, DO-LEO-AI-036 | scripts/opus_training_auditor.py | test_opus_training_auditor.py | VT-LEO-AI-047 |
| FR-AUD-002 | Bedrock tool_config passthrough and toolUse response parsing in LLMClient.converse() | DI-LEO-AI-054, DO-LEO-AI-036 | libs/llm_client/factory.py | test_opus_training_auditor.py, test_llm_providers.py | VT-LEO-AI-047 |
| FR-AUD-003 | ToolExecutor: resolve_term, get_related_concepts, get_descendants via Terminology API | DI-LEO-AI-054, DO-LEO-AI-036 | scripts/opus_training_auditor.py (ToolExecutor) | test_opus_training_auditor.py | VT-LEO-AI-047 |
| FR-AUD-004 | CostGuardrail: per-run token budget and dollar cap with automatic halt | DI-LEO-AI-054, DO-LEO-AI-036 | scripts/opus_training_auditor.py (CostGuardrail) | test_opus_training_auditor.py | VT-LEO-AI-047 |
| FR-AUD-005 | Hard cap of 5 tool-use iterations per record in agentic loop | DI-LEO-AI-054, DO-LEO-AI-036 | scripts/opus_training_auditor.py (_agentic_audit_record) | test_opus_training_auditor.py | VT-LEO-AI-047 |
| FR-AUD-006 | SNOMED READONLY_FIELDS enforcement -- tool-informed fixes become proposals only | DI-LEO-AI-054, DO-LEO-AI-036 | scripts/opus_training_auditor.py (_classify_fixes) | test_opus_training_auditor.py | VT-LEO-AI-047 |
| FR-AUD-007 | Audit trail JSONL records all tool calls with name, input, and result | DI-LEO-AI-054, DO-LEO-AI-036 | scripts/opus_training_auditor.py (_write_trail_entry) | test_opus_training_auditor.py | VT-LEO-AI-047 |
| FR-AUD-008 | sanitise_for_prompt() applied to all terminology API responses before LLM re-submission | DI-LEO-AI-054, DO-LEO-AI-036 | scripts/opus_training_auditor.py (_agentic_audit_record) | test_opus_training_auditor.py | VT-LEO-AI-047 |

### 2.19 NICE Guideline Ingest (DI-LEO-AI-063)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-NI-001 | Async NICE Syndication API client with retry and Redis-cached catalogue | DI-LEO-AI-063, DO-LEO-AI-063 | services/api/app/services/nice_api_client.py | services/api/tests/test_nice_api_client.py | VT-LEO-AI-063 |
| FR-NI-002 | Idempotent Neo4j MERGE of Guideline, Recommendation, Section nodes from NICE JSON | DI-LEO-AI-063, DO-LEO-AI-063 | services/api/app/services/nice_graph_upserter.py | services/api/tests/test_nice_graph_upserter.py | VT-LEO-AI-063 |
| FR-NI-003 | FastAPI router: catalogue search, fire-and-track ingest, SSE progress, job status | DI-LEO-AI-063, DO-LEO-AI-063 | services/api/app/routers/nice_guidance.py | services/api/tests/test_nice_api_client.py | VT-LEO-AI-063 |

### 2.20 LLM Rule Authoring and HITL (DI-LEO-AI-064)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-RA-001 | GuidanceRuleGenerator uses run_consensus with INJECTION_GUARD and sanitise_for_prompt | DI-LEO-AI-064, DO-LEO-AI-064 | services/api/app/services/guidance_rule_generator.py | services/api/tests/test_guidance_rule_generator.py | VT-LEO-AI-064 |
| FR-RA-002 | Conservative fail_verdict=None -- no rule written on LLM failure or parse error | DI-LEO-AI-064, DO-LEO-AI-064 | services/api/app/services/guidance_rule_generator.py | services/api/tests/test_guidance_rule_generator.py | VT-LEO-AI-064 |
| FR-RA-003 | Generated rules stored with status: pending_review; only active rules visible to bitmap compiler | DI-LEO-AI-064, DO-LEO-AI-064 | services/api/app/services/guidance_rule_generator.py | services/api/tests/test_guidance_rule_generator.py | VT-LEO-AI-064 |
| FR-RA-004 | HITL review queue: list, detail, decide (approve/edit/reject) with immutable audit event | DI-LEO-AI-064, DO-LEO-AI-064 | services/api/app/routers/guidance_rules.py | services/api/tests/test_guidance_rule_generator.py | VT-LEO-AI-064 |

### 2.21 Bitmap Store, Compiler, and Evaluator (DI-LEO-AI-065)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-BM-001 | BitmapStore: pyroaring BitMap with Redis persistence and deterministic BLAKE2b key scheme | DI-LEO-AI-065, DO-LEO-AI-065 | services/terminology_api/app/services/bitmap_store.py | services/terminology_api/tests/test_bitmap_store.py | VT-LEO-AI-065 |
| FR-BM-002 | GuidelineCompiler reads only active AppropriatenessRules from Neo4j and compiles bitmaps | DI-LEO-AI-065, DO-LEO-AI-065 | services/terminology_api/app/services/guideline_compiler.py | services/terminology_api/tests/test_guideline_compiler.py | VT-LEO-AI-065 |
| FR-BM-003 | GuidelineEvaluator applies reqAll and forbid bitwise intersection against patient codes | DI-LEO-AI-065, DO-LEO-AI-065 | services/terminology_api/app/services/guideline_evaluator.py | services/terminology_api/tests/test_guideline_evaluator.py | VT-LEO-AI-065 |
| FR-BM-004 | Versioned bitmaps with explicit admin activate; compile runs in asyncio.to_thread | DI-LEO-AI-065, DO-LEO-AI-065 | services/terminology_api/app/routers/guidelines.py | services/terminology_api/tests/test_guideline_compiler.py | VT-LEO-AI-065 |

### 2.22 Admin Guidance UI (DI-LEO-AI-066)

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-GU-001 | Guidance admin page with Autocomplete catalogue search, SSE ingest progress, job list | DI-LEO-AI-066, DO-LEO-AI-066 | services/ui/src/app/admin/guidance/NiceLoaderSection.tsx | services/ui/src/app/admin/guidance/__tests__/GuidancePage.test.tsx | VT-LEO-AI-066 |
| FR-GU-002 | Plain-English HITL rule review with approve/edit/reject and ConfirmDialog for bulk approve | DI-LEO-AI-066, DO-LEO-AI-066 | services/ui/src/app/admin/guidance/RuleReviewSection.tsx | services/ui/src/app/admin/guidance/__tests__/GuidancePage.test.tsx | VT-LEO-AI-066 |
| FR-GU-003 | Bitmap lifecycle with version accordion, Stepper, and ConfirmDialog for activate | DI-LEO-AI-066, DO-LEO-AI-066 | services/ui/src/app/admin/guidance/BitmapLifecycleSection.tsx | services/ui/src/app/admin/guidance/__tests__/GuidancePage.test.tsx | VT-LEO-AI-066 |
| FR-GU-004 | All fetch errors surface via Alert; no silent swallowing; reading age 11 copy | DI-LEO-AI-066, DO-LEO-AI-066 | services/ui/src/app/admin/guidance/ | services/ui/src/app/admin/guidance/__tests__/GuidancePage.test.tsx | VT-LEO-AI-066 |

---

## 3. Coverage Summary

| Category | Requirements | With Design | With Implementation | With Unit Test | With System Test |
|----------|-------------|------------|-------------------|---------------|-----------------|
| Training Pipeline | 13 | 13 | 13 | 8 | 4 |
| HITL Review | 5 | 5 | 5 | 0 | 4 |
| Gold Sync | 3 | 3 | 3 | 3 | 2 |
| Terminology Writeback | 4 | 4 | 4 | 3 | 3 |
| Reset | 4 | 4 | 4 | 4 | 2 |
| MedSpaCy | 6 | 6 | 6 | 0 | 3 |
| LLM Usage | 3 | 3 | 3 | 3 | 1 |
| Data Governance | 3 | 3 | 3 | 0 | 2 |
| Terminology API | 4 | 4 | 4 | 3 | 4 |
| Coding Worker | 5 | 5 | 5 | 1 | 2 |
| Analysis Worker | 6 | 6 | 6 | 1 | 5 |
| FHIR API | 5 | 5 | 5 | 3 | 3 |
| Analytics API | 4 | 4 | 4 | 2 | 4 |
| Auth & Multi-tenancy | 3 | 3 | 3 | 1 | 2 |
| Frontend UI | 5 | 5 | 5 | 0 | 5 |
| Fix Analyzer | 1 | 1 | 1 | 0 | 1 |
| Message Bus | 2 | 2 | 2 | 1 | 1 |
| Agentic Training Auditor | 8 | 8 | 8 | 8 | 8 |
| NICE Guideline Ingest | 3 | 3 | 3 | 3 | 3 |
| LLM Rule Authoring + HITL | 4 | 4 | 4 | 4 | 4 |
| Bitmap Store/Compiler/Evaluator | 4 | 4 | 4 | 4 | 4 |
| Admin Guidance UI | 4 | 4 | 4 | 4 | 4 |
| **Total** | **99** | **99** | **99** | **56** | **71** |

All requirements have design references, implementations, and at least one verification method (unit test, system test, or both).

---

## 5. User Needs Register -- Referral Triage Programme (UN-030 to UN-048)

The following user needs were identified through structured user research
(UR-LEO-AI-001, 20 interviews across NHS clinical, operational, information,
and internal roles) conducted in March 2026. They represent unmet needs specific
to the referral triage use case and are not yet covered by DIs or VTs.

| UN ID | Title | Stakeholder Role | Safety Class | Priority | DIs | Status |
|-------|-------|-----------------|-------------|----------|-----|--------|
| UN-LEO-AI-030 | Referral Completeness Checking at Point of Triage | Triage Clinician / Referral Management Admin | B | MUST | -- | Draft |
| UN-LEO-AI-031 | Triage Consistency Measurement Across Clinicians | Clinical Lead / Quality Improvement Lead | B | SHOULD | -- | Draft |
| UN-LEO-AI-032 | Real-Time Referral Queue Management | Referral Management Team Leader / Pathway Coordinator | B | MUST | -- | Draft |
| UN-LEO-AI-033 | Referrer Quality Feedback | GP Partner / Practice Manager | B | SHOULD | -- | Draft |
| UN-LEO-AI-034 | Specialty Mis-Routing Detection | Referral Management Administrator | B | SHOULD | -- | Draft |
| UN-LEO-AI-035 | Rejection Rate Analytics | Clinical Director / Referral Management Lead | A | SHOULD | -- | Draft |
| UN-LEO-AI-036 | Triage Queue Backlog Alerting | Referral Management Team Leader / Patient Safety Lead | B | MUST | -- | Draft |
| UN-LEO-AI-037 | Code-to-Source Provenance Linking | Triage Clinician / Clinical Coder / Auditor | B | MUST | -- | Draft |
| UN-LEO-AI-038 | Structured MDT Preparation from Coded Referral Data | MDT Coordinator / Cancer Pathway Coordinator | B | SHOULD | -- | Draft |
| UN-LEO-AI-039 | Junior Clinician Triage Decision Support | Registrar / Junior Doctor covering triage | B | MUST | -- | Draft |
| UN-LEO-AI-040 | Detection of Patients Who Should Be on a Pathway but Are Not | Clinical Lead / Pathway Coordinator | C | SHOULD | -- | Draft |
| UN-LEO-AI-041 | Pathway Segment Decomposition | Clinical Lead / Information Analyst | A | MUST | -- | Draft |
| UN-LEO-AI-042 | Symptom-to-Referral Interval Measurement | Information Analyst / Clinical Lead | A | SHOULD | -- | Draft |
| UN-LEO-AI-043 | Pseudonymisation Before LLM Processing | Data Protection Officer / IG Lead | B | MUST | -- | Draft |
| UN-LEO-AI-044 | Structured Override Error Categories for Model Improvement | NLP Engineer / Clinical AI Quality Lead | B | SHOULD | -- | Draft |
| UN-LEO-AI-045 | Configuration Validation UI with Test Mode | Platform Administrator | B | SHOULD | -- | Draft |
| UN-LEO-AI-046 | Multi-Channel Referral Ingestion | Referral Management Administrator | B | MUST | -- | Draft |
| UN-LEO-AI-047 | Active Engagement Design to Prevent Automation Bias | Clinical Safety Officer / Triage Clinician | B | MUST | -- | Draft |
| UN-LEO-AI-048 | NHS-Specific ROI and Commercial Evidence Pack | Commercial Director | A | SHOULD | -- | Draft |

**Evidence source:** UR-LEO-AI-001 (de-identified interview dataset,
`reports/user-research/user-interviews-deidentified.json`)

---

## 4. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | | | |
| Quality Manager | | | |
