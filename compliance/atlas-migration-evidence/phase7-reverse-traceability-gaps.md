# Phase 7 - Reverse Traceability Gaps

Implementation files in the repo with no DI/DO/VT YAML referencing them. Sorted by service bucket. Coverage is computed file-level then directory-level (a DI/DO that references a directory covers everything below it).

**Safety-class hint** uses the proportionality gate from `design-controls-first.mdc`:
- `scripts/` -> Class A (internal tooling; DI/DO only if a new capability)
- everything else -> Class B+ (full DI/DO/VT chain required)

Phase 8 will create UN/DI/DO/VT entries for the **Class B+ uncovered** set; Class A scripts are listed for awareness only.

## Summary by service

| Service bucket | Class | Files total | Uncovered | LoC uncovered |
|---|---|---|---|---|
| `libs/agent_config` | B+ | 3 | 3 | 255 |
| `libs/analytics` | B+ | 1 | 0 | 0 |
| `libs/audit` | B+ | 4 | 3 | 505 |
| `libs/auth` | B+ | 6 | 2 | 165 |
| `libs/azure` | B+ | 1 | 1 | 33 |
| `libs/classifiers` | B+ | 2 | 2 | 520 |
| `libs/clinical_scoping` | B+ | 1 | 0 | 0 |
| `libs/coding_engine` | B+ | 1 | 0 | 0 |
| `libs/cypher` | B+ | 34 | 17 | 2135 |
| `libs/deid` | B+ | 1 | 1 | 95 |
| `libs/domain_config` | B+ | 1 | 0 | 0 |
| `libs/domains` | B+ | 2 | 0 | 0 |
| `libs/dq` | B+ | 12 | 0 | 0 |
| `libs/episodes` | B+ | 2 | 0 | 0 |
| `libs/exclusion_detector` | B+ | 1 | 0 | 0 |
| `libs/keyvault` | B+ | 1 | 0 | 0 |
| `libs/llm_client` | B+ | 11 | 2 | 258 |
| `libs/llm_usage.py` | B+ | 1 | 1 | 163 |
| `libs/message_bus` | B+ | 4 | 1 | 69 |
| `libs/metrics` | B+ | 1 | 0 | 0 |
| `libs/model_registry` | B+ | 4 | 4 | 1394 |
| `libs/model_store` | B+ | 1 | 1 | 373 |
| `libs/neo4j_client` | B+ | 1 | 0 | 0 |
| `libs/ner` | B+ | 17 | 8 | 2082 |
| `libs/nlp` | B+ | 2 | 1 | 52 |
| `libs/ods` | B+ | 1 | 1 | 173 |
| `libs/pipeline` | B+ | 4 | 2 | 302 |
| `libs/pipeline_graph` | B+ | 31 | 0 | 0 |
| `libs/prompts` | B+ | 52 | 30 | 4871 |
| `libs/redis_client` | B+ | 3 | 2 | 236 |
| `libs/relations` | B+ | 1 | 0 | 0 |
| `libs/sbar` | B+ | 6 | 0 | 0 |
| `libs/search` | B+ | 1 | 0 | 0 |
| `libs/service_auth` | B+ | 2 | 0 | 0 |
| `libs/staging` | B+ | 2 | 0 | 0 |
| `libs/telemetry` | B+ | 1 | 1 | 97 |
| `libs/terminology` | B+ | 4 | 3 | 346 |
| `libs/training` | B+ | 1 | 1 | 506 |
| `libs/utils` | B+ | 3 | 2 | 375 |
| `libs/work` | B+ | 1 | 0 | 0 |
| `libs/workflow` | B+ | 2 | 0 | 0 |
| `scripts` | A | 540 | 510 | 104948 |
| `services/analysis_worker` | B+ | 34 | 4 | 653 |
| `services/analytics_api` | B+ | 24 | 6 | 1567 |
| `services/api` | B+ | 77 | 1 | 245 |
| `services/coding_worker` | B+ | 8 | 3 | 23 |
| `services/dq_mcp` | B+ | 2 | 0 | 0 |
| `services/fhir_api` | B+ | 17 | 9 | 1727 |
| `services/model_inference` | B+ | 2 | 0 | 0 |
| `services/neo4j_mcp` | B+ | 18 | 15 | 1900 |
| `services/ods_sync` | B+ | 3 | 3 | 485 |
| `services/pipeline_worker` | B+ | 5 | 0 | 0 |
| `services/research_worker` | B+ | 3 | 0 | 0 |
| `services/terminology` | B+ | 14 | 8 | 653 |
| `services/terminology_api` | B+ | 20 | 3 | 205 |
| `services/training_worker` | B+ | 11 | 3 | 378 |
| `services/ui` | B+ | 554 | 0 | 0 |
| **TOTAL** |  | **1562** | **654** (42%) | **127789** |
| **CLASS B+ TOTAL** |  |  | **144** | **22841** |

