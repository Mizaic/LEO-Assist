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
| FR-RS-005 | Bulk reset-and-reprocess with preview and explicit destructive confirmations | DI-LEO-AI-095, DO-LEO-AI-093 | services/api/app/routers/pipeline.py, services/ui/src/app/admin/operations/run/page.tsx | services/api/tests/test_pipeline_router_runtime.py | VT-LEO-AI-095 |
| FR-RS-006 | Encounter-centric batch reset-and-recode with trigger_analysis default false, near-duplicate suppression control, relevance-floor gating (min score plus keyword anchor), and queue-all-results orchestration with chunked submissions | DI-LEO-AI-099, DO-LEO-AI-097 | services/analytics_api/app/routers/mission_control_encounters.py, services/api/app/routers/patients.py, services/ui/src/components/mission-control/EncounterMissionControl.tsx | services/analytics_api/tests/test_mission_control_encounters.py, services/api/tests/test_patients_batch_recode.py, services/ui/src/__tests__/mission-control/EncounterMissionControl.test.tsx | VT-LEO-AI-099 |
| FR-RS-007 | Admin gold-dataset manual duplicate-candidate reduction with preview and similarity-threshold apply | DI-LEO-AI-055, DO-LEO-AI-055 | services/api/app/routers/training.py, libs/cypher/training_candidate_queries.py, services/ui/src/components/gold-dataset/GoldDatasetPanel.tsx | services/api/tests/test_training_candidate_delete.py | VT-LEO-AI-096 |

### 2.6 MedSpaCy

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-MT-001 | Export gold to JSONL | 03-detail 3.7 | export_service.py | -- | ST-MT-001 |
| FR-MT-002 | Training script | 06-plan 2.3 | scripts/train_medspacy.py | -- | ST-MT-001 |
| FR-MT-003 | Configurable training | 06-plan 2.3 | argparse in train_medspacy.py | -- | -- |
| FR-MT-004 | GoldLabel single source for training export and operations workflow alignment | DI-LEO-AI-100, DO-LEO-AI-098 | scripts/migrate_training_labels_to_gold.py, services/training_worker/app/label_exporter.py, services/ui/src/components/operations/OperationsWorkspace.tsx, services/ui/src/components/operations/TrainSection.tsx | tests/test_training_worker_label_exporter.py, services/ui/src/components/operations/__tests__/TrainSection.test.tsx, services/ui/src/components/operations/__tests__/OperationsWorkspace.test.tsx | VT-LEO-AI-100 |
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
| FR-CW-001 | Service Bus consumer for coding jobs | Plan WS-C | services/api pipeline-jobs publish; pipeline-worker consumer | -- | ST-CW-001 |
| FR-CW-002 | Two-phase pipeline (LLM extract -> unified post-processing -> Terminology resolve) | Plan WS-C | coding-worker/app/pipeline/pipeline_service.py, libs/pipeline/post_processing.py | test_post_processing_pipeline.py, test_pipeline_parity.py | ST-CW-001 |
| FR-CW-003 | LLM response caching | Plan WS-C | libs/llm-client/cache.py | test_shared_libs.py (3 tests) | -- |
| FR-CW-004 | LLM fallback (Bedrock -> Azure OpenAI) | Plan WS-C | libs/llm-client/providers.py | -- | ST-CW-002 |
| FR-CW-005 | Redis progress streaming | Plan WS-C | coding-worker/app/services/progress_publisher.py | -- | -- |
| FR-CW-006 | Production coding routing through WorkflowEngine with encounter_loader and queue payload hardening | DI-LEO-AI-094, DO-LEO-AI-092 | services/coding_worker/app/services/job_handler.py, libs/workflow/engine.py, libs/pipeline_graph/subgraphs/encounter_loader.py, services/api/app/routers/pipeline.py, scripts/seed_plan_definitions.py | services/coding_worker/tests/test_job_handler_engine.py, tests/test_workflow_events.py | VT-LEO-AI-094 |
| FR-CW-007 | NER-first extraction route with deterministic non-evidence pre-filter and model-inference provider integration | DI-LEO-AI-096, DO-LEO-AI-094 | libs/nlp/sentence_splitter.py, libs/pipeline_graph/subgraphs/extraction.py, services/coding_worker/app/pipeline/providers/model_provider.py | tests/test_sentence_splitter.py, tests/test_model_provider.py, tests/test_extraction_subgraph_routing.py | VT-LEO-AI-096 |
| FR-CW-008 | Pre-terminology relation_linking plus extraction quality LLM check with constrained drop/correct/add/relation operations, extraction condition routing to hitl_ner_queue, referral-procedure assertion guard, side-effect counselling suppression, provenance tagging, gold-training write gating with sentence-level candidate entities_json persistence, unsafe terminology mapping blocklist, and shared annotation-guideline prompt composition across check/link paths | DI-LEO-AI-097, DO-LEO-AI-095 | libs/pipeline_graph/subgraphs/relation_linking.py, libs/pipeline_graph/subgraphs/llm_check.py, libs/pipeline/post_processing.py, libs/ner/scope_guard.py, libs/nlp/sentence_splitter.py, libs/pipeline_graph/subgraphs/persist.py, libs/pipeline_graph/subgraphs/terminology.py, libs/pipeline_graph/subgraphs/hitl_ner_queue.py, libs/cypher/training_candidate_queries.py, libs/prompts/relation_linking_v1.py, libs/prompts/extraction_check_v1.py, libs/prompts/annotation_guidelines_v1.py, libs/prompts/registry.py, libs/pipeline_graph/registry.py, libs/workflow/engine.py, scripts/seed_prompt_configs.py, scripts/seed_plan_definitions.py | tests/test_relation_linking_subgraph.py, tests/test_llm_check_subgraph.py, tests/test_post_processing_pipeline.py, tests/test_scope_guard.py, tests/test_sentence_splitter.py, tests/test_persist_subgraph_gold.py, tests/test_training_candidate_queries.py, tests/test_terminology_subgraph.py, tests/test_seed_plan_definitions.py, services/api/tests/test_training_candidate_delete.py | VT-LEO-AI-097 |
| FR-CW-009 | Post-terminology coding quality LLM check with drop or force_review, coding condition routing to hitl_coding_queue, tier override enforcement, and guarded persist hold before patient write-back | DI-LEO-AI-098, DO-LEO-AI-096 | libs/pipeline_graph/subgraphs/llm_check.py, libs/pipeline_graph/subgraphs/tier_classify.py, libs/pipeline_graph/subgraphs/persist.py, libs/pipeline_graph/subgraphs/hitl_coding_queue.py, libs/prompts/coding_check_v1.py, libs/pipeline_graph/registry.py, libs/workflow/engine.py, scripts/seed_plan_definitions.py | tests/test_llm_check_subgraph.py, tests/test_tier_classify_subgraph.py, tests/test_persist_subgraph_gold.py, tests/test_seed_plan_definitions.py | VT-LEO-AI-098 |
| FR-CW-010 | Service Bus consumer reconnect backoff and consumer health visibility for pipeline-worker | DI-LEO-AI-019, DO-LEO-AI-060 | libs/message_bus/azure_adapter.py, services/pipeline_worker/app/main.py | tests/test_servicebus_resilience.py, services/coding_worker/tests/test_job_handler_engine.py | VT-LEO-AI-094 |

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
| FR-GU-005 | Reviewers can edit pending rule logic (replace/add/remove SNOMED concepts, edit AT_LEAST minimums and demographics) from a centred dialog with live SNOMED search; edits persist as a new versioned rule that supersedes the predecessor with an immutable audit event | DI-LEO-AI-154, DO-LEO-AI-150, R-LEO-AI-106 | services/api/app/services/guidance_rule_edit.py, services/api/app/routers/guidance_rules.py, services/ui/src/app/admin/guidance/EditRuleDialog/ | services/api/tests/test_guidance_rule_edit.py, services/ui/src/app/admin/guidance/EditRuleDialog/__tests__/ | VT-LEO-AI-152 |
| FR-GU-006 | Reviewers see and can swap the SNOMED-coded recommended procedure (action) on a pending rule; the API exposes `action` parsed from `actionJson`, the dialog renders an Action panel routed through the existing concept search, and saved edits validate the action concept exists before persisting on the new versioned rule (predecessor preserved when omitted) | DI-LEO-AI-170, DO-LEO-AI-169, R-LEO-AI-169 | services/api/app/services/guidance_rule_edit.py, services/api/app/routers/guidance_rules.py, services/ui/src/app/admin/guidance/EditRuleDialog/ActionPanel.tsx, services/ui/src/app/admin/guidance/EditRuleDialog/index.tsx | services/api/tests/test_guidance_rule_edit_action.py, services/ui/src/app/admin/guidance/EditRuleDialog/__tests__/EditRuleDialog.action.test.tsx | VT-LEO-AI-168 |
| FR-GU-007 | Test-patient regression diagnostic uses the SAME roaring-bitmap evaluator as production firing: a per-rule `/diagnose` endpoint walks the compiled `logic_tree` with bitmap subset/intersection ops (including the SNOMED IS_A descendant closure), the Replay Results dialog calls it on demand for each regression and renders the annotated tree hierarchically (AND/OR/AT_LEAST counts visible); the legacy client-side walker is deleted so there is exactly one source of truth | DI-LEO-AI-180, DO-LEO-AI-179, R-LEO-AI-175 | services/terminology_api/app/services/guideline_evaluator.py, services/terminology_api/app/routers/guidelines.py, services/api/app/services/test_patient_service.py, services/api/app/routers/test_patients.py, services/ui/src/app/admin/guidance/test-patients/api.ts, services/ui/src/app/admin/guidance/test-patients/ReplayResultsDialog.tsx | services/terminology_api/tests/test_guideline_evaluator_diagnose.py, services/ui/src/__tests__/test-patients-page.test.tsx | VT-LEO-AI-174 |
| FR-GU-008 | Reviewers can replay UNSAVED draft rules against the saved test-patient library: `GuidelineCompiler.compile_drafts()` builds an isolated custom-scope bitmap (refusing the `global` scope) that re-uses the production compiler, `test_patient_service.sandbox_replay()` orchestrates compile -> replay -> cleanup with try/finally + Redis TTL fallback, and the EditRuleDialog "Test draft" button surfaces the report in the Replay Results dialog; every bitmap-backed surface (production runtime, sandbox, diagnose) explicitly returns `not_compiled: True` + a `recompile_hint` when no ruleset is loaded, and a `RulesetNotCompiledBanner` (with a one-click "Compile now" button for production scopes, an explanation for sandbox scopes) makes the empty-ruleset state impossible to confuse with a clean pass | DI-LEO-AI-181, DO-LEO-AI-180, R-LEO-AI-176 | services/terminology_api/app/services/guideline_compiler.py, services/terminology_api/app/services/bitmap_store.py, services/terminology_api/app/services/guideline_evaluator.py, services/terminology_api/app/routers/guidelines.py, services/api/app/services/test_patient_service.py, services/api/app/routers/test_patients.py, services/ui/src/app/admin/guidance/test-patients/RulesetNotCompiledBanner.tsx, services/ui/src/app/admin/guidance/test-patients/ReplayResultsDialog.tsx, services/ui/src/app/admin/guidance/EditRuleDialog/TestPatientsPanel.tsx | services/terminology_api/tests/test_compile_drafts.py, services/api/tests/test_sandbox_replay.py, services/ui/src/app/admin/guidance/test-patients/__tests__/RulesetNotCompiledBanner.test.tsx, services/ui/src/app/admin/guidance/EditRuleDialog/__tests__/TestPatientsPanel.sandbox.test.tsx | VT-LEO-AI-175 |
| FR-GU-009 | Reviewers can edit a saved test patient in place from /admin/guidance/test-patients: a single Cypher statement updates the TestPatient profile (name, codes, age, sex, pathway, content_hash, updated_at, updated_by) AND atomically clears every existing EXPECTED_RESULT relationship before the service rewrites them; the FastAPI PATCH endpoint is admin-guarded and returns 404 when the id is unknown; BuildPatientDialog accepts an editingPatient prop that seeds the form from the saved patient + expectations, switches title and button copy, calls api.updatePatient, enables Save without a fresh dry-run, and preserves the saved matched_branch_node_ids when the reviewer edits a name; the library page exposes an Edit button on every row | DI-LEO-AI-185, DO-LEO-AI-184, R-LEO-AI-179 | libs/cypher/test_patient_queries.py, services/api/app/services/test_patient_service.py, services/api/app/routers/test_patients.py, services/ui/src/app/admin/guidance/test-patients/api.ts, services/ui/src/app/admin/guidance/test-patients/BuildPatientDialog.tsx, services/ui/src/app/admin/guidance/test-patients/page.tsx | services/api/tests/test_test_patient_service.py, services/api/tests/test_test_patient_router.py, services/ui/src/__tests__/test-patients-page.test.tsx | VT-LEO-AI-179 |

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

## 6. Three Learning Loops -- Continuous Improvement (UN-049 to UN-050)

Design controls for the Three Learning Loops feature (coding quality audit,
surface form vocabulary growth, and NER training data collection). Created
2026-04-03 as Pre-Sprint artefacts per the Three Learning Loops Production
Plan v3.0 (QA-001).

### 6.1 User Needs

| UN ID | Title | Stakeholder Role | Safety Class | Priority | DIs | Status |
|-------|-------|-----------------|-------------|----------|-----|--------|
| UN-LEO-AI-049 | Coding Quality Monitoring and Continuous Improvement (Loops 1 + 2) | Clinical Operations Lead / CSO | B | MUST | DI-072, DI-073, DI-074, DI-075, DI-076 | Draft |
| UN-LEO-AI-050 | NER Model Training Data Collection (Loop 3) | NLP Engineer / Clinical AI Quality Lead | B | MUST | DI-077, DI-078, DI-079 | Draft |

### 6.2 Design Input -> Design Output -> Risk -> Verification Traceability

| DI ID | Title | DO ID | Risks | VT ID | Safety Class | Status |
|-------|-------|-------|-------|-------|-------------|--------|
| DI-LEO-AI-072 | Loop 1: Automated Audit Execution | DO-LEO-AI-070 | R-LEO-AI-047 | VT-LEO-AI-072 | B | Draft |
| DI-LEO-AI-073 | Loop 1: Drift Detection and Alerting | DO-LEO-AI-071 | R-LEO-AI-047; R-LEO-AI-048 | VT-LEO-AI-073 | B | Draft |
| DI-LEO-AI-074 | Loop 1: Overcoded Item Remediation | DO-LEO-AI-072 | R-LEO-AI-049 | VT-LEO-AI-074 | B | Draft |
| DI-LEO-AI-075 | Loop 2: Surface Form Task Creation (Streams A/B/C) | DO-LEO-AI-073 | R-LEO-AI-050 | VT-LEO-AI-075 | B | Draft |
| DI-LEO-AI-076 | Loop 2: Surface Form Revocation and Cascade | DO-LEO-AI-074 | R-LEO-AI-051 | VT-LEO-AI-076 | B | Draft |
| DI-LEO-AI-077 | Loop 3: De-identified Evidence Collection | DO-LEO-AI-075 | R-LEO-AI-052 | VT-LEO-AI-077 | B | Draft |
| DI-LEO-AI-078 | Loop 3: Holdout Set Integrity | DO-LEO-AI-076 | R-LEO-AI-053 | VT-LEO-AI-078 | B | Draft |
| DI-LEO-AI-079 | Loop 3: Training Data Export and PII Gate | DO-LEO-AI-077 | R-LEO-AI-052 | VT-LEO-AI-079 | B | Draft |

### 6.3 Risk Register (Three Learning Loops)

| Risk ID | Title | Category | Initial RPN | Residual RPN | Acceptability | DI Controls |
|---------|-------|----------|-------------|-------------|--------------|-------------|
| R-LEO-AI-047 | Coding quality regression goes undetected | clinical_safety | 18 | 6 | acceptable | DI-072, DI-073 |
| R-LEO-AI-048 | Alert fatigue causes regression to be ignored | use_error | 12 | 3 | acceptable | DI-073 |
| R-LEO-AI-049 | False clinical record persists (overcoded diagnosis) | clinical_safety | 18 | 3 | acceptable | DI-074 |
| R-LEO-AI-050 | Incorrect surface form propagates to future encounters | clinical_safety | 27 | 6 | acceptable | DI-075, DI-076 |
| R-LEO-AI-051 | Revoked mapping leaves historical records incorrect | data_integrity | 18 | 4 | acceptable | DI-076 |
| R-LEO-AI-052 | PII leaks into training corpus | security_breach | 16 | 4 | conditionally_acceptable | DI-077, DI-079 |
| R-LEO-AI-053 | Training/test contamination inflates evaluation metrics | data_integrity | 18 | 6 | acceptable | DI-078, DI-079 |

### 6.4 Pre-existing DI stubs (VT files created to close gaps)

| DI ID | Title | VT ID | Status |
|-------|-------|-------|--------|
| DI-LEO-AI-070 | NCDA Report Template Generation | VT-LEO-AI-070 | Draft (stub) |
| DI-LEO-AI-071 | Avoidable Delay Assessment | VT-LEO-AI-071 | Draft (stub) |

### 6.5 Pipeline Precision Improvements (April 2026 Audit)

| DI ID | Title | DO ID | Risks | VT ID | Safety Class | Status |
|-------|-------|-------|-------|-------|-------------|--------|
| DI-LEO-AI-080 | Appointment and Admin Header Filtering in NLP Pipeline | DO-LEO-AI-078 | R-LEO-AI-054 | VT-LEO-AI-080 | B | Passed |
| DI-LEO-AI-081 | Ambiguous Abbreviation Disambiguation in Extraction and Resolution | DO-LEO-AI-079 | R-LEO-AI-055 | VT-LEO-AI-081 | B | Passed (rev 2) |

Note: Resolver input normalisation (lab-value stripping, EMIS code stripping)
is a bug fix to DI-LEO-AI-004. VT-LEO-AI-003 covers this via the existing
test file (tests/test_coding_resolver.py); new tests added to
tests/test_terminology_normalise.py (VT-LEO-AI-080 also covers these).

DI-LEO-AI-081 revised April 2026: NAD policy changed from "always resolve to
281900007" to "always suppress -- leave for manual review". NAD is ambiguous
between "No abnormality detected" and "No apparent distress" (no SNOMED code);
cannot be auto-coded. Revision captured in VT-081-RUN-002 (33 tests, all pass).

### 6.6 Risk Register (Pipeline Precision)

| Risk ID | Title | Category | Initial RPN | Residual RPN | Acceptability | DI Controls |
|---------|-------|----------|-------------|-------------|--------------|-------------|
| R-LEO-AI-054 | Administrative header lines coded as clinical SNOMED findings | clinical_safety | 24 | 4 | acceptable | DI-080 |
| R-LEO-AI-055 | Ambiguous abbreviation miscoding (CA, MSK, NAD) | clinical_safety | 18 | 4 | acceptable | DI-081 |

### 6.8 Audit-Driven Automated Encounter Remediation (April 2026)

| Artefact | ID | Status | Notes |
|----------|----|--------|-------|
| User Need | UN-LEO-AI-049 | draft | Extends existing coding quality monitoring UN |
| Design Input | DI-LEO-AI-082 | draft | Audit-Driven Automated Encounter Remediation |
| Design Output | DO-LEO-AI-080 | draft | Remediation script + Cypher query module |
| Risk | R-LEO-AI-056 | analyzed | Incorrect automated fix changes clinical coding |
| Verification Test | VT-LEO-AI-082 | draft | LLM gate, audit trail, idempotency, terminology miss |

### 6.10 Domain-Driven Episode Detector (April 2026)

| Artefact | ID | Status | Notes |
|----------|----|--------|-------|
| User Need | UN-LEO-AI-052 | draft | Domain-driven episode detector configuration |
| Design Input | DI-LEO-AI-084 | active | Domain-Driven Episode Detector (v1.1 -- adds IS_A expansion, fast-track pipeline fixes) |
| Design Output | DO-LEO-AI-082 | draft | anchor_detector.py, registry.py, domains.py, episode_builder.py, UI, encounter_rules.json, sentence_splitter.py, extraction_v1.py |
| Risk | R-LEO-AI-058 | analyzed | Episode created from negated/historical assertion |
| Verification Test | VT-LEO-AI-084 | passed | Assertion filter, fail-fast registry, domain_id, flag round-trips, sentence_splitter allowlist, classifier override, IS_A expansion (47 tests) |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-084 | Domain-Driven Episode Detector | R-LEO-AI-058 | VT-LEO-AI-084 |

---

### 6.9 Unified Encounter Coding Agent (April 2026)

| Artefact | ID | Status | Notes |
|----------|----|--------|-------|
| User Need | UN-LEO-AI-051 | draft | Unified LangGraph coding/audit agent |
| Design Input | DI-LEO-AI-083 | draft | Unified Encounter Coding Agent |
| Design Output | DO-LEO-AI-081 | draft | encounter_coding_agent.py + prompts + extractor provider |
| Risk | R-LEO-AI-057 | analyzed | Agent miscoding applied without human review |
| Verification Test | VT-LEO-AI-083 | draft | Tool loop, legacy verdict, NER offsets, kill switch |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-083 | Unified Coding Agent | R-LEO-AI-057 | VT-LEO-AI-083 |

Architecture decisions:
- Agent produces backward-compatible audit verdict (missing/overcoded/wrong_assertion) for
  existing audit pipeline compatibility. New fields (sentence, char_start, char_end,
  snomed_concept_id, metadata) are additive extensions.
- Runtime AgentExtractorProvider always invokes with apply=False: existing pipeline
  persistence layer controls all write-back and HITL routing (preserves R-LEO-AI-026
  and R-LEO-AI-034 mitigations).
- CODING_AGENT_ENABLED=false kill switch falls back to LLMExtractorProvider without
  redeployment.
- 9-layer run_post_processing() stack runs in post_process node before any write-back.

Remediation approach (April 2026 run):
- Phase A -- Systematic Cypher fixes (no LLM): deleted 539 NAD "Normal appearance"
  (281900007) codes and 104 "Seen in GP surgery" (185202000) codes from telephone
  encounter records. Total: 643 DOCUMENTS relationships removed from Neo4j.
- Phase B -- Sonnet verification pass: 10,136 encounters with audit findings sent
  to Claude Sonnet 4.6 for independent clinical verification. Only changes with
  confidence >= 0.80 and agree=true are applied. Disputes written to disputes.jsonl
  for human review. Status: in progress (April 4, 2026).
- Phase C -- Re-audit: planned after Phase B completes to verify pct_clean improvement.

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-082 | Audit-Driven Remediation | R-LEO-AI-056 | VT-LEO-AI-082 |

### 6.7 Terminology Coverage Expansion (April 2026)

118 synonym and structured result surface forms added to terminology server.
No new DI/DO required (surface form maintenance is within scope of DI-LEO-AI-004
and DI-LEO-AI-081 for the lab interpretation pattern prompt additions).

Key additions:
- 93 clinical synonyms: fatigue variants, appetite, back pain, breathlessness,
  weight, GI symptoms, urinary symptoms, systemic findings, pain, mental health
- 3 lymphadenopathy surface forms (swollen glands etc.)
- 22 structured lab result phrases: dipstick urinalysis (glucose+, protein+,
  leucocytes+), abnormal lab summary phrases (PSA raised, Hb low, raised
  creatinine, neutrophilia, eosinophilia, glycosuria, proteinuria)
- Option B extraction prompt additions: lab interpretation pattern rules added
  to EXTRACTION_SYSTEM_V1 so the LLM recognises structured result phrases
- NAD: removed from lookup table and moved to _ALWAYS_IGNORE_TERMS (see 6.5)

### 6.10 Benign Cancer Pathway Closure Detection (April 2026)

Addresses 39-episode referral-only audit: cancer investigation episodes that ended
in a benign histology result were left as 'in_progress' because SNOMED 395100000
(No evidence of cancer found) was not recognised as a pathway-closure milestone.

Changes:
- episode_builder.py: _benign_closure_for_episode() scoped per-episode with 365-day
  window constraint. 395100000 outside the window does NOT close the episode.
- anchor_detector.py: benign_closure milestone bucket added to _classify_anchor_rows.
- anchor.py: benign_closure_anchors now included in _flatten_anchor_result and the
  anchor_result dict passed through LangGraph state.
- registry.py: no_cancer_discharge domain added to NCDA_DOMAIN_CONFIGS with
  milestone_type='benign_closure' (fallback path).
- _seed_no_cancer_discharge_valueset.py: ncda-no-cancer-discharge FHIR ValueSet
  seeded into Neo4j, linked to cancer_audit AuditDomain via HAS_SUBDOMAIN.
- _pin_2ww_clinic_aliases.py: 55 surface forms for 2WW clinic shorthand and
  benign discharge phrases (e.g. 'benign histology', 'Seen in 2WW Clinic') pinned
  to correct SNOMED concepts via terminology server.
- extraction_v1.py: LLM prompt updated to extract 2WW clinic shorthand, hospital
  clinic letter headers as specialist visit evidence, and benign pathway discharge
  statements as 395100000.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-052 | draft | Extended to cover benign closure milestone |
| Design Input | DI-LEO-AI-085 | draft | Benign Cancer Pathway Closure Detection |
| Design Output | DO-LEO-AI-083 | draft | episode_builder.py benign closure logic |
| Risk | R-LEO-AI-059 | analyzed | Spurious benign closure from unrelated 395100000 |
| Verification Test | VT-LEO-AI-085 | passed | 8/8 test cases -- pytest 2026-04-06 |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-085 | Benign Closure Detection | R-LEO-AI-059 | VT-LEO-AI-085 |

Safety constraints enforced:
- Benign closure requires referral anchor (episode must exist before closure can apply).
- 395100000 must be coded AFTER the referral date AND within 365 days.
- Cancer diagnosis (any diagnosis anchor) always takes precedence over benign closure.
- Only present-assertion DOCUMENTS relationships trigger closure.

---

### Change: Per-episode specialist visit claiming (2026-04-07)

**Summary:** Replaced the global-per-site-key specialist matching algorithm
(_group_specialists) with a per-episode temporal claiming algorithm
(_claim_specialists_for_episodes). A specialist visit anchor is now eligible for
an episode only if its encounter date >= episode referral date and falls within
the episode window. Each visit is claimed by at most one episode, processed in
referral-date order. Eliminates specialist_visit_date < referral_date inversions
that caused false stale_post_specialist episode closures.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-053 | draft | Per-episode specialist visit attribution without cross-pathway contamination |
| Design Input | DI-LEO-AI-086 | draft | Per-episode specialist claiming algorithm |
| Design Output | DO-LEO-AI-084 | draft | _claim_specialists_for_episodes implementation |
| Risk | R-LEO-AI-060 | mitigated | False stale status from cross-episode specialist contamination |
| Verification Test | VT-LEO-AI-086 | passed | 10/10 test cases + live rebuild -- pytest 2026-04-07 |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-086 | Per-episode specialist claiming | R-LEO-AI-060 | VT-LEO-AI-086 |

Safety constraints enforced:
- visit_date >= ref_date is a hard filter applied before any site-key check.
- Each specialist visit index is added to a claimed set on first claim; re-use is impossible.
- Episodes with no matching visit receive specialist_seen=False (no fallback to neighbouring episodes).
- Live rebuild confirmed: 0 episodes with specialist_visit_date < referral_date (was 8).
- stale_post_specialist count reduced from 51 to 43 (8 false closures corrected).

### 3.xx Specialist outcome letter milestone (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-054 | draft | Specialist correspondence detection and inferred benign completion |
| Design Input | DI-LEO-AI-087 | draft | specialist_outcome_letter anchors and inference rules |
| Design Output | DO-LEO-AI-085 | draft | anchor_detector + episode_builder letter milestone module |
| Risk | R-LEO-AI-061 | analyzed | False benign completion from letter inference |
| Verification Test | VT-LEO-AI-087 | passed | Letter bucket + inference unit tests |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-087 | Specialist outcome letter milestone | R-LEO-AI-061 | VT-LEO-AI-087 |

