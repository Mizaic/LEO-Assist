"""Schema constraints and indexes for Neo4j databases.

Centralised from services/api/app/models/neo4j_schema.py.
Includes missing indexes for EncounterCandidate properties identified during audit.
"""

PATIENT_SCHEMA_CONSTRAINTS = [
    "CREATE CONSTRAINT encounter_candidate_id IF NOT EXISTS FOR (c:EncounterCandidate) REQUIRE c.candidate_id IS UNIQUE",
    "CREATE CONSTRAINT review_task_id IF NOT EXISTS FOR (t:ReviewTask) REQUIRE t.task_id IS UNIQUE",
    "CREATE CONSTRAINT approval_id IF NOT EXISTS FOR (a:Approval) REQUIRE a.approval_id IS UNIQUE",
    "CREATE CONSTRAINT change_id IF NOT EXISTS FOR (chg:Change) REQUIRE chg.change_id IS UNIQUE",
    "CREATE INDEX review_task_status IF NOT EXISTS FOR (t:ReviewTask) ON (t.status)",
    "CREATE INDEX review_task_priority IF NOT EXISTS FOR (t:ReviewTask) ON (t.priority)",
    "CREATE CONSTRAINT game_score_id IF NOT EXISTS FOR (gs:GameScore) REQUIRE gs.id IS UNIQUE",
    "CREATE INDEX game_score_game IF NOT EXISTS FOR (gs:GameScore) ON (gs.game)",
    # Multi-tenancy indexes
    "CREATE INDEX patient_tenant IF NOT EXISTS FOR (p:Patient) ON (p.tenantId)",
    "CREATE INDEX encounter_candidate_tenant IF NOT EXISTS FOR (c:EncounterCandidate) ON (c.tenantId)",
    "CREATE INDEX review_task_tenant IF NOT EXISTS FOR (t:ReviewTask) ON (t.tenantId)",
    "CREATE INDEX organization_id IF NOT EXISTS FOR (o:Organization) ON (o.id)",
    # Missing indexes for EncounterCandidate lookups
    "CREATE INDEX encounter_candidate_patient IF NOT EXISTS FOR (c:EncounterCandidate) ON (c.patient_id)",
    "CREATE INDEX encounter_candidate_encounter IF NOT EXISTS FOR (c:EncounterCandidate) ON (c.encounter_id)",
    "CREATE INDEX encounter_candidate_approval IF NOT EXISTS FOR (c:EncounterCandidate) ON (c.approval_status)",
    # Post-M1 labels
    "CREATE INDEX safety_net_alert_id IF NOT EXISTS FOR (n:SafetyNetAlert) ON (n.alert_id)",
    "CREATE INDEX episode_of_care_id IF NOT EXISTS FOR (n:EpisodeOfCare) ON (n.episode_id)",
    # Model registry (NER pipeline manifests)
    "CREATE CONSTRAINT model_version_id IF NOT EXISTS FOR (m:ModelVersion) REQUIRE m.version IS UNIQUE",
    "CREATE CONSTRAINT model_registry_config_id IF NOT EXISTS FOR (c:ModelRegistryConfig) REQUIRE c.id IS UNIQUE",
    # Tenant management
    "CREATE CONSTRAINT group_id IF NOT EXISTS FOR (g:Group) REQUIRE g.id IS UNIQUE",
    "CREATE CONSTRAINT role_name IF NOT EXISTS FOR (r:Role) REQUIRE r.name IS UNIQUE",
    "CREATE CONSTRAINT system_config_id IF NOT EXISTS FOR (sc:SystemConfig) REQUIRE sc.id IS UNIQUE",
    "CREATE CONSTRAINT practitioner_id IF NOT EXISTS FOR (pr:Practitioner) REQUIRE pr.id IS UNIQUE",
    "CREATE INDEX practitioner_email IF NOT EXISTS FOR (pr:Practitioner) ON (pr.email)",
    "CREATE INDEX group_org_id IF NOT EXISTS FOR (g:Group) ON (g.org_id)",
    # PCN (Primary Care Network) — new org tier between ICB and GP Practice
    "CREATE CONSTRAINT pcn_id IF NOT EXISTS FOR (p:PCN) REQUIRE p.id IS UNIQUE",
    "CREATE INDEX pcn_ods_code IF NOT EXISTS FOR (p:PCN) ON (p.odsCode)",
    # Subscription — linked to Organization nodes
    "CREATE CONSTRAINT subscription_id IF NOT EXISTS FOR (s:Subscription) REQUIRE s.id IS UNIQUE",
    "CREATE INDEX subscription_org_id IF NOT EXISTS FOR (s:Subscription) ON (s.org_id)",
    # ODS sync tracking indexes
    "CREATE INDEX organization_ods_code IF NOT EXISTS FOR (o:Organization) ON (o.odsCode)",
    "CREATE INDEX organization_ods_sync_status IF NOT EXISTS FOR (o:Organization) ON (o.ods_sync_status)",
    "CREATE INDEX organization_entra_tenant IF NOT EXISTS FOR (o:Organization) ON (o.entra_tenant_id)",
    "CREATE INDEX organization_onboarding_status IF NOT EXISTS FOR (o:Organization) ON (o.onboarding_status)",
    # PromptConfig — LLM prompt management
    "CREATE CONSTRAINT prompt_config_id IF NOT EXISTS FOR (p:PromptConfig) REQUIRE p.id IS UNIQUE",
    "CREATE INDEX prompt_config_name IF NOT EXISTS FOR (p:PromptConfig) ON (p.name, p.version)",
    # Reference ranges for abnormal lab result classification
    "CREATE CONSTRAINT reference_range_id IF NOT EXISTS FOR (r:ReferenceRange) REQUIRE r.range_id IS UNIQUE",
    "CREATE INDEX reference_range_concept IF NOT EXISTS FOR (r:ReferenceRange) ON (r.conceptId)",
    "CREATE INDEX reference_range_org IF NOT EXISTS FOR (r:ReferenceRange) ON (r.org_id)",
    # Three learning loops — Loop 1 audit nodes (Sprint 1)
    "CREATE CONSTRAINT audit_run_id IF NOT EXISTS FOR (a:AuditRun) REQUIRE a.run_id IS UNIQUE",
    "CREATE INDEX audit_run_status IF NOT EXISTS FOR (a:AuditRun) ON (a.status)",
    "CREATE CONSTRAINT drift_metric_id IF NOT EXISTS FOR (d:DriftMetric) REQUIRE d.metric_id IS UNIQUE",
    "CREATE CONSTRAINT loop_config_id IF NOT EXISTS FOR (c:LoopConfig) REQUIRE c.loop_id IS UNIQUE",
]