## Class B+ uncovered files (Phase 8 candidates)

### libs/agent_config

- `libs/agent_config/models.py` (119 loc)
- `libs/agent_config/store.py` (78 loc)
- `libs/agent_config/loader.py` (58 loc)

### libs/audit

- `libs/audit/kg_verified_writeback.py` (195 loc)
- `libs/audit/escalation.py` (171 loc)
- `libs/audit/security_log.py` (139 loc)

### libs/auth

- `libs/auth/role_state.py` (126 loc)
- `libs/auth/service_auth.py` (39 loc)

### libs/azure

- `libs/azure/credentials.py` (33 loc)

### libs/classifiers

- `libs/classifiers/encounter_classifier.py` (311 loc)
- `libs/classifiers/encounter_textcat.py` (209 loc)

### libs/cypher

- `libs/cypher/label_verification_queries.py` (231 loc)
- `libs/cypher/cleanup_queries.py` (224 loc)
- `libs/cypher/synthetic_candidate_queries.py` (209 loc)
- `libs/cypher/training_label_queries.py` (184 loc)
- `libs/cypher/candidate_queries.py` (172 loc)
- `libs/cypher/anchor_review_queries.py` (164 loc)
- `libs/cypher/device_queries.py` (140 loc)
- `libs/cypher/classification_vote_queries.py` (136 loc)
- `libs/cypher/reference_range_queries.py` (113 loc)
- `libs/cypher/preset_queries.py` (105 loc)
- `libs/cypher/exclusion_queries.py` (92 loc)
- `libs/cypher/model_registry_queries.py` (87 loc)
- `libs/cypher/post_processor_rule_queries.py` (70 loc)
- `libs/cypher/role_queries.py` (68 loc)
- `libs/cypher/service_config_queries.py` (53 loc)
- `libs/cypher/phrase_consistency_queries.py` (44 loc)
- `libs/cypher/terminology_queries.py` (43 loc)

### libs/deid

- `libs/deid/deid.py` (95 loc)

### libs/llm_client

- `libs/llm_client/cache.py` (161 loc)
- `libs/llm_client/bedrock_retry.py` (97 loc)

### libs/llm_usage.py

- `libs/llm_usage.py` (163 loc)

### libs/message_bus

- `libs/message_bus/in_memory_adapter.py` (69 loc)

### libs/model_registry

- `libs/model_registry/registry.py` (498 loc)
- `libs/model_registry/neo4j_registry.py` (435 loc)
- `libs/model_registry/training_adapter.py` (232 loc)
- `libs/model_registry/manifest_reader.py` (229 loc)

### libs/model_store

- `libs/model_store/store.py` (373 loc)

### libs/ner