### 3.xx Data Quality Toolkit -- API-first DQ service layer (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-056 | approved | Admin data quality toolkit -- inspect, audit, remediate patient graph without scripts |
| Design Input | DI-LEO-AI-089 | draft | DQ toolkit API service layer -- /admin/dq/* + libs/dq/ + MCP + UI |
| Design Output | DO-LEO-AI-087 | draft | libs/dq/ service modules, FastAPI router, MCP server, admin UI dashboard |
| Risk | R-LEO-AI-063 | analyzed | Incorrect patient graph mutation via DQ remediation API |
| Verification Test | VT-LEO-AI-089 | passed | 16 tests: episode health, outcome inference, rules engine, dry-run safety, SF audit, patient inspect |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-089 | Data Quality Toolkit API service layer | R-LEO-AI-063 | VT-LEO-AI-089 |

---

### 3.xx Post-specialist outcome inference engine (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-055 | draft | Infer cancer or benign outcome from post-specialist encounter signals |
| Design Input | DI-LEO-AI-088 | draft | Post-specialist outcome inference engine with confidence scoring |
| Design Output | DO-LEO-AI-086 | draft | outcome_inference.py + episode_builder third pass + analytics fallback |
| Risk | R-LEO-AI-062 | analyzed | Incorrect benign inference masking cancer pathway |
| Verification Test | VT-LEO-AI-088 | passed | All 5 verdict branches, confidence cap, earliest-date, status immutability |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-088 | Post-specialist outcome inference engine | R-LEO-AI-062 | VT-LEO-AI-088 |

---

### 3.xx Stage-at-Diagnosis Enrichment Engine (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-052 | draft | Domain-driven episode detector configuration extended with stage-at-diagnosis enrichment |
| Design Input | DI-LEO-AI-090 | draft | Deterministic stage-at-diagnosis engine (explicit > TNM > unknown) and persistence fields |
| Design Output | DO-LEO-AI-088 | draft | TNM parser, staging rules engine, staging_enrichment subgraph, analytics and UI updates |
| Risk | R-LEO-AI-064 | analyzed | Incorrect stage derivation from explicit stage or TNM evidence |
| Verification Test | VT-LEO-AI-090 | passed | 7 tests: TNM parse, explicit priority, TNM derivation, non-TNM mapping, unknown fallback |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-090 | Stage-at-diagnosis enrichment engine | R-LEO-AI-064 | VT-LEO-AI-090 |

---

### 3.xx Clinical Audit Mission Control (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-058 | draft | Cancer auditors need Mission Control to filter, review, and validate cancer pathway episodes before clinical decisions |
| Design Input | DI-LEO-AI-091 | draft | Mission Control backend API: GET /patients (paginated), GET /kpis, PATCH /review |
| Design Input | DI-LEO-AI-092 | draft | Mission Control frontend UI: Command Bar, KPI Strip, Case Table, Detail Drawer, Timeline, Review Actions |
| Design Output | DO-LEO-AI-089 | draft | mission_control.py FastAPI router implementation |
| Design Output | DO-LEO-AI-090 | draft | Mission Control React UI component tree and API client layer |
| Risk | R-LEO-AI-065 | analyzed | Auditor approves incorrect episode data, leading to flawed clinical decisions |
| Verification Test | VT-LEO-AI-091 | passed | 16 tests: pathway filter, cancer type filter, review filter, pagination, KPI fields, confirmed_cancer benign exclusion (TC-009), review write safety, auth enforcement |
| Verification Test | VT-LEO-AI-092 | passed | 42 tests: plain English labels, URL param round-trip, KPI colour thresholds, timeline rendering, encounter milestone jump chips, coded-entity evidence tooltip with fallback sentence derivation, confirm guard, ReviewActionsPanel |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-091 | Mission Control backend API | R-LEO-AI-065 | VT-LEO-AI-091 |
| DI-LEO-AI-092 | Mission Control frontend UI | R-LEO-AI-065 | VT-LEO-AI-092 |
| DI-LEO-AI-099 | Encounter Mission Control batch recode workflow | R-LEO-AI-063; R-LEO-AI-065 | VT-LEO-AI-099 |
| DI-LEO-AI-179 | Encounter timeline scrubber for Mission Control patient detail | R-LEO-AI-174 | VT-LEO-AI-173 |

---

### 3.xx Mission Control Encounter Timeline Scrubber (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-077 | approved | Cancer auditors and clinical reviewers need to navigate every encounter in a patient's history without losing the focused episode, so surrounding context is one click away rather than hidden behind scope toggles and date guesswork |
| Design Input | DI-LEO-AI-179 | draft | Persistent, sticky encounter timeline on the Mission Control patient detail Encounter text tab: stacked-bar histogram with auto-binning (day / week / month / quarter / year) over a real date axis, linked-vs-other segmentation, episode-window band, hover preview, single-bin direct jump and multi-bin per-encounter popover with framer-motion shared-layout indicator (layoutId="timeline-active-bin"), zoom brush with two role=slider handles + reset-zoom affordance, position: sticky; top: 0 with stuck-state shadow, IntersectionObserver scroll-sync, **brush-driven encounter list filter with timeline-filter-banner and Clear control, jumpToEncounter clears the filter so jumps are always visible**, auto-hide for short histories, full keyboard accessibility, reduced-motion honoured |
| Design Output | DO-LEO-AI-178 | draft | EncounterTimelineScrubber.tsx histogram orchestrator plus new sibling modules timelineBins.ts (pure helpers), TimelineBinPopover.tsx (per-bin popover) and TimelineRangeBrush.tsx (zoom rail). v1.2 adds the controlled visible-range API (visibleFromMs / visibleToMs / onVisibleRangeChange), encounterFilters.ts (timeline-range-aware applyCommonFilters + splitEncounters) and useEncounterLoad.ts (extracted load hook). Built on the existing modular refactor of EncounterTextTab.tsx (497 LOC) and its siblings EncounterCard.tsx, EncounterCodesPanel.tsx, encounterStyles.ts, encounterTextUtils.tsx, encounterRecodeProgress.ts |
| Risk | R-LEO-AI-174 | analyzed | Reviewer skips surrounding-context check during episode review because the affordance is hidden behind scope toggle plus manual scroll, and so misses a clinically relevant signal sitting just outside the episode window |
| Verification Test | VT-LEO-AI-173 | passed | 40 tests: 13 live-render scrubber cases (histogram render, stacked-segment counts, episode window band, single-bin direct jump, multi-bin popover open + popover-row jump, aria-label format, Enter activation, brush slider semantics, reset-zoom round-trip via keyboard, active-bar attributes, sticky position via getComputedStyle), 21 static-source chrome cases (layoutId="timeline-active-bin", useMotion + reducedMotion, framer-motion primitives, MIN_ENCOUNTERS threshold + null guard, position: sticky / top: 0, sibling-module composition, pickGranularity threshold ladder, popover Escape handling, brush ARIA, EncounterTextTab wiring, IntersectionObserver scroll-sync, 497 <= 500 LOC ceiling), 3 regression cases for the existing EncounterTextTab milestone-jump and tooltip behaviour, plus 3 v1.2 integration cases (TC-020/021/022) covering the brush -> encounter list filter coupling, the timeline-filter-banner Clear control, and jumpToEncounter clearing the filter on single-bin click. Wider mission-control sweep: 11 suites / 88 cases passing |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-179 | Encounter timeline scrubber for Mission Control patient detail | R-LEO-AI-174 | VT-LEO-AI-173 |

---

### 3.xx Mission Control Encounter Overlay-First Navigation (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-077 | approved | Cancer auditors and clinical reviewers need to navigate every encounter in a patient's history without losing the focused episode, so surrounding context is one click away rather than hidden behind scope toggles and date guesswork |
| Design Input | DI-LEO-AI-213 | draft | Mission Control patient detail Encounter text tab MUST replace the scope chips and Other-encounters / All-other-encounters accordions with a single chronological encounter list filtered ONLY by the histogram brush; brush MUST default to the padded episode-linked window; linked encounter cards MUST carry an "In episode" chip and accent; histogram MUST render three episode overlays -- a tightened band spanning first-linked..last-linked encounter dates, per-encounter linked tick markers along the bottom axis, and labelled milestone markers along the top axis; every jump path (milestone chips, single-bin click, popover row, milestone marker) MUST clear the brush, coded-only, and search filters; Coded only and Search filters MUST be retained; EncounterTextTab.tsx MUST stay <=500 LOC |
| Design Output | DO-LEO-AI-210 | draft | EncounterTextTab.tsx (472 LOC) refactor: scope state and accordions removed, splitEncounters helper deleted, applyCommonFilters drives a single chronological list, defaultRangeAppliedRef seeds the brush to the padded episode-linked window, jumpToEncounter clears all filters before scrolling. New TimelineOverlays.tsx renders LinkedEncounterTicks (bottom axis) and MilestoneMarkers (top axis with tooltips). EncounterTimelineScrubber.tsx tightens its windowBand to the first-linked..last-linked timestamp range and threads the milestones prop. EncounterCard.tsx renders the "In episode" chip and 3px accent when isLinkedToEpisode is true. New useEncounterRecode.ts hook lifts the reset-and-recode flow so EncounterTextTab.tsx stays under 500 LOC |
| Risk | R-LEO-AI-174 | analyzed | Reviewer skips surrounding-context check during episode review because the affordance is hidden behind scope toggle plus manual scroll, and so misses a clinically relevant signal sitting just outside the episode window |
| Verification Test | VT-LEO-AI-205 | passed | 65 targeted tests (113 mission-control suite tests overall): EncounterTextTab.test.tsx asserts removal of scope chips and accordions, retention of Coded only switch and Search field, "In episode" chip presence on linked cards, and clearing of brush/coded-only/search filters when a milestone chip is clicked; EncounterTextTab-timeline-filter.test.tsx covers the default padded brush, brush-driven list filtering, single-bin click clearing the filter, and milestone-marker jumps clearing the filter; EncounterTextTab-scrubber-chrome.test.ts asserts removal of legacy UI strings, presence of milestones prop wiring, linkedTicks/milestoneMarkers usage, the updated "drag the focus band to widen or narrow your view" caption, and the 472 <= 500 LOC ceiling; EncounterTimelineScrubber.test.tsx covers the tightened first-linked..last-linked windowBand, the LinkedEncounterTicks render path, and the MilestoneMarkers render path with keyboard activation |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-213 | Mission Control encounter overlay-first navigation | R-LEO-AI-174 | VT-LEO-AI-205 |

---

### 3.xx Test-Patient Diagnostic Source-of-Truth (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-076 | approved | Reviewers must confirm that previously approved patient profiles still reach the same recommendation after any rule edit, deploy or rebuild |
| Design Input | DI-LEO-AI-180 | approved | Test-patient regression diagnostics MUST use the same roaring-bitmap evaluator that production uses to fire rules; per-rule diagnose() returns an annotated logic_tree (matched + matched_count + min) so the UI can render it hierarchically and the reviewer's verdict can never disagree with the live firing decision |
| Design Output | DO-LEO-AI-179 | approved | GuidelineEvaluator.diagnose() + POST /terminology/guidelines/diagnose + test_patient_service.diagnose_rule_against_patient + POST /guidance/test-patients/diagnose + ReplayResultsDialog.RegressionDetail/DiagnoseNodeRow hierarchical render; legacy client-side evaluateLogicTree.ts deleted |
| Risk | R-LEO-AI-175 | mitigated | Reviewer diagnostic disagrees with the production rule firing decision (could approve a real regression that silently disables a 2-week wait recommendation, or block a benign edit) |
| Verification Test | VT-LEO-AI-174 | passed | 9 tests: 7 backend pytest cases (parity v1+v2, AT_LEAST counts, missing bitmap, no ruleset, unknown rule) plus 2 jest cases for the dialog (diagnose fetch + hierarchical render, recompile-hint on failure); guidance UI suite 105/105 passing |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-180 | Test-patient regression diagnostics use the production bitmap evaluator | R-LEO-AI-175 | VT-LEO-AI-174 |

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| Design Input | DI-LEO-AI-181 | approved | Sandbox replay of UNSAVED draft rules MUST reuse the production compiler in an isolated custom scope (refusing global), AND every bitmap-backed surface MUST signal `not_compiled` + recompile_hint instead of returning a silent zero-match when no ruleset is loaded |
| Design Output | DO-LEO-AI-180 | approved | GuidelineCompiler.compile_drafts + BitmapStore.delete_scope/set_scope_ttl + evaluator/diagnose `not_compiled` payload + POST /guidelines/bitmap/compile-draft + DELETE /guidelines/scopes + test_patient_service.sandbox_replay + POST /guidance/test-patients/sandbox-replay + RulesetNotCompiledBanner + Test draft button in EditRuleDialog |
| Risk | R-LEO-AI-176 | mitigated | Reviewer interprets a silent zero-match as "rule does not match" when no ruleset is compiled (could approve a regressing edit because the empty ruleset is indistinguishable from a clean pass) |
| Verification Test | VT-LEO-AI-175 | passed | 13 tests: 8 backend pytest cases (compile_drafts global refusal, custom-scope happy path, evaluator/diagnose not_compiled, delete_scope happy path + global refusal, sandbox_replay compile+replay+cleanup happy + failure paths, diagnose passthrough) plus 5 jest cases (banner production/sandbox/error variants + TestPatientsPanel sandbox happy + empty-compile paths); guidance UI suite 93/93 passing |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-181 | Sandbox draft-rule replay and explicit "no ruleset compiled" signalling | R-LEO-AI-176 | VT-LEO-AI-175 |

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| Design Input | DI-LEO-AI-185 | approved | Reviewers MUST be able to edit a saved test patient in place from /admin/guidance/test-patients (PATCH endpoint + atomic Cypher rewrite + dialog edit-mode + library-page Edit button) so that fixing a typo or adjusting an expectation no longer requires delete + rebuild |
| Design Output | DO-LEO-AI-184 | approved | UPDATE_TEST_PATIENT Cypher (atomic props update + EXPECTED_RESULT clear) + update_patient service helper + PATCH /guidance/test-patients/{id} endpoint + api.updatePatient client + BuildPatientDialog editingPatient prop + page.tsx Edit button |
| Risk | R-LEO-AI-179 | mitigated | Editing a saved test patient silently drops or corrupts an EXPECTED_RESULT, masking future regressions (the in-place edit replaces the existing expectations, so a bad edit could drop a must-NOT-fire assertion) |
| Verification Test | VT-LEO-AI-179 | passed | 10 cases: 3 service pytest cases (happy path / 404 / empty expectations), 3 router cases (PATCH happy / 404 / empty), 1 api client jest case (PATCH + JSON_HEADERS), 3 static-source cases (dialog edit-mode wiring + matched_branch_node_ids preservation + page Edit button) -- 34 backend + 21 frontend tests passing |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-185 | In-place edit for saved test patients | R-LEO-AI-179 | VT-LEO-AI-179 |

---

### 3.xx Spinal-TNM Context Disambiguation Guard (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-002 | draft | System assigns SNOMED CT codes to free-text encounter narratives using NLP |
| Design Input | DI-LEO-AI-093 | draft | Spinal-TNM context disambiguation guard: suppress standalone TNM tokens in spinal/physiotherapy sentences; add LLM prompt negative extraction rule |
| Design Output | DO-LEO-AI-091 | draft | is_spinal_context() predicate + reclassify_assertion() spinal guard block in scope_guard.py; vertebral level DO NOT EXTRACT rule in extraction_v1.py |
| Risk | R-LEO-AI-066 | analyzed | Spinal vertebral level notation misclassified as cancer TNM staging observable entity |
| Verification Test | VT-LEO-AI-093 | passed | 25 tests: spinal facet/nags/snags/radiculopathy/vertebrae suppression, full-triplet exemption, oncology-context exemption, non-staging tags unaffected, absent-assertion bypass, is_spinal_context predicate |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-093 | Spinal-TNM context disambiguation guard | R-LEO-AI-066 | VT-LEO-AI-093 |

---

### 3.xx GDPR-Isolated Candidate Cascade Delete (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-027 | implemented | AI-augmented training data quality assurance with terminology verification |
| Design Input | DI-LEO-AI-055 | draft | GDPR-isolated learning loop supports cascade delete and manual similarity-dedupe of TrainingCandidate records |
| Design Output | DO-LEO-AI-055 | draft | Candidate cascade delete and dedupe preview/apply query and API/UI integration for admin gold dataset |
| Risk | R-LEO-AI-039; R-LEO-AI-040; R-LEO-AI-041 | analyzed | Protect training data quality and prevent patient linkage or identity leakage |
| Verification Test | VT-LEO-AI-096 | passed | Candidate delete and dedupe preview/apply endpoints return expected status and payloads |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-055 | GDPR-isolated learning loop and operations UX | R-LEO-AI-039; R-LEO-AI-040; R-LEO-AI-041 | VT-LEO-AI-055; VT-LEO-AI-096 |

---

### 3.xx GoldLabel Single Source for Training (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-050; UN-LEO-AI-027 | draft/implemented | Consolidated model training data source and aligned operations workflow |
| Design Input | DI-LEO-AI-100 | draft | GoldLabel is the single source for training export; legacy include=true TrainingLabel migrated |
| Design Output | DO-LEO-AI-098 | draft | Migration utility, GoldLabel exporter path, and operations training UX redesign |
| Risk | R-LEO-AI-052; R-LEO-AI-053; R-LEO-AI-039 | analyzed | PII, contamination, and quality risks controlled while consolidating sources |
| Verification Test | VT-LEO-AI-100 | passed | Exporter and operations workflow verification for consolidated path |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-100 | GoldLabel single source for training | R-LEO-AI-052; R-LEO-AI-053; R-LEO-AI-039 | VT-LEO-AI-100 |

---

### 3.xx Double-Negation Guard for Pre-Negated SNOMED Situation Concepts (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-002 | implemented | SNOMED CT coding with negation detection |
| Design Input | DI-LEO-AI-101 | draft | Guard detects and corrects double negation when ConText sets absent on a situation concept whose PT already encodes a negative |
| Design Output | DO-LEO-AI-099 | draft | fix_double_negated_situations() in post_processing.py + terminology._resolve_terms wiring |
| Risk | R-LEO-AI-069 | analyzed | Clinical assertion inversion on pre-negated SNOMED situation concepts (e.g. suicidal ideation, self-harm) |
| Verification Test | VT-LEO-AI-101 | passed | 15 automated tests covering correction, non-interference, idempotency, and runtime path |
| Design Input | DI-LEO-AI-102 | draft | Analytics assertion filter - exclude absent/hypothetical codes from CCI and cohort queries |
| Design Output | DO-LEO-AI-100 | draft | _CONFIRMED_ASSERTIONS guard in cci.py and cohorts.py |
| Risk | R-LEO-AI-070 | mitigated | Absent-coded condition included in CCI score or cohort selection |
| Verification Test | VT-LEO-AI-102 | passed | 12 automated tests covering query structure and assertion-aware scoring |

| Design Input | DI-LEO-AI-103 | draft | Assertion determined solely by post-processing pipeline - LLM extraction SHALL NOT assign assertion |
| Design Output | DO-LEO-AI-101 | draft | Assertion-free LLM extraction output; parser hardcodes present; ConText is sole assertion authority |
| Verification Test | VT-LEO-AI-103 | passed | 8 automated source-inspection and prompt-schema tests |
| Design Input | DI-LEO-AI-104 | draft | Polarity-encoded finding guard - corrects double negation on finding concepts with absent/not-detected/negative suffix in SNOMED PT |
| Design Output | DO-LEO-AI-102 | draft | fix_polarity_encoded_findings in post_processing.py; called from terminology.py after SNOMED resolution |
| Risk | R-LEO-AI-071 | analyzed | Assertion inversion on polarity-encoding SNOMED finding concepts (e.g. Perineural invasion by tumor absent) |
| Verification Test | VT-LEO-AI-104 | passed | 13 automated tests covering all polarity suffix patterns, tag gates, idempotency, and runtime path wiring |
| Design Input | DI-LEO-AI-104 | draft | Referral episode closure from same-encounter benign/normal qualifier plus site-related finding within 90 days, suppressed by competing diagnosis |
| Design Output | DO-LEO-AI-102 | draft | BENIGN_QUALIFIER_CLOSURE_QUERY and closed_benign_qualifier episode lifecycle wiring |
| Risk | R-LEO-AI-071 | mitigated | Unrelated benign qualifier causes erroneous cancer pathway closure |
| Verification Test | VT-LEO-AI-104 | passed | 11 automated tests including site-match, mismatch rejection, diagnosis suppression, and HITL enforcement |

| Design Input | DI-LEO-AI-105 | draft | Intelligence Console UX - unified admin navigation, 6-stage health bar, contextual nudge, URL migration |
| Design Output | DO-LEO-AI-103 | draft | Console page, stage components, design tokens, 301 redirects |
| User Need | UN-LEO-AI-059 | draft | Clinical informaticians need a unified Intelligence Console |
| Verification Test | VT-LEO-AI-105 | passed | URL audit CI test (0 deprecated admin URLs) and redirect config |

| Design Input | DI-LEO-AI-106 | draft | Training quality - span realign, assertion filter, golden set, warm-start, active learning |
| Design Output | DO-LEO-AI-104 | draft | label_exporter, evaluator, trainer, job_store, golden_set_queries, active learning API |
| User Need | UN-LEO-AI-060 | draft | Model trainers need active learning, per-entity F1, golden set, warm-start |
| Risk | R-LEO-AI-072 | mitigated | Corrupt or non-present training data degrades NER model |
| Verification Test | VT-LEO-AI-106 | passed | 21 automated tests: span realign, assertion filter, per-label F1, warm-start fallback, golden gate |

| Design Input | DI-LEO-AI-107 | draft | Multi-label NER - spancat, layer 5 nesting refinement, prompt preservation, and canonical shared annotation-guideline reuse |
| Design Output | DO-LEO-AI-105 | draft | base.cfg spancat (ngram_range_suggester max_size=10), label_exporter doc.spans["sc"], evaluator spans_sc_*, inference fallback, post_processing nesting, prompt updates, shared guideline composition, and reviewer guidance surfaces |
| User Need | UN-LEO-AI-061 | draft | Clinicians need NER to classify same span under multiple SNOMED semantic types |
| Risk | R-LEO-AI-073 | analyzed | Spurious additional NER label inflates false positive SNOMED coding rate |
| Verification Test | VT-LEO-AI-107 | passed | Multi-label export, inference multi-label, layer 5 nesting, backward compat |
| Design Input | DI-LEO-AI-108 | draft | Ontology-grounded relation modeling and reviewer workflow |
| Design Output | DO-LEO-AI-106 | draft | Canonical relation schema, policy validation, relation train/eval, model-first runtime fallback |
| User Need | UN-LEO-AI-062 | draft | Clinical reviewers need ontology-grounded relation linking for safe entity semantics |
| Risk | R-LEO-AI-074 | analyzed | Invalid or missing relations distort coding interpretation and analytics |
| Verification Test | VT-LEO-AI-108 | passed | Relation schema/policy/runtime and relation train/eval verification |
| User Need | UN-LEO-AI-063 | draft | Guided research workspace for longitudinal patient graph exploration |
| Design Input | DI-LEO-AI-109 | draft | Pathway Explorer API and GDS services |
| Design Input | DI-LEO-AI-110 | draft | Pathway Explorer UI/UX components |
| Design Output | DO-LEO-AI-107 | draft | Pathway Explorer API and GDS services implementation |
| Design Output | DO-LEO-AI-108 | draft | Pathway Explorer UI components implementation |
| Risk | R-LEO-AI-075 | analyzed | Misleading graph algorithm results acted on clinically |
| Risk | R-LEO-AI-076 | analyzed | Algorithm jargon in UI causes user misinterpretation |
| Verification Test | VT-LEO-AI-109 | passed | Pathway Explorer API/GDS services unit tests |
| Verification Test | VT-LEO-AI-110 | passed | Pathway Explorer UI static analysis (49 assertions) |

| User Need | UN-LEO-AI-064 | draft | Pipeline must completely capture string results and pre-entity values for observable entities |
| Design Input | DI-LEO-AI-111 | draft | Observable value-unit linking: string results and pre-entity values |
| Design Output | DO-LEO-AI-109 | draft | Extended link_observable_value_units with string pass and raw-text fallback |
| Risk | R-LEO-AI-077 | analyzed | Observable value left empty for string or pre-entity results - downstream abnormal detection degraded |
| Verification Test | VT-LEO-AI-111 | passed | Four tests: string after, string before, numeric raw-text fallback, string raw-text fallback |

| User Need | UN-LEO-AI-065 | draft | Patient-facing surfaces usable ages 8-80 at WCAG 2.1 AA with plain-English copy |
| User Need | UN-LEO-AI-066 | draft | Carer-facing surfaces make patient context, permission scope, and escalation explicit |
| User Need | UN-LEO-AI-067 | draft | Junior / trainee staff can self-onboard through in-product explanation and coach marks |
| User Need | UN-LEO-AI-068 | draft | Older clinicians can work at full speed with larger default text, high contrast, and keyboard-first alternatives |
| Design Input | DI-LEO-AI-118 | draft | Inclusive design token system (typography, spacing, radius, motion, focus, contrast pairs) |
| Design Output | DO-LEO-AI-115 | draft | services/ui/src/theme/tokens.ts + tokens.css + theme.ts consume tokens; AA pairs validated |
| Risk | R-LEO-AI-078 | analyzed | Low-contrast text or unchecked motion causes missed safety information |
| Verification Test | VT-LEO-AI-113 | passed | 5 Jest cases: token group presence, WCAG AA contrast pairs, focus-ring size/contrast, readable typography, tokens.css :root + reduced-motion |
| Design Input | DI-LEO-AI-119 | draft | Density modes (compact/comfortable/spacious) with 44x44px touch targets on patient-reachable routes |
| Design Output | DO-LEO-AI-116 | draft | DensityProvider + useDensity/useDensityTokens hooks; localStorage persistence; route-based default |
| Risk | R-LEO-AI-079 | analyzed | Dense UI causes mis-taps for touch / low-dexterity users on patient-reachable screens |
| Verification Test | VT-LEO-AI-114 | passed | 5 Jest cases: default tier, patient-reachable override, >=44px spacious, localStorage persist, staff preference |
| Design Input | DI-LEO-AI-120 | draft | Global a11y baseline - AppShell landmarks, aria-current, logo-as-button, OrgSelect label, ConfirmDialog aria, StatusDot shape encoding |
| Design Output | DO-LEO-AI-117 | draft | AppShell.tsx, ConfirmDialog.tsx, StatusDot.tsx, TermSearch.tsx updates; eslint-plugin-jsx-a11y; @axe-core/playwright e2e |
| Risk | R-LEO-AI-080 | analyzed | Assistive-tech users cannot perceive navigation state or status information |
| Verification Test | VT-LEO-AI-115 | partial_pass | 5 Jest cases pass (aria-current, nav landmark, OrgSelect, ConfirmDialog, StatusDot); axe-core e2e case wired and pending CI run |
| Design Input | DI-LEO-AI-121 | draft | Explanation pattern framework (PageIntro, HelpPopover, CoachMark, ProgressiveReveal, GlossaryTerm) with FK grade <=9 |
| Design Output | DO-LEO-AI-118 | draft | services/ui/src/components/ui/{PageIntro,HelpPopover,CoachMark,ProgressiveReveal,GlossaryTerm}.tsx + src/lib/{glossary,readability}.ts |
| Risk | R-LEO-AI-081 | analyzed | Patients / juniors misunderstand clinical terms without in-product explanation |
| Verification Test | VT-LEO-AI-116 | passed | 6 Jest cases: PageIntro collapse, HelpPopover dialog, ProgressiveReveal expand, GlossaryTerm known+unknown, glossary FK grade gate |
| Design Input | DI-LEO-AI-125 | draft | NCDA interval KPIs computed and persisted as named properties on every EpisodeOfCare with prerequisite milestones |
| Design Output | DO-LEO-AI-122 | draft | kpi_calculator.calculate_kpis wired into build_episodes; _DIAGNOSIS_MILESTONES / _TREATMENT_MILESTONES accept canonical + legacy keys; MATCH-only persistence |
| Risk | R-LEO-AI-085 | analyzed | Inconsistent interval KPIs across dashboards when computed ad-hoc per router |
| Verification Test | VT-LEO-AI-120 | passed | Covers complete milestone set, missing milestones, idempotency, build_episodes integration, null-safety |
| Design Input | DI-LEO-AI-126 | draft | Staging enrichment uses diagnosis + 90 day window and filters evidence rows by cancer-type specialty markers |
| Design Output | DO-LEO-AI-123 | draft | libs/clinical_scoping specialty markers; staging_enrichment._choose_window and filter_rows_by_specialty integration |
| Risk | R-LEO-AI-086 | analyzed | Staging cross-contamination between concurrent cancer pathways for the same patient |
| Verification Test | VT-LEO-AI-121 | passed | Marker coverage, window calculation, filtering, fallback when no rows match marker |
| Design Input | DI-LEO-AI-124 | draft | Milestone temporal integrity: MIN_REFERRAL_TO_DIAG_DAYS gap + PRISM authoritative primacy over generic text referrals |
| Design Input | DI-LEO-AI-127 | draft | Safety-net alert persistence with Patient edge + canonical alert_id in analytics router |
| Design Output | DO-LEO-AI-124 | draft | services/analysis_worker/app/analyzers/safety_net_persistence.py; subgraph wiring; dashboards.py alert_id cleanup |
| Design Output | DO-LEO-AI-125 | approved | libs/metrics consolidation; kpi_calculator and ncda export delegate to shared interval KPI math |
| Verification Test | VT-LEO-AI-124 | passed | 17 pytest cases: cardinality/join integrity, schema validity, distribution tripwires, interval KPI parity between clean_episode_ground_truth.json and ncda_export.json via libs.metrics |
| Risk | R-LEO-AI-087 | analyzed | Safety-net alerts lost (never persisted) or silently unactionable (router matches wrong key) |
| Verification Test | VT-LEO-AI-122 | passed | 11 pytest cases: persistence, Patient edge, FOR_EPISODE link, idempotency, alert_id in router SELECT/MATCH/SET, subgraph wiring |
| Design Output | DO-LEO-AI-121 | draft | _config.MIN_REFERRAL_TO_DIAG_DAYS; _grouping._find_best_referral gap guard; anchor_detector._RE_REFERRAL_PRISM + referral_subtype dedupe |
| Risk | R-LEO-AI-084 | analyzed | False same-day referral-to-diagnosis interval misleads quality improvement decisions |
| Verification Test | VT-LEO-AI-119 | passed | 11 pytest cases: same-day skip, earlier-referral preference, env override, PRISM regex positive/negative, PRISM primacy, generic fallback, parametrised gap checks |
| Design Input | DI-LEO-AI-122 | draft | OperationsWorkspace inclusive redesign - PageIntro, shared StatusDot shape encoding, aria-expanded/controls on SectionRow |
| Design Output | DO-LEO-AI-119 | draft | OperationsWorkspace.tsx renders PageIntro screenId='admin-operations'; local StatusDot.tsx removed; SectionRow trigger carries aria-expanded and aria-controls to named region |
| Risk | R-LEO-AI-082 | analyzed | Operations workspace misread by junior staff or older clinicians due to jargon and colour-only status cues |
| Verification Test | VT-LEO-AI-117 | passed | 7 Jest cases: PageIntro renders with h2 + collapses via localStorage, why/how/what FK grade <=9, SectionRow aria-expanded/aria-controls toggle, local StatusDot.tsx removed |
| Design Input | DI-LEO-AI-123 | draft | CodingReviewCasesModal split into eight modules (main, title, CaseCard, CaseCardLeoResult, CaseCardSuppressForm, EncounterContextPanel, utils, copy) each <=500 LOC with PageIntro + GlossaryTerm + HelpPopover |
| Design Output | DO-LEO-AI-120 | draft | CodingReviewCasesModal.tsx (389) + CodingReviewCasesModalTitle.tsx (213) + CaseCard.tsx (461) + CaseCardLeoResult.tsx (174) + CaseCardSuppressForm.tsx (175) + EncounterContextPanel.tsx (133) + codingReviewUtils.ts (135) + codingReviewCopy.ts (44); glossary expanded with semantic-tag, suppress, declined, absent, planned, hypothetical |
| Risk | R-LEO-AI-083 | analyzed | Junior operator makes wrong coding-review decision due to unexplained clinical terms |
| Verification Test | VT-LEO-AI-118 | passed | 19 Jest cases: all eight split modules <=500 LOC, CODING_REVIEW_INTRO FK grade <=9, seven glossary terms resolve at grade <=9, CodingReviewCasesModal empty-state Props preserved |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-101 | Double-negation guard for pre-negated SNOMED situations | R-LEO-AI-069 | VT-LEO-AI-101 |
| DI-LEO-AI-102 | Analytics assertion filter for CCI and cohort queries | R-LEO-AI-070 | VT-LEO-AI-102 |
| DI-LEO-AI-103 | Assertion determined solely by post-processing pipeline | R-LEO-AI-003 | VT-LEO-AI-103 |
| DI-LEO-AI-104 | Polarity-encoded finding guard corrects assertion inversion after SNOMED resolution | R-LEO-AI-071 | VT-LEO-AI-104 |
| DI-LEO-AI-104 | Benign/normal qualifier-based episode closure with site compatibility | R-LEO-AI-071 | VT-LEO-AI-104 |
| DI-LEO-AI-105 | Intelligence Console UX - unified navigation and URL migration | - | VT-LEO-AI-105 |
| DI-LEO-AI-106 | Training quality capabilities (span realign, assertion filter, golden set) | R-LEO-AI-072 | VT-LEO-AI-106 |
| DI-LEO-AI-107 | Multi-label NER - spancat component, layer 5 nesting refinement, prompt preservation (VT passed 2026-04-13) | R-LEO-AI-073 | VT-LEO-AI-107 |
| DI-LEO-AI-108 | Ontology-grounded relation modeling and reviewer workflow | R-LEO-AI-074 | VT-LEO-AI-108 |
| DI-LEO-AI-109 | Pathway Explorer API and GDS services | R-LEO-AI-075 | VT-LEO-AI-109 |
| DI-LEO-AI-110 | Pathway Explorer UI/UX components | R-LEO-AI-076 | VT-LEO-AI-110 |
| DI-LEO-AI-111 | Observable value-unit linking: string results and pre-entity raw-text fallback (VT passed 2026-04-15) | R-LEO-AI-077 | VT-LEO-AI-111 |
| DI-LEO-AI-118 | Inclusive design token system (WCAG AA contrast pairs, 16px base, focus ring, reduced motion) | R-LEO-AI-078 | VT-LEO-AI-113 |
| DI-LEO-AI-119 | Density modes with patient-reachable 44px minimum touch target | R-LEO-AI-079 | VT-LEO-AI-114 |
| DI-LEO-AI-120 | Global a11y baseline (AppShell, ConfirmDialog, StatusDot, TermSearch, axe-core CI) | R-LEO-AI-080 | VT-LEO-AI-115 |
| DI-LEO-AI-121 | Explanation pattern framework (PageIntro, HelpPopover, CoachMark, ProgressiveReveal, GlossaryTerm) and FK grade gate | R-LEO-AI-081 | VT-LEO-AI-116 |
| DI-LEO-AI-125 | NCDA interval KPIs persisted on EpisodeOfCare (VT passed 2026-04-16) | R-LEO-AI-085 | VT-LEO-AI-120 |
| DI-LEO-AI-126 | Specialty-scoped staging with post-diagnosis 90-day window (VT passed 2026-04-16) | R-LEO-AI-086 | VT-LEO-AI-121 |
| DI-LEO-AI-124 | Referral-to-diagnosis temporal integrity + PRISM primacy (VT passed 2026-04-16) | R-LEO-AI-084 | VT-LEO-AI-119 |
| DI-LEO-AI-127 | Safety-net alert persistence + canonical alert_id (VT passed 2026-04-16) | R-LEO-AI-087 | VT-LEO-AI-122 |
| DI-LEO-AI-122 | OperationsWorkspace inclusive redesign (PageIntro, shared StatusDot, aria-expanded) - VT passed 2026-04-16 | R-LEO-AI-082 | VT-LEO-AI-117 |
| DI-LEO-AI-123 | CodingReviewCasesModal split (8 modules <=500 LOC) + PageIntro/GlossaryTerm/HelpPopover - VT passed 2026-04-16 | R-LEO-AI-083 | VT-LEO-AI-118 |
| DI-LEO-AI-134 | Canonical NCDA 'Confirmed Cancer' cohort across analytics (libs/analytics/cohorts.py, DO-LEO-AI-131) - VT passed 2026-04-17. Refined 2026-04-17: dropped status='completed' precondition (in_progress episodes with diagnosis_confirmed milestones now counted) and added explicit closed_benign exclusion (legacy 8 episodes carrying spurious diagnosis_confirmed milestones from historic-cancer text mentions remain excluded); regression covered by VT-LEO-AI-163. Headline tile moved 47->50 in 2024-2026 window. | R-LEO-AI-092 | VT-LEO-AI-130, VT-LEO-AI-163 |
| DI-LEO-AI-129 | Role-first Practitioner.selected_role + allowed_roles + RoleSwitch audit (DO-LEO-AI-126) - VT passed 2026-04-17 | R-LEO-AI-089, R-LEO-AI-091 | VT-LEO-AI-125 |
| DI-LEO-AI-130 | @leo/design-system npm workspace package with tokens (DO-LEO-AI-127) - VT passed 2026-04-17 | R-LEO-AI-089 | VT-LEO-AI-126 |
| DI-LEO-AI-131 | MotionProvider + prefers-reduced-motion gate (DO-LEO-AI-128) - VT passed 2026-04-17 | R-LEO-AI-090 | VT-LEO-AI-127 |
| DI-LEO-AI-132 | next/font DM Sans + JetBrains Mono; un-monospace subtitles (DO-LEO-AI-129) - VT passed 2026-04-17 | R-LEO-AI-089 | VT-LEO-AI-128 |
| DI-LEO-AI-133 | RoleGate + RolePicker + RoleSwitcher primitives with NEXT_PUBLIC_ROLE_FIRST flag (DO-LEO-AI-130) - VT passed 2026-04-17 | R-LEO-AI-089, R-LEO-AI-091 | VT-LEO-AI-129 |
| DI-LEO-AI-135 | Merge /admin/clinical into /admin/knowledge, 301 redirects, nav consolidation (DO-LEO-AI-132) - VT passed 2026-04-17 | R-LEO-AI-093 | VT-LEO-AI-131 |
| DI-LEO-AI-136 | Episode builder two-pass referral matching with fallback-any-site claim + honest NULL referral_date for truly floating episodes (DO-LEO-AI-133) - verified | R-LEO-AI-096 | VT-LEO-AI-137 (passed 2026-04-16) |
| DI-LEO-AI-137 | Evidence-wins duplicate-episode merger with IS_PART_OF edge migration via MOVE_LINKS_Q, including NSS clusters (DO-LEO-AI-133) - verified | R-LEO-AI-096, R-LEO-AI-097 | VT-LEO-AI-138 (passed 2026-04-16) |
| DI-LEO-AI-138 | Broadened SPECIALTY_MARKERS['breast'] regex (endocrine therapy, invasive ductal/lobular, BRCA, axilla, sentinel node, fast-track phrasing) plus childrens_tumour regex tightening to capture "Fast track referral for suspected <site>" canonical SNOMED phrasing end-to-end (DO-LEO-AI-134) - verified | R-LEO-AI-096 | VT-LEO-AI-139 (passed 2026-04-16) |
| DI-LEO-AI-139 | Role-first intro copy across all nine landing pages (Care Overview, Operations, Pathway Explorer, Platform, Users, Portal, Support, Settings, Work); centralised AREA_INTRO_COPY map with default FK <=9 + role coverage; AreaIntro wrapper; NEXT_PUBLIC_ROLE_FIRST shipped enabled by default (DO-LEO-AI-136) - VT passed 2026-04-17 | R-LEO-AI-094 | VT-LEO-AI-135 |
| DI-LEO-AI-140 | Phase 6 zero-tech-debt cleanup: NEXT_PUBLIC_ROLE_FIRST rollout flag deleted from next.config.mjs / RoleShellProvider / AppShell; duplicate services/ui/src/components/ui/ProgressiveReveal.tsx deleted and callers migrated to @leo/design-system; Google Fonts @import removed from globals.css (next/font handles fonts); eslint.config.mjs carries no-restricted-syntax rule flagging sx colour literals (DO-LEO-AI-137) - VT passed 2026-04-17 | (none) | VT-LEO-AI-136 |
| DI-LEO-AI-141 | MUI theme factory relocated into @leo/design-system as createLeoTheme; services/ui/src/components/ThemeRegistry.tsx imports from @leo/design-system/theme; services/ui/src/theme.ts deleted; palette + typography + shape sourced from tokens so a single token change propagates to every MUI surface (DO-LEO-AI-138) - VT passed 2026-04-17 | (none) | VT-LEO-AI-140 |
| DI-LEO-AI-142 | Wave E Phase 1 Knowledge primitives (MetricTile, ProgressStrip, SegmentedTabs, FilterBar, ToolbarActions, ReviewListCard, DataGridCard) + StatHero framer-motion stagger upgrade, all in @leo/design-system with no @mui imports, keyboard/ARIA correct, motion tokens applied (DO-LEO-AI-139) - VT passed 2026-04-17 | (none) | VT-LEO-AI-141 |
| DI-LEO-AI-143 | Wave E Phase 2a Training Data tab chrome rewrite: GoldDatasetPanel.tsx header/stats/progress/segmented-tabs/toolbar replaced with StatHero, ProgressStrip, SegmentedTabs, ToolbarActions from @leo/design-system; legacy MUI Tabs removed from chrome; handlers and state preserved (DO-LEO-AI-140) - VT passed 2026-04-17 | R-LEO-AI-098 | VT-LEO-AI-142 |
| DI-LEO-AI-145 | first_seen milestone: _RE_FIRST_SEEN regex detects fast-track/2WW clinic attendance text; AnchorResult gains first_seen_anchors; _build_closed_episode writes IS_PART_OF {milestone_type: 'first_seen'} edges and first_seen_date on EpisodeOfCare; MIN_REFERRAL_TO_DIAG_DAYS lowered to 0 for same-day PRISM workflows (DO-LEO-AI-141) - VT passed 2026-04-17 | R-LEO-AI-096 | VT-LEO-AI-143 |
| DI-LEO-AI-146 | Wave E Phase 2a-iv GoldLabelDetailDialog chrome redesign: legacy DialogTitle / dual-green-button DialogActions / saturated suggestions box / inline delete confirm replaced with DialogTitleStrip + DialogActionsBar + SuggestionsPanel + DeleteConfirmPanel under services/ui/src/components/gold-dataset/GoldLabelDetailDialog/; single primary action with morphing label, status pill, kebab-disclosed delete; all legacy handlers preserved (DO-LEO-AI-142) - VT passed 2026-04-17 | R-LEO-AI-099 | VT-LEO-AI-144 |
| DI-LEO-AI-147 | Wave E Phase 3 CRUD Knowledge tabs (Context Rules + Surface Forms + Domains + Terminology) on @leo/design-system: StatHero + ToolbarActions + SegmentedTabs/FilterBar chrome on every page; per-page body primitive (ReviewListCard + ProgressiveReveal for Context Rules, restyled concept-group cards for Surface Forms, framer-motion DomainCard grid for Domains, tone-accented PackageCard list + streaming LogPanel for Terminology); legacy Breadcrumbs / h5 page titles / "Domain Configuration" heading removed; every legacy data + write + streaming handler preserved (DO-LEO-AI-143) - VT passed 2026-04-17 | R-LEO-AI-100 | VT-LEO-AI-145 |
| DI-LEO-AI-148 | Wave E Phase 4 AI Instructions list page on @leo/design-system: StatHero (4 tiles) + FilterBar + SegmentedTabs + ToolbarActions ("New instructions" single primary) + ReviewListCard body (one row per prompt with category + version + double-check + examples chips); grouped browse mode preserved; legacy h4 page title + bespoke PromptCard grid + raw chip filter + raw TextField removed; /api/prompts fetch + router.push routes to /admin/prompts/:id and /admin/prompts/new + sortByIsoDateDesc all preserved; detail-page editor rebuild deferred (DO-LEO-AI-144) - VT passed 2026-04-17 | R-LEO-AI-101 | VT-LEO-AI-146 |
| DI-LEO-AI-149 | Histology vocabulary expansion in anchor_detector.py: _RE_CONFIRMED_CANCER and _RE_CANCER_TERM extended with histology-letter terms (invasive ductal/lobular, adenocarcinoma, DCIS/LCIS, BCC/SCC, Gleason, Dukes, FIGO with letter suffix, Breslow, Clark level, T/N/M staging, grade 1-3 / poorly|moderately|well differentiated, in-situ, metastatic). _RE_NO_CANCER extended with benign-histology vocabulary (lipoma, fibroadenoma, sebaceous/epidermal cyst, seborrhoeic/actinic keratosis, skin tag, dermatofibroma, no malignant cells, no atypia, unremarkable biopsy, hyperplastic/inflammatory polyp, fibrocystic change, hamartoma, discharge back to GP, reassurance given). Closes 24/79 missed-diagnosis and 19/79 missed-benign-closure auto-close failures (DO-LEO-AI-145) - VT passed 2026-04-17 | R-LEO-AI-102 | VT-LEO-AI-147 |
| DI-LEO-AI-150 | Diagnosis-aware open-episode rescue + first_seen_date persistence in episode_builder/_builder.py: _rescue_diagnosis_for_open_episode() finds confirmed, site-compatible diagnosis anchors in [ref_date, ref_date+STALE_HARD_DAYS] window; if status would still be 'in_progress', promote to 'completed' with end_date=earliest diag date and HITL flag for review. unknown / non_site_specific diagnoses match any site. _first_seen_link_anchors() now invoked BEFORE _write_episode so first_seen_date is persisted on the EpisodeOfCare node (defect fix for DI-LEO-AI-145). Post-rebuild metrics 2026-04-17: auto_closed 79->44 (-44%), completed 52->109 (+110%), with_first_seen 31->130 (+319%) (DO-LEO-AI-146) - VT passed 2026-04-17 | R-LEO-AI-103 | VT-LEO-AI-148 |
| DI-LEO-AI-151 | Wave E polish: Knowledge tab width parity (TAB_WIDTH map promotes ai-instructions and clinical-guidelines from 'reading' to 'wide' so all eight Knowledge tabs render at 1600px) + DomainCard / PackageCard visual consistency (canonical 12px radius / 18px padding / 3px tone-coded accent strip / 168px minHeight / canonical knowledge tone palette) + Domains responsive grid capped at 3 columns (DO-LEO-AI-147) - VT passed 2026-04-16 | (none) | VT-LEO-AI-149 |
| DI-LEO-AI-152 | Wave E Phase 5 Clinical Guidelines orchestrator on @leo/design-system: sticky SegmentedTabs jump strip (Load / Review / Compile) + four motion-enabled StepCards (12px radius, 3px tone-coded accent strip, framer-motion stagger entry) wrapping the unchanged child sections (NiceLoaderSection, LoadedGuidelinesPanel, RuleReviewSection, BitmapLifecycleSection); legacy 4px-accent SectionBox / Card chrome removed; loadedRefreshKey + ruleRefreshKey state bridges preserved verbatim (DO-LEO-AI-148) - VT passed 2026-04-16 | R-LEO-AI-104 | VT-LEO-AI-150 |
| DI-LEO-AI-153 | Wave E Phase 6 Pathways admin list on @leo/design-system: 815 LOC monolith split into page.tsx orchestrator + PathwayCard.tsx + dialogs.tsx + templates.ts + types.ts; StatHero (4 tiles) + SegmentedTabs status filter (All / Live / Drafts / Retired with counts) + ToolbarActions ("New pathway" single primary); PathwayCard rebuilt on the canonical 12px / 18px / 3px-accent / motion-stagger pattern; all FHIR + routing handlers (api.get/post/put/delete on /fhir/PlanDefinition, router.push to /admin/pathways/:id) preserved; type-the-name delete confirm gate + explicit publish dialog preserved; all four starter templates (blank, extraction-only, extraction-verify-persist, training-audit) preserved; detail-page canvas editor explicitly deferred (DO-LEO-AI-149) - VT passed 2026-04-16 | R-LEO-AI-105 | VT-LEO-AI-151 |
| DI-LEO-AI-154 | Manual review-time editing of AI-generated guidance rules: centred Dialog (~1100px) replacing the read-only side drawer, two-column layout (recursive editable logic tree + debounced SNOMED ConceptSearchPanel reusing /api/terminology/search), reviewer can replace/add/remove SNOMED concepts, switch group kinds (AND/OR/NOT/AT_LEAST), edit AT_LEAST minimums and demographic checks; edits persist as a NEW versioned :AppropriatenessRule that supersedes the predecessor (status='superseded') with an immutable :GuidanceAuditEvent; server-side validate_logic_tree enforces depth <= 6, node count <= 80, NOT arity 1, AT_LEAST min in [1, children], and existence of every SNOMED concept; duplicated NICE recommendation block + redundant plain-English summary removed (DO-LEO-AI-150) - VT passed 2026-04-17 | R-LEO-AI-106 | VT-LEO-AI-152 |
| DI-LEO-AI-155 | Text-based cancer-site classification using a gold-mined surface-form dictionary (services/analysis_worker/app/analyzers/cancer_site_terms.py): 955 unique lower-case literals across 29 NCDA-aligned site keys, mined from 1,620 GoldLabel entities and 4,956 SurfaceForm-MAPS_TO-Concept edges in the knowledge graph by scripts/_mine_cancer_site_terms.py; surface-form anatomy-stem filter rejects noise such as "cramps" / "amy was not elevated" / "abnormal lfts"; anchor_detector.py _classify_text_encounters tags each text anchor with site_key + site_hits via match_cancer_site(text); episode_builder/_site_resolution.py _extract_condition_key_from_anchor prefers explicit site_key over the generic "Text: ..." sentinel concept_name. Post-rebuild metrics 2026-04-17: cancer_type 0/230 (0%) -> 148/183 (80%) on active episodes (excluding merged duplicates) (DO-LEO-AI-151) - VT passed 2026-04-17 | R-LEO-AI-107 | VT-LEO-AI-153 |
| DI-LEO-AI-156 | Wave E Phase 6b-ii pathway editor chrome decomposition (UN-LEO-AI-072): the 5,960 LOC services/ui/src/app/admin/pathways/[id]/page.tsx orchestrator extracted into stateless prop-driven sibling modules under services/ui/src/app/admin/pathways/[id]/editor/ -- PathwayToolbar.tsx (top toolbar: back/name/status/save/publish/retire/add-node/auto-layout/test/history/delete), PathwaySaveBar.tsx (sticky bottom save state idle|dirty|saving|saved|error), dialogs/EdgeDeleteConfirm.tsx, dialogs/PublishDialog.tsx (pipeline preview + version notes), dialogs/DeletePathwayDialog.tsx (type-the-name confirm gate) and editor/utils.ts (formatSaveTime + lifecycleLabel + lifecycleColor); legacy inline JSX + unused MUI imports removed; every existing save/publish/delete/add-node handler preserved verbatim; orchestrator state remains the single source of truth (DO-LEO-AI-152) - VT passed 2026-04-16 | R-LEO-AI-108 | VT-LEO-AI-154 |
| DI-LEO-AI-157 | Wave E Phase 6b-iii pathway canvas node primitives (UN-LEO-AI-072): all 10 pathway node types (action, condition, rest_connector, queue_publish, trigger, parallel, merge, transform, source, output, viewer) refactored onto a shared BaseNode + NodeHandle + NodeStatusStrip + NodeHeader contract under services/ui/src/components/pathway/nodes/_base/; canonical 12px borderRadius / 2px border / single-click + Enter/Space activation applied centrally; every Handle gains a generated aria-label of the form 'input port <id>' / 'output port <id>'; double-click configure migrated to single-click on SourceNode / OutputNode / MiniHitlNode; resolveRunStatus() centralises raw step result -> NodeRunStatus mapping for ActionNode (DO-LEO-AI-153) - VT passed 2026-04-16 | R-LEO-AI-109 | VT-LEO-AI-155 |
| DI-LEO-AI-159 | Wave E Phase 6b-iv pathway editor configurator wiring (UN-LEO-AI-072): services/ui/src/app/admin/pathways/[id]/page.tsx wires the existing ConditionRuleBuilder under the wizard's Settings step for nodeType==="condition" nodes; new editor/hooks/useDirtyGuard.ts hook computes a stable signature over plan.name/description/status/trigger/nodes/edges/configs, marks the editor dirty whenever the signature drifts from the saved baseline, installs a beforeunload listener while dirty, and exposes markSaved() called after every successful handleSave; PathwaySaveBar state is now derived from {isSaving, saveError, dirty, lastSaved}; the silent .catch(() => {}) on the FHIR PlanDefinition loader is replaced with a visible PathwayLoadError surface that offers retry + dismiss (DO-LEO-AI-155) - VT passed 2026-04-16 | R-LEO-AI-110 | VT-LEO-AI-157 |
| DI-LEO-AI-160 | Wave E Phase 6b-v pathway probe parity + popover safety (UN-LEO-AI-072): services/ui/src/components/pathway/config/subgraphs.ts adds SUBGRAPH_OPTIONS_RAW + SUBGRAPH_IO + SUBGRAPH_CATEGORY entries for the four backend subgraphs (encounter_loader, staging_enrichment, human_review_gate, encounter_coding_agent) that previously had no UI canvas presence; services/ui/src/components/pathway/edges/probeStrategies.tsx registers a ProbeStrategy implementation (icon + headline + Detail) for each, and CONFIG_INJECTED_FIELDS records that encounter_coding_agent ingests {mode, tier, apply, max_input_tokens} as configuration rather than upstream port data; services/ui/src/components/pathway/edges/PortEdge.tsx ProbeMonitor installs a window-level keydown listener that closes the inspector drawer first then calls onClose, and the popover root carries role="dialog" with an aria-label naming source/target/Escape (DO-LEO-AI-156) - VT passed 2026-04-16 | R-LEO-AI-162 | VT-LEO-AI-158 |
| DI-LEO-AI-163 | Hand-authored cancer-positive / benign-control gold seed for the spancat NER model (UN-LEO-AI-074): design-controls/training-data/manual-gold-seed-2026-04-17.yaml carries 21 verified records (4 cancer-positive, 17 benign / excluded / normal control) drawn from real GP encounters, every sentence already de-identified and re-validated against libs.utils.deidentify.deidentify_text + libs.ner.deid_validator.DeIdValidator; scripts/seed_manual_gold_records.py loads the manifest, re-derives entity start/end offsets via libs.ner.span_finder.find_span, computes deterministic candidate_id (sha256 of text) and label_id (GL- + first 16 hex of sha256(text + sorted entity texts)), enforces lowercase SNOMED semantic-tag labels and the canonical assertion vocabulary, and idempotently UPSERTs one TrainingCandidate (status=completed) + one linked GoldLabel per record into the Knowledge Graph with the (:TrainingCandidate)-[:PRODUCED]->(:GoldLabel) edge (DO-LEO-AI-159) - VT passed 2026-04-17 | R-LEO-AI-003 | VT-LEO-AI-160 |
| DI-LEO-AI-161 | Stale-detector five fixes (UN-LEO-AI-006): the 41-episode 2026-04-17 deep-read of stale 2024+2025 patients identified five recurring root-causes that the episode builder needed to address. (1) libs/domains/code_inventories.py centralises curated MALIGNANCY_READ_CODES (e.g. X78WM breast, BB5j2 / X78XO endometrial), BENIGN_EXPLANATION_READ_CODES (XaK99 LPR, F5801 presbyacusis), FAST_TRACK_REFERRAL_READ_CODES (XaMeC breast, XaMeB gynaecological), BENIGN_INVESTIGATION_PHRASES ("mammogram normal", "cancer excluded - discharge to GP"), and LETTER_STUB_PATTERNS plus typed lookup helpers; (2) services/analysis_worker/app/analyzers/anchor_detector.py _classify_text_encounters consumes those helpers to emit diagnosis_confirmed / benign_closure anchors with explicit diagnosis_source / benign_source provenance and tags site_key + site_source="explicit_2ww_code" on referral anchors when an explicit 2WW code is present; (3) services/analysis_worker/app/analyzers/episode_builder/_site_resolution.py _extract_condition_key_from_anchor prefers explicit_2ww_code / explicit_malignancy_code over generic surface-form / SNOMED resolution; (4) services/analysis_worker/app/analyzers/episode_builder/_cypher.py STALE_CLOSE_Q gains an EXISTS guard so episodes with diagnosis / diagnosis_confirmed / benign_closure / treatment_started milestones are never auto-stamped stale; (5) libs/pipeline/outcome_inference.py extends POST_CANCER + POST_BENIGN with the new code/phrase signals (with overlap filtering to preserve the inference engine's HITL_REQUIRED tie-break behaviour). Live-corpus wipe-and-rebuild via scripts/_wipe_episodes_and_rebuild.py 2026-04-17: total EpisodeOfCare 518 -> 360 (phantoms + duplicates resolved), stale_post_specialist + stale_no_diagnosis distinct patients 36 -> 6 (well below the <=12 acceptance threshold), closed_benign patients 41 -> 81 (>=25 increase met) (DO-LEO-AI-161) - VT passed 2026-04-17 | R-LEO-AI-163 | VT-LEO-AI-161 |
| DI-LEO-AI-162 | DQ alert dq_letter_stub_unfilled in services/neo4j_mcp/tools/query_pack_safety.py (UN-LEO-AI-054): surfaces incoming Encounter records whose body matches LETTER_STUB_PATTERNS (e.g. "Urology to Greenfields Surgery"), is shorter than max_chars (default 200), is older than days_threshold (default 7), and whose patient has at least one EpisodeOfCare in stale_post_specialist or stale_no_diagnosis; result envelope uses the standard MCP _result helper (category="safety", summary "Found N letter stubs (>X days old) on stale episodes."); Cypher is read-only with no MERGE / SET / DELETE / CREATE; tool is auto-registered through the existing TOOLS dynamic-load path in services/neo4j_mcp/server.py (DO-LEO-AI-162) - VT passed 2026-04-17 | R-LEO-AI-164 | VT-LEO-AI-161 |
| DI-LEO-AI-165 | Persistent test patient library: schema + content_hash dedup (UN-LEO-AI-076): libs/cypher/test_patient_queries.py defines :TestPatient and :RulesetReplay constraints + indexes and the CREATE_TEST_PATIENT / WRITE_EXPECTED_RESULT / LIST_TEST_PATIENTS / FIND_BY_CONTENT_HASH / WRITE_REPLAY_REPORT / LIST_REPLAY_REPORTS / GET_REPLAY_REPORT Cypher; services/api/app/services/test_patient_service.py builds the PatientPayload dataclass (blake2b 16-byte hash over normalised codes + age + lowercase sex + pathway_id), confirm_and_save() with idempotent skip_if_exists, dry_run() that walks each matched rule's logic tree to produce branch_paths, and the /api/guidance/test-patients FastAPI router gated by require_admin (DO-LEO-AI-164) - VT passed 2026-04-17 | R-LEO-AI-166 | VT-LEO-AI-164 |
| DI-LEO-AI-166 | Test patient generator + dry-run preview (UN-LEO-AI-076): services/api/app/services/test_patient_generator.py emits Proposal records (kind happy / fail / branch / boundary) per rule, walking AND / OR / AT_LEAST / NOT subtrees with _collect_satisfying() and DEMOGRAPHIC nodes with _collect_demographic(); boundary_plus_pairs depth emits at-boundary and just-below-boundary patients per age node and one happy patient per top-level OR branch; _dedup() drops proposals whose content_hash already exists in the same guideline; BuildPatientDialog.tsx reuses ConceptSearchPanel and gates Save behind a successful dry-run, GeneratePatientsDialog.tsx bulk-saves selected proposals with skip_if_exists=True (DO-LEO-AI-165) - VT passed 2026-04-17 | R-LEO-AI-166 | VT-LEO-AI-165 |
| DI-LEO-AI-167 | Replay engine, post-compile gate and Clinical Guidelines surfacing (UN-LEO-AI-076): test_patient_service.diff_replay() buckets each asserted rule into passes / regressions / unexpected_matches and replay_scope() persists the aggregate as a :RulesetReplay node tagged with ruleset_version; services/terminology_api/app/routers/guidelines.py _trigger_test_patient_replay() POSTs to /guidance/test-patients/replay after every successful guideline compile carrying the SERVICE_AUTH_SECRET Bearer header from libs/auth/service_auth.get_service_auth_header (errors logged at WARNING, do not block the compile); services/api/app/deps.py require_admin_or_service accepts EITHER an admin session cookie OR the SERVICE_AUTH_SECRET token so the inter-service hook authenticates without leaning on LEO_LOCAL_DEV_BYPASS, and is applied to /guidance/test-patients/replay; BitmapLifecycleSection.tsx surfaces the latest report with a coloured banner and a link to the test-patient library; EditRuleDialog/TestPatientsPanel.tsx re-runs a rule-scoped replay on every change of the rule's logic-tree signature and shows a regression banner naming the affected rules in plain English (DO-LEO-AI-166) - VT passed 2026-04-19 | R-LEO-AI-166 | VT-LEO-AI-166 |
| DI-LEO-AI-168 | Wave E Phase 6b-vi pathway probe surface decomposition (UN-LEO-AI-072): the legacy services/ui/src/components/pathway/edges/PortEdge.tsx (1781 LOC) split into a thin barrel + PortEdge/{utils,diff,TreeNode,SemanticSection,ProbeInspectorDrawer,ProbeMonitor,ProbeMonitorBanners,ProbeMonitorChanges,ProbeMonitorData,ProbeMonitorValidate,index}.tsx with each module <=500 LOC; services/ui/src/components/pathway/edges/probeStrategies.tsx (1048 LOC) split into a 158-LOC barrel + probes/{_shared,extraction,verification,persist,connectors,guidance}.tsx; dead services/ui/src/components/pathway/panel/{InputsTab,OverviewTab,ReviewTab,TriggerContextPanel}.tsx removed; services/ui/eslint.config.mjs gains a no-restricted-imports rule scoped to pathway/** that warns on direct @mui/* imports; services/ui/e2e/pathway-editor.spec.ts adds a Playwright + axe baseline for /admin/pathways (DO-LEO-AI-167) - VT passed 2026-04-16 | R-LEO-AI-167 | VT-LEO-AI-167 |
| DI-LEO-AI-170 | Editable SNOMED procedure (action) on a pending guidance rule (UN-LEO-AI-028): closes a gap left by DI-LEO-AI-154 by surfacing the recommended SNOMED procedure (the action that fires when the rule matches a patient) in the EditRuleDialog and letting reviewers swap it. Backend - services/api/app/routers/guidance_rules.py _format_rule now exposes a parsed `action` field (snomed_concept_id, preferred_term, semantic_tag, term) on every rule response via the new _parse_action_json helper; services/api/app/services/guidance_rule_edit.py RuleUpdates accepts an optional `action: LogicCriterion`, apply_rule_edit verifies the action concept exists in the SnomedConcept graph alongside the logic-tree concepts, the new _action_payload helper composes the persisted actionJson, and _INSERT_EDITED_RULE Cypher uses coalesce($action_json, pred.actionJson) so omitting the action preserves the predecessor's value (no silent null-out path). Frontend - new services/ui/src/app/admin/guidance/EditRuleDialog/ActionPanel.tsx renders the procedure as a chip (success.50 background when coded, warning.50 empty state) with a tooltip carrying the SNOMED code; index.tsx adds an `action` + `actionDirty` state pair, a new `replace_action` SearchTarget mode that routes through the existing ConceptSearchPanel (heading "Swap the recommended procedure"), and only sends `action` in the save payload when the reviewer touched it; RuleReviewSection.tsx forwards the optional action through the /api/guidance/rules/review/{id}/decision request. (DO-LEO-AI-169) - VT passed 2026-04-17 | R-LEO-AI-169 | VT-LEO-AI-168 |
| DI-LEO-AI-174 | Wave E Phase 4b AI Instructions editor decomposition (UN-LEO-AI-061): the legacy services/ui/src/app/admin/prompts/[id]/page.tsx (1110 LOC) split into a 406-LOC orchestrator that owns data fetching + save + sandbox state, plus dedicated tab body and helper modules under _components/ - IdentitySection, InstructionsTab, OutputFormatTab, TeachingExamplesTab, SandboxTab, SandboxCostTable, ExampleCard (with internal ExampleEditMode + ExamplePreviewMode), InputDisplay, OutputPreview, and a single types.ts holding CATEGORY_OPTIONS, SCOPE_OPTIONS, TAG_COLORS, ASSERTION_COLORS, categoryLabel, categoryColor, FewShotExample, PromptConfigData, CostEstimate, SandboxResult, PresetItem, SandboxProvider, SandboxTier, DEFAULT_MAX_FEW_SHOT. Every module stays inside the 500 LOC hard cap, the orchestrator imports each tab body from ./_components/, and the save payload contract (name, description, systemPrompt, outputSchema, verification, fewShotExamples, maxFewShot) is preserved byte-for-byte (DO-LEO-AI-173) - VT passed 2026-04-16 | - | VT-LEO-AI-169 |
| DI-LEO-AI-176 | Wave E Phase 7 Knowledge tabs guards (UN-LEO-AI-061): services/ui/eslint.config.mjs gains a no-restricted-imports rule scoped to src/app/admin/knowledge/**/*.{ts,tsx} that warns on @mui/* imports, nudging contributors toward @leo/design-system primitives (KnowledgePageLayout, StatHero, ToolbarActions, FilterBar, PromptEditorCard, ReviewListCard, DataGridCard, MetricTile, NudgeStrip); services/ui/e2e/knowledge-tabs.spec.ts adds a Playwright + @axe-core/playwright spec that iterates the eight Knowledge tab keys (training-data, surface-forms, context-rules, ai-instructions, clinical-guidelines, pathways, domains, terminology) and asserts each route loads with zero critical or serious WCAG 2.0/2.1 AA violations on the wrapper chrome (DO-LEO-AI-175) - VT passed 2026-04-16 | - | VT-LEO-AI-171 |
| DI-LEO-AI-171 | Problem-list malignancy term + active-care + history-of-cancer recognition + Read appendix sweep (UN-LEO-AI-005, UN-LEO-AI-006): the 2025 closed_benign audit identified 6 missed cancers where libs/domains/code_inventories.py lacked corpus-confirmed Read codes (X78Y6 prostate, Ya0ln breast and others) and where free-text malignancy phrases on Major:/Problem: lines were ignored. The DI extends MALIGNANCY_READ_CODES with the missing Xa-prefix codes from configs/read codes/readcode.md, removes the buggy generic `B5...` -> head_and_neck mapping (only B57.. -> brain remains valid), and adds three new lookups: ACTIVE_CANCER_CARE_CODES (XaIph "Cancer confirmed", XaN5C MDT meeting, 8BAD0 chemotherapy and ~25 others), HISTORY_OF_CANCER_CODE_PREFIXES (ZV10, B934, XaXGk and related personal-history prefixes), MALIGNANCY_TERM_PATTERNS (regex pairs such as "carcinoma of prostate" -> prostate, "invasive ductal carcinoma" -> breast that only fire on PROBLEM_LIST_LINE_PREFIX-anchored lines). services/analysis_worker/app/analyzers/anchor_detector.py _classify_text_encounters wires text_contains_history_of_cancer / find_malignancy_term_in_problem_line / find_active_cancer_care_code as new diagnosis paths with diagnosis_source provenance and hitl_required=True for all new sources; the history guard suppresses the entire diagnosis path on history-of-cancer encounters. The DI also includes the silent-closure provenance fix in services/analysis_worker/app/analyzers/episode_builder/_builder.py: every closed_benign episode now writes a benign_closure IS_PART_OF edge via the new _benign_closure_link_anchors helper, eliminating the 77 silent-closure episodes discovered during live verification (DO-LEO-AI-170) - VT passed 2026-04-17 | R-LEO-AI-170 | VT-LEO-AI-170 |
| DI-LEO-AI-172 | Adjuvant cancer-therapy diagnosis inference with co-condition guard (UN-LEO-AI-005, UN-LEO-AI-055): libs/domains/code_inventories.py adds ADJUVANT_THERAPY_DRUG_PATTERNS (regex+site_key+indication for letrozole/anastrozole/exemestane/tamoxifen/fulvestrant -> breast; goserelin/leuprorelin/triptorelin/bicalutamide/enzalutamide/abiraterone -> prostate; trastuzumab -> breast; capecitabine -> non_site_specific HITL-only; etc.) and ADJUVANT_THERAPY_ISSUE_MARKERS (regex such as "newly issued", "first prescription", "initiated on") plus the helpers find_adjuvant_therapy_drug and adjuvant_therapy_is_newly_issued. services/analysis_worker/app/analyzers/anchor_detector.py _classify_text_encounters fires diagnosis_source=adjuvant_therapy_drug ONLY when (a) an issue marker is present in the same encounter text, OR (b) an active-cancer-care code is present, OR (c) a malignancy term/code is present. Drug-alone encounters (routine repeat prescription reviews) never fire. confidence=0.75 and hitl_required=True on every adjuvant-derived anchor, so episodes promoted via this path are surfaced for HITL review and never become authoritative without human sign-off. The history-of-cancer guard from DI-LEO-AI-171 also short-circuits this path so survivors on long-term hormone therapy do not get re-diagnosed (DO-LEO-AI-171) - VT passed 2026-04-17 | R-LEO-AI-171 | VT-LEO-AI-170 |
| DI-LEO-AI-173 | Site reconciliation in episode build (UN-LEO-AI-006): services/analysis_worker/app/analyzers/episode_builder/_site_resolution.py _extract_condition_key_from_anchor short-circuits to the diagnosis anchor's site_key when site_source is one of {explicit_2ww_code, explicit_malignancy_code, malignancy_term_problem_line} and site_key is not unknown / non_site_specific. services/analysis_worker/app/analyzers/episode_builder/_builder.py _build_closed_episode adds a reconciliation block: if any diagnosis anchor in a diagnosis-led group carries an explicit site_source and a well-defined site_key that differs from the episode's referral-derived site_key, the builder adopts the diagnosis site, sets hitl_flag=True, and appends "site_reconciliation_hitl: <ref_site> -> <diag_site>" to hitl_reason. Verified live: post-rebuild 2026-04-17 the canonical confirmed-cancer cohort for 2025 rises from 24 to 27 episodes (+3) and 2024 from 23 to 26 (+3), with the explicit malignancy-code path catching 2 of 6 audit-discovered missed prostate cancers and the adjuvant-therapy path catching 1 letrozole-only breast cancer (DO-LEO-AI-172) - VT passed 2026-04-17 | R-LEO-AI-170 | VT-LEO-AI-170 |
| DI-LEO-AI-175 | Skin / melanoma inventory completeness (UN-LEO-AI-005, UN-LEO-AI-006): the 2026-04-17 audit of patient 4921442355 (Mr Harold Allwyn, lentigo maligna melanoma) found that XaMeA "Fast track referral for suspected skin cancer" was missing from FAST_TRACK_REFERRAL_READ_CODES, XaPyd "Seen in fast track suspected skin cancer clinic" was missing from SPECIALIST_CLINIC_READ_CODES, the entire B32.. CTV3 family (B320.-B325., B32y., B32z., B32A0-B32A2) was missing from MALIGNANCY_READ_CODES, and Xa99Y "Lentigo maligna melanoma" along with melanoma histological subtypes (lentigo maligna, superficial spreading, nodular, acral lentiginous, desmoplastic) were not recognised on Major:/Problem: lines. libs/domains/code_inventories.py adds all of the above plus a new CANCER_TREATMENT_PROCEDURE_CODES set ({7G055, X90PX}) and a find_cancer_treatment_procedure_code helper. services/analysis_worker/app/analyzers/anchor_detector.py wires find_specialist_clinic_site so XaPyd-style codes emit first_seen anchors with first_seen_source=specialist_clinic_code (and back-fill site_key when match_cancer_site missed it); the treatment branch now ORs _RE_TREATMENT with _treatment_proc_hit and labels procedure_code-derived treatment anchors with treatment_source=procedure_code (DO-LEO-AI-174) - VT passed 2026-04-17 | R-LEO-AI-172 | VT-LEO-AI-172 |
| DI-LEO-AI-177 | Cancer follow-up template recogniser (UN-LEO-AI-005, UN-LEO-AI-006): UHL Dermatology surveillance encounters use a "Skin Cancer Follow Up" template that on its own should imply an established cancer diagnosis but did not match any anchor pattern. libs/domains/code_inventories.py adds CANCER_FOLLOW_UP_PHRASES (regex+site_key for skin/melanoma, breast, prostate, lung, lower GI, upper GI, head and neck, urological, gynaecological, haematological, brain, thyroid, sarcoma, plus a generic "cancer follow up clinic" -> non_site_specific) and the helper find_cancer_follow_up_phrase(text). services/analysis_worker/app/analyzers/anchor_detector.py adds _follow_up_hit to the diagnosis path: if the text matches a follow-up template AND the history-of-cancer guard does not fire, has_cancer and has_confirmed are forced True and a diagnosis_confirmed anchor is emitted with diagnosis_source=cancer_follow_up_template, hitl_required=True, confidence=0.8, and site_key back-filled when no other site source has set one. The site reconciliation precedence chain inside the same encounter loop also accepts cancer_follow_up_template as a site source so the anchor's site survives into the episode. The history-of-cancer guard inside the helper prevents fresh diagnosis emission when the encounter encodes "personal history of cancer" (DO-LEO-AI-176) - VT passed 2026-04-17 | R-LEO-AI-172 | VT-LEO-AI-172 |
| DI-LEO-AI-178 | Benign-investigation phrase scope guard / day-17 closure bug fix (UN-LEO-AI-005, UN-LEO-AI-006, UN-LEO-AI-054): patient 4921442355's confirmed melanoma episode was prematurely closed as closed_benign on day 17 because an unrelated CKD/blood-pressure review encounter on 2024-11-18 contained the generic phrase "no further action". The phrase satisfied two broad regexes (BENIGN_INVESTIGATION_PHRASES and _RE_NO_CANCER) and emitted a benign_closure anchor that the episode builder then attached to the parallel skin-cancer episode. libs/domains/code_inventories.py adds BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT (frozenset of broad phrase labels: "no further action", "discharged from clinic", "discharged from care") and CANCER_PATHWAY_CONTEXT_REGEX (a strict regex matching only cancer/carcinoma/malignan*/tumour/melanoma/lymphoma/leukaemia/sarcoma/2WW/two-week wait/fast track/oncology/chemo*/radiotherapy/MDT meeting|review/suspected <site> cancer) plus the helper text_has_cancer_pathway_context(text). services/analysis_worker/app/analyzers/anchor_detector.py rewires the benign_closure emission so it requires ONE of: a concrete benign Read-code hit, a tier-1 phrase hit (cancer-scoped patterns such as "PSA normal, no further action", "mammogram normal", "FOBT normal", "colonoscopy benign finding"), a tier-2 phrase hit that passes the gate (gated label AND cancer-pathway context in the same encounter), OR has_no_cancer with cancer-pathway context already in the encounter. The deliberately STRICT gate excludes match_cancer_site() because the gold-mined dictionary contains incidental terms (e.g. "chronic kidney disease stage 3" under the renal site) that would re-open the day-17 bug. Verified end-to-end: post-rebuild 2026-04-17, episode 42b722eb6082a4b7 reclassifies from closed_benign to completed/melanoma, and the global benign_outcome cohort drops from 67 -> 41 distinct patients (-26) while diagnosed_or_treated rises from 82 -> 83 (DO-LEO-AI-177) - VT passed 2026-04-17 | R-LEO-AI-173 | VT-LEO-AI-172 |
| DI-LEO-AI-182 | Detect 2WW referral rejection and resubmission as auditable workflow events (UN-LEO-AI-041): _classify_text_encounters in services/analysis_worker/app/analyzers/anchor_detector.py adds three regex families (_RE_REFERRAL_REJECTED, _RE_REFERRAL_MARKED_IN_ERROR, _RE_REFERRAL_RESUBMITTED) and a priority branch that emits the encounter as a referral anchor with referral_subtype 'rejected' or 'resubmitted', suppressing diagnosis / benign_closure emission on the same row. services/analysis_worker/app/analyzers/episode_builder/_persistence.py and _cypher.py persist anchor.referral_subtype on the IS_PART_OF edge via LINK_ENCOUNTERS. New MCP tool dq_rejected_referrals_resubmission_delay in services/neo4j_mcp/tools/query_pack_pathway.py reports rejection-to-resubmission delay in calendar days for 2WW pathways, excluding status='merged' episodes. Pattern-level test class TestReferralRejectionAndResubmission in tests/test_anchor_detector.py covers Choose-and-book rejection, Marked-in-Error referral, resubmission with referral context, suppression of diagnosis/benign on referral lifecycle rows, PRISM and text_generic regression, and three negative tests for transplant rejection, lab-sample resubmission, and BP value Marked-in-Error. Companion fix in libs/episodes/duplicate_resolver.py.pick_evidence_winner adds a multi-distinct-type guard that skips the merge whenever a cluster carries >=2 known cancer types and the diagnosis text does not uniquely name one of them (closes the gap behind the alphabetical tie-break that allowed cross-type merges); scripts/backfill_unmerge_unsafe_episodes.py reverts pre-existing unsafe merges to status='reopened_for_rebuild'. dq_missing_milestone_chains in services/neo4j_mcp/tools/query_pack_pathway.py now filters out status='merged' episodes to remove the false-positive milestone-gap signal (DO-LEO-AI-181) - VT passed 2026-04-17 | R-LEO-AI-097 | VT-LEO-AI-176 |
| DI-LEO-AI-183 | Calibrated absolute confidence scoring in the SNOMED resolver (UN-LEO-AI-078): services/terminology_api/app/services/coding_resolver.py rewrites HybridCodingResolver._fuse_and_rank to compute a calibrated absolute confidence in [0, 1] (replacing per-term-relative normalisation + 1.3x multiplicative tag boost). Lexical signal is 1.0 when had_exact_match else bm25/(bm25+1); vector signal is cosine; combined via max + 0.10 * min capped at 1.0; tag adjustment is additive (+0.10 exact match, neutral same-group, *0.5 cross-group, hard-block non-clinical when clinical expected). New module helpers _calibrate_confidence and _apply_tag_adjustment encapsulate the math. CodingCandidate exposes had_exact_match, lexical_raw, vector_raw alongside the calibrated score. /terminology/resolve CandidateResponse mirrors all four fields. libs/terminology/client.py ResolvedTerm parses the new fields; cache prefix bumped v2 -> v3 to flush stale entries. Downstream gates retuned: libs/pipeline_graph/subgraphs/terminology.py _DEFAULT_MIN_SCORE 0.70 -> 0.55, libs/pipeline_graph/subgraphs/surface_form_validation.py threshold 0.9 -> 0.7. Verified: 56/56 tests pass in tests/test_coding_resolver.py + tests/test_gold_label_snomed_check.py including 8 new TestCalibratedScoring cases pinning every per-branch score path; live API smoke tests confirm 'prostate cancer' and 'CKD' score 1.000, 'rising PSA' 0.966, 'cancer free' 0.895 (DO-LEO-AI-182) - VT passed 2026-04-17 | R-LEO-AI-177 | VT-LEO-AI-177 |
| DI-LEO-AI-184 | SNOMED proposal validator with tiered acceptance ladder (UN-LEO-AI-078): scripts/lib/gold_label_snomed_check.py implements an explicit three-branch acceptance model (EXACT branch on had_exact_match=True with tag compatibility, SEMANTIC branch on vector_raw>=0.92 AND surface_match>=0.66, SURFACE branch on surface_match>=0.7 AND _meets_shared_token_floor AND polarity_guard) keyed off the resolver's absolute signals -- never on the fused score. Defaults tuned against the 950 HITL-completed backfill so that all four documented false positives (nipple inversion on the right breast -> Pendulous right breast; worsened over the last six months -> Sexually active in last six months; right sided sciatica feels pain from back/buttocks to toes; surgery in jan to remove cyst in left kidney) are rejected. Polarity guard catches negation flips ('no hydrocephalus' -> Hydrocephalus -> reject as polarity_mismatch). Shared-token floor catches lexical-coincidence false positives ('cancer free' -> 'Seizure free' -> reject as shared_token_floor). scripts/validate_backfill_snomed.py CLI streams a backfill JSONL through the validator and writes *.validated.jsonl + *.validated.summary.json with structured rejection reasons. End-to-end re-validation on the 950 HITL-completed backfill produced 240 kept additions with resolver_score in [0.873, 1.000] (mean 0.989). Verified: 21/21 tests pass in tests/test_gold_label_snomed_check.py (DO-LEO-AI-183) - VT passed 2026-04-17 | R-LEO-AI-177, R-LEO-AI-178 | VT-LEO-AI-178 |
| DI-LEO-AI-185 | GoldLabelDetailDialog re-mount + state resync (UN-LEO-AI-082): every JSX mount of <GoldLabelDetailDialog> in services/ui/src/components/gold-dataset/GoldDatasetPanel.tsx carries a stable `key` prop derived from `label_id` (with per-surface namespace prefixes gold-/syn-/cand-/sim- to avoid collisions). The dialog body adds a belt-and-braces useEffect with deps [item.label_id, item.entities_json] that re-derives entities, rejectedRelationKeys, and clears suggestion drafts, term drafts, surface-form drafts, lookup target, save state, and delete-confirm flags when label_id changes. The lazy useState(() => parseEntities(item.entities_json)) initialiser is preserved as the mount-time fast path. Closes the regression class observed on 2026-04-17 (GL-d3ffb211468a5bcf rendering 'Flexible cystoscopy' against an unrelated breast-USS sentence). Verified: 5/5 tests pass in services/ui/src/__tests__/gold-label-detail-dialog-rekey.test.tsx (DO-LEO-AI-184) - VT passed 2026-04-17 | R-LEO-AI-179 | VT-LEO-AI-179 |
| DI-LEO-AI-186 | Offline gold-label entity audit (UN-LEO-AI-082): scripts/lib/gold_label_snomed_check.py adds audit_existing_entity + audit_gold_label_entities + ENTITY_AUDIT_ISSUE_CODES + _derive_semantic_tag_from_term + _CLINICAL_LABELS + _NON_CLINICAL_SEMANTIC_TAGS that audit every persisted GoldLabel entity for self-consistency without calling the terminology service. Issue codes: missing_concept_id (critical), missing_label (critical), qualifier_value_on_clinical_label (critical), tag_label_mismatch (critical), stored_tag_drift (info), missing_snomed_term (warning), blocked_assertion_with_concept (info). Authoritative semantic_tag derivation: SNOMED preferred-term suffix wins, falls back to stored field. CLI scripts/audit_gold_label_entities.py sweeps `MATCH (g:GoldLabel) WHERE g.entities_json IS NOT NULL`, writes data/audit/gold_label_entity_audit_<UTC>.jsonl + .summary.json, supports --severity, --source, --exclude-source, --limit. First sweep against the live KG (967 GoldLabels, 2073 entities): 88 critical, 80 warning, 398 info; identified the 5 manual_gold_seed_2026_04_17 known offenders + 24 tag_label_mismatch + 58 missing_concept_id for triage. Verified: 22/22 tests pass in tests/test_gold_label_existing_entities_audit.py including a live-payload replay of GL-d3ffb211468a5bcf (DO-LEO-AI-185) - VT passed 2026-04-17 | R-LEO-AI-180 | VT-LEO-AI-180 |
| DI-LEO-AI-187 | Manual gold seed safety check (UN-LEO-AI-082): scripts/seed_manual_gold_records.py::_validate_entity now derives `semantic_tag` from the SNOMED preferred-term suffix via _derive_semantic_tag_from_term (suffix-derived tag is authoritative), rejects writes where declared semantic_tag disagrees with the suffix outside the validator's _TAG_SYNONYMS table, REJECTS writes where label is in _CLINICAL_LABELS but the authoritative semantic_tag is in _NON_CLINICAL_SEMANTIC_TAGS (with R-LEO-AI-180 named in the error), and rejects writes where snomed_concept_id is set but snomed_term is empty. The persisted entity carries the SNOMED-truthful semantic_tag, not the curator's declared field. Manual gold seed manifest design-controls/training-data/manual-gold-seed-2026-04-17.yaml updated: 5 entries (NEG-04, NEG-06, NEG-07, NEG-13, NEG-17) relabelled from finding/finding to qualifier_value/qualifier_value, then re-seeded against Neo4j -- audit confirms zero remaining offenders from this source (was 5, now 0). Verified: 19/19 tests pass in tests/scripts/test_seed_manual_gold_records.py (13 pre-existing + 6 new TC-006 cases) (DO-LEO-AI-186) - VT passed 2026-04-17 | R-LEO-AI-180 | VT-LEO-AI-181 |

