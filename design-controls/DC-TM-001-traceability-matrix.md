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

---

## 4. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | | | |
| Quality Manager | | | |