- `libs/ner/lab_triple_recovery.py` (465 loc)
- `libs/ner/domain_loader.py` (387 loc)
- `libs/ner/observable_post_processor.py` (330 loc)
- `libs/ner/seed_ingester.py` (276 loc)
- `libs/ner/deid_validator.py` (226 loc)
- `libs/ner/training_label_writer.py` (171 loc)
- `libs/ner/post_processor_rules.py` (157 loc)
- `libs/ner/span_finder.py` (70 loc)

### libs/nlp

- `libs/nlp/assertion_inference.py` (52 loc)

### libs/ods

- `libs/ods/client.py` (173 loc)

### libs/pipeline

- `libs/pipeline/label_filter.py` (215 loc)
- `libs/pipeline/extraction_response_parse.py` (87 loc)

### libs/prompts

- `libs/prompts/extraction_examples.py` (521 loc)
- `libs/prompts/guidance_rule_extraction_v1.py` (393 loc)
- `libs/prompts/label_verification_examples.py` (303 loc)
- `libs/prompts/label_disambiguation_examples.py` (291 loc)
- `libs/prompts/guidance_rule_code_verifier_v1.py` (258 loc)
- `libs/prompts/synthetic_ner_sentences.py` (220 loc)
- `libs/prompts/few_shot_builder.py` (207 loc)
- `libs/prompts/disambiguation_examples.py` (200 loc)
- `libs/prompts/extraction_output_schema.py` (195 loc)
- `libs/prompts/exclusion_detect_examples.py` (191 loc)
- `libs/prompts/guidance_rule_extraction_output_schema.py` (191 loc)
- `libs/prompts/episode_builder_examples.py` (185 loc)
- `libs/prompts/encounter_classify_examples.py` (164 loc)
- `libs/prompts/anchor_domain_review_examples.py` (155 loc)
- `libs/prompts/label_verification_output_schema.py` (142 loc)
- `libs/prompts/model_training_labels.py` (129 loc)
- `libs/prompts/anchor_domain_review_output_schema.py` (126 loc)
- `libs/prompts/episode_builder_output_schema.py` (117 loc)
- `libs/prompts/encounter_classify_output_schema.py` (112 loc)
- `libs/prompts/guidance_rule_code_verifier_output_schema.py` (111 loc)
- `libs/prompts/label_disambiguation_output_schema.py` (89 loc)
- `libs/prompts/anchor_domain_review_v1.py` (76 loc)
- `libs/prompts/exclusion_detect_output_schema.py` (76 loc)
- `libs/prompts/encounter_classify_v1.py` (69 loc)
- `libs/prompts/exclusion_detect_v1.py` (69 loc)
- `libs/prompts/disambiguation_output_schema.py` (66 loc)
- `libs/prompts/label_disambiguation_v1.py` (66 loc)
- `libs/prompts/verification_v1.py` (60 loc)
- `libs/prompts/verification_output_schema.py` (55 loc)
- `libs/prompts/verification_examples.py` (34 loc)

### libs/redis_client

- `libs/redis_client/checkpoint.py` (158 loc)
- `libs/redis_client/rebuild_status.py` (78 loc)

### libs/telemetry

- `libs/telemetry/tracing.py` (97 loc)

### libs/terminology

- `libs/terminology/preferred_terms.py` (176 loc)
- `libs/terminology/surface_normalize.py` (89 loc)
- `libs/terminology/semantic_tag.py` (81 loc)

### libs/training

- `libs/training/lab_span_detector.py` (506 loc)

### libs/utils

- `libs/utils/device_resolver.py` (242 loc)
- `libs/utils/logging.py` (133 loc)

### services/analysis_worker

- `services/analysis_worker/app/analyzers/episode_builder/_first_presentation.py` (305 loc)
- `services/analysis_worker/app/episode_engine/writer_rollups.py` (196 loc)
- `services/analysis_worker/app/episode_engine/agents/audit_guards.py` (105 loc)
- `services/analysis_worker/app/episode_engine/state.py` (47 loc)

### services/analytics_api