---

### 3.xx SBAR Generation Workflow + Document Chunks (April 2026)

NOTE: DI-LEO-AI-186 and DI-LEO-AI-187 in the table below SUPERSEDE the
earlier same-numbered rows in section "GoldLabel Single Source for
Training" -- the underlying YAMLs in design-controls/design-inputs/ have
been re-authored against UN-LEO-AI-082 to describe the chunk schema
foundation that the SBAR pipeline depends on. The legacy gold-label
audit and manual-gold-seed safety controls remain in force in code
(scripts/lib/gold_label_snomed_check.py, scripts/seed_manual_gold_records.py)
and are still verified by VT-LEO-AI-180 and VT-LEO-AI-181 respectively.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-079 | draft | Make narrative document content queryable as discrete clinical evidence (drives the Chunk schema and the generalised :DOCUMENTS writer) |
| User Need | UN-LEO-AI-080 | draft | Generate an SBAR summary for a patient on demand (clinical-encounter preparation) |
| User Need | UN-LEO-AI-081 | draft | Reviewers can interactively test SBAR generation (admin playground) |
| Design Input | DI-LEO-AI-186 | approved | :Chunk node and HAS_CHUNK relationship (deterministic id, ordinal, char offsets, sha256) |
| Design Input | DI-LEO-AI-187 | approved | Generalise :DOCUMENTS to accept Encounter|Chunk source (OPTIONAL MATCH on Patient via parent DocumentReference) |
| Design Input | DI-LEO-AI-188 | approved | SBAR queue contract (SBARRequestPayload + SBARSituationInput + SBARArtifactRef + SBARBackgroundSourceRef) |
| Design Input | DI-LEO-AI-189 | approved | :Assessment node and HAS_ASSESSMENT relationships (incremental SET_*, FINALISE) |
| Design Input | DI-LEO-AI-190 | approved | SBAR orchestrator: four-stage pipeline with incremental persistence + per-stage Redis events |
| Design Input | DI-LEO-AI-191 | approved | SBAR HTTP API + SSE relay (POST /sbar/jobs, GET /sbar/jobs/{id}/events, GET /sbar/assessments/{id}) |
| Design Input | DI-LEO-AI-192 | approved | SBAR LLM prompt suite (situation, background, recommendation) + JSON output schemas + 12 hardening rules |
| Design Input | DI-LEO-AI-193 | approved | Deterministic Assessment formatter from /terminology/guidelines/evaluate (no LLM in the loop; rule-derived stt/rtr/alternative_pathway) |
| Design Input | DI-LEO-AI-194 | approved | AI Summarisation Playground (admin UI tab + form + SSE viewer + 'test only' banner) |
| Design Input | DI-LEO-AI-230 | draft | PatientFinder primitive (Search/Filter/Cohort tabs) + analytics-api /patient-finder router with NHS+DOB on every result row |
| Design Input | DI-LEO-AI-231 | draft | SummarisationContext enum (34 NHS-aligned reasons across Primary care / Secondary care / Statutory and social / Quality assurance) + card-grid Dialog picker primitive (search field + responsive grid of selectable cards) |
| Design Input | DI-LEO-AI-507 | approved | Per-context SBAR Situation framing snippets editable as :PromptConfig nodes (sbar_situation_context_<value> v1) with Neo4j-first lookup + hardcoded-dict fallback + per-call cache; AI Instructions list grouping by [<Group>] description prefix |
| User Need | UN-LEO-AI-092 | approved | Platform admins can tune per-context SBAR Situation framing without engineering involvement, via /admin/knowledge?tab=ai-instructions |
| Design Input | DI-LEO-AI-232 | draft | BackgroundSourcePicker primitive (Encounters tab + Documents->Chunks nested expansion) |
| Design Input | DI-LEO-AI-233 | draft | GuidelinePicker primitive (MUI Autocomplete over /api/nice/loaded) + QSIR-aligned Concern field (max 500 chars) |
| Design Output | DO-LEO-AI-185 | approved | libs/cypher/chunk_queries.py + schema_constraints additions |
| Design Output | DO-LEO-AI-186 | approved | libs/cypher/documents_queries.py generalisation (source_label, OPTIONAL MATCH, null-safe FOREACH) |
| Design Output | DO-LEO-AI-187 | approved | libs/sbar/events.py (SBARRequestPayload + supporting models) |
| Design Output | DO-LEO-AI-188 | approved | libs/cypher/sbar_assessment_queries.py + ASSESSMENT_CONSTRAINTS |
| Design Output | DO-LEO-AI-189 | approved | services/pipeline_worker/app/services/sbar_orchestrator.py + libs/sbar/source_resolver.py + libs/sbar/prompt_calls.py |
| Design Output | DO-LEO-AI-190 | approved | services/api/app/routers/sbar.py + Redis pub/sub SSE relay |
| Design Output | DO-LEO-AI-191 | approved | libs/prompts/sbar_*_v1.py + libs/prompts/sbar_output_schemas.py + scripts/seed_prompt_configs.py entries |
| Design Output | DO-LEO-AI-192 | approved | libs/sbar/assessment_formatter.py |
| Design Output | DO-LEO-AI-193 | approved | services/ui/src/app/admin/ai-summarisation/* + useSbarStream + three Next.js Route Handler proxies |
| Risk | R-LEO-AI-180 | mitigated | Chunk text drift / desynchronisation (re-ingestion creates new chunks; old chunks survive for audit) |
| Risk | R-LEO-AI-181 | analyzed | LLM hallucination in SBAR Situation/Background/Recommendation (12 hardening rules + rule-id grounding + deterministic Assessment substrate) |
| Risk | R-LEO-AI-182 | mitigated | Partial SBAR rendered as complete (Assessment.status + errors[] + terminal SSE events + 300s idle timeout) |
| Risk | R-LEO-AI-183 | mitigated | Rule evaluator outage masks unmatched safety rules (status='failed', explicit 'evaluator unavailable' narrative, pathway hints set to 'unknown') |
| Risk | R-LEO-AI-184 | analyzed | Prompt injection from CONTEXT free text (hardening rule 10 + rule-id grounding + JSON schema) |
| Risk | R-LEO-AI-185 | mitigated | Reviewer treats playground SBAR output as production-ready (always-visible 'test only' banner + admin role gate + typed SummarisationContext + capped Concern) |
| Risk | R-LEO-AI-211 | mitigated | Reviewer picks the wrong patient in PatientFinder (NHS+DOB on every row + pre-submit echo chip + admin gate) |
| Design Output | DO-LEO-AI-230 | draft | services/ui/src/components/sbar-playground/PatientFinder.tsx + services/analytics_api/app/routers/patient_finder.py + extended cohorts.py |
| Design Output | DO-LEO-AI-231 | draft | libs/sbar/events.py SummarisationContext enum + libs/sbar/source_resolver.py + services/ui/src/components/sbar-playground/SummarisationContextSelect.tsx |
| Design Output | DO-LEO-AI-232 | draft | services/ui/src/components/sbar-playground/BackgroundSourcePicker.tsx + GET /document-references/{id}/chunks endpoint |
| Design Output | DO-LEO-AI-233 | draft | services/ui/src/components/sbar-playground/GuidelinePicker.tsx + SBARRequestPayload.concern field + orchestrator forwarding |
| Verification Test | VT-LEO-AI-185 | passed | Chunk id determinism + UPSERT_CHUNK shape + generalised DOCUMENTS writer (Encounter|Chunk) with null-safe FOREACH |
| Verification Test | VT-LEO-AI-186 | passed | SBARRequestPayload validation: minimal happy path, situation artefact id-or-text rules, background source enum gates, JSON round-trip |
| Verification Test | VT-LEO-AI-187 | passed | SBAROrchestrator runs all four stages in order, persists incrementally to :Assessment, captures per-stage errors, degrades to draft on LLM failure |
| Verification Test | VT-LEO-AI-188 | passed | AI Summarisation tab + 'test only' banner + useSbarStream wiring + three proxy routes + axe baseline |
| Verification Test | VT-LEO-AI-189 | draft  | SBAR prompt registration + JSON schema enforcement + deterministic Assessment formatter pinned; golden-set TC-009 (10 fixtures, manual sign-off) gates broader rollout |
| Verification Test | VT-LEO-AI-230 | draft  | PatientFinder dialog (3 tabs + NHS/DOB row contract + 250ms typeahead debounce) + /patient-finder router scope and CohortFilter extension coverage |
| Verification Test | VT-LEO-AI-231 | draft  | SummarisationContext enum stability + source_resolver prompt fragment injection + frontend/backend parity + fixed_text backward compatibility (legacy 20-member contract; superseded for the 34-member contract by VT-LEO-AI-509) |
| Verification Test | VT-LEO-AI-509 | passed | 34-member SummarisationContext enum + group mapping + sbar_situation_context_* PromptConfig seed parity + Neo4j-first source resolver with hardcoded fallback + per-call cache + UI Secondary care rename + AI Instructions categoriser routes by [<Group>] prefix |
| Risk | R-LEO-AI-507 | mitigated | Admin edits a per-context PromptConfig snippet and removes safety-critical framing (e.g. 2WW pathway action), causing the SBAR Situation prompt to omit information the receiving clinician relies on |
| Design Output | DO-LEO-AI-507 | draft | scripts/seed_prompt_configs.py (34 sbar_situation_context_<value> PromptConfig entries) + libs/sbar/source_resolver.py (Neo4j-first lookup + dict fallback + per-call cache) + libs/sbar/events.py (SUMMARISATION_CONTEXT_GROUPS + 14 new contexts) + services/ui/src/app/admin/prompts/page.tsx (categorise() recognises sbar_situation_context_* and uses [<Group>] description prefix) + services/ui/src/components/sbar-playground/SummarisationContextSelect.tsx (Acute -> Secondary care rename + 14 new options) |
| Verification Test | VT-LEO-AI-232 | draft  | BackgroundSourcePicker (2 tabs only + nested chunk Collapse + chunk-drops-parent rule) + ordered chunk endpoint + scope check |
| Verification Test | VT-LEO-AI-233 | draft  | GuidelinePicker Autocomplete + use-all-loaded toggle + Concern textarea cap + Pydantic 500-char cap + orchestrator concern forwarding |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-186 | :Chunk node + HAS_CHUNK (UN-LEO-AI-079): libs/cypher/chunk_queries.py adds make_chunk_id (sha256 of document_reference_id + ordinal + sha256(text)) and the UPSERT_CHUNK Cypher; libs/cypher/schema_constraints.py adds CHUNK_CONSTRAINTS (UNIQUE on Chunk.id; index on document_reference_id, sha256). Verified: 20/20 tests pass in tests/test_chunk_documents_queries.py + tests/test_documents_sentence_evidence_mapping.py - VT passed 2026-04-17 | R-LEO-AI-180 | VT-LEO-AI-185 |
| DI-LEO-AI-187 | DOCUMENTS writer generalised to Encounter|Chunk (UN-LEO-AI-079): libs/cypher/documents_queries.py _build_upsert_query takes source_label parameter; chunk path uses OPTIONAL MATCH ... <-[:HAS_CHUNK]-(:DocumentReference)<-[:HAS_DOCUMENT_REFERENCE]-(p:Patient) and guards the Patient FOREACH with `p IS NOT NULL`. write_documents_from_sentences_payload accepts source_label and source_id (encounter_id alias preserved for back-compat). - VT passed 2026-04-17 | R-LEO-AI-180 | VT-LEO-AI-185 |
| DI-LEO-AI-188 | SBARRequestPayload (UN-LEO-AI-080): libs/sbar/events.py + libs/sbar/__init__.py introduce the sbar_requested wire contract used by the UI playground and the future referral / encounter producers. Strict enums on situation artefact and background source types; id-or-text validator per artefact type. - VT passed 2026-04-17 | R-LEO-AI-181 | VT-LEO-AI-186 |
| DI-LEO-AI-189 | :Assessment Cypher (UN-LEO-AI-080): libs/cypher/sbar_assessment_queries.py + ASSESSMENT_CONSTRAINTS in libs/cypher/schema_constraints.py. CREATE_ASSESSMENT links to Patient up-front; LINK_ASSESSMENT_TO_REFERRAL_REQUEST / _PROCEDURE_REQUEST / _ENCOUNTER attach in best-effort fashion; SET_SITUATION / SET_BACKGROUND / SET_ASSESSMENT_NARRATIVE / SET_RECOMMENDATION write incrementally; FINALISE_ASSESSMENT pins status + content; GET_ASSESSMENT + assessment_to_dict serve the API. - VT passed 2026-04-17 | R-LEO-AI-182 | VT-LEO-AI-187 |
| DI-LEO-AI-190 | SBAROrchestrator (UN-LEO-AI-080): services/pipeline_worker/app/services/sbar_orchestrator.py runs Situation -> Background -> deterministic Assessment -> Recommendation, persisting after each stage and publishing per-stage events on Redis pipeline:{run_id}. Source resolution delegated to libs/sbar/source_resolver.py; LLM calls to libs/sbar/prompt_calls.py. services/pipeline_worker/app/main.py dispatches sbar_requested directly to handle_sbar_message. - VT passed 2026-04-17 | R-LEO-AI-182, R-LEO-AI-183 | VT-LEO-AI-187 |
| DI-LEO-AI-191 | SBAR HTTP API + SSE relay (UN-LEO-AI-080): services/api/app/routers/sbar.py exposes POST /sbar/jobs (queues onto pipeline-jobs), GET /sbar/jobs/{run_id}/events (Redis pub/sub SSE relay with last-event catch-up + 300s idle timeout), GET /sbar/assessments/{id}. All three depend on require_admin. services/api/app/main.py wires the router. - VT covered by UI proxy + playground tests (VT-LEO-AI-188) | R-LEO-AI-182 | VT-LEO-AI-188 |
| DI-LEO-AI-192 | SBAR LLM prompt suite (UN-LEO-AI-080): libs/prompts/sbar_situation_v1.py, sbar_background_v1.py, sbar_recommendation_v1.py + libs/prompts/sbar_output_schemas.py provide three system prompts and JSON schemas (additionalProperties=false; minLength=1 on *_markdown). 12 hardening rules per prompt (source attribution, no inference, conflict surfacing, plain English, prompt-injection guard, JSON-only). Seeded into Neo4j by scripts/seed_prompt_configs.py. - VT pending golden-set sign-off | R-LEO-AI-181, R-LEO-AI-184 | VT-LEO-AI-189 |
| DI-LEO-AI-193 | Deterministic Assessment formatter (UN-LEO-AI-080): libs/sbar/assessment_formatter.py wraps /terminology/guidelines/evaluate via httpx and is a pure function of (matched_rules, patient_codes, guideline_ids). Sorts rules by action priority (2WW > urgent > routine), renders verbatim recommendation_verbatim with rule + guideline attribution, and derives stt/rtr/alternative_pathway + *_evidence deterministically. Empty matches yield 'no rules matched' + rtr=no; evaluator outage yields 'evaluator unavailable' + rtr=unknown. - VT passed 2026-04-17 | R-LEO-AI-181, R-LEO-AI-183 | VT-LEO-AI-189 |
| DI-LEO-AI-194 | AI Summarisation Playground (UN-LEO-AI-081): services/ui/src/app/admin/ai-summarisation/{page,SbarPlayground}.tsx + services/ui/src/hooks/useSbarStream.ts + three Next.js Route Handlers under services/ui/src/app/api/sbar/* proxy POST /sbar/jobs, GET /sbar/jobs/{runId}/events (SSE), GET /sbar/assessments/{id}. Tab registered in services/ui/src/app/admin/knowledge/page.tsx + services/ui/src/lib/knowledgeCopy.ts. Permanent 'Test only' banner (data-testid sbar-test-only-banner). - VT passed 2026-04-17 | R-LEO-AI-185 | VT-LEO-AI-188 |
| DI-LEO-AI-230 | PatientFinder primitive + analytics-api router (UN-LEO-AI-081): services/ui/src/components/sbar-playground/PatientFinder.tsx ships a 3-tab MUI Dialog (Search / Filter / Saved cohort) where every result row in every tab renders NHS number AND DOB alongside the display name. services/analytics_api/app/routers/patient_finder.py exposes /search, /by-filter, /by-cohort/{id}, /{patient_id}/encounters, /{patient_id}/document-references, all scoped via CallerScope. cohorts.py adds imd_decile_min/max, encounter_count_min/max + window_months, episode_domain, episode_subdomain, episode_outcome and POST /cohorts/preview. - VT pending | R-LEO-AI-211 | VT-LEO-AI-230 |
| DI-LEO-AI-231 | SummarisationContext enum + select primitive (UN-LEO-AI-081, extended by UN-LEO-AI-091): libs/sbar/events.SummarisationContext (str, Enum) + SUMMARISATION_CONTEXT_LABELS + SUMMARISATION_CONTEXT_PROMPTS now deliver 34 NHS-aligned reasons grouped via SUMMARISATION_CONTEXT_GROUPS into Primary care (8) / Secondary care (15, replaces "Acute") / Statutory and social (9) / Quality assurance (2). The mdt_discussion label is disambiguated to "MDT prep (primary care)" so it does not collide with the new mdt_specialty (Secondary care) entry. libs/sbar/source_resolver.py injects the matching fragment for type=summarisation_context artefacts (Neo4j-first via DI-LEO-AI-507, with the events.py dict as fallback). services/ui/src/components/sbar-playground/SummarisationContextSelect.tsx renders a button that opens a Dialog with a search field and a responsive grid of selectable cards (1 / 2 / 3 columns) grouped by clinical setting; the selected card is marked with aria-pressed=true and the chosen description appears as helper text below the trigger. The legacy fixed_text type is retained for one minor version. - VT-LEO-AI-509 passed 2026-04-19 (21/21 pytest + 7/7 jest after picker re-shape; 11/11 jest in combined chrome run) | R-LEO-AI-185, R-LEO-AI-507 | VT-LEO-AI-231, VT-LEO-AI-509 |
| DI-LEO-AI-507 | Per-context SBAR Situation snippets editable in AI Instructions (UN-LEO-AI-092): scripts/seed_prompt_configs.py iterates over SummarisationContext and seeds one :PromptConfig node per value as sbar_situation_context_<value> v1 with the framing snippet from libs.sbar.events.SUMMARISATION_CONTEXT_PROMPTS and a description carrying a [<Group>] prefix (Primary care / Secondary care / Statutory and social / Quality assurance). libs/sbar/source_resolver._situation_context_snippet fetches the snippet via GET_PROMPT_BY_NAME (version=1) when a session is provided and falls back to the hardcoded dict when the session is None / returns no row / returns an empty systemPrompt / raises - so the orchestrator never sees a None framing. resolve_situation() threads a per-call cache through _resolve_artifact so two artefacts with the same context cause exactly one PromptConfig lookup. services/ui/src/app/admin/prompts/page.tsx::categorise() detects the sbar_situation_context_ prefix and parses the [<Group>] description prefix to label the row, so the AI Instructions list groups SBAR snippets by clinical setting; all internal call sites now use categoriseFromPrompt(p) so the description is always read. PromptConfig CRUD reuses the existing admin-only auth path (no new role added). - VT-LEO-AI-509 passed 2026-04-19 (21/21 pytest + 11/11 jest) | R-LEO-AI-507 | VT-LEO-AI-509 |
| DI-LEO-AI-232 | BackgroundSourcePicker primitive + chunks endpoint (UN-LEO-AI-081): services/ui/src/components/sbar-playground/BackgroundSourcePicker.tsx is a patient-scoped MUI Dialog with two tabs only (Encounters, Letters and documents). Documents rows expand to reveal child :Chunk nodes via GET /document-references/{id}/chunks (chunks ordered by chunk_index ascending). Selecting any chunks under a document implicitly drops the parent DocumentReference from the emitted SBARBackgroundSourceRef[]. Chunks live inside the document Collapse, never as a top-level tab. - VT pending | R-LEO-AI-211 | VT-LEO-AI-232 |
| DI-LEO-AI-233 | GuidelinePicker primitive + Concern field (UN-LEO-AI-081): services/ui/src/components/sbar-playground/GuidelinePicker.tsx wraps an MUI Autocomplete (multiple) loaded from /api/nice/loaded with a 'Use all loaded' shortcut. services/ui/src/app/admin/ai-summarisation/SbarPlayground.tsx adds a 500-char Concern textarea with visible counter; useSbarStream forwards it as SBARRequestPayload.concern. libs/sbar/events.SBARRequestPayload.concern is Optional[str] with Field(max_length=500). services/pipeline_worker/app/services/sbar_orchestrator.py forwards (payload.concern or '').strip() into extra_context['concern'] on the Situation stage. - VT pending | R-LEO-AI-185 | VT-LEO-AI-233 |
| DI-LEO-AI-195 | PRISM cancer-context guard + Marked-in-Error admin amendment filter (UN-LEO-AI-005, UN-LEO-AI-006): services/analysis_worker/app/analyzers/anchor_detector.py adds _RE_PRISM_CANCER_CONTEXT and an is_prism_cancer guard so PRISM proforma encounters only emit referral_subtype='prism' when the same text carries 2WW / TWW / two-week-wait / 'fast track referral for suspected' / 'suspected cancer' / XaMe[A-Z] Read code; non-cancer PRISM (sexual health, MSK, IBD, mental-health crisis, ultrasound, etc.) emits no referral anchor and does not open a 2WW pathway. Same module adds an _is_admin_amendment qualifier check so 'Marked in Error: Amended data' QOF amendments fall through to text_generic instead of inflating the rejection-resubmission DQ metric. - VT passed 2026-04-17 | R-LEO-AI-186 | VT-LEO-AI-190 |
| DI-LEO-AI-200 | Strict NSS classification (UN-LEO-AI-005, UN-LEO-AI-006): services/analysis_worker/app/analyzers/episode_builder/_site_resolution.py adds _NSS_PHRASE_RE (word-boundary regex covering 'non-site-specific symptoms', '2WW NSS', 'NSS 2WW', 'NSS referral', 'fast track NSS', 'fast track referral for suspected cancer due to non-site-specific symptoms'); removes the over-broad ('fast', 'non_site_specific') _SITE_MAP entry; tightens _extract_condition_key generic-term fallback to return 'unknown' instead of 'non_site_specific'. libs/domains/code_inventories.py corrects three Read-code mis-mappings (XaMeD: NSS->childrens_tumour, XaMeL: NSS->testicular, XaPyS: NSS->childrens_tumour). Live cohort dropped from 48 phantom/misclassified NSS episodes to 0; previously-misclassified children's tumour pathway now correctly classified. Verified: 18/18 pytest cases pass in tests/test_site_resolution_nss.py - VT passed 2026-04-18 | R-LEO-AI-190 | VT-LEO-AI-193 |
| DI-LEO-AI-201 | Tighten _RE_FIRST_SEEN attestation guard (UN-LEO-AI-005, UN-LEO-AI-006): services/analysis_worker/app/analyzers/anchor_detector.py rebuilds _RE_FIRST_SEEN so every alternation requires an attestation verb (seen|attended|reviewed|assessed|consulted) within proximity of the clinic / fast-track / 2WW token. Suppresses phantom first_seen anchors from narrative mentions ('discussed 2WW', 'considering fast track', 'awaiting clinic appointment') so the rescue path no longer promotes open referrals to phantom 'completed'. Verified by tests/test_patient_4643293950_patterns.py::TestPatternBFirstSeenAttestationGuard - VT passed 2026-04-18 | R-LEO-AI-191 | VT-LEO-AI-194 |
| DI-LEO-AI-202 | Narrative-reference referral guard (UN-LEO-AI-005, UN-LEO-AI-006): anchor_detector.py adds _RE_NARRATIVE_REFERRAL_REFERENCE (DNA, awaiting result, follow-up of, in light of past referral, etc.) and _RE_STRUCTURAL_REFERRAL (XaY59, Outbound referral, fast track / 2WW Read codes). _classify_text_encounters suppresses text_generic referrals when the encounter is purely narrative commentary about a past referral with no structural referral evidence. Verified by tests/test_patient_4643293950_patterns.py::TestPatternCDNarrativeReferralGuard - VT passed 2026-04-18 | R-LEO-AI-192 | VT-LEO-AI-195 |
| DI-LEO-AI-203 | PMHx history-of-cancer detection (UN-LEO-AI-005, UN-LEO-AI-006, UN-LEO-AI-007): libs/domains/code_inventories.py adds _PMHX_SECTION_RX and _malignancy_under_pmhx_section. text_contains_history_of_cancer treats malignancy mentions inside a recognised Past medical history section header as historical context. Suppresses phantom diagnosis anchors and avoids false benign closure of open cancer pathways from PMHx malignancy lines. Verified by tests/test_patient_4643293950_patterns.py::TestPatternEPmhxBenignClosure - VT passed 2026-04-18 | R-LEO-AI-193 | VT-LEO-AI-196 |
| DI-LEO-AI-204 | care_obstruction milestone (UN-LEO-AI-005, UN-LEO-AI-007): anchor_detector.py adds _RE_CARE_OBSTRUCTION (DNA + reason such as mobility/transport/carer/safeguarding; refusal of named investigation; hospital cancel/retract referral; family aggression / capacity / safeguarding; avoidable delay). _AnchorBuckets expanded to 9-tuple to carry care_obstructions; episode_builder/_builder.py adds _care_obstruction_link_anchors + _care_obstruction_hitl so any obstruction inside the episode window forces hitl_flag=True with a structured reason. Verified by tests/test_patient_4643293950_patterns.py::TestPatternGCareObstruction - VT passed 2026-04-18 | R-LEO-AI-194 | VT-LEO-AI-198 |
| DI-LEO-AI-205 | rejected_no_followup status (UN-LEO-AI-006, UN-LEO-AI-007): episode_builder/_status.py adds _has_followup_referral + _rejection_followup_status. _determine_episode_status now distinguishes a rejected referral that produced a follow-up (treated as in_progress) from one that did not (rejected_no_followup) so broken referral chains surface within the rescue window rather than waiting for the stale-close pass. Verified by tests/test_patient_4643293950_patterns.py::TestPatternARejectedNoFollowupStatus - VT passed 2026-04-18 | R-LEO-AI-195 | VT-LEO-AI-197 |
| DI-LEO-AI-206 | Exclusive encounter claiming (UN-LEO-AI-006): episode_builder/_types.py adds BuildContext.claimed_encounters; _builder.py adds _filter_unclaimed_link_groups which drops already-claimed encounters from non-protected milestones, protects the referral identity encounter, and removes link groups that become empty after filtering. Enforces single-claim invariant per encounter / per non-referral milestone so duplicate-resolver no longer churns on the same encounter being attached to multiple episodes. Verified by tests/test_patient_4643293950_patterns.py::TestPatternFExclusiveEncounterClaiming - VT passed 2026-04-18 | R-LEO-AI-196 | VT-LEO-AI-199 |
| DI-LEO-AI-210 | Family-history-of-cancer guard (Pattern H, UN-LEO-AI-005, UN-LEO-AI-006): anchor_detector.py adds _RE_FAMILY_HISTORY_CANCER (FH ca, FHx, "father had/diagnosed with cancer", "mother died of ovarian cancer", "family history of breast cancer"). _classify_text_encounters extends the suppression hook so a text_generic referral candidate is dropped when only FH context is present and no structural artefact exists. libs/domains/code_inventories.py adds _FAMILY_HISTORY_CANCER_RX + text_contains_family_history_of_cancer; text_contains_history_of_cancer wires both checks so the diagnosis path also treats FH-only mentions as historical context. Verified by tests/test_patient_4842019832_patterns.py::TestPatternHFamilyHistoryGuard - VT passed 2026-04-18 | R-LEO-AI-198 | VT-LEO-AI-202 |
| DI-LEO-AI-211 | Boilerplate lab-report referral guidance suppression (Pattern I, UN-LEO-AI-005, UN-LEO-AI-006): anchor_detector.py adds _RE_BOILERPLATE_REFERRAL_GUIDANCE (covers PSA / CEA / CA125 / FIT / calprotectin disclaimer wording: "If the PSA value remains elevated above the age specific threshold, refer as a 2WW", "should be referred", "Consider 2WW referral if ...", "referrals made at the time of UTI will be rejected") and _RE_AUTO_FILED_PREFIX (matches "<HH:MM> - Surgery: Auto-filed"). _classify_text_encounters drops text_generic referral candidates when (_has_boilerplate AND not _has_structural) OR (_is_auto_filed AND not _has_structural). PRISM, rejection, resubmission, and Read-code subtypes are unaffected. Verified by tests/test_patient_4842019832_patterns.py::TestPatternIBoilerplateLabGuidance - VT passed 2026-04-18 | R-LEO-AI-199 | VT-LEO-AI-203 |
| DI-LEO-AI-212 | Extended narrative-reference guard (Pattern J, UN-LEO-AI-005, UN-LEO-AI-006): anchor_detector.py extends _RE_NARRATIVE_REFERRAL_REFERENCE with two new alternation groups: past-tense seen-narrative ('(was|were|has been|had been) seen (by|under|in|at) ... (2WW|TWW|fast.?track|clinic|specialist)' and 'seen (by|under|in|at) ... (2WW|TWW|fast.?track)') and inter-clinician clarification ('(write|writing|wrote|letter|email|message) (to|back to) (ENT|consultant|specialist|hospital|registrar|clinic)'). The Pattern C+D suppression hook then drops text_generic referrals on follow-up encounters whose only referral-shaped tokens are these narrative shapes. Verified by tests/test_patient_4842019832_patterns.py::TestPatternJWasSeenNarrativeGuard - VT passed 2026-04-18 | R-LEO-AI-200 | VT-LEO-AI-204 |

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| Risk | R-LEO-AI-186 | mitigated | False-positive 2WW pathway from non-cancer PRISM proforma encounters (cancer-context guard + admin-amendment qualifier filter) |
| Verification Test | VT-LEO-AI-190 | passed | PRISM cancer-context guard (sexual health / MSK / mental-health / IBD PRISM emit no referral anchor; cancer PRISM still emits prism subtype) + Marked-in-Error admin-amendment filter |
| Design Input | DI-LEO-AI-200 | approved | Strict NSS classification: only explicit NSS surface forms or canonical NSS SNOMED/Read codes classify cancer_type='non_site_specific'; generic cancer text without a site returns 'unknown' so NSS-absorption (DI-LEO-AI-196) folds it into a typed pathway |
| Design Output | DO-LEO-AI-198 | approved | _NSS_PHRASE_RE regex + tightened _SITE_MAP / _extract_condition_key in services/analysis_worker/app/analyzers/episode_builder/_site_resolution.py + Read-code map corrections (XaMeD/XaMeL/XaPyS) in libs/domains/code_inventories.py |
| Risk | R-LEO-AI-190 | mitigated | Phantom or false-positive non-site-specific cancer pathway misclassification (mitigated by strict NSS rule, Read-code corrections, NSS-absorption coordination) |
| Verification Test | VT-LEO-AI-193 | passed | Strict NSS classification: 9 positive cases + 9 negative/type-clash cases (fasting, PRISM, generic carcinoma, children's tumour codes); live cohort verifies zero phantom NSS episodes |
| Design Input | DI-LEO-AI-201 | approved | Tighten _RE_FIRST_SEEN to require attestation verb within proximity of clinic token; suppress phantom first_seen anchors from narrative 2WW mentions |
| Design Output | DO-LEO-AI-199 | approved | _RE_FIRST_SEEN attestation guard implementation in services/analysis_worker/app/analyzers/anchor_detector.py |
| Risk | R-LEO-AI-191 | mitigated | Open referral falsely promoted to 'completed' via phantom first_seen anchor from narrative discussion |
| Verification Test | VT-LEO-AI-194 | passed | First-seen attestation guard: positive (clinic seen / attended) + negative (narrative discussion / awaiting / considering) cases |
| Design Input | DI-LEO-AI-202 | approved | Narrative-reference referral guard suppressing text_generic referral when text is commentary about past referral with no structural referral evidence |
| Design Output | DO-LEO-AI-200 | approved | _RE_NARRATIVE_REFERRAL_REFERENCE + _RE_STRUCTURAL_REFERRAL + _classify_text_encounters suppression logic in services/analysis_worker/app/analyzers/anchor_detector.py |
| Risk | R-LEO-AI-192 | mitigated | Inflated referral count from narrative commentary about past referrals creating phantom text_generic referrals |
| Verification Test | VT-LEO-AI-195 | passed | Narrative-reference referral guard: DNA / awaiting result narratives suppressed; structural referral codes still emit referral |
| Design Input | DI-LEO-AI-203 | approved | PMHx history-of-cancer detection: malignancy under recognised Past medical history section header treated as historical context |
| Design Output | DO-LEO-AI-201 | approved | _PMHX_SECTION_RX + _malignancy_under_pmhx_section + text_contains_history_of_cancer wiring in libs/domains/code_inventories.py |
| Risk | R-LEO-AI-193 | mitigated | Open cancer pathway falsely closed as benign because PMHx malignancy line is misread as new diagnosis |
| Verification Test | VT-LEO-AI-196 | passed | PMHx history-of-cancer detection: PMHx-section malignancy treated as history; current-encounter malignancy still surfaced |
| Design Input | DI-LEO-AI-204 | approved | care_obstruction milestone covering DNA+reason, refusal of named investigation, safeguarding, hospital retraction, family aggression; HITL escalation on parent episode |
| Design Output | DO-LEO-AI-202 | approved | _RE_CARE_OBSTRUCTION + 9-tuple _AnchorBuckets + _care_obstruction_link_anchors / _care_obstruction_hitl wiring in anchor_detector.py + episode_builder/_builder.py |
| Risk | R-LEO-AI-194 | mitigated | Blocked / refused / safeguarding-flagged pathways swallowed by stale-close pass without HITL review |
| Verification Test | VT-LEO-AI-198 | passed | care_obstruction emission + HITL escalation on parent EpisodeOfCare |
| Design Input | DI-LEO-AI-205 | approved | rejected_no_followup status engine surfacing referrals rejected with no follow-up referral within 90 days as a discrete HITL status |
| Design Output | DO-LEO-AI-203 | approved | _has_followup_referral + _rejection_followup_status + _determine_episode_status integration in services/analysis_worker/app/analyzers/episode_builder/_status.py |
| Risk | R-LEO-AI-195 | mitigated | Rejected referral with no follow-up silently aged out by stale-close instead of being surfaced for HITL action |
| Verification Test | VT-LEO-AI-197 | passed | rejected_no_followup status: rejection without follow-up returns rejected_no_followup; rejection followed by new referral remains in_progress |
| Design Input | DI-LEO-AI-206 | approved | Exclusive encounter claiming via BuildContext.claimed_encounters + _filter_unclaimed_link_groups enforcing single-claim invariant per encounter / per non-referral milestone |
| Design Output | DO-LEO-AI-204 | approved | BuildContext.claimed_encounters in _types.py + _filter_unclaimed_link_groups + integration into _build_open_episode / _build_closed_episode in _builder.py |
| Risk | R-LEO-AI-196 | mitigated | Same encounter claimed by multiple EpisodeOfCare nodes causing duplicate-resolver churn and inflated milestone counts |
| Verification Test | VT-LEO-AI-199 | passed | Exclusive encounter claiming: non-referral milestone encounter claimed once; referral encounter remains protected; empty groups dropped |
| Design Input | DI-LEO-AI-210 | approved | Family-history-of-cancer guard (Pattern H): suppress text_generic referrals when only FH context is present and no structural artefact exists; treat FH mentions as historical context for the diagnosis path |
| Design Output | DO-LEO-AI-207 | approved | _RE_FAMILY_HISTORY_CANCER + _FAMILY_HISTORY_CANCER_RX + text_contains_family_history_of_cancer + history-of-cancer wiring + suppression hook in _classify_text_encounters (anchor_detector.py + libs/domains/code_inventories.py) |
| Risk | R-LEO-AI-198 | mitigated | Family-history mention misread as a patient cancer event, opening phantom pathways for unaffected patients (e.g. PSA + FH prostate ca) |
| Verification Test | VT-LEO-AI-202 | passed | Family-history guard: 5 positive FH-shape detections + false-positive guard (genuine patient diagnosis still recognised) + end-to-end suppression on PSA + FH encounter |
| Design Input | DI-LEO-AI-211 | approved | Boilerplate lab-report referral guidance suppression (Pattern I): drop text_generic referrals when only conditional disclaimer wording is present on auto-filed result drops |
| Design Output | DO-LEO-AI-208 | approved | _RE_BOILERPLATE_REFERRAL_GUIDANCE + _RE_AUTO_FILED_PREFIX + suppression hook in _classify_text_encounters (anchor_detector.py) |
| Risk | R-LEO-AI-199 | mitigated | Auto-filed lab-report disclaimer text containing conditional referral guidance is mis-classified as an actual referral, opening phantom pathways |
| Verification Test | VT-LEO-AI-203 | passed | Boilerplate lab-guidance suppression: positive boilerplate / Auto-filed detection + false-positive guard (active referral instruction still recognised) + end-to-end suppression on auto-filed PSA encounter + structural referral keep-list cross-check |
| Design Input | DI-LEO-AI-212 | approved | Extended narrative-reference guard (Pattern J): _RE_NARRATIVE_REFERRAL_REFERENCE additionally matches past-tense seen-narrative and inter-clinician clarification text |
| Design Output | DO-LEO-AI-209 | approved | Extended _RE_NARRATIVE_REFERRAL_REFERENCE alternations covering was-seen and write-to-clinician shapes (anchor_detector.py) |
| Risk | R-LEO-AI-200 | mitigated | Past-tense seen-narrative or inter-clinician clarification text is mis-classified as a new referral, opening phantom unknown-cancer episodes |
| Verification Test | VT-LEO-AI-204 | passed | Extended narrative-reference guard: 4 positive narrative shapes + structural keep-list cross-check + end-to-end suppression on patient 4842019832 follow-up encounter |
| Design Input | DI-LEO-AI-215 | approved | Pattern K: hard problem-list diagnosis evidence (malignancy Read code OR malignancy term on a Major:/Problem: line OR active-cancer-care code) overrides the DI-LEO-AI-145 same-encounter referral gate so confirmed-cancer additions like "Major: Invasive carcinoma of breast (Ya0ln) (New Episode)" still fire diagnosis_confirmed when the same encounter raises the 2WW |
| Design Output | DO-LEO-AI-212 | draft | find_malignancy_code_in_problem_line strict helper in libs/domains/code_inventories.py + _has_hard_dx_evidence override gate inside _classify_text_encounters (anchor_detector.py) |
| Risk | R-LEO-AI-202 | mitigated | Confirmed cancer diagnosis silently dropped when GP records the diagnosis on the problem list at the same encounter as the 2WW referral (106 completed cancer episodes have no diagnosis_date in the cohort baseline) |
| Verification Test | VT-LEO-AI-207 | passed | Pattern K: same-encounter referral + Major:/Problem: malignancy code emits diagnosis; active-care code overrides; DI-LEO-AI-145 trap preserved on bare suspected-cancer text; non-referral diagnosis path unchanged |
| Design Input | DI-LEO-AI-216 | approved | Pattern L: extend _RE_NARRATIVE_REFERRAL_REFERENCE with five retrospective self-narration shapes (referred by me/us/GP/Dr|Mr|Mrs|Ms|Miss; I/we referred; GP referred; referred (on) 2WW earlier/last/previously/back/in <Month|Year>; previously referred) so cancer-care-review notes that narrate the original referral do not open phantom EpisodeOfCare nodes |
| Design Output | DO-LEO-AI-213 | draft | _RE_NARRATIVE_REFERRAL_REFERENCE alternation extension in services/analysis_worker/app/analyzers/anchor_detector.py |
| Risk | R-LEO-AI-203 | mitigated | Self-narration of a prior referral inside a follow-up note opens a fresh phantom EpisodeOfCare and fragments the patient pathway (patient 4802892365 cancer-care-review created phantom episode 47c987c92e50e545 six months after the real referral) |
| Verification Test | VT-LEO-AI-208 | passed | Pattern L: 5 narrative shapes match + structural fresh referral still fires (no over-suppression) + end-to-end suppression on patient 4802892365 cancer-care-review encounter |
| Design Input | DI-LEO-AI-217 | approved | Pattern M: expand CANCER_TREATMENT_PROCEDURE_CODES with 17 definitive cancer treatment / staging Read codes (breast: XacLJ, XacLK, X40EC, 7H601, XaF83; bowel: X20Y4, XaFB2, XaCvE, XaZVW, 77132; prostate: Y3c24; thyroid: Xa8OS, 71102; chemo/radio: 8BAD0, 8BAD1, ZV58A) so treatment_started fires when these codes appear in a post-referral encounter |
| Design Output | DO-LEO-AI-214 | draft | CANCER_TREATMENT_PROCEDURE_CODES expansion in libs/domains/code_inventories.py (data-only; no detector logic change) |
| Risk | R-LEO-AI-204 | mitigated | Cancer treatment milestone silently absent because surgery Read code (mastectomy, prostatectomy, hemicolectomy, etc.) is missing from CANCER_TREATMENT_PROCEDURE_CODES (5 breast-specific encounters and 106 completed cancer episodes with no treatment_started milestone in the cohort baseline) |
| Verification Test | VT-LEO-AI-209 | passed | Pattern M: 17-code inventory membership + legacy preservation + helper resolves XacLJ + end-to-end treatment_started emission on patient 4802892365 mastectomy and a sibling anterior-resection case |
| Design Input | DI-LEO-AI-225 | approved | Pattern N5: off-pathway non-cancer Problem-header guard. New helper encounter_problem_is_off_pathway() in libs/domains/code_inventories.py (regexes _PROBLEM_HEADER_RX, _PROBLEM_HEADER_CANCER_TOKEN_RX, _OFF_PATHWAY_PROBLEM_RX). The Pattern G care_obstruction emission gate in anchor_detector.py is tightened to AND on `not encounter_problem_is_off_pathway(text)` so that routine off-pathway primary-care encounters (foreign travel, vaccination, repeat / acute / new prescription, medication review, hot flushes, sick note, MED3, fit note, failed encounter, telephone consultation, administration, summary care record) with incidental cancer mentions never emit a phantom care_obstruction. Guard is inert when no Problem: header is present (clinic letters, document_transfer rows). Inert when any Problem header carries a cancer / pathway token (cancer/carcinoma/malignancy/tumour/melanoma/lymphoma/leukaemia/sarcoma/2WW/fast-track/oncology/chemo/radio/biopsy/mastectomy/lumpectomy/MDT/cancer-site words). NOTE: re-instated at fresh ID DI-LEO-AI-225 because the original placeholder DI-LEO-AI-219 was overwritten by gold-editor (UN-LEO-AI-088) artefacts in commit 2067a5f. |
| Design Output | DO-LEO-AI-222 | approved | encounter_problem_is_off_pathway() helper + supporting regexes in libs/domains/code_inventories.py; care_obstruction emission gate update in services/analysis_worker/app/analyzers/anchor_detector.py; verification cases in tests/test_pattern_n5_off_pathway_guard.py. (Re-instated at fresh ID DO-LEO-AI-222; original DO-LEO-AI-216 was overwritten by gold-editor artefacts in commit 2067a5f.) |
| Risk | R-LEO-AI-209 | mitigated | Routine off-pathway primary-care encounter (foreign travel, vaccination, repeat prescription, sick note, hot flushes) with an incidental cancer mention emits a phantom care_obstruction milestone on the patient's cancer EpisodeOfCare. Patient 4802892365 2025-07-01 MMR / Mexico travel-vaccine encounter matched _RE_CARE_OBSTRUCTION on `unable to attend` and emitted a phantom obstruction on the breast pathway. (Re-instated at fresh ID R-LEO-AI-209; original R-LEO-AI-206 was overwritten by gold-editor artefacts in commit 2067a5f.) |
| Verification Test | VT-LEO-AI-217 | passed | Pattern N5: 14/14 cases pass via `python -m pytest tests/test_pattern_n5_off_pathway_guard.py -v` (10 helper unit cases covering travel-vaccine / repeat-medication / hot-flushes / telephone-consultation off-pathway, suspected-cancer / cancer-care-review / 2WW NOT-off-pathway, no-Problem-header inertness, mixed-headers cancer override, unknown-subject conservative default; 4 integration cases through _classify_text_encounters covering canonical 4802892365 2025-07-01 zero-emission, repeat-medication zero-emission, genuine cancer-pathway refusal still fires, clinic-letter without Problem header still fires). 231 passed across the regression sweep over the existing anchor-detector and pattern test suites. (Re-instated at fresh ID VT-LEO-AI-217; original VT-LEO-AI-211 was overwritten by gold-editor artefacts in commit 2067a5f.) |
| Design Input | DI-LEO-AI-224 | approved | Pattern N3: structured-form-field restatement guard. New helpers `_extract_form_field_dates()` and `encounter_restates_past_event(text, encounter_date, lookback_days=14)` in `libs/domains/code_inventories.py` parse five date formats (DD MMM YYYY, DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, ISO YYYY-MM-DD) on Field-shape lines (lines containing `:`). The Pattern C+D text_generic referral suppression block in `anchor_detector.py` is extended with the new restatement flag (overrides structural-evidence override because Field-shape past-date lines are by definition restatements). The first_seen emission gate (including the specialist-clinic Read code branch) is wrapped with the same guard so XaPyQ `Seen in 2WW Clinic?:` proforma updates do not double-fire first_seen weeks after the real clinic visit. Inert for prose without Field shape (Pattern L / DI-LEO-AI-216 owns narrative-referral suppression). |
| Design Output | DO-LEO-AI-221 | approved | `_extract_form_field_dates()` + `encounter_restates_past_event()` helpers and date regexes in `libs/domains/code_inventories.py`; suppression-flag wiring on the text_generic referral block and first_seen emission wrap in `services/analysis_worker/app/analyzers/anchor_detector.py`; verification cases in `tests/test_pattern_n3_form_field_restatement_guard.py`. |
| Risk | R-LEO-AI-208 | mitigated | Receptionist-driven 2WW proforma update on a date later than the event the field describes creates duplicate referral / first_seen milestones on the patient's cancer EpisodeOfCare. Patient 4802892365 2025-05-13 (`Date of First outpatient appointment: 07 Apr 2025`) emitted a fresh text_generic referral; 2025-06-10 (`Seen in 2WW Clinic?: ... 28 Apr 2025`) emitted a duplicate first_seen via the XaPyQ specialist-clinic Read code. Inflates time-to-first-seen and referral-count KPIs and degrades reviewer trust. |
| Verification Test | VT-LEO-AI-216 | passed | Pattern N3: 21/21 cases pass via `python -m pytest tests/test_pattern_n3_form_field_restatement_guard.py -v` (8 extractor unit cases covering all five date formats, colon-required shape, invalid-date rejection, multi-date lines; 8 guard-predicate cases covering the canonical 4802892365 2025-05-13 and 2025-06-10 restatements, the 14-day lookback edge, prose-without-colon, empty input, malformed encounter date, and the lookback_days parameter; 5 integration cases through _classify_text_encounters covering zero-referral on the canonical 2025-05-13 row, zero-first_seen on the canonical 2025-06-10 row, and three no-over-suppression sanity cases). 231 passed across the regression sweep over the existing anchor-detector and pattern test suites. |
| Design Input | DI-LEO-AI-401 | approved | Pattern N1: no-anchor episode rejection. New helper `encounter_diagnosis_is_narrative_restatement(text)` in `libs/domains/code_inventories.py` (regexes `_SICK_NOTE_RX` for eMED3 / MED3 / fit note / "not fit for work" / "unfit for work" / "fitness for work" / "sickness certificate"; `_KNOWN_CANCER_RESTATEMENT_RX` for "known X cancer", "history of X carcinoma", "PMHx history of X ca", "previously diagnosed with X cancer", "post mastectomy / prostatectomy / chemotherapy / radiotherapy recovery / follow-up / review", "recovering from X cancer", "referred by me ... earlier this year, confirmed X cancer"; site vocabulary mirrors `_PROBLEM_HEADER_CANCER_TOKEN_RX`). The diagnosis_confirmed emission path in `anchor_detector.py` tags anchors with `is_narrative_restatement: True` when the helper returns True. `_build_diagnosis_led_groups` in `services/analysis_worker/app/analyzers/episode_builder/_grouping.py` rejects floating diagnosis-led groups whose anchors are ALL tagged. Inert when at least one anchor is untagged or when the group has claimed a referral (referral-attached groups always materialise). |
| Design Output | DO-LEO-AI-401 | approved | `encounter_diagnosis_is_narrative_restatement()` helper plus `_SICK_NOTE_RX` and `_KNOWN_CANCER_RESTATEMENT_RX` in `libs/domains/code_inventories.py`; diagnosis_confirmed tagging in `services/analysis_worker/app/analyzers/anchor_detector.py`; floating-group rejection filter in `services/analysis_worker/app/analyzers/episode_builder/_grouping.py`; verification cases in `tests/test_pattern_n1_no_anchor_episode_rejection.py`. |
| Risk | R-LEO-AI-401 | mitigated | A routine sick note (eMED3 / fit note) or "known X cancer" narrative restates an existing cancer diagnosis on an encounter with no referral within the diagnosis-claim lookback window, causing the episode builder to materialise a phantom EpisodeOfCare built entirely from restatement text. Patient 4802892365 phantom episode 862a306e1ee82616 was built from the 2025-09-24 "Cancer care review and general catch up ... referred by me on 2ww earlier this year, confirmed breast cancer ... post mastectomy recovery review" encounter (Pattern K firing on the problem-list malignancy code) and the 2025-12-06 eMED3 sick-note "not fit for work ... known breast ca" -- both pure restatements of the lobular carcinoma already recorded under episode 1ecfb55618c2a6d2. |
| Verification Test | VT-LEO-AI-401 | passed | Pattern N1: 24/25 cases pass (1 conditionally skipped) via `python -m pytest tests/test_pattern_n1_no_anchor_episode_rejection.py -v` (17 helper unit cases covering 5 sick-note shapes, 7 known-cancer narrative shapes, 5 INERT cases including fresh diagnosis, 2WW referral, routine BP check, pharmacist failed-encounter alone; 3 integration cases through `_classify_text_encounters` covering the canonical 4802892365 2025-09-24 cancer-care-review tagging, fresh diagnosis NOT tagged, and the conditional sick-note tagging case; 5 integration cases through `_build_diagnosis_led_groups` covering all-restatement floating-group rejection, mixed-anchor preservation, no-restatement preservation, referral-attached preservation, and empty inputs). 152 passed across the regression sweep over N1, N3, N5, episode_builder, episode_duplicate_resolver, first_seen_milestone, open_episode_diagnosis_rescue. |
| Design Input | DI-LEO-AI-402 | approved | Pattern N4: cancer-care-review restatement guard. New helpers `encounter_has_new_episode_marker(text)` (regex `_NEW_EPISODE_MARKER_RX` for "(New Episode)" / "newly diagnosed" / "new diagnosis of" / "diagnosis confirmed today" / "first presentation of" / "new presentation of") and `encounter_is_cancer_care_review_restatement(text)` (regex `_CANCER_CARE_REVIEW_RX` for "cancer (care) review" plus the existing N1 `_KNOWN_CANCER_RESTATEMENT_RX`, gated INERT by the new-episode-marker exception) added to `libs/domains/code_inventories.py`. The `_classify_text_encounters` `has_cancer and has_confirmed` branch in `services/analysis_worker/app/analyzers/anchor_detector.py` gains a `_dx_cancer_review_blocked` guard that suppresses the diagnosis_confirmed anchor entirely when the helper fires. N4 sits one layer deeper than N1 (which only filters floating restatement-only groups) -- it stops phantom diagnosis_confirmed milestones from polluting the timeline of REAL referral-anchored episodes (e.g. patient 4802892365 episode 1ecfb55618c2a6d2's 2025-09-24 phantom). The sick-note shape is deliberately NOT a trigger -- N1's floating-group filter remains the safety net. |
| Design Output | DO-LEO-AI-402 | approved | `encounter_has_new_episode_marker()`, `encounter_is_cancer_care_review_restatement()` helpers plus `_CANCER_CARE_REVIEW_RX` and `_NEW_EPISODE_MARKER_RX` in `libs/domains/code_inventories.py`; `_dx_cancer_review_blocked` guard wired into the `has_cancer and has_confirmed` emission branch in `services/analysis_worker/app/analyzers/anchor_detector.py`; verification cases in `tests/test_pattern_n4_cancer_care_review_restatement_guard.py`. |
| Risk | R-LEO-AI-402 | mitigated | A routine annual cancer-care-review encounter restates an existing cancer diagnosis on a patient with a real referral-anchored cancer episode, causing Pattern K paths to emit a phantom diagnosis_confirmed anchor that attaches to the real episode timeline -- e.g. patient 4802892365's real episode 1ecfb55618c2a6d2 received a phantom 2025-09-24 diagnosis_confirmed milestone five months after the real 2025-05-19 fresh diagnosis and two months after treatment_started. Causes reviewer disengagement, incorrect pathway-stage classification, inflated diagnosis-count analytics. N1 cannot help here because the restatement attaches to a real referral-anchored episode rather than forming a floating group. |
| Verification Test | VT-LEO-AI-402 | passed | Pattern N4: 33/33 cases pass via `python -m pytest tests/test_pattern_n4_cancer_care_review_restatement_guard.py -v` (10 cancer-care-review-restatement helper unit cases; 5 inert helper cases including 2WW referral and sick-note-alone; 3 new-episode-marker exception cases; 5 `encounter_has_new_episode_marker` unit cases; 4 anchor-detector suppression integration cases including the canonical 4802892365 2025-09-24 phantom; 5 fresh-diagnosis-NOT-suppressed safety cases including the new-episode-marker exception, the newly-diagnosed phrase exception, the 2WW referral and the routine repeat prescription; 1 N4-precedence-over-N1 case). 203 passed across the broad regression sweep over N1, N3, N4, N5, episode_builder, episode_duplicate_resolver, first_seen_milestone, open_episode_diagnosis_rescue, and the patient-4802892365 pattern tests. Cohort wipe-and-rebuild confirms total EpisodeOfCare 248 -> 244 (delta -4) and patient 4802892365's phantom 2025-09-24 diagnosis_confirmed eliminated. |

---

### 3.xx Confidence-Gated TrainingCandidate Auto-Prune (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-083 | superseded | Reduce HITL backlog by auto-pruning training candidates that cannot produce defensible SNOMED codes. Superseded by UN-LEO-AI-085 (AI first-pass) which replaces "delete the unloved" with "pre-code what we can, delete what we can't, leave the rest for review". Endpoints, dialog and CLI from the prune service remain in place but are no longer the recommended reviewer entry point. |
| Design Input | DI-LEO-AI-196 | approved | candidate_prune service + /candidates/prune/preview + /candidates/prune/execute endpoints (verdict ladder keep/delete/review; TOCTOU re-check on execute; admin-only) |
| Design Input | DI-LEO-AI-197 | approved | CandidatePruneDialog + ToolbarAction id='auto-prune' on Candidates tab (preview-then-confirm contract; explicit acknowledge checkbox; loading guard on close) |
| Design Output | DO-LEO-AI-195 | draft | services/api/app/services/candidate_prune.py (PruneParams, CandidateAssessment, assess_candidates, execute_prune, summarise) + 2 routes in services/api/app/routers/training.py + scripts/prune_low_confidence_candidates.py CLI |
| Design Output | DO-LEO-AI-196 | draft | services/ui/src/components/gold-dataset/CandidatePruneDialog.tsx + GoldDatasetPanel.tsx ToolbarAction wiring |
| Risk | R-LEO-AI-187 | mitigated | Auto-prune deletes a TrainingCandidate that the model actually needed to learn from (mitigated by verdict ladder, three safety rails, two-phase preview/execute) |
| Risk | R-LEO-AI-188 | mitigated | Auto-prune masks systemic LLM extractor regression (mitigated by grouped preview surfacing rejection-reason distribution + per-call audit log) |
| Verification Test | VT-LEO-AI-182 | passed | candidate_prune verdict ladder + safety rails + endpoints (20/20 pytest cases pass: 14 service + 6 endpoint) |
| Verification Test | VT-LEO-AI-183 | passed | CandidatePruneDialog static-source jest VT (6/6 cases pass: ToolbarAction wired, default 0.7/0.92/0.66 floors, destructive button gated, explicit 'permanently delete' label, loading-close guard, file size <=500 LOC) |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-196 | candidate_prune service + endpoints (UN-LEO-AI-083): services/api/app/services/candidate_prune.py implements PruneParams (default floors 0.7/0.92/0.66 mirroring R-LEO-AI-180 validator), CandidateAssessment dataclass, assess_candidates (ThreadPoolExecutor max 8 workers; verdict ladder: zero-entity/blocked-assertion/manual-seed -> review; all-rejected -> delete; all-accepted -> keep; mixed -> review), execute_prune (TOCTOU re-check via GET_TRAINING_CANDIDATE_BY_ID; never deletes status='completed'; reports cascade counts), summarise. Two FastAPI routes added to services/api/app/routers/training.py: POST /candidates/prune/preview (read-only) and POST /candidates/prune/execute (explicit candidate_ids only; 400 on empty list). Both depend on require_admin and emit INFO audit log lines with actor email + per-verdict counts. CLI mirror in scripts/prune_low_confidence_candidates.py (defaults to dry-run; --apply required to delete; writes data/audit/candidate_prune_<UTC>.{preview.jsonl,summary.json,execute.json}). Verified: 20/20 pytest cases pass in tests/test_candidate_prune.py + services/api/tests/test_candidate_prune_endpoint.py (DO-LEO-AI-195) - VT passed 2026-04-17 | R-LEO-AI-187, R-LEO-AI-188 | VT-LEO-AI-182 |
| DI-LEO-AI-197 | CandidatePruneDialog + ToolbarAction (UN-LEO-AI-083): services/ui/src/components/gold-dataset/CandidatePruneDialog.tsx (471 LOC) wraps the preview-then-execute flow. Three numeric inputs (min_surface_match=0.7, semantic_vector_floor=0.92, semantic_min_surface=0.66), status multi-select default [pending,processing,failed], limit cap 500. Preview table groups candidates by verdict with rejection-reason chips; destructive Delete button disabled until previewLoaded && deleteCount > 0 && confirmAcknowledged. Confirmation FormControlLabel uses literal 'permanently delete' phrase. handleClose is a no-op while loading is true. GoldDatasetPanel.tsx registers id='auto-prune' label='Auto-prune low confidence' on the candidates tab next to 'Deduplicate similar', mounts <CandidatePruneDialog/> with onPruned reloading list+stats. Verified: 6/6 jest cases pass in services/ui/src/__tests__/candidate-prune-dialog.test.tsx (DO-LEO-AI-196) - VT passed 2026-04-17 | R-LEO-AI-187 | VT-LEO-AI-183 |

---

### 3.xx Dry-run NER errors to gold-label correction (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-084 | approved | One-click conversion of dry-run NER errors into gold training data (per-row 'Open in gold editor' on /admin/console -> Evaluate -> 2b dry-run; deep link to GoldLabelDetailDialog; idempotent on candidate_id) |
| Design Input | DI-LEO-AI-198 | approved | POST /api/training/candidates/from-dry-run: server-side deidentify_text(ner=True) before hashing; candidate_id = sha256(deidentified text); upsert TrainingCandidate (source='dry_run_correction'); ensure draft GoldLabel; idempotent |
| Design Input | DI-LEO-AI-199 | approved | EvaluateStage 'Open in gold editor' IconButton on every dry-run row (NER-only and full-pipeline) + GoldDatasetPanel useSearchParams deep-link handler (?labelId, from=dry_run -> candidates tab) + Suspense wrapper on /gold-dataset/page |
| Design Output | DO-LEO-AI-197 | draft | services/api/app/routers/training.py (candidate_from_dry_run, _sanitise_dry_run_entities) + services/ui/src/components/console/EvaluateStage.tsx (openInGoldEditor + IconButton in both row blocks) + services/ui/src/components/gold-dataset/GoldDatasetPanel.tsx (deep-link effect) + services/ui/src/app/gold-dataset/page.tsx (Suspense) |
| Risk | R-LEO-AI-189 | mitigated | PHI leakage into gold dataset via dry-run correction path (mitigated by server-side de-identification before hashing/persisting; sha256 hash matches existing pipeline candidate_id contract; source='dry_run_correction' lets audits segment rows; truncated source_hint) |
| Verification Test | VT-LEO-AI-191 | passed | candidate_from_dry_run pytest VT (6/6 cases pass: deidentify-before-hash, source/status pinning, entity re-anchoring, idempotency, 400 on empty input, source_hint truncation) |
| Verification Test | VT-LEO-AI-192 | passed | EvaluateStage + GoldDatasetPanel + page Suspense static-source jest VT (8/8 cases pass: imports, IconButton in both row blocks, POST + deep-link push, disabled guards, useSearchParams plumbing, deep-link effect with router.replace clear, candidates tab on dry_run, Suspense wrapper) |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-198 | POST /api/training/candidates/from-dry-run (UN-LEO-AI-084): de-identifies encounter text via libs.utils.deidentify.deidentify_text(text, ner=True) before either hashing it or persisting it; candidate_id = sha256(deidentified_text) matching libs/pipeline_graph/subgraphs/persist.py::_candidate_id contract so dry-run-corrected and pipeline-produced candidates collapse onto the same node; upserts TrainingCandidate with source='dry_run_correction', status='pending', schema_version='v4'; entities are re-anchored onto the de-identified text via libs.ner.span_finder.find_span and any unmappable ones dropped (counted in dropped_entity_count); ensures a draft GoldLabel via the same code path as POST /training/gold-labels/by-candidate/{id}/ensure; idempotent on second call (no duplicate UPSERT). Verified by VT-LEO-AI-191 (DO-LEO-AI-197) | R-LEO-AI-189 | VT-LEO-AI-191 |
| DI-LEO-AI-199 | EvaluateStage 'Open in gold editor' + GoldDataset deep-link (UN-LEO-AI-084): IconButton with aria-label='Open in gold editor' rendered next to the entity-count badge in BOTH the NER-only and the full-pipeline dry-run row blocks of services/ui/src/components/console/EvaluateStage.tsx. openInGoldEditor POSTs {encounter_text, entities, source_hint} to /api/training/candidates/from-dry-run and on success calls router.push(`/admin/gold-dataset?labelId=...&from=dry_run`); disabled while in flight or when row text is empty; failures surface in the existing setError Alert. services/ui/src/components/gold-dataset/GoldDatasetPanel.tsx imports usePathname/useRouter/useSearchParams, switches the active tab to 'candidates' on from=dry_run, resolves labelId via in-memory items first then fetchGoldLabel, opens GoldLabelDetailDialog by setting selectedItem, and clears the query param via router.replace. /gold-dataset/page.tsx wraps GoldDatasetPanel in <Suspense>. Verified by VT-LEO-AI-192 (DO-LEO-AI-197) | R-LEO-AI-189 | VT-LEO-AI-192 |

---

### 3.xx AI first-pass over the candidate to-do list (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-085 | approved | AI first-pass over the non-completed TrainingCandidate backlog: per candidate, run a Haiku entity extractor seeded with BioClinicalBERT few-shot exemplars from the gold pool, run the SNOMED resolver + validator with up to N Haiku alt-search-term retries, and assign one of three verdicts (pre_done -> overwrite entities_json + audit copy + keep in queue; delete -> cascade-delete; review -> leave alone). Callable from the Training Data UI as an admin-gated background job with SSE progress. Never modifies status='completed'. |
| Design Input | DI-LEO-AI-208 | approved | candidate_ai_first_pass service + per-candidate orchestrator: extractor (Haiku + few-shot), per-entity smart coder (validator + Haiku alt-query loop), verdict ladder, writeback (UPSERT_AI_FIRST_PASS_ENTITIES with write-once entities_json_original + TOCTOU re-check), TOCTOU-defended cascade delete. Safety rails for zero-entity, _AUTO_CODE_BLOCKED assertion, manual_gold_seed source. |
| Design Input | DI-LEO-AI-209 | approved | Admin-gated background job with SSE progress: POST /api/training/candidates/ai-first-pass/jobs (queue), GET /jobs/{run_id} (status), GET /jobs/{run_id}/events (SSE candidate.processed -> job.summary). Reviewer UI: AIFirstPassDialog (live by_verdict + by_action tally), CandidateReviewList "AI suggested" row badge, GoldLabelDetailDialog per-entity AI chip + "show original" toggle bound to entities_json_original. |
| Design Output | DO-LEO-AI-205 | draft | services/api/app/services/candidate_ai_first_pass/ (_types, _gold_pool, _extractor, _coder, _verdict, _writeback, _job_runner, __init__) + libs/cypher/training_candidate_queries.py UPSERT_AI_FIRST_PASS_ENTITIES + READ_GOLD_POOL_FOR_FEW_SHOT + GET_TRAINING_CANDIDATE_BY_ID extension + scripts/ai_first_pass.py CLI mirror |
| Design Output | DO-LEO-AI-206 | draft | services/api/app/routers/_training_ai_first_pass.py (queue/status/events endpoints) + services/ui/src/app/api/training/candidates/ai-first-pass/jobs/[runId]/events/route.ts (Next.js SSE proxy) + services/ui/src/components/gold-dataset/AIFirstPassDialog.tsx + GoldDatasetPanel.tsx (toolbar id='ai-first-pass' + dialog mount + GoldLabelDetailDialog AI chip/toggle wiring) + CandidateReviewList.tsx (row badge) |
| Risk | R-LEO-AI-197 | mitigated | AI first-pass overwrites entities_json and corrupts gold-bound labels (mitigated by write-once entities_json_original audit copy, dry-run default in dialog, TOCTOU re-check excluding status='completed', "AI suggested" chip + "show original" toggle on every reviewer surface) |
| Verification Test | VT-LEO-AI-200 | passed | candidate_ai_first_pass pytest VT (extractor fallback, few-shot pool, smart coder retries, verdict ladder, writeback invariants, endpoint admin gating + queue/status/SSE) |
| Verification Test | VT-LEO-AI-201 | passed | AI first-pass reviewer UI static-source jest VT (15/15 cases pass: toolbar id='ai-first-pass', AIFirstPassDialog SSE wiring + dry_run default + close-while-running guard, GoldLabelDetailDialog AI chip + show-original toggle + read-only audit view + reset on candidate change, CandidateReviewList row badge, Candidate/GoldLabel UI type contracts) |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-208 | candidate_ai_first_pass service (UN-LEO-AI-085): services/api/app/services/candidate_ai_first_pass/ implements AIFirstPassParams (default floors 0.7/0.92/0.66, dry_run=False, haiku_tier='small', few_shot_k=5, coder_max_retries=2), ai_extract_entities (Haiku + BioClinicalBERT few-shot exemplars from gold pool; falls back to original entities_json on extractor failure with extractor_error recorded), ai_code_entity (validator + Haiku alt-search-term loop, max_retries enforced, surface_match + score recorded), classify_candidate (verdict ladder: zero-entity / _AUTO_CODE_BLOCKED assertion / manual_gold_seed source -> review; >=1 accepted -> pre_done; >=1 entity & all rejected -> delete), writeback_pre_done (UPSERT_AI_FIRST_PASS_ENTITIES sets entities_json_original write-once, refuses to write status='completed'), execute_delete (TOCTOU re-check via GET_TRAINING_CANDIDATE_BY_ID; never deletes status='completed'; reports cascade counts). CLI mirror in scripts/ai_first_pass.py (always runs dry-run first, --apply required to write back, writes data/audit/ai_first_pass_<UTC>.{preview.jsonl,summary.json,execute.json}). | R-LEO-AI-197 | VT-LEO-AI-200 |
| DI-LEO-AI-209 | AI first-pass background job + reviewer UI (UN-LEO-AI-085): services/api/app/routers/_training_ai_first_pass.py exposes POST /candidates/ai-first-pass/jobs (admin-gated, queues an in-process worker thread, returns run_id), GET /jobs/{run_id} (status), GET /jobs/{run_id}/events (SSE: candidate.processed per row, terminating job.summary). Next.js Route Handler at services/ui/src/app/api/training/candidates/ai-first-pass/jobs/[runId]/events/route.ts proxies the SSE stream straight to the browser (the global middleware proxy drops long-lived connections at ~30s). services/ui/src/components/gold-dataset/AIFirstPassDialog.tsx renders the parameter form with dry_run defaulted to true, the start button, and a live by_verdict + by_action tally driven by EventSource subscription. GoldDatasetPanel.tsx registers id='ai-first-pass' label='AI first-pass' on the candidates tab as the new primary action and mounts the dialog. CandidateReviewList.tsx renders an "AI suggested" row chip when ai_first_pass_run_id is set. GoldLabelDetailDialog (inside GoldDatasetPanel.tsx) shows a per-entity AI chip and a "show original" toggle that flips the entity list to entities_json_original (read-only - no save handlers wired to the original view). The toggle resets to false whenever item.label_id changes. | R-LEO-AI-197 | VT-LEO-AI-201 |

---

### 3.xx Mission Control KPI unit clarity + cohort denominator (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| Design Input | DI-LEO-AI-214 | draft | Mission Control /care/patients KPI strip MUST present audit headline figures in the same unit (patients) as the label and tooltip claim AND surface the cohort denominator so hidden patients are discoverable. GET /mission-control/kpis MUST return both episode counts and patient counts for confirmed_cancer and pathway_closures, plus a "cohort" block with total + 3 excluded buckets (no pathway / missing referral date / outside window) scoped by org/scope only. KPIStrip MUST render the patient count as the headline and the pathway count as a sub-line; tooltips MUST describe the metric as a count of PATIENTS in plain English; a caption (data-testid="kpi-cohort-denominator") MUST appear below the strip when at least one patient is hidden, formatted "Showing <inView> of <total> patients - <hidden> hidden (<reason1>, ...)" |
| Design Output | DO-LEO-AI-211 | draft | services/analytics_api/app/routers/mission_control.py: _kpis_cypher returns confirmed_cancer_patients (DISTINCT p with confirmed_cancer_where) and pathway_closure_patients (DISTINCT p with status IN _CLOSURE_STATUSES) alongside the existing episode aliases; new _cohort_denominator_cypher helper resolves the cohort denominator + 3 excluded buckets, scoped by org/scope only (no cancer_type/closure_reason/reviewed_at predicates); get_mission_control_kpis runs both queries on a single PatientGraphClient and packs a stable "cohort" block (zero-filled when the row is absent). services/ui/src/lib/missionControlApi.ts: MissionKPIs gains confirmed_cancer_patients, pathway_closure_patients, optional cohort: MissionKPICohort. services/ui/src/components/mission-control/KPIStrip.tsx: KPICard subValue prop; patient-headline + "<N> pathways" sub-line on Confirmed cancer and Pathway closures cards; rewritten plain-English tooltips; cohort denominator caption rendered below the strip with reading-age 9-11 builder helper buildCohortDenominatorLine() |
| Risk | R-LEO-AI-201 | mitigated | Mission Control KPI strip presents episode counts under patient-unit labels and hides patients excluded by the date / referral-date filter, leading reviewers to miss real cancers (mitigated by patient-equivalent counts using confirmed_cancer_where to stay aligned with /audit/summary, plain-English tooltips, and an always-visible cohort denominator caption that lists each excluded bucket) |
| Verification Test | VT-LEO-AI-206 | passed | KPI patient-headline + cohort denominator (15/15 cases pass: 9 backend pytest cases including patient-equivalent counts, cohort fields, scope binding, endpoint cohort block + zero-fill on empty; 6 UI jest cases including patient-headline / pathway-sub-line on both cards, cohort caption with breakdown, showing-all variant, missing-cohort guard, helper pluralisation) |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-214 | Mission Control KPI patient counts + cohort denominator (UN-LEO-AI-058): GET /mission-control/kpis exposes confirmed_cancer (DISTINCT ep) AND confirmed_cancer_patients (DISTINCT p) sharing confirmed_cancer_where('ep'), plus pathway_closures (DISTINCT ep) AND pathway_closure_patients (DISTINCT p) sharing _CLOSURE_STATUSES. New top-level "cohort" object returns cohort_total_patients, excluded_total, excluded_no_pathway (no EpisodeOfCare), excluded_missing_referral_date (only NULL-referral-date episodes), excluded_outside_window (only out-of-window referral_date episodes); query is scoped by org/caller scope ONLY, ignoring date/pathway/cancer-type/closure-reason/review filters so the denominator answers "how many patients exist behind the filter". KPIStrip renders the patient count as the headline of Confirmed cancer + Pathway closures, with the pathway count as a sub-line ("<N> pathways"); tooltips rewritten in plain English ("Patients with at least one pathway in the selected period where..."); cohort caption (data-testid="kpi-cohort-denominator") sits below the strip showing "Showing 89 of 107 patients - 18 hidden (8 no pathway, 7 missing referral date, 3 outside the date range)." or "Showing all 107 patients in the cohort." or nothing when kpis.cohort is undefined. Verified: 15/15 cases pass across services/analytics_api/tests/test_mission_control_cohort_kpis.py (DO-LEO-AI-211 backend) and services/ui/src/__tests__/mission-control/KPIStripCohortDenominator.test.tsx (DO-LEO-AI-211 UI) - VT passed 2026-04-18 | R-LEO-AI-201 | VT-LEO-AI-206 |

---

### 3.xx UI shell SSR session bootstrap and cache strategy (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-087 | approved | After signing in I must reach the LEO application immediately and never see a stale loading spinner cached by Cloudflare or the Next.js Full Route Cache. |
| Design Input | DI-LEO-AI-218 | draft | UI root layout SHALL resolve the user's session on the server via fetchInitialSession() and forward it as initialSession to the AuthProvider; the layout segment SHALL declare force-dynamic, revalidate=0, and fetchCache=force-no-store so Next.js never caches the loading shell; /auth/login and /auth/callback route handlers SHALL set Cache-Control: no-store on every response. |
| Design Output | DO-LEO-AI-215 | approved | services/ui/src/lib/serverSession.ts (fetchInitialSession), services/ui/src/app/layout.tsx (force-dynamic + SSR session resolve), services/ui/src/lib/authContext.tsx (initialSession prop), services/ui/src/components/AuthProviderWrapper.tsx (server -> client forwarding), services/ui/src/app/auth/login/route.ts + auth/callback/route.ts (Cache-Control: no-store on every response). |
| Risk | R-LEO-AI-205 | mitigated | Cloudflare cached the build-time prerender of /care/dashboard (cache-control: s-maxage=31536000, x-nextjs-cache: HIT, x-nextjs-prerender: 1) so authenticated users were stuck on a loading spinner. Mitigated by force-dynamic on the root layout, server-side session bootstrap, and no-store on auth route handlers. |
| Verification Test | VT-LEO-AI-210 | passed | 5/5 cases pass via `cd services/ui && npx jest --testPathPatterns "server-session-bootstrap" --no-coverage`: AuthProvider hydrates straight to authenticated/unauthenticated from initialSession, never reports loading; background refetch does not regress; layout.tsx static-source contains force-dynamic + revalidate=0 + fetchInitialSession; auth/login and auth/callback contain Cache-Control: no-store. |
| Design Input | DI-LEO-AI-229 | approved | Every backend service that calls libs/redis_client/session.py::load_session or services/api/app/services/session_store.py::load_session SHALL resolve the same Redis key namespace per environment; the deployed configuration SHALL set SESSION_KEY_NAMESPACE explicitly on every backend container (core-api, analytics-api, fhir-api, terminology-api, training-worker, pipeline-worker, research-worker, model-inference) so namespace resolution is independent of FRONTEND_URL / AUTH_REDIRECT_URI / ENVIRONMENT / APP_ENV / LEO_ENV being set on each service. |
| Design Output | DO-LEO-AI-224 | approved | infra/bicep/modules/container-apps.bicep declares sessionKeyNamespace (derived from frontendUrl host first label) and adds { name: 'SESSION_KEY_NAMESPACE', value: sessionKeyNamespace } to sharedEnv so every backend container app receives the value. Hot-fix az containerapp update --set-env-vars SESSION_KEY_NAMESPACE=leo-ai-audit applied to all 8 backend container apps in leo-ai-dev. Both Python namespace resolvers share identical precedence rules (libs/redis_client/session.py + services/api/app/services/session_store.py). |
| Risk | R-LEO-AI-210 | mitigated | core-api wrote sessions under one Redis namespace (auth:leo-ai-audit:session:<id>) while every downstream service silently looked them up under another (auth:local:session:<id>) because SESSION_KEY_NAMESPACE was not set on those services and FRONTEND_URL did not reach them either. Inter-service auth returned 401 on every /api/proxy/* call, the UI auth interceptor treated each 401 as session expiry, and bounced the user back to /auth/login in a tight loop. Mitigated by explicit SESSION_KEY_NAMESPACE on every backend container in sharedEnv, plus an automated parity test between the two Python namespace resolvers. |
| Verification Test | VT-LEO-AI-217 | passed | 8/8 cases pass via `python3 -m pytest tests/test_session_namespace_parity.py -v`: explicit SESSION_KEY_NAMESPACE wins on both modules; ENVIRONMENT/APP_ENV/LEO_ENV fallback parity (parametrized x3); FRONTEND_URL host first-label parity; scheme-less AUTH_REDIRECT_URI parity; total fallback to "local"; container-apps.bicep static-source check confirms SESSION_KEY_NAMESPACE in sharedEnv bound to sessionKeyNamespace variable. |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-218 | UI shell SSR session bootstrap + cache strategy (UN-LEO-AI-087): root layout exports dynamic="force-dynamic"/revalidate=0/fetchCache="force-no-store" and calls await fetchInitialSession() before passing the resolved Session into AuthProviderWrapper as initialSession. fetchInitialSession (services/ui/src/lib/serverSession.ts) reads the leo_session cookie via next/headers, calls GET ${INTERNAL_API_BASE}/auth/session with cache: 'no-store', and returns Session | null - never throws. AuthProvider initialises status = 'authenticated' / 'unauthenticated' from initialSession on the very first render so consumers never see 'loading'; a background fetchSession() still runs after hydration so cross-tab role/density updates remain visible. /auth/login and /auth/callback route handlers continue to set response.headers.set('Cache-Control', 'no-store') on every redirect. Verified: 5/5 jest cases pass + 14/14 dependent tests stay green. | R-LEO-AI-205 | VT-LEO-AI-210 |
| DI-LEO-AI-229 | Inter-service session namespace consistency (UN-LEO-AI-087): infra/bicep/modules/container-apps.bicep adds sessionKeyNamespace (split(_frontendHostPart, '.')[0]) and injects { name: 'SESSION_KEY_NAMESPACE', value: sessionKeyNamespace } into sharedEnv so every backend container app gets the value uniformly. Both Python namespace resolvers (libs/redis_client/session.py::_detect_session_namespace and services/api/app/services/session_store.py::_detect_session_namespace) follow the same precedence (SESSION_KEY_NAMESPACE > ENVIRONMENT > APP_ENV > LEO_ENV > FRONTEND_URL > AUTH_REDIRECT_URI > "local") and produce identical output for any env-var combination, enforced by tests/test_session_namespace_parity.py (8/8 pass). | R-LEO-AI-210 | VT-LEO-AI-217 |

### UN-LEO-AI-088 -- One editor for live encounter codes and gold training data

| Artefact | ID | Status | Notes |
|----------|----|--------|-------|
| User Need | UN-LEO-AI-088 | approved | Reviewers must be able to edit codes on any encounter (dry-run row, candidate, search hit, live encounter) using one editor that always feeds the model. The dialog must save with surface-appropriate semantics: gold-only for /admin/training and /admin/console; dual save (live :DOCUMENTS + gold mirror) for /care/patients and /care/encounters. PHI must never enter the gold copy. |
| Design Input | DI-LEO-AI-219 | approved | Shared GoldLabelEditorDialog component: stable export from `@/components/gold-editor`, optional saveMode/entitySaver/onAfterSave/headerChrome props with safe defaults, dual-save warning banner gated on saveMode='dual', barrel surfaces dialog + useDualSaveAdapter + four API helpers + shared types. |
| Design Input | DI-LEO-AI-220 | approved | POST /training/gold-labels/from-encounter: server-side de-id + span re-anchoring + idempotent TrainingCandidate/GoldLabel upsert; returns full GoldLabel + baseline_concept_ids + dropped_link_count. |
| Design Input | DI-LEO-AI-221 | approved | POST /patients/.../coded-links/sync-from-gold: optimistic concurrency by concept_id set (HTTP 409 on drift), transactional add/remove/update via PatientGraphWriter, whole-array gold mirror via UPDATE_GOLD_LABEL_ENTITIES. |
| Design Input | DI-LEO-AI-222 | approved | EvaluateStage mounts the shared dialog inline above the dry-run table; from-dry-run returns full GoldLabel; no window.open or router.push. |
| Design Input | DI-LEO-AI-223 | approved | /care/patients EncounterCard mounts the shared dialog with saveMode='dual'. /care/encounters EncounterPreviewDialog now opens as a read-only preview that renders the encounter text from item.text without an API call on open and highlights search-query and match-rationale terms via <mark>; an explicit 'Edit codes' footer button seeds via createGoldLabelFromEncounter and mounts the shared dialog in saveMode='dual' with rationale chips forwarded via headerChrome; seed failures keep the preview open with an inline error. Legacy full-page editor routes (/patients/{id}/encounters/{eid} and /patients/{id}/encounters/view/{eid}) redirect to /care/patients?...; EncounterCodedView component deleted. |
| Design Output | DO-LEO-AI-216 | approved | Shared GoldLabelEditorDialog module: services/ui/src/components/gold-editor/{GoldLabelEditorDialog,index,types,api,useDualSaveAdapter}.tsx + extended GoldDatasetPanel.tsx props (saveMode/entitySaver/onAfterSave/headerChrome). |
| Design Output | DO-LEO-AI-217 | approved | from-encounter endpoint in services/api/app/routers/training.py (EncounterGoldLabelRequest, _ner_label_for_semantic_tag, _sanitise_live_links, gold_label_from_encounter). |
| Design Output | DO-LEO-AI-218 | approved | sync-from-gold endpoint in services/api/app/routers/patients.py (SyncCodedLinksFromGoldRequest, _build_link_payload_from_gold_entity, _list_baseline_concept_ids, sync_coded_links_from_gold). |
| Design Output | DO-LEO-AI-219 | approved | EvaluateStage inline mount: services/ui/src/components/console/EvaluateStage.tsx + extended candidate_from_dry_run response in training.py. |
| Design Output | DO-LEO-AI-220 | approved | /care surfaces consume the shared dialog: EncounterCard.tsx, EncounterTextTab.tsx, EncounterMissionControl.tsx (no longer prefetches coded links for preview), EncounterPreviewDialog.tsx (rewritten as a thin wrapper), legacy /encounters routes replaced with redirect()s, EncounterCodedView.tsx deleted. |
| Risk | R-LEO-AI-206 | mitigated | Reviewer overwrites live encounter codes from the dual-save editor (concurrent pipeline write or peer reviewer). Mitigated by HTTP 409 optimistic concurrency on concept_id set, dual-save warning banner, PatientGraphWriter audit trail. |
| Risk | R-LEO-AI-207 | mitigated | De-identification re-anchoring drops or shifts gold entities, training the model on a corrupted version of the reviewer's correction. Mitigated by server-side dropped_link_count surfaced to the reviewer, whole-array overwrite contract on the gold mirror, and idempotent candidate_id keyed by sha256(de-id text). |
| Verification Test | VT-LEO-AI-211 | passed | 6/6 pytest cases pass for from-encounter: happy path, idempotent upsert, dropped-link accounting, empty-text 400, missing-encounter 404, semantic-tag normalisation fallback. |
| Verification Test | VT-LEO-AI-212 | passed | 6/6 pytest cases pass for sync-from-gold: happy path (add/remove/update + mirror), 409 on baseline drift, empty-entities removal, no-concept-id skip, empty-label-id 422, missing-gold-label 502. |
| Verification Test | VT-LEO-AI-213 | passed | 9/9 jest static-source cases pass for the shared dialog: re-export, plumbing props with safe defaults, persist branch selection, dual-save banner gating, barrel surface, types, API helpers, and useDualSaveAdapter baseline advancement. |
| Verification Test | VT-LEO-AI-214 | passed | 8/8 jest static-source cases pass for the /care/encounters preview wrapper: shared editor imports, read-only preview with no API call on open, on-demand 'Edit codes' button that seeds and mounts saveMode='dual', headerChrome rationale forwarding, search-query + rationale highlight via <mark>, inline seed-failure error that does not hide the encounter text, GoldLabelDetailDialog headerChrome support, and host wiring (searchQuery + onCodingChanged refresh, no coded-links prefetch). |
| Verification Test | VT-LEO-AI-215 | passed | 7/7 jest static-source cases pass for EvaluateStage inline mount: imports, no window.open / no useRouter, aria-label, from-dry-run POST + gold_label seed, shared dialog mount with saveMode='gold', disabled guards, legacy /gold-dataset?labelId deep link still works. |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-219 | Shared GoldLabelEditorDialog component (UN-LEO-AI-088). | R-LEO-AI-206 | VT-LEO-AI-213 |
| DI-LEO-AI-220 | from-encounter seeding endpoint with server-side de-id and span re-anchoring (UN-LEO-AI-088). | R-LEO-AI-206, R-LEO-AI-207 | VT-LEO-AI-211 |
| DI-LEO-AI-221 | sync-from-gold dual-save endpoint with optimistic concurrency (UN-LEO-AI-088). | R-LEO-AI-206, R-LEO-AI-207 | VT-LEO-AI-212 |
| DI-LEO-AI-222 | EvaluateStage inline mount of the shared dialog (UN-LEO-AI-088). | R-LEO-AI-207 | VT-LEO-AI-215 |
| DI-LEO-AI-223 | /care surfaces consume the shared dialog with dual save + headerChrome; legacy editor routes retired (UN-LEO-AI-088). | R-LEO-AI-206, R-LEO-AI-207 | VT-LEO-AI-214 |

---

### UN-LEO-AI-096 -- Consistent encounter row + search experience across surfaces

| Artefact | ID | Status | Notes |
|----------|----|--------|-------|
| User Need | UN-LEO-AI-096 | approved | Reviewers see one consistent encounter row + search experience across `/care/encounters`, the `/care/patients` side drawer, and the `/admin/training` Candidates (dry-run) queue, so muscle memory transfers between surfaces. The dry-run row template (ReviewListCard tone strip + chip taxonomy) is the visual template; the patient-drawer amber `#fde68a` is the highlight token; the dry-run search box (clear button + query-echoing empty state) is the search pattern. |
| Design Input | DI-LEO-AI-514 | approved | `/care/encounters` lifts the dry-run row template and ships a unified `<HighlightedText>` primitive. Each row composes a tone strip (`positive` when `coded_count >= 1`, `danger` on failed batch run, `warning` when matched but no codes, `neutral` otherwise), a `chips` slot (match-type + `{n} coded` + status + up to 4 `match_rationale`), a `meta` line (date, patient, match-strength bar), and an `actions` slot (selection checkbox). The search input ships a clear (X) end-adornment; the empty state echoes the query as `Nothing matches "<q>". Try different words.` A new module `services/ui/src/components/mission-control/HighlightedText.tsx` exports `HighlightedText` + `collectHighlightTerms` and is consumed by `EncounterPreviewDialog`, `EncounterCard`, and the new row template. The retired `highlightSearchMatches` helper in `encounterTextUtils.tsx` is removed. |
| Design Output | DO-LEO-AI-513 | draft | Shared `HighlightedText` primitive + `collectHighlightTerms` helper at `services/ui/src/components/mission-control/HighlightedText.tsx`; rebuilt `EncounterResultsTable.tsx` on `ReviewListCard` with `toneFor()` / `buildEncounterListItem()` / `rowMeta()` / `rowChips()` / `rowActions()` helpers; clear-button end-adornment on `EncounterSearchPanel.tsx`; `EncounterMissionControl.tsx` forwards `searchQuery` to the table and drops the duplicate host-level empty state; `EncounterPreviewDialog.tsx` and `EncounterCard.tsx` updated to import the shared primitive; `encounterTextUtils.tsx` `highlightSearchMatches` retired. |
| Risk | R-LEO-AI-063 | mitigated | Existing mission-control batch-recode safety controls are preserved by the refactor (selection checkbox + batch bar + pagination + live-threshold drift banner all still wired up). |
| Risk | R-LEO-AI-206 | mitigated | Dual-save preview entry point (DI-LEO-AI-223) is unchanged: `EncounterPreviewDialog` still seeds via `createGoldLabelFromEncounter` on the explicit "Edit codes" button. |
| Verification Test | VT-LEO-AI-512 | passed | 8/8 jest static-source cases pass: shared `HighlightedText` contract (#fde68a, MIN_HIGHLIGHT_LEN=3, longest-first, /gi), `EncounterPreviewDialog` and `EncounterCard` import the shared primitive (no inline copy / orphan helper), `EncounterResultsTable` rebuilt on `ReviewListCard` with no MUI Table imports remaining, row title uses `<HighlightedText>` and chips slot composes match-type + coded + status + rationale (sliced 4), checkbox in actions slot stops row click propagation, search box renders clear button when query is non-empty, and empty state echoes the active query. |
| Design Input | DI-LEO-AI-516 | approved | `/care/encounters` lifts the patient-drawer `EncounterTimelineScrubber` (DI-LEO-AI-179) onto the search-results surface via a new `EncounterResultsTimeline` adapter wrapper. The wrapper maps `EncounterListItem[]` to `ScrubberEncounter[]` (renaming `encounter_date` -> `date`, dropping null dates), passes empty `linkedEncounterIds` / `milestones` and null episode bounds, and renders nothing when fewer than 5 dated rows are loaded. The host owns `timelineRange` state, intersects it with the existing `bucketFilter` (BEFORE pagination), wires `activePreview.encounter_id` into both the table row highlight and the histogram active ring, and routes timeline-bar clicks through to the preview dialog. |
| Design Output | DO-LEO-AI-515 | draft | New module `services/ui/src/components/mission-control/EncounterResultsTimeline.tsx` (adapter + min-row gate); `EncounterMissionControl.tsx` gains `timelineRange` state + `handleTimelineRangeChange` + `handleTimelineJump`, intersects the brush window into `filteredRows` alongside `bucketFilter`, resets the brush on every fresh `loadAll()`, and forwards `activePreview.encounter_id ?? null` as both `highlightedEncounterId` and `activeEncounterId`. |
| Risk | R-LEO-AI-174 | mitigated | Reuses the previously verified scrubber primitive unchanged; the brush filter operates on a derived view and never mutates the loaded result set, preserving existing safety semantics around batch operations. |
| Verification Test | VT-LEO-AI-515 | passed | 8/8 jest static-source cases pass under jest 30 + ts-jest in 0.68s: wrapper module contract (default export, scrubber + ScrubberEncounter imports, EMPTY_LINKED / EMPTY_MILESTONES / null episode bounds), adapter `useMemo` mapping `encounter_date` -> `date` with `Number.isFinite` guard, `MIN_DATED_ROWS = 5` early-return null, host `timelineRange` state + reset on load, `filteredRows` intersection with `bucketFilter` and `timelineRange` BEFORE pagination, `highlightedEncounterId` + `activeEncounterId` both fed from `activePreview?.encounter_id ?? null`, `handleTimelineJump` resolves row from `rows.find(...)` and calls `setActivePreview(target)`, and the wrapper passes through `visibleFromMs` / `visibleToMs` / `onVisibleRangeChange` to the scrubber. Wider regression on encounter / mission-control suites: 143 tests across 15 suites, all green. |
| Design Input | DI-LEO-AI-520 | approved | Drawer encounter search (`/care/patients` Encounter text tab) lifts the deterministic part of the `/care/encounters` server query understanding (typo + synonym + match rationale) onto the client via a new shared `encounterRelevance.ts` module. `applyCommonFilters` switches from a bare `text.includes(query)` to `hasAnyExpandedHit(text, expandSearchTerms(query))` so a query for "lump" also surfaces encounters mentioning "mass", "swelling", or "nodule" (the configured synonym group). When the query expands and at least one hit term is found, `EncounterCard` renders an outlined chip row in the card header (max 4 chips, height 20, fontSize 0.65rem, `variant="outlined"`) using the same chip token as the host row, and feeds `matchRationale.hitTerms` into the `<HighlightedText>` primitive so the amber highlighter paints synonyms. |
| Design Output | DO-LEO-AI-520 | draft | New module `services/ui/src/components/mission-control/encounterRelevance.ts` mirrors the server's `_TYPO_MAP` / `_SYNONYM_MAP` / `_normalise_tokens` / `_expand_terms` / `feature_match_rationale` (pure TypeScript, no React imports so future surfaces can reuse). `encounterFilters.ts` delegates to `expandSearchTerms` + `hasAnyExpandedHit`. `EncounterCard.tsx` computes `expandedTerms` + `matchRationale` via `useMemo`, conditionally renders the rationale chip row, and feeds synonym hits into `collectHighlightTerms(search, matchRationale.hitTerms)`. |
| Verification Test | VT-LEO-AI-519 | passed | 8/8 jest static-source cases pass under jest 30 + ts-jest in 0.56s: shared module exports (`expandSearchTerms`, `computeMatchRationale`, `hasAnyExpandedHit`, `MatchRationale`), `TYPO_MAP` / `SYNONYM_MAP` mirroring the server's vocabulary byte-for-byte, typo correction applied BEFORE synonym expansion, blank-query early-return + 12-token / 36-expansion caps, `feature_match_rationale` shape with the 8-hit cap, `applyCommonFilters` rewire (no bare substring path), `EncounterCard` wires expanded terms into the highlighter and renders the rationale chip row capped at 4 with `data-testid="encounter-card-match-rationale-chip"`. Wider regression on encounter / mission-control / drawer suites: 151 tests across 16 suites, all green. |
| Design Input | DI-LEO-AI-523 | approved | The `/admin/training` Candidates, Verified gold, and Synthetic gold sub-tabs (the dry-run review queue) lift the same shared `encounterRelevance.ts` vocabulary onto their `@leo/design-system ReviewListCard` rows. `CandidateReviewList` and `GoldLabelReviewList` accept a `search?: string` prop forwarded by `GoldDatasetPanel` (the panel's `debouncedSearch`), expand it once per render via `expandSearchTerms`, compute a per-row `matchRationale = computeMatchRationale(text, expandedTerms)`, wrap the truncated row title in `<HighlightedText>` (testId `candidate-row-highlight`), and prepend an outlined chip row to the existing `chips:` slot capped at 4 hit terms (testid `candidate-row-match-rationale[-chip]`, height 20, fontSize 0.65rem, `variant="outlined"`). The change is additive: blank queries, no expansion, or no hits all fall back to the prior plain title and chip set. |
| Design Output | DO-LEO-AI-523 | draft | `services/ui/src/components/gold-dataset/CandidateReviewList.tsx` gains a `search?: string` prop, a memoised `expandedTerms`, a `renderRationaleChips` helper, and a `<HighlightedText>` row title; `services/ui/src/components/gold-dataset/GoldLabelReviewList.tsx` mirrors the same wiring for `item.text`; `services/ui/src/components/gold-dataset/GoldDatasetPanel.tsx` passes `search={debouncedSearch}` to both review lists. Reuses the pure-TS `mission-control/encounterRelevance.ts` and `mission-control/HighlightedText.tsx` modules unchanged. |
| Verification Test | VT-LEO-AI-521 | passed | 7/7 jest static-source cases pass under jest 30 + ts-jest in 0.53s: `CandidateReviewList` imports the shared `encounterRelevance` + `HighlightedText` helpers, exposes `search?: string` and memoises `expandedTerms`, computes per-row `matchRationale = computeMatchRationale(candidate.text, expandedTerms)` and wraps the title in `<HighlightedText>` (testId `candidate-row-highlight`), `renderRationaleChips` returns `null` for empty input and otherwise renders a Box with testid `candidate-row-match-rationale` containing `hitTerms.slice(0, 4)` outlined Chips with testid `candidate-row-match-rationale-chip`, `GoldLabelReviewList` mirrors all of the above for `item.text`, and `GoldDatasetPanel` forwards `search={debouncedSearch}` to both review lists. The chip token (variant outlined, height 20, fontSize 0.65rem) matches the drawer's `encounter-card-match-rationale-chip` byte-for-byte. Wider regression sweep across all training-data / gold-dataset / gold-label / encounter / drawer / mission-control suites: 201 tests across 23 suites, all green. |
| Design Input | DI-LEO-AI-526 | approved | Server-side convergence: the dry-run review queue endpoints (`GET /api/training/candidates`, `GET /api/training/gold-labels`) now expand the reviewer's free-text query into the same typo-corrected, synonym-expanded term list used by the host encounter search and pass it as a new `$terms` cypher parameter, so a query for "lump" actually fetches rows that wrote "mass", "swelling", or "nodule" (not just decorates the substring matches). A new `libs/search/term_expansion.py` module holds the single source of truth for `TYPO_MAP` / `SYNONYM_MAP` / `expand_search_terms`, and `services/analytics_api/app/services/encounter_query_understanding.py` is refactored to import them so the host search and the dry-run queue cannot drift apart. Cypher `GET_TRAINING_CANDIDATES_PAGE`, `COUNT_TRAINING_CANDIDATES_PAGE`, `GET_GOLD_LABELS_PAGE`, `COUNT_GOLD_LABELS_PAGE` gain a CASE branch: when `$terms` is non-empty, `ANY(t IN $terms WHERE toLower(text) CONTAINS t)`; otherwise fall back to the legacy `$search` substring filter for backward compatibility. |
| Design Output | DO-LEO-AI-526 | draft | New `libs/search/__init__.py` and `libs/search/term_expansion.py` (TYPO_MAP, SYNONYM_MAP, normalise_tokens, expand_search_terms). `libs/cypher/training_candidate_queries.py` and `libs/cypher/gold_label_queries.py` extend their list/count queries with the `$terms` CASE branch. `services/api/app/routers/training.py::list_training_candidates`, `list_gold_labels`, `_fetch_dedupe_candidates` call `expand_search_terms(search)` and pass identical `terms=` kwargs to both the page and count queries. `services/analytics_api/app/services/encounter_query_understanding.py` re-exports the shared maps and helper. `services/neo4j_mcp/tools/training.py`, `services/api/app/services/candidate_prune.py`, `services/api/app/routers/pipeline.py`, and `services/pipeline_worker/app/main.py` are updated to forward `terms=[]` (or expanded) so the new cypher parameter is always supplied. |
| Verification Test | VT-LEO-AI-524 | passed | 8/8 pytest cases pass via `pytest services/api/tests/test_training_search_term_expansion.py` in 4.33s: `expand_search_terms("breat lump")` returns `["breast","mammary","lump","mass","swelling","nodule"]` (typo correction before synonym expansion) and returns `[]` for `None` / `""` / `"   "`; `GET /training/candidates?search=lump` forwards `terms=["lump","mass","swelling","nodule"]` to BOTH `GET_TRAINING_CANDIDATES_PAGE` and `COUNT_TRAINING_CANDIDATES_PAGE`; the no-search default request passes `terms=[]` and `search=None`; `GET /training/gold-labels?search=weight loss` forwards expanded terms (including `weight`, `loss`, `cachexia`) to both gold-label queries; both cypher strings contain the `ANY(t IN $terms WHERE toLower(...) CONTAINS t)` branch and a CASE fallback to `$search`; and the analytics-layer `_TYPO_MAP` / `_SYNONYM_MAP` are the SAME Python objects as `libs.search.term_expansion.TYPO_MAP` / `SYNONYM_MAP` (single-source-of-truth identity check). |
| Design Input | DI-LEO-AI-527 | approved | The "Apply to similar candidates" batch dialog (`SimilarCandidatesBatch.tsx`) that opens after a reviewer marks a row as gold from the dry-run review queue lifts the same shared `encounterRelevance` + `HighlightedText` vocabulary onto each row's encounter text. The dialog accepts a `search?: string` prop (forwarded by `GoldDatasetPanel` from `debouncedSearch`), memoises `expandedTerms = expandSearchTerms(search)`, computes per-row `matchRationale` + `highlightTerms`, conditionally wraps the truncated text in `<HighlightedText testId="similar-candidate-row-highlight">`, and renders an outlined chip row inside the encounter-text cell (mt 0.5, gap 0.5, flex-wrap) with up to 4 hit terms using the same chip token (height 20, fontSize 0.65rem, variant outlined) and stable `data-testid="similar-candidate-row-match-rationale[-chip]"` attributes. The accept / review / skip / toggle handlers are untouched; the wiring is purely visual. |
| Design Output | DO-LEO-AI-527 | draft | `services/ui/src/components/gold-dataset/SimilarCandidatesBatch.tsx` adds the imports, the `search?: string` prop, the memoised `expandedTerms`, per-row rationale + highlight computation, the conditional `<HighlightedText>` wrapper, the new outlined chip Box, and a `showRationale` guard. `services/ui/src/components/gold-dataset/GoldDatasetPanel.tsx` passes `search={debouncedSearch}` into the dialog. Reuses the pure-TS `mission-control/encounterRelevance.ts` and `mission-control/HighlightedText.tsx` modules unchanged. |
| Verification Test | VT-LEO-AI-525 | passed | 7/7 jest static-source cases pass under jest 30 + ts-jest in 0.52s: shared imports from `encounterRelevance` + `HighlightedText`; `search?: string` on Props and `useMemo(() => expandSearchTerms(search), [search])`; per-row `computeMatchRationale(item.text, expandedTerms)` + `collectHighlightTerms(search, matchRationale.hitTerms)`; conditional `<HighlightedText testId="similar-candidate-row-highlight">`; rationale Box with `data-testid="similar-candidate-row-match-rationale"`, `slice(0, 4)`, `data-testid="similar-candidate-row-match-rationale-chip"`, `variant="outlined"`, height 20, fontSize 0.65rem; `showRationale` guard for empty / no-hit queries; `GoldDatasetPanel` forwards `search={debouncedSearch}` into `<SimilarCandidatesBatch>`. |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-514 | `/care/encounters` row template on `ReviewListCard` + shared `HighlightedText` primitive (UN-LEO-AI-096). | R-LEO-AI-063, R-LEO-AI-206 | VT-LEO-AI-512 |
| DI-LEO-AI-516 | `/care/encounters` timeline brush + jump (lifts drawer scrubber via `EncounterResultsTimeline` wrapper, UN-LEO-AI-096). | R-LEO-AI-063, R-LEO-AI-174, R-LEO-AI-206 | VT-LEO-AI-515 |
| DI-LEO-AI-520 | Drawer encounter search uses host typo + synonym vocabulary; renders match-rationale chip row when synonyms hit (UN-LEO-AI-096). | R-LEO-AI-063, R-LEO-AI-174 | VT-LEO-AI-519 |
| DI-LEO-AI-523 | Dry-run Candidates / Verified gold / Synthetic gold rows render shared `<HighlightedText>` titles + outlined match-rationale chip row using the same `encounterRelevance` vocabulary (UN-LEO-AI-096). | R-LEO-AI-063, R-LEO-AI-174 | VT-LEO-AI-521 |
| DI-LEO-AI-526 | `/api/training/candidates` and `/api/training/gold-labels` expand the reviewer's query into the same typo + synonym vocabulary as the host encounter search and pass `$terms` to cypher (UN-LEO-AI-096). | R-LEO-AI-063, R-LEO-AI-174 | VT-LEO-AI-524 |
| DI-LEO-AI-527 | "Apply to similar candidates" batch dialog renders shared `<HighlightedText>` titles + outlined match-rationale chip row (UN-LEO-AI-096). | R-LEO-AI-063, R-LEO-AI-174 | VT-LEO-AI-525 |

---

### 3.xx ICD-10 / OPCS-4 classification ingest (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-089 | approved | Coding leads, finance teams, and downstream NHS payers need SNOMED-coded findings to be expressible as ICD-10 diagnoses and OPCS-4 procedures with their full hierarchy and human-readable titles, so map targets surfaced in TermSearch / surface-forms / Coding Review are interpretable without leaving LEO. |
| Design Input | DI-LEO-AI-228 | approved | Ingest NHS ICD-10 5th Edition XML (TRUD item 259) into Neo4j as `(:Icd10Code {code, title, level, chapter, block, included_terms, excluded_terms, age_low, age_high, sex, edition, source})` nodes plus `(:Icd10Code)-[:IS_A]->(:Icd10Code)` hierarchy edges. Streaming ClaML parser, MERGE on `code`, idempotent re-runs, drift-detection on title backfill. |
| Design Input | DI-LEO-AI-226 | approved | Ingest NHS OPCS-4 data files (TRUD item 119) into Neo4j as `(:OpcsCode {code, title, level, chapter, block, edition, source})` nodes plus `(:OpcsCode)-[:IS_A]->(:OpcsCode)` hierarchy edges; extend `services/terminology/scripts/loaders/snomed_map.py` to load SNOMED -> OPCS-4 simple-map refset (id `1126491000000109`) as `(:Concept)-[:MAPS_TO_OPCS4]->(:OpcsCode)` edges. Fixes a latent defect in `load_simple_map` which previously ingested OPCS-4 rows as `ReadCode` nodes (Read v3 refset filter `900000000000497000` was implicit). |
| Design Output | DO-LEO-AI-301 | approved | New `services/terminology/scripts/loaders/icd10_xml.py` (ClaML streaming parser + Neo4j writer); `Icd10Files` finder in `loaders/file_finder.py`; `:Icd10Code(level)` index in `loaders/schema.py`; phase 6 in `loaders/run_all.py`; `icd10` package (TRUD item 259, phase {6}) in `services/api/app/services/trud_sync.py` with new `icd10_codes` Neo4j count; `OPTIONAL MATCH (c)-[:MAPS_TO]->(ic:Icd10Code)` extended to return `icd10_term` in `services/api/app/models/neo4j_schema.py`; UI changes in `services/ui/src/app/settings/terminology/page.tsx`, `components/TermSearch.tsx`, `app/settings/surface-forms/page.tsx`, `lib/types.ts`, `lib/api/legacy.ts`. |
| Design Output | DO-LEO-AI-223 | approved | New `services/terminology/scripts/loaders/opcs4.py` (tab-delimited parser + chapter/block hierarchy builder); `Opcs4Files` finder in `loaders/file_finder.py`; `:OpcsCode {code}` constraint and `:OpcsCode(level)` index in `loaders/schema.py`; extension of `loaders/snomed_map.py` (`OPCS4_REFSET_ID`, `MERGE_OPCS4_MAP`, `load_opcs4_map`, `refset_filter` parameter on `load_simple_map`); phase 7 in `loaders/run_all.py`; `opcs4` package (TRUD item 119, phase {7}) in `trud_sync.py` with new `opcs4_codes` and `opcs4_maps` Neo4j counts; `OPTIONAL MATCH (c)-[:MAPS_TO_OPCS4]->(op:OpcsCode)` returning `opcs4` and `opcs4_term` in `neo4j_schema.py`; UI surfacing in TermSearch, surface-forms page, terminology settings page. |
| Risk | R-LEO-AI-301 | mitigated | Stale, missing, or partially loaded ICD-10 / OPCS-4 reference data leads to bare codes or wrong human-readable titles being shown to clinicians and finance teams in TermSearch / surface-forms / Coding Review, causing miscoded discharges, payer disputes, and incorrect clinical interpretation. Mitigated by: idempotent loaders with title-drift detection, package status + Neo4j counts visible in `/settings/terminology` (graceful degradation when missing), refset-id filtering on `load_simple_map` so OPCS-4 codes never leak into `ReadCode` nodes, and procedural quarterly TRUD freshness checks. |
| Verification Test | VT-LEO-AI-301 | passed | 14/14 pytest cases pass for `services/terminology/scripts/loaders/icd10_xml.py` via `python3 -m pytest tests/test_icd10_xml_loader.py -v`: code normalisation (dotted form), level classification (chapter/block/three_char/four_char/five_char), title extraction, included/excluded terms, age/sex constraints, IS_A hierarchy edges, idempotent re-runs, title-drift detection, batch-size flushing, empty-file resilience, malformed-XML resilience, age-range parsing edges, sex-coding edges, end-to-end load against synthetic ClaML fixture. Plus 6/6 jest static-source cases for the terminology page chrome (`services/ui/src/__tests__/settings-terminology-classifications.test.tsx`) and 4/4 jest static-source cases for ICD-10 title rendering in TermSearch + surface-forms (`services/ui/src/__tests__/term-search-classification-titles.test.tsx`). |
| Verification Test | VT-LEO-AI-302 | passed | 21/21 pytest cases pass via `python3 -m pytest tests/test_opcs4_loader.py tests/test_snomed_map_opcs4.py -v` covering OPCS-4 parser (code normalisation; chapter/block/three_char/four_char level classification; tab-delimited row streaming; chapter-name backfill; IS_A hierarchy edge construction; idempotent re-runs; empty-file and malformed-row resilience) and SNOMED -> OPCS-4 map (refset-id filter ensures only refset `1126491000000109` produces `MAPS_TO_OPCS4` edges; `load_simple_map(refset_filter=CTV3_REFSET_ID)` no longer leaks OPCS-4 rows into `ReadCode` nodes; idempotent re-runs; batch flushing; multi-refset RF2 input). Plus the shared 6/6 jest static-source cases for terminology page chrome and 4/4 jest static-source cases for OPCS-4 title rendering in TermSearch + surface-forms. |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-228 | NHS ICD-10 5th Edition XML loader (UN-LEO-AI-089). | R-LEO-AI-301 | VT-LEO-AI-301 |
| DI-LEO-AI-226 | NHS OPCS-4 loader + SNOMED -> OPCS-4 map extension with refset-id filter (UN-LEO-AI-089). | R-LEO-AI-301 | VT-LEO-AI-302 |

---

### 3.xx Haiku Episode Engine -- LLM-driven episode + milestone detection (April 2026)

This section supersedes the rule-based episode-builder Pattern A..N stack
(DI-LEO-AI-401, DI-LEO-AI-402, DI-LEO-AI-224, DI-LEO-AI-225, and the older
DI/DO/Risk/VT artefacts that anchored on regex / Read-code heuristics).
The new pipeline is a LangGraph chain of four LLM agents
(segmenter -> classifier -> milestone extractor -> reconciler) plus a
deterministic timeline loader, idempotent writer, and provenance trace
node. SYN-EE-001 is the synthetic reference case used in every prompt
few-shot, fixture, and frozen-cohort baseline (no real NHS numbers in
source control or test definitions).

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-090 | approved | Replace the rule-based episode detector with an LLM-driven engine that finds cancer episodes reliably, including patients with multiple episodes over time and patients with multi-site referrals that resolve to a single primary diagnosis (synthetic reference SYN-EE-001). |
| Design Input | DI-LEO-AI-500 | approved | Timeline loader: pulls and de-noises a patient's encounter timeline; produces a 240-char "trunk" view for cheap stages and a 1200-char "full" encounter_index for the milestone extractor's targeted lookups. |
| Design Input | DI-LEO-AI-501 | approved | Segmenter agent (Haiku): splits the timeline into candidate episode windows with referral / first_seen / treatment / closure boundaries, low-confidence flagging, and structured tool-call output. |
| Design Input | DI-LEO-AI-502 | approved | Classifier agent (Haiku): labels each window cancer / multi_site / benign / non_cancer with a justification and a confidence score; ties get needs_human_review=true. |
| Design Input | DI-LEO-AI-503 | approved | Milestone extractor agent (Haiku): finds canonical milestones (referral, first_seen, diagnosis_confirmed, treatment_started, treatment_completed, benign_closure) inside each window with evidence quotes; explicitly avoids anchoring treatment_started on the SYN-EE-001 "Failed encounter" administrative task -- the canonical failure mode of the deterministic detector. |
| Design Input | DI-LEO-AI-504 | approved | Reconciler agent (Sonnet): merges overlapping windows that are actually one episode (multi-site referrals resolving to a single diagnosis), preserves merged_from window ids, and surfaces merges with low confidence to HITL. |
| Design Input | DI-LEO-AI-505 | approved | Provenance + idempotent writeback: EpisodeEngineTrace per run captures model id, prompt version, token + latency totals, per-stage error containment; writer deletes existing EpisodeOfCare for the patient and rewrites with deterministic ids. |
| Design Output | DO-LEO-AI-500 | approved | services/analysis_worker/app/episode_engine/timeline_loader.py + schemas.py + state.py. |
| Design Output | DO-LEO-AI-501 | approved | services/analysis_worker/app/episode_engine/agents/segmenter.py + libs/prompts/episode_engine/segmenter_v1.py + _shared.py (BREAST_REFERENCE_CASE / SYN-EE-001 few-shot). |
| Design Output | DO-LEO-AI-502 | approved | services/analysis_worker/app/episode_engine/agents/classifier.py + libs/prompts/episode_engine/classifier_v1.py. |
| Design Output | DO-LEO-AI-503 | approved | services/analysis_worker/app/episode_engine/agents/milestone_extractor.py + libs/prompts/episode_engine/milestone_extractor_v1.py. |
| Design Output | DO-LEO-AI-504 | approved | services/analysis_worker/app/episode_engine/agents/reconciler.py + libs/prompts/episode_engine/reconciler_v1.py + chain.py LangGraph wiring. |
| Design Output | DO-LEO-AI-505 | approved | services/analysis_worker/app/episode_engine/{tracing,writer}.py + libs/pipeline_graph/subgraphs/episode_engine.py + registry/probe wiring. |
| Risk | R-LEO-AI-500 | mitigated | Timeline loader drops critical encounter text (e.g. the SYN-EE-001 "Failed encounter" or "(New Episode)" markers) and starves downstream agents (mitigated by dual-view loader, fixture-driven integration VT confirms preservation of both critical strings). |
| Risk | R-LEO-AI-501 | mitigated | Segmenter splits a single multi-site episode into multiple windows OR fuses two unrelated episodes into one window (mitigated by reconciler stage and per-window low-confidence flags). |
| Risk | R-LEO-AI-502 | mitigated | Classifier mislabels a benign 2WW closure as cancer or vice versa (mitigated by required justification + confidence; ties marked needs_human_review). |
| Risk | R-LEO-AI-503 | mitigated | Milestone extractor anchors treatment_started on an administrative "Failed encounter" task instead of the real reconciliation or definitive surgery (mitigated by SYN-EE-001 reference case in the prompt + frozen-cohort regression VT). |
| Risk | R-LEO-AI-504 | mitigated | Reconciler over-merges and hides a true second cancer episode (mitigated by merged_from audit trail + reviewer split-merge action in <=2 clicks). |
| Risk | R-LEO-AI-505 | mitigated | Provenance / writeback failure corrupts patient timeline OR loses cost / drift telemetry (mitigated by idempotent writer, error-contained tracing, EpisodeEngineTrace per run). |
| Verification Test | VT-LEO-AI-500 | passed | Timeline loader unit + synthetic-fixture VTs (services/analysis_worker/app/episode_engine/timeline_loader.py + tests/episode_engine/test_timeline_loader.py + test_synthetic_fixture_loader.py). |
| Verification Test | VT-LEO-AI-501 | passed | Segmenter agent unit VT with mocked LLM (tests/episode_engine/test_segmenter_agent.py). |
| Verification Test | VT-LEO-AI-502 | passed | Classifier agent unit VT with mocked LLM (tests/episode_engine/test_classifier_agent.py). |
| Verification Test | VT-LEO-AI-503 | passed | Milestone extractor unit VT with mocked LLM and the SYN-EE-001 anti-pattern (tests/episode_engine/test_milestone_extractor_agent.py). |
| Verification Test | VT-LEO-AI-504 | passed | Reconciler agent unit VT with mocked LLM (tests/episode_engine/test_reconciler_agent.py). |
| Verification Test | VT-LEO-AI-505 | passed | Idempotent writer VT (tests/episode_engine/test_writer.py). |
| Verification Test | VT-LEO-AI-506 | passed | Provenance / tracing VT -- trace ids, aggregation, persistence, error containment (tests/episode_engine/test_tracing.py). |
| Verification Test | VT-LEO-AI-507 | draft | Frozen-cohort regression on 20 synthetic patient ids (SYN-EE-001 .. SYN-EE-020); gated on RUN_EPISODE_ENGINE_FROZEN_VT=1 + secrets/episode_engine_cohort_map.json; baseline.json keyed by synthetic id only. |
| Validation Test | VAL-LEO-AI-014 | draft | Reviewer-led clinical validation on synthetic + de-identified review cohort; SYN-EE-001 acceptance is blocking (must produce endocrine 2025-05-19 + surgery 2025-07-28; must not anchor treatment_started on the 2025-05-02 Failed encounter). |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-500 | Timeline loader (UN-LEO-AI-090). | R-LEO-AI-500 | VT-LEO-AI-500 |
| DI-LEO-AI-501 | Segmenter agent (UN-LEO-AI-090). | R-LEO-AI-501 | VT-LEO-AI-501 |
| DI-LEO-AI-502 | Classifier agent (UN-LEO-AI-090). | R-LEO-AI-502 | VT-LEO-AI-502 |
| DI-LEO-AI-503 | Milestone extractor agent (UN-LEO-AI-090). | R-LEO-AI-503 | VT-LEO-AI-503, VT-LEO-AI-507 |
| DI-LEO-AI-504 | Reconciler agent (UN-LEO-AI-090). | R-LEO-AI-504 | VT-LEO-AI-504, VT-LEO-AI-507 |
| DI-LEO-AI-505 | Provenance + idempotent writeback (UN-LEO-AI-090). | R-LEO-AI-505 | VT-LEO-AI-505, VT-LEO-AI-506 |

Supersession note: DI-LEO-AI-401, DI-LEO-AI-402, DI-LEO-AI-224, DI-LEO-AI-225
and their DO/Risk/VT chains MUST be marked `superseded_by:
[DI-LEO-AI-500..505]` once the cutover lands (todo id `supersede_dcs`).

---

### 3.xx Universal LLM cost telemetry across every generation pipeline (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-091 | draft | Platform admins can monitor LLM token usage and cost for every generation pipeline (coding, episode engine, SBAR) |
| Design Input | DI-LEO-AI-506 | draft | Universal LLM token + cost telemetry: invoke_llm_json extracts tokens, LLMUsageRecorder accumulates per-run via contextvars, SBAR orchestrator writes Assessment.llm_usage_json + a PipelineRun :AuditEvent |
| Design Output | DO-LEO-AI-506 | draft | libs/llm_client/json_helper.py token extraction + libs/llm_client/usage_recorder.py + SBAR orchestrator _record_telemetry + libs/cypher/sbar_assessment_queries.py SET_ASSESSMENT_USAGE / WRITE_SBAR_AUDIT_EVENT + libs/cypher/model_config_queries.py GET_PATIENT_LLM_SPEND UNION over :Assessment |
| Risk | R-LEO-AI-506 | analyzed | Non-coding LLM pipelines (SBAR, future features) write no cost telemetry, so per-tenant invoicing under-counts AI spend and prompt-version regressions go undetected (mitigated by routing every call through invoke_llm_json + LLMUsageRecorder + best-effort write at FINALISE) |
| Verification Test | VT-LEO-AI-508 | passed | 10/10 cases: token extraction (TC-001/002), recorder accumulation + concurrent isolation (TC-003/004), SBAR Assessment + AuditEvent telemetry (TC-005/006), telemetry-failure isolation (TC-007) |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-506 | Universal LLM cost telemetry (UN-LEO-AI-091): invoke_llm_json now extracts input/output/cache tokens + latency + model id from the Bedrock response and forwards them to the registered tracking callback for every call. libs/llm_client/usage_recorder.py adds a contextvars-based LLMUsageRecorder so any orchestrator can wrap a logical run, accumulate token usage from nested invoke_llm_json calls, and read the totals after the block. The SBAR orchestrator wraps Situation/Background/Recommendation in a single recorder and on FINALISE writes (a) Assessment.llm_usage_json + flat llm_input_tokens/llm_output_tokens/llm_cached_tokens/llm_cost_usd/llm_latency_ms/llm_model_id and (b) a :AuditEvent {type:'PipelineRun'} with the same flat fields linked to the Patient via [:AUDIT_FOR]. GET_PATIENT_LLM_SPEND extended with a UNION over :Assessment so the per-encounter drill-down covers SBAR rows (source='sbar_assessment'). Telemetry writes are best-effort: failures are logged at WARNING and never fail the SBAR run. - VT passed 2026-04-18 | R-LEO-AI-506 | VT-LEO-AI-508 |

---

### 3.xx Sync LLM entry-point telemetry (LLMClient.converse + invoke_with_fallback) (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-091 | draft | (Updated) Now also covers the dominant SYNC LLM entry point used by ~14 production callers (escalation, consensus, label_verifier, candidate_ai_first_pass, llm_extractor, training, _training_askleo, prompts, terminology, encounter_query_understanding, terminology_api/concepts, exclusion_detector, _extractor, fix_analyzer) so per-tenant invoicing and the dashboard LLMSpendPanel see those calls without modifying any caller. |
| Design Input | DI-LEO-AI-515 | draft | LLMClient.converse (Bedrock + Azure branches) and providers.invoke_with_fallback emit one track_llm_usage event per call -- success and failure paths -- forwarding model_provider, model_name, input/output/cache token counts, latency_ms, agent_task and patient_id. Best-effort: a callback exception or missing usage object MUST NOT break the caller. New sync helper track_llm_usage_sync handles both sync callbacks (the LLMUsageRecorder default) and async callbacks (drained via the running loop or asyncio.run). |
| Design Output | DO-LEO-AI-514 | draft | libs/llm_client/factory.py: LLMClient.converse times the call (time.monotonic), accepts agent_task / patient_id kwargs, fires _fire_converse_tracking on success and on the failure path before re-raising. libs/llm_client/providers.py: invoke_with_fallback times each branch, calls extract_token_counts on the responding provider, fires track_llm_usage exactly once per attempted provider with success/error tagging. libs/llm_client/token_tracker.py: adds track_llm_usage_sync. |
| Risk | R-LEO-AI-506 | analyzed | (Updated mitigations) Adds a 5th mitigation: every sync LLM entry point now fires the tracking callback; the ~14 production caller surfaces become observable to LLMSpendPanel and per-tenant billing without modifying any caller. Implemented_by includes DI-LEO-AI-515; verified_by includes VT-LEO-AI-513. |
| Verification Test | VT-LEO-AI-513 | passed | 9/9 cases: TC-001 Bedrock converse fires with matching tokens, TC-002 Azure converse fires with matching tokens, TC-003 failure-path callback + re-raise, TC-004 callback-exception isolation, TC-005 agent_task / patient_id forwarding, TC-006 active LLMUsageRecorder accumulates two converse calls, TC-007 invoke_with_fallback primary path single event, TC-008 Bedrock-fail Azure-fallback emits one bedrock failure event + one azure success event, plus a USE_AZURE_PRIMARY bonus case. Pre-existing tests/test_llm_providers.py (16) + VT-LEO-AI-508 (10) suites pass with no regressions (62/62 across the combined run). |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-515 | Sync LLM entry-point cost telemetry (UN-LEO-AI-091): closes the gap exposed by the audit against .cursor/rules/llm-cost-telemetry.mdc -- LLMClient.converse (the dominant sync helper, used by 13 caller surfaces) and invoke_with_fallback (used by fix_analyzer) extracted token counts onto LLMResponse but never called track_llm_usage. After this change every sync call fires the registered callback exactly once on success, and once with success=False on the failure path before the original exception is re-raised. agent_task and patient_id are accepted as kwargs and forwarded verbatim. The active LLMUsageRecorder picks up sync calls via the same default callback that already routes invoke_llm_json events. Telemetry emission is best-effort: a callback exception is swallowed at DEBUG and converse returns the response unchanged. - VT passed 2026-04-18 | R-LEO-AI-506 | VT-LEO-AI-513 |

---

### 3.xx LLM cost telemetry P1 follow-ups: episode engine + guidance + kwarg backfill (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-091 | draft | (Updated) Now also covers episode-engine and guidance-rule pipelines, plus stable per-task / per-patient cost attribution across every production sync LLM call site, so /admin/billing and the per-patient drill-down panel see every pipeline that calls an LLM. |
| Design Input | DI-LEO-AI-517 | draft | Episode engine writes a parallel :AuditEvent {type:'PipelineRun', subtype:'episode_engine'} from persist_trace carrying the four canonical token / cost properties; status derived from per-stage ok flags; OPTIONAL MATCH (p:Patient) keeps the write idempotent; failure swallowed at WARNING. GET_PATIENT_LLM_SPEND extended with a UNION over those rows so the per-patient drill-down picks them up with no UI change. |
| Design Input | DI-LEO-AI-518 | draft | GuidanceRuleGenerator audit event normalised to type='PipelineRun', subtype='guidance_rule_extraction' (was custom 'GuidanceRuleExtraction'). The synchronous /guidance/rules/test dry-run endpoint writes a parallel :AuditEvent {subtype:'guidance_rule_dry_run', would_write:bool}. GET_PATIENT_LLM_SPEND extended with a UNION over both subtypes. Both writes are best-effort and never block the API response. |
| Design Input | DI-LEO-AI-519 | draft | Every production LLMClient.converse call site under libs/ and services/{api,coding_worker,analytics_api,terminology_api,analysis_worker,pipeline_worker} passes a stable agent_task literal (and patient_id where in scope) so the telemetry events from DI-LEO-AI-515 carry meaningful task labels. The duplicated services/api/app/services/llm_usage module is consolidated into a thin re-export of libs.llm_usage so cost numbers stop depending on import path. |
| Design Output | DO-LEO-AI-517 | draft | services/analysis_worker/app/episode_engine/tracing.py (_WRITE_EPISODE_ENGINE_AUDIT_EVENT, _write_audit_event, _resolve_total_cost_usd) + libs/cypher/model_config_queries.py (GET_PATIENT_LLM_SPEND UNION). |
| Design Output | DO-LEO-AI-518 | draft | services/api/app/services/guidance_rule_generator.py (props: type=PipelineRun, subtype=guidance_rule_extraction) + services/api/app/routers/guidance_rules.py (_DRY_RUN_AUDIT_EVENT + _write_dry_run_audit_event) + libs/cypher/model_config_queries.py (UNION over both guidance subtypes). |
| Design Output | DO-LEO-AI-519 | draft | services/api/app/services/llm_usage.py becomes a re-export of libs.llm_usage. agent_task literals added to every converse() call site enumerated in DI-LEO-AI-519 file_structure (29 stable labels). Tests updated to accept **kwargs in fixture stubs. |
| Risk | R-LEO-AI-506 | analyzed | (Updated) Adds three new mitigations covering episode-engine telemetry (DI-LEO-AI-517), unified guidance audit events (DI-LEO-AI-518), and stable agent_task / patient_id attribution + LLMUsage consolidation (DI-LEO-AI-519). Verified by VT-LEO-AI-516 / 517 / 518 respectively. |
| Verification Test | VT-LEO-AI-516 | draft | Episode-engine PipelineRun AuditEvent: 4 cases (audit-event-with-token-totals, patient-link-when-patient-exists, status-reflects-partial-failure, write-failure-does-not-raise). Test file: tests/episode_engine/test_tracing.py. |
| Verification Test | VT-LEO-AI-517 | draft | Guidance pipeline PipelineRun unification: 3 cases (generator-writes-unified-pipelinerun, dry-run-endpoint-writes-audit-event, audit-event-failure-does-not-raise). Test files: services/api/tests/test_guidance_rule_generator.py and services/api/tests/test_guidance_rules_dry_run_audit.py. |
| Verification Test | VT-LEO-AI-518 | draft | Telemetry kwarg coverage + LLMUsage module identity: 2 cases (all-production-converse-sites-have-agent-task via static-source walk, llm-usage-module-identity via runtime is-comparison). Test files: tests/llm_client/test_telemetry_kwarg_coverage.py and tests/llm_client/test_llm_usage_module_identity.py. |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-517 | Episode-engine PipelineRun :AuditEvent + GET_PATIENT_LLM_SPEND UNION (UN-LEO-AI-091). | R-LEO-AI-506 | VT-LEO-AI-516 |
| DI-LEO-AI-518 | Guidance pipeline audit-event unification: generator type/subtype + dry-run endpoint persistence (UN-LEO-AI-091). | R-LEO-AI-506 | VT-LEO-AI-517 |
| DI-LEO-AI-519 | agent_task / patient_id backfill at every production converse call site + LLMUsage module consolidation (UN-LEO-AI-091). | R-LEO-AI-506 | VT-LEO-AI-518 |

---

### 3.xx Guideline rule synonym sets + per-seed descendants + carve-outs (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-093 | approved | Clinical guideline authors can express a single rule criterion as a set of equivalent SNOMED codes (a synonym set), opt into descendant expansion per code, and exclude specific sub-codes that should not fire the rule -- so a "Smoker" chip can match the patient on "Cigarette smoker" or "Pipe smoker" while never firing on "Trial of smoking". |
| Design Input | DI-LEO-AI-508 | approved | LogicCriterion schema upgrade (Pydantic + TypeScript): adds `seeds: LogicSeed[]`, `excluded_concept_ids: string[]`, `primary_concept_id`; LogicSeed carries per-seed `include_descendants` + `distance_child` override. `model_validator` derives the legacy `snomed_concept_id` / `preferred_term` from the primary seed, rejects primary-not-in-seeds, and rejects seed/exclusion overlap. Migration script `scripts/migrations/logic_criterion_synonym_set.py` upgrades persisted v2 rules in-place without changing the int-id set passed to `put_bitmap`. |
| Design Input | DI-LEO-AI-509 | approved | Bitmap compiler: `_compile_concept_leaf` builds the union of every seed's IS_A closure (per-seed `include_descendants` + `distance_child`), subtracts `excluded_concept_ids`, and compiles to one bitmap per CONCEPT leaf. Echoes `seed_concept_ids` (sorted SNOMED string list) onto the compiled tree so the evaluator can attribute hits without a reverse int->id lookup. Falls back to the primary seed when every closure is excluded. |
| Design Input | DI-LEO-AI-510 | approved | Evaluator + diagnose return per-leaf hit attribution: `matched_concept_ids` on every CONCEPT leaf in the annotated tree, plus a `matched_via: [{node_id, primary_concept_id, preferred_term, matched_concept_ids}]` array on every matched rule in `evaluate_patient`. SBAR formatter passes `matched_via` through into the rule snapshot and renders a "Matched on: ..." bullet ("Smoker", "`2` (a kind of Smoker)", "`2`, `3` (kinds of Smoker)") in the Assessment markdown. SBAR Recommendation prompt rule 13 instructs the LLM to name the specific match in plain English on first reference. |
| Design Input | DI-LEO-AI-511 | approved | UI: SynonymChipEditor popover (search/add/remove seeds, set primary, toggle include_descendants per seed, override distance_child, search/manual-id exclude codes) plus an inline SeedDescendantsList per seed that fetches /api/terminology/concepts/{id}/descendants and lets the author audit and one-click block any unintended descendant before saving (DI-511 AC-007). LogicTreeEditor mounts the badge on every CONCEPT chip (ConceptChipInline + ConceptNodeView). treeOps grows pure helpers (addSeed/removeSeed/setPrimarySeed/toggleIncludeDescendants/setSeedDistance/addExcluded/removeExcluded) routed through `applyUpdate`. treeToSentence renders multi-seed chips as "is a smoker (or any kind of: smoker, cigarette smoker)" and exclusions as "except trial of smoking" via an optional TermResolver. RuleReviewSection.tsx adds an Edit affordance on the "Approved in this session" card (AC-010) and a Pending review / Active / Superseded ToggleButtonGroup (AC-011, AC-012) so any rule -- pending, active, or superseded -- can be opened in the editor; Approve-all and per-row Looks right / Reject collapse outside Pending so bulk decisions cannot be misapplied to live rules. |
| Design Output | DO-LEO-AI-508 | draft | services/api/app/services/guidance_rule_edit.py (LogicSeed + LogicCriterion + validators) + services/ui/src/app/admin/guidance/EditRuleDialog/types.ts (mirror) + scripts/migrations/logic_criterion_synonym_set.py |
| Design Output | DO-LEO-AI-509 | draft | services/terminology_api/app/services/guideline_compiler.py (`_seeds_from_criterion` + `_compile_concept_leaf`) |
| Design Output | DO-LEO-AI-510 | draft | services/terminology_api/app/services/guideline_evaluator.py (`_matched_seed_ids`, `_collect_matched_via`, annotated CONCEPT.matched_concept_ids) + libs/sbar/assessment_formatter.py (`_render_matched_via` + snapshot pass-through) + libs/prompts/sbar_recommendation_v1.py (rule 13) |
| Design Output | DO-LEO-AI-511 | draft | services/ui/src/app/admin/guidance/EditRuleDialog/SynonymChipEditor.tsx + LogicTreeEditor.tsx wiring + treeOps.ts helpers + treeToSentence.ts (TermResolver) |
| Risk | R-LEO-AI-508 | mitigated | A misconfigured exclusion or synonym set silently drops clinically meaningful patient matches -- e.g. an over-broad descendant expansion masks a needed alternate diagnosis, or an excluded code blocks a legitimate hit. Mitigated by: server-side validator rejects primary-not-in-seeds and seed/exclusion overlap; UI plain-English warnings; replay-on-save against the rule's saved test cohort (test patients); evaluator surfaces `matched_via` so SBAR + audit logs name the exact code that fired (or, on no match, the closest seed near-miss is visible in `diagnose`); inline SeedDescendantsList lets the author SEE every descendant the bitmap will match before saving and one-click block any unintended one (DI-511 AC-007); migration is idempotent and changes zero int-ids on read for legacy single-seed rules. Residual risk dropped from RPN 12 to RPN 6 (medium -> low) after the inline audit affordance landed. |
| Verification Test | VT-LEO-AI-510 | passed | 19 pytest cases (5 schema, 5 compiler, 5 evaluator, 4 SBAR) + 24 jest cases (15 treeOps, 5 treeToSentence, 4 SeedDescendantsList). Verifies legacy back-compat, multi-seed union + closure expansion, exclusion subtraction, primary-only fallback, matched_via attribution end-to-end into the SBAR markdown + JSON snapshot, full UI wiring of the new NodeUpdate variants, and the inline descendants viewer (TC-016) that lets the author audit and block any unintended descendant before saving. |
| Validation Test | VAL-LEO-AI-015 | draft | Reviewer-led validation in staging: a clinical lead authors a real synonym set + exclusion on a NICE 2WW rule, runs replay on the rule's test cohort, and confirms that (a) the chip label matches the primary seed, (b) descendant codes fire as expected, (c) the excluded sub-code does NOT fire, and (d) the SBAR Assessment narrative names the matched code in plain English. |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-508 | LogicCriterion synonym set + exclusions schema (UN-LEO-AI-093). | R-LEO-AI-508 | VT-LEO-AI-510 |
| DI-LEO-AI-509 | Bitmap compiler union-of-closures + exclusion subtraction (UN-LEO-AI-093). | R-LEO-AI-508 | VT-LEO-AI-510 |
| DI-LEO-AI-510 | Evaluator + SBAR matched_via attribution (UN-LEO-AI-093). | R-LEO-AI-508 | VT-LEO-AI-510 |
| DI-LEO-AI-511 | EditRuleDialog SynonymChipEditor + treeOps/treeToSentence (UN-LEO-AI-093). | R-LEO-AI-508 | VT-LEO-AI-510 |

---

### 3.xx Stepped widescreen "Change this rule" editor for non-specialist reviewers (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-094 | approved | Non-specialist reviewers (audit clerks, junior coders, clinical leads, age 8-80, UK reading age 7-11) can change a clinical guidance rule step by step without ever feeling overwhelmed by the editor or saving a rule they did not understand. |
| Design Input | DI-LEO-AI-512 | draft | EditRuleDialog refactored as a widescreen split-view modal with a sticky left numbered step rail (4 steps: Who / Suggest / Try / Save), a focused centre canvas, and a sticky right LivePreviewPane. Save payload contract is unchanged (action='edit', node_ids stripped, action SNOMED omitted unless touched). All chrome copy reads at UK reading age 7-11. |
| Design Output | DO-LEO-AI-512 | draft | services/ui/src/app/admin/guidance/EditRuleDialog/index.tsx orchestrator + StepRail.tsx + LivePreviewPane.tsx + steps/Step1Who.tsx + steps/Step2Suggest.tsx + steps/Step3Try.tsx + steps/Step4Save.tsx + copy.ts (~950 LOC). |
| Risk | R-LEO-AI-509 | mitigated | A non-specialist reviewer saves a guidance rule edit that does not match what they intended because the legacy one-column editor presented too many concerns at once. Mitigated by the four-step wizard, the always-on plain-English LivePreviewPane, the step-4 Before/After variant, the reason-gated single primary Save action, and reading-age-7-to-11 chrome copy. |
| Verification Test | VT-LEO-AI-511 | passed | 14 jest cases (6 suites): static-source orchestrator wiring, rail navigation, live preview reactivity, before/after on step 4, save gating on reason + tree validity, save payload omits criterion when action chip untouched, save payload includes criterion when action chip touched, node_ids stripped, reading-age sweep on copy.ts (Flesch-Kincaid grade <= 6), helper-sentence length sweep, cancel discards. Regression sweep: 92/92 EditRuleDialog suites green after rail-aware step navigation in the legacy tests. |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-512 | Stepped widescreen EditRuleDialog (UN-LEO-AI-094). | R-LEO-AI-509 | VT-LEO-AI-511 |

---

### 3.xx SBAR background partition + map + reduce + plain-English error surfacing (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-095 | approved | Reviewers can run SBAR on patients with large records and still get an output, no clinical record is silently truncated or dropped to make space (the work is split across multiple LLM calls), and when something does go wrong they see a plain-English explanation (UK reading age 9-11) of which section / which part did not finish and what to try next -- never a raw AWS error. |
| Design Input | DI-LEO-AI-513 | draft | Token-budget aware SBAR background partition + map + reduce. `libs/sbar/background_partitioner.partition_background_sources()` greedy-packs ResolvedSource records into one or more `Partition` objects respecting a per-part token budget, splits oversized single records intra-record with `part_in_record` metadata, and refuses runs that would need more than 8 parts (`too_many_parts`). `call_background` runs the existing `sbar_background` prompt once per partition (MAP), runs the new `sbar_background_reduce` prompt exactly once when N >= 2 and every MAP succeeded (REDUCE), and falls back to a deterministic stitch of the partial markdowns ("## Background -- part k of N") with a `reduce_failed` notice on REDUCE failure or per-part MAP failure. The single-partition path is a direct pass-through. `error_messages.translate_error()` maps Bedrock failure modes plus the new `too_many_parts` / `reduce_failed` / `background_part_failed` codes to friendly stage-aware messages so reviewers never see raw vendor strings. |
| Design Input | DI-LEO-AI-516 | draft | Surface SBAR run errors and notices to the reviewer (SSE + UI). The orchestrator emits structured `errors` and `notices` arrays on every `sbar_completed` event, per-stage `error` / `notice` / `parts` keys on every `sbar_stage_completed` event, and a new `sbar_stage_progress` event per Background part / phase so the playground can show "Generating Background, part 2 of 5" live progress. Each item is a `{stage, code, message}` triple. The /admin/knowledge AI Summarisation playground renders an MUI Alert `severity="warning"` with `data-testid="sbar-errors-alert"`, an Alert `severity="info"` with `data-testid="sbar-notices-alert"`, per-part progress / reduce / parts-summary Chips (`sbar-part-progress-${stage}`, `sbar-reduce-progress-${stage}`, `sbar-parts-summary-${stage}`), and demotes the result button from `colour="success"` to `colour="warning"` when errors are present. |
| Design Input | DI-LEO-AI-521 | draft | SBAR background reduce prompt (lossless editor). New module `libs/prompts/sbar_background_reduce_v1.py::SBAR_BACKGROUND_REDUCE_SYSTEM_V1` with six HARD RULES (NO NEW FACTS, NO LOSS, PRESERVE DATES / MEDICATIONS / VALUES verbatim, DEDUPE LITERAL DUPLICATES ONLY, PRESERVE CITATIONS, EDITOR-NOT-CLINICIAN). Registered at version 1 by `scripts/seed_prompt_configs.py` against `SBAR_BACKGROUND_OUTPUT_SCHEMA`. Invoked once per multi-part successful run from `call_background`. |
| Design Output | DO-LEO-AI-521 | draft | `libs/sbar/background_partitioner.py` (partition_background_sources, _split_oversize_source, Partition, PartitionReport) + `libs/sbar/prompt_calls.py` (call_background uses partitioner + MAP per partition + REDUCE + deterministic stitch fallback + progress_cb) + `services/pipeline_worker/app/services/sbar_orchestrator.py` (sbar_stage_progress emission, parts payload, per-part FriendlyError stage labels) + `libs/sbar/error_messages.py` (too_many_parts / reduce_failed / background_part_failed codes; background_split / background_record_split notices). |
| Design Output | DO-LEO-AI-516 | draft | `services/pipeline_worker/app/services/sbar_orchestrator.py` (SBAResult.errors_detail / notices, _record_stage_error, _record_background_notices, _record_background_part_errors, sbar_stage_progress emission, sbar_completed / sbar_stage_completed payload changes) + `services/ui/src/hooks/useSbarStream.ts` (SbarErrorDetail / SbarNotice / SbarStagePart / SbarStagePartProgress types, partProgress + parts state) + `services/ui/src/app/admin/ai-summarisation/SbarPlayground.tsx` (sbar-errors-alert + sbar-notices-alert + sbar-part-progress + sbar-reduce-progress + sbar-parts-summary chips + dynamic result button colour). |
| Design Output | DO-LEO-AI-522 | draft | `libs/prompts/sbar_background_reduce_v1.py::SBAR_BACKGROUND_REDUCE_SYSTEM_V1` (six HARD RULES system prompt) + `scripts/seed_prompt_configs.py` (registers sbar_background_reduce@1) + `libs/sbar/prompt_calls.py::_try_reduce_partials` (single reduce invocation per multi-part successful run). |
| Risk | R-LEO-AI-185 | analyzed | (Updated mitigations) Adds a 4th mitigation: token-budget aware partition + map + reduce flow plus structured errors / notices on the wire and warning / info Alerts + per-part progress chips in the playground; the result button shifts from green to amber when any stage failed so a partial SBAR can no longer be confused with a complete one. Implemented_by includes DI-LEO-AI-513, DI-LEO-AI-516, and DI-LEO-AI-521; verified_by includes VT-LEO-AI-514. |
| Risk | R-LEO-AI-510 | analyzed | A reviewer mistakes a partially-failed SBAR for a complete one because errors are hidden behind a green "Done" button. Mitigated by the partition + map + reduce flow (removes the dominant cause without dropping records), structured errors / notices on the wire (DI-LEO-AI-516), per-part `sbar_stage_progress` SSE events, the warning Alert + amber button in the playground, and the translator-only message text invariant. Initial RPN 36 (high) -> residual RPN 6 (low). |
| Risk | R-LEO-AI-511 | analyzed | (New) The SBAR Background reduce step silently loses a clinical fact, or invents a fact, while merging partial Background sections. Mitigated by (a) the strict editor-only `sbar_background_reduce` prompt with six HARD RULES (DI-LEO-AI-521), (b) the deterministic stitch fallback that takes over on reduce failure (DI-LEO-AI-513), (c) the all-MAP-succeeded gate that prevents reduce from running over a poisoned input set, and (d) the playground per-part / parts-summary chips that surface that the Background was assembled from multiple LLM calls. Initial RPN 36 (high) -> residual RPN 12 (medium, conditionally acceptable for QA cohort). |
| Verification Test | VT-LEO-AI-514 | passed | 18/18 cases: partitioner single-part no-op, multi-part packing with no-record-dropped invariant, intra-record splitting, too_many_parts refusal, MAP+REDUCE happy path, REDUCE failure -> deterministic stitch with notice, per-part MAP failure containment, progress_cb emission, translator covering Bedrock + new partition codes, notice helpers, orchestrator sbar_stage_progress emission, per-part FriendlyError stage labels, useSbarStream consumption, SbarPlayground per-part chips. Run 1: pytest tests/sbar/ tests/test_sbar_orchestrator.py -- 40 passed in 0.14s; Run 2: jest sbar-playground-chrome -- all cases pass. |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-513 | Token-budget aware SBAR background partition + map + reduce (SUPERSEDED by DI-LEO-AI-522). | R-LEO-AI-185, R-LEO-AI-510, R-LEO-AI-511 | VT-LEO-AI-514 |
| DI-LEO-AI-516 | Structured SBAR errors / notices / parts / progress on SSE + Playground surfacing (UN-LEO-AI-095). | R-LEO-AI-185, R-LEO-AI-510 | VT-LEO-AI-514 |
| DI-LEO-AI-518 | SBAR background reduce prompt (lossless editor) (SUPERSEDED by DI-LEO-AI-522). | R-LEO-AI-511 | VT-LEO-AI-514 |
| DI-LEO-AI-521 | SBAR background reduce prompt (lossless editor) -- duplicate of DI-LEO-AI-518 (SUPERSEDED by DI-LEO-AI-522). | R-LEO-AI-511 | VT-LEO-AI-514 |
| DI-LEO-AI-522 | SBAR Background partition + map + deterministic stitch (no reduce) (UN-LEO-AI-095). | R-LEO-AI-510, R-LEO-AI-511 | VT-LEO-AI-520 |
| DO-LEO-AI-521 | Implementation of DI-LEO-AI-522: partitioner + prompt_calls deterministic stitch + per-part SSE progress + Playground per-part chip. | R-LEO-AI-510, R-LEO-AI-511 | VT-LEO-AI-520 |
| Risk R-LEO-AI-510 | (Updated) Mitigations now point at DI-LEO-AI-522 (no-reduce flow) and VT-LEO-AI-520. Residual RPN unchanged at 6 (low). | -- | VT-LEO-AI-520 |
| Risk R-LEO-AI-511 | (Updated) Status -> mitigated by design: DI-LEO-AI-522 retires the reduce LLM step entirely, so editor-induced fact loss / hallucination is no longer architecturally possible. Initial RPN 36 -> residual RPN 3 (low). | -- | VT-LEO-AI-520 |
| VT-LEO-AI-520 | passed | 11 cases verifying the no-reduce architecture: partitioner one-part / multi-part / oversize-record-split / too-many-parts refusal, call_background no-reduce-call invariant, per-part failure containment, deterministic stitch heading + sources comment, progress callback per part, hook sbar_stage_progress handler, Playground per-part chip. Run 1: pytest tests/sbar -v -- 46 passed; Run 2: jest sbar-playground-chrome -- 15 passed. |

### Episode Engine: Audit Relevance Filter + Window Partitioner safety net (UN-LEO-AI-097)

| Artefact | ID | Status | Notes |
|----------|----|--------|-------|
| User Need | UN-LEO-AI-097 | approved | Cancer pathway audits stay focused on pathway-relevant encounters, never silently drop a relevant one, and complete for every patient regardless of record size. Sits in front of UN-LEO-AI-090 to keep the milestone extractor's input tight while preserving the no-encounter-dropped invariant. |
| Design Input | DI-LEO-AI-524 | draft | Episode Engine Audit Relevance Filter (focus-first). Two layers: deterministic always-keep guards (cancer-coded encounters, EVERY encounter the segmenter tagged in any anchor role for this window -- referral / first_seen / diagnosis_confirmed / treatment_started / treatment_completed / benign_closure / first_presentation / place_of_first_presentation / outcome_letter, deterministic safety-netting / disruption hint matches -- guard decision is final and the LLM cannot override) plus a Bedrock Haiku batched relevance triage on the unguarded remainder (batch <= 20, forced submit_relevance tool, returns {encounter_id, keep, reason} per encounter). Focused set is the chronological-order union with no duplicates. Fail-open on Haiku error (every encounter in a failed batch flows through with kept_by_fallback=true). Records audit_input_encounters / audit_kept_by_guards / audit_kept_by_llm / audit_dropped_by_llm (with up to 10 reason samples) / audit_filter_failed on every EoC; LLMUsage written with stage=audit_relevance_filter. |
| Design Input | DI-LEO-AI-525 | draft | Episode Engine Window Partitioner safety net for milestone extraction (partition + map + deterministic merge). Mirrors DI-LEO-AI-522 (SBAR Background) for the milestone extractor schema. Bin-packs the focused encounter set into N <= 8 Partitions; oversized single encounters are split intra-encounter with part_in_encounter metadata; partitioner refuses with too_many_parts when N would exceed 8 (zero LLM invocations). Chain invokes the milestone extractor once per Partition (sequentially); per-part failures contribute an empty milestone list with needs_human_review=true while surviving parts still contribute. merge_milestones_deterministic is pure Python: de-dup milestones on (type, date, encounter_id) keeping highest confidence + longest evidence_quote, union safety_netting flags, de-dup disruptions on the same key, any-true on needs_human_review, concatenate reasoning as 'Part i of N: ...' lines. NO second LLM merge call (R-LEO-AI-513). Single-Partition runs are byte-for-byte identical to the legacy single-call extractor. EoC carries audit_parts and per-part trace; too_many_parts flips the EoC to needs_human_review=true + audit_filter_overflow=true. timeline_loader._FULL_SNIPPET_CHARS demoted to a corner-case fallback. |
| Design Output | DO-LEO-AI-524 | draft | services/analysis_worker/app/episode_engine/agents/audit_relevance_filter.py (run, _apply_guards, _batch_unguarded, _call_relevance_triage, _merge_decisions) + libs/prompts/episode_engine/audit_relevance_filter_v1.py (SYSTEM + USER_TEMPLATE + submit_relevance JSON Schema, reading age 9-11) + episode_engine/chain.py (_node_audit_relevance_filter wired before _node_milestone_extractor; LLMUsage stage=audit_relevance_filter) + episode_engine/schemas.py (FocusedSet, FocusedEncounter, AuditFilterReport, audit fields on EpisodeOfCareTrace). |
| Design Output | DO-LEO-AI-525 | draft | services/analysis_worker/app/episode_engine/window_partitioner.py (partition_window, merge_milestones_deterministic, _pack_partitions, _intra_encounter_split) + episode_engine/chain.py (_node_milestone_extractor wires partition + map + deterministic merge; legacy single-call pass-through when N == 1) + episode_engine/schemas.py (WindowPartition, PartitionReport, audit_parts, per-part trace) + episode_engine/timeline_loader.py (_FULL_SNIPPET_CHARS demoted to corner-case fallback so the partitioner is the single point of token-budget control). |
| Risk | R-LEO-AI-512 | analyzed | The Audit Relevance Filter (Haiku triage) drops a clinically relevant encounter, leading to a missing pathway milestone, missed safety-netting note, or missed avoidable delay on the EoC audit. Mitigated by deterministic always-keep guards (cancer-coded / anchor / deterministic-hint-flagged encounters cannot be dropped at all), plain-English {encounter_id, reason} samples on the EoC audit trace so a reviewer can spot a wrongly-dropped encounter in one click, and fail-open behaviour on Haiku error so transient LLM outages cannot silently turn an encounter into a missing milestone. Initial RPN 36 (high) -> residual RPN 6 (low). |
| Risk | R-LEO-AI-513 | analyzed | The Window Partitioner safety net cannot fit the focused encounter set in <=8 parts, or a future LLM merge step would lose / invent a pathway fact during partition stitching. Mitigated by deterministic Python merge (replaces an LLM merge step -- editor-induced fact loss / fact invention is architecturally impossible, same as DI-LEO-AI-522 for SBAR), explicit too_many_parts refusal that flips the EoC to needs_human_review=true + audit_filter_overflow=true with zero LLM invocations, per-part failure containment, and per-part {encounter_count, milestones_count, error} trace on every multi-part EoC. Initial RPN 24 (medium) -> residual RPN 3 (low). |
| Verification Test | VT-LEO-AI-522 | passed | tests/episode_engine/test_audit_relevance_filter.py: 10 cases covering (1) cancer-coded guard cannot be overridden, (2) anchor preservation, (3) deterministic safety-netting hint guard cannot be overridden, (4) Haiku batching shape (25 unguarded -> 2 batches of 20+5), (5) fail-open on Haiku error, (6) audit trace fields populated, (7) no duplicate encounter when guard + LLM both keep (LLM bypassed), (8) chronological order preserved, (9) one StageTrace per Haiku batch, (10) apply_guards pure-function smoke test. Run: 10/10 pass via `pytest tests/episode_engine/test_audit_relevance_filter.py -v` in 0.66s on 2026-04-19. |
| Verification Test | VT-LEO-AI-523 | passed | tests/episode_engine/test_window_partitioner.py + test_chain.py + test_milestone_extractor_agent.py: 14 cases covering (1) single-partition common case, (2) multi-part packing preserves every focused encounter, (3) intra-encounter split for oversized record (part_in_encounter), (4) too_many_parts refusal with friendly notice, (5) empty focused set, (6-7) deterministic merge dedup keeps highest-confidence + longest evidence_quote and unions safety_netting / disruptions, (8) single-part legacy pass-through, (9) empty merge, (10) chain single-call common case, (11) chain multi-call per-part, (12) per-part failure containment, (13) chain overflow refusal with zero LLM invocations + EoC flagged, (14) milestone_extractor pass-through regression. Run: 14/14 pass via `pytest tests/episode_engine/test_window_partitioner.py tests/episode_engine/test_chain.py tests/episode_engine/test_milestone_extractor_agent.py -v` on 2026-04-19. |

---

## 4. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | | | |
| Quality Manager | | | |