CODING_SCHEMA_CONSTRAINTS: list[str] = [
    'CREATE FULLTEXT INDEX surface_form_fulltext IF NOT EXISTS FOR (sf:SurfaceForm) ON EACH [sf.form]',
    "CREATE CONSTRAINT surface_form_normalized IF NOT EXISTS FOR (sf:SurfaceForm) REQUIRE sf.normalized IS UNIQUE",
    "CREATE CONSTRAINT coding_decision_id IF NOT EXISTS FOR (d:CodingDecision) REQUIRE d.decision_id IS UNIQUE",
    "CREATE INDEX coding_decision_encounter IF NOT EXISTS FOR (d:CodingDecision) ON (d.encounter_id)",
    "CREATE INDEX coding_decision_decision IF NOT EXISTS FOR (d:CodingDecision) ON (d.decision)",
    # GDPR-isolated learning-loop schemas
    "CREATE CONSTRAINT training_candidate_id IF NOT EXISTS FOR (c:TrainingCandidate) REQUIRE c.candidate_id IS UNIQUE",
    "CREATE INDEX training_candidate_status IF NOT EXISTS FOR (c:TrainingCandidate) ON (c.status)",
    "CREATE INDEX training_candidate_source IF NOT EXISTS FOR (c:TrainingCandidate) ON (c.source)",
    "CREATE CONSTRAINT gold_label_id IF NOT EXISTS FOR (g:GoldLabel) REQUIRE g.label_id IS UNIQUE",
    "CREATE INDEX gold_label_source IF NOT EXISTS FOR (g:GoldLabel) ON (g.source)",
    "CREATE INDEX gold_label_candidate IF NOT EXISTS FOR (g:GoldLabel) ON (g.candidate_id)",
    "CREATE CONSTRAINT surface_form_task_id IF NOT EXISTS FOR (t:SurfaceFormTask) REQUIRE t.task_id IS UNIQUE",
    "CREATE INDEX surface_form_task_status IF NOT EXISTS FOR (t:SurfaceFormTask) ON (t.status)",
]