- `services/analytics_api/app/services/algorithm_runner_condition.py` (450 loc)
- `services/analytics_api/app/services/algorithm_runner_helpers.py` (323 loc)
- `services/analytics_api/app/routers/_audit_helpers.py` (260 loc)
- `services/analytics_api/app/services/algorithm_runner_patient.py` (250 loc)
- `services/analytics_api/app/routers/_audit_comorbidities.py` (169 loc)
- `services/analytics_api/app/routers/org_context.py` (115 loc)

### services/api

- `services/api/app/models/contracts.py` (245 loc)

### services/coding_worker

- `services/coding_worker/app/pipeline/providers/llm_provider.py` (21 loc)
- `services/coding_worker/app/pipeline/extractor_contract.py` (1 loc)
- `services/coding_worker/app/pipeline/sentence_splitter.py` (1 loc)

### services/fhir_api

- `services/fhir_api/app/services/benchmark_service.py` (566 loc)
- `services/fhir_api/app/services/benchmark_loader.py` (332 loc)
- `services/fhir_api/app/routers/schema.py` (256 loc)
- `services/fhir_api/app/routers/benchmark.py` (214 loc)
- `services/fhir_api/app/routers/activity_definition.py` (114 loc)
- `services/fhir_api/app/main.py` (104 loc)
- `services/fhir_api/app/services/library_service.py` (78 loc)
- `services/fhir_api/app/config/scopes.py` (34 loc)
- `services/fhir_api/app/services/org_resolver.py` (29 loc)

### services/neo4j_mcp

- `services/neo4j_mcp/tools/coded_links.py` (243 loc)
- `services/neo4j_mcp/tools/surface_forms.py` (173 loc)
- `services/neo4j_mcp/tools/patients.py` (172 loc)
- `services/neo4j_mcp/tools/query_pack_escalation.py` (157 loc)
- `services/neo4j_mcp/server.py` (152 loc)
- `services/neo4j_mcp/tools/episodes.py` (152 loc)
- `services/neo4j_mcp/tools/encounter_candidates.py` (144 loc)
- `services/neo4j_mcp/tools/query_pack_training_quality.py` (137 loc)
- `services/neo4j_mcp/tools/llm_usage.py` (134 loc)
- `services/neo4j_mcp/tools/query_pack_config.py` (117 loc)
- `services/neo4j_mcp/_http.py` (108 loc)
- `services/neo4j_mcp/tools/resets.py` (70 loc)
- `services/neo4j_mcp/tools/cypher.py` (64 loc)
- `services/neo4j_mcp/_client.py` (41 loc)
- `services/neo4j_mcp/tools/query_pack_common.py` (36 loc)

### services/ods_sync

- `services/ods_sync/app/sync_service.py` (375 loc)
- `services/ods_sync/app/circuit_breaker.py` (63 loc)
- `services/ods_sync/app/main.py` (47 loc)

### services/terminology

- `services/terminology/scripts/loaders/dmd_drugs.py` (185 loc)
- `services/terminology/scripts/loaders/base.py` (112 loc)
- `services/terminology/scripts/loaders/snomed_attribute_projection.py` (94 loc)
- `services/terminology/scripts/loaders/snomed_description.py` (83 loc)
- `services/terminology/scripts/loaders/snomed_relationship.py` (66 loc)
- `services/terminology/scripts/loaders/snomed_language.py` (60 loc)
- `services/terminology/scripts/loaders/snomed_concept.py` (50 loc)
- `services/terminology/scripts/loaders/__main__.py` (3 loc)

### services/terminology_api

- `services/terminology_api/app/services/text_embedder.py` (108 loc)
- `services/terminology_api/app/queries/valueset.py` (51 loc)
- `services/terminology_api/app/queries/conceptmap.py` (46 loc)

### services/training_worker

