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
]

CODING_SCHEMA_CONSTRAINTS: list[str] = [
    'CREATE FULLTEXT INDEX surface_form_fulltext IF NOT EXISTS FOR (sf:SurfaceForm) ON EACH [sf.form]',
    "CREATE CONSTRAINT surface_form_normalized IF NOT EXISTS FOR (sf:SurfaceForm) REQUIRE sf.normalized IS UNIQUE",
]