- `services/training_worker/app/main.py` (318 loc)
- `services/training_worker/app/spacy_listener_width.py` (41 loc)
- `services/training_worker/app/run_spacy_train_cli.py` (19 loc)

## Class A uncovered files (`scripts/`, informational)

<details><summary>scripts (510 files)</summary>

- `scripts/generate_exclusion_training.py` (4010 loc)
- `scripts/_smart_hitl_lookup.py` (3610 loc)
- `scripts/extract_surface_forms.py` (1740 loc)
- `scripts/investigations/_write_critical_surface_forms.py` (1664 loc)
- `scripts/remediate_hitl_queue.py` (1190 loc)
- `scripts/validate_surface_forms_llm.py` (1096 loc)
- `scripts/remediate_hitl_phase4.py` (1078 loc)
- `scripts/audit_patient_anchors.py` (981 loc)
- `scripts/atlas/phase3_do_vt_migrate.py` (953 loc)
- `scripts/evaluate_training_data.py` (945 loc)
- `scripts/mine_all_domains.py` (922 loc)
- `scripts/atlas/phase4_risk_migrate.py` (861 loc)
- `scripts/expand_surface_forms_llm.py` (797 loc)
- `scripts/remediate_episodes.py` (797 loc)
- `scripts/build_episode_ground_truth.py` (701 loc)
- `scripts/semantic_exclusion_search.py` (677 loc)
- `scripts/investigations/_audit_cancer_procedures.py` (663 loc)
- `scripts/audit_ng12_guidance_coverage.py` (639 loc)
- `scripts/validate_auditor.py` (624 loc)
- `scripts/generate_training_datasets.py` (615 loc)
- `scripts/export_read_to_snomed_jsonl.py` (611 loc)
- `scripts/investigations/_debug_stale_episodes.py` (590 loc)
- `scripts/analyse_referral_episodes.py` (581 loc)
- `scripts/atlas/phase7_reverse_discovery.py` (573 loc)
- `scripts/atlas/phase2_un_di_triage.py` (571 loc)
- `scripts/vnv_anchor_report.py` (564 loc)
- `scripts/investigations/_full_surface_form_audit.py` (546 loc)
- `scripts/investigations/_place_surface_form_audit.py` (536 loc)
- `scripts/prototype_clinical_coder_v2.py` (525 loc)
- `scripts/audit_cancer_status.py` (519 loc)
- `scripts/run_gold_patients.py` (518 loc)
- `scripts/atlas/phase2c_low_confidence_action.py` (516 loc)
- `scripts/investigations/_seed_treatment_domain.py` (512 loc)
- `scripts/explore_cancer_expressions.py` (511 loc)
- `scripts/review_anchor_training.py` (510 loc)
- `scripts/backfill_gold_lab_triples.py` (476 loc)
- `scripts/investigations/_find_snomed_for_missing_forms.py` (476 loc)
- `scripts/reset_and_rebuild_gold_data.py` (467 loc)
- `scripts/investigations/_scan_encounters_for_surface_forms.py` (458 loc)
- `scripts/build_atlas_id_mapping.py` (455 loc)
- `scripts/investigations/_delete_out_of_window_encounters.py` (454 loc)
- `scripts/select_golden_test_set.py` (454 loc)
- `scripts/investigations/_pin_and_writeback_fast_track_referrals.py` (443 loc)
- `scripts/investigations/_fix_wrong_situation_orphans.py` (441 loc)
- `scripts/investigations/_fix_ng12_pins_schema.py` (440 loc)
- `scripts/investigations/_fix_mh_orphan_forms.py` (439 loc)
- `scripts/investigations/_extract_pre_referral_encounters.py` (425 loc)
- `scripts/investigations/surface_form_full_audit.py` (419 loc)
- `scripts/investigations/_run_episodes_and_stats.py` (414 loc)
- `scripts/validate_phrase_annotation_consistency.py` (407 loc)
- _... 460 more omitted_

</details>

