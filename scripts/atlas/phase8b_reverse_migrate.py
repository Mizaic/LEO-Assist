"""
Phase 8b - Reverse Traceability Migration (mutating).

For the 137 truly-uncovered Class B+ files identified by Phase 8a, this
script:

  1. Re-probes Atlas via search_design_controls to skip any DI that already
     exists (race-safe between baseline snapshot and now).
  2. Resolves each bucket to a parent User Need (existing or newly created
     catch-all UN).
  3. Creates the missing DI / DO / VT and links them via:
       UN -[HAS_DESIGN_INPUT]-> DI
       DO -[IMPLEMENTS]-> DI
       VT -[VERIFIES]-> DI
       VT -[TESTS]-> DO
  4. Re-probes and creates the candidate risks (multi-tenant scoping,
     PHI logging discipline) and links them via:
       DI -[MITIGATES]-> Risk

All work is journalled to `design-controls/phase8b-ledger.csv` so re-runs
are idempotent and resume-safe. No bucket is processed twice.

Usage:
  python3 scripts/atlas/phase8b_reverse_migrate.py            # live
  python3 scripts/atlas/phase8b_reverse_migrate.py --dry-run  # plan only
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DC = ROOT / "design-controls"
sys.path.insert(0, str(ROOT))

from scripts.atlas._mcp_transport import call_tool, initialize  # noqa: E402

PRODUCT_ID = "PROD-LEO-CORE-AI-20260415-6AE8A23B"
LEDGER_PATH = DC / "phase8b-ledger.csv"
LEDGER_COLS = [
    "kind",          # un | di | do | vt | risk | link
    "bucket",        # bucket id
    "atlas_id",      # dcId returned (or risk id)
    "atlas_uuid",    # internal uuid where known
    "decision",      # created | reused | skipped
    "note",
    "ts",
]

# ---------------------------------------------------------------------------
# Parent UN catch-alls (created if no existing UN matches)
# ---------------------------------------------------------------------------
PARENT_UNS = {
    "platform_infra": {
        "title": "Platform reliability and infrastructure components",
        "search": "platform infrastructure reliability internal services",
        "description": (
            "As a platform engineer, I need reliable shared infrastructure "
            "components (configuration loaders, audit logging, telemetry, "
            "caches, queues, registries) so the clinical pipeline can run "
            "safely under production load."
        ),
        "stakeholders": ["Developer", "IT Admin"],
        "rationale": (
            "Production stability of clinical software depends on shared "
            "infrastructure. Treating these as first-class design items "
            "ensures they are tested and risk-assessed."
        ),
        "ac": [
            "Each shared infra component has a documented contract",
            "Each component has a verification test in CI",
            "Failure modes for each component are mapped to risks",
        ],
        "priority": "MUST",
    },
    "data_quality": {
        "title": "Read-only Cypher access for data quality and analytics",
        "search": "cypher query helpers read-only data access analytics",
        "description": (
            "As a data quality analyst, I need consistent, parameterised "
            "Cypher query helpers that enforce multi-tenant scoping at the "
            "service layer so downstream analytics and dashboards stay "
            "tenant-safe."
        ),
        "stakeholders": ["Quality Engineer", "Developer"],
        "rationale": (
            "Cypher in scattered ad-hoc strings led to multi-tenant scoping "
            "drift. Centralising query templates with documented scoping "
            "expectations is a control measure."
        ),
        "ac": [
            "All Patient/Encounter MATCH queries declare org_id scoping in "
            "their docstring",
            "Helpers compose with caller-supplied org_id parameters",
            "Library is unit-tested against a synthetic tenanted graph",
        ],
        "priority": "MUST",
    },
    "fhir_exposure": {
        "title": "FHIR resource exposure for downstream interoperability",
        "search": "FHIR resource exposure interop benchmark schema",
        "description": (
            "As a downstream interop developer, I need FHIR R4 endpoints "
            "(ActivityDefinition, Library, PlanDefinition, Schema, "
            "Benchmark) so external systems can consume Leo AI guidance "
            "outputs in a standards-conformant way."
        ),
        "stakeholders": ["Developer", "External Auditor"],
        "rationale": (
            "FHIR interop is required by the NHS DTAC. Exposing canonical "
            "resources avoids bespoke per-vendor adapters."
        ),
        "ac": [
            "ActivityDefinition GET returns FHIR-compliant JSON",
            "Library GET returns FHIR-compliant JSON",
            "Benchmark service emits FHIR-compliant Bundle",
        ],
        "priority": "MUST",
    },
    "mcp_workflows": {
        "title": "MCP server workflows for analyst and reviewer use",
        "search": "MCP server analyst reviewer Neo4j tools",
        "description": (
            "As an analyst, I need a Model Context Protocol (MCP) server "
            "that exposes Neo4j read tools (patients, episodes, encounters, "
            "coded links, surface forms) so I can investigate cohorts from "
            "Cursor/Claude without writing Cypher."
        ),
        "stakeholders": ["Quality Engineer", "Clinician"],
        "rationale": (
            "Direct Neo4j queries are error-prone and bypass tenant scoping. "
            "An MCP layer enforces the read-only contract and standardises "
            "responses for AI assistants."
        ),
        "ac": [
            "MCP server exposes read-only tools only",
            "Every tool documents its input/output schema",
            "Server enforces tenant scope from the caller's session",
        ],
        "priority": "MUST",
    },
    "terminology_loaders": {
        "title": "Terminology loaders for SNOMED, dm+d, OPCS-4, ICD-10",
        "search": "terminology loaders SNOMED dmd OPCS ICD ingestion",
        "description": (
            "As a terminology curator, I need idempotent loaders that ingest "
            "official UK terminology releases (SNOMED CT UK, dm+d, OPCS-4, "
            "ICD-10) into the knowledge graph so downstream coding agents "
            "can map free text to authoritative codes."
        ),
        "stakeholders": ["Knowledge Base Author", "Developer"],
        "rationale": (
            "Terminology drift causes silent coding errors. Versioned "
            "loaders provide a defensible audit trail."
        ),
        "ac": [
            "Each loader records the source release version",
            "Loaders are idempotent on re-run",
            "A failed load leaves the graph in a consistent state",
        ],
        "priority": "MUST",
    },
}

# ---------------------------------------------------------------------------
# Bucket plan
# ---------------------------------------------------------------------------
BUCKETS: list[dict] = [
    {
        "id": "libs/agent_config",
        "parent": "platform_infra",
        "title": "FHIR-based agent configuration registry",
        "shall": (
            "The system shall load AI agent configuration from FHIR Device "
            "resources, exposing prompt templates, valuesets, and feature "
            "flags so clinical operations can change agent behaviour "
            "without a code release."
        ),
        "rationale": (
            "Decouples LLM agent behaviour from compiled code. Lets the "
            "clinical safety team govern prompts via FHIR."
        ),
        "safety_class": "B",
        "files": [
            "libs/agent_config/loader.py",
            "libs/agent_config/models.py",
            "libs/agent_config/store.py",
        ],
        "ac": [
            "AgentConfig.from_device parses Device.code, version, status, properties, prompts",
            "FHIRConfig aggregates agents/valuesets/measures keyed by id",
            "Loader rejects malformed FHIR Device JSON with a clear error",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/audit",
        "parent": "platform_infra",
        "title": "Audit-quality, escalation, and security event logging",
        "shall": (
            "The system shall maintain three durable audit surfaces: "
            "(1) write-back of audit-verified encounters to the knowledge "
            "graph as training data, (2) escalation of unacknowledged safety "
            "alerts on a 48h/14d ladder, and (3) a structured security "
            "event log emitted at WARNING level for SIEM ingestion."
        ),
        "rationale": (
            "Required by IEC 62304 for traceability of clinical decisions, "
            "and by UK GDPR / NHS DSPT for security event auditability."
        ),
        "safety_class": "B",
        "files": [
            "libs/audit/kg_verified_writeback.py",
            "libs/audit/escalation.py",
            "libs/audit/security_log.py",
        ],
        "ac": [
            "kg_verified_writeback persists deidentified encounter text only",
            "escalation marks alerts at >48h level 1 and >14d level 2 with auto-pause",
            "security_log writes single-line JSON at WARNING for every taxonomy event",
        ],
        "candidate_risks": ["raw_phi_logging"],
    },
    {
        "id": "libs/auth",
        "parent": "platform_infra",
        "title": "Service-to-service authentication helper",
        "shall": (
            "The system shall provide a service-to-service authentication "
            "helper that validates inter-service JWTs and surfaces denied "
            "calls through the structured security log."
        ),
        "rationale": (
            "Zero-trust between pods: every internal call must carry and "
            "verify a service JWT to prevent lateral movement."
        ),
        "safety_class": "B",
        "files": ["libs/auth/service_auth.py"],
        "ac": [
            "Helper rejects unsigned or expired JWTs",
            "Denials are logged with the caller service id",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/azure",
        "parent": "platform_infra",
        "title": "Azure managed-identity credential resolver",
        "shall": (
            "The system shall resolve Azure credentials via Managed Identity "
            "in production and DefaultAzureCredential locally so secrets are "
            "never embedded in code or environment variables."
        ),
        "rationale": (
            "Eliminates a class of secret-leak risks; matches the key "
            "management disclosure in the SAD."
        ),
        "safety_class": "B",
        "files": ["libs/azure/credentials.py"],
        "ac": [
            "Returns a Managed Identity token in production",
            "Falls back to DefaultAzureCredential outside production",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/classifiers",
        "parent": "platform_infra",
        "title": "Encounter classifier (NER + spaCy textcat)",
        "shall": (
            "The system shall classify encounters by clinical context using "
            "a hybrid pipeline combining spaCy textcat scores with NER "
            "entity overlap, producing a per-encounter context label set."
        ),
        "rationale": (
            "Encounter context controls downstream extraction prompts and "
            "guidance rule eligibility; a wrong context can suppress safety "
            "alerts."
        ),
        "safety_class": "B",
        "files": [
            "libs/classifiers/encounter_classifier.py",
            "libs/classifiers/encounter_textcat.py",
        ],
        "ac": [
            "Classifier returns a stable label set across runs on the same input",
            "Textcat scores below the configured threshold are suppressed",
        ],
        "candidate_risks": ["missing_org_scope"],
    },
    {
        "id": "libs/cypher",
        "parent": "data_quality",
        "title": "Cypher query helper library (read-side, multi-tenant)",
        "shall": (
            "The system shall provide a centralised library of parameterised "
            "Cypher query helpers covering anchor reviews, candidates, "
            "classification votes, cleanup, devices, exclusions, label "
            "verification, model registry reads, post-processor rules, "
            "presets, phrase consistency, reference ranges, role state, "
            "service config, synthetic candidates, terminology lookups, "
            "and training labels. Each helper documents its expected "
            "tenant-scoping contract for the calling service layer."
        ),
        "rationale": (
            "Centralising Cypher prevents drift in multi-tenant scoping and "
            "keeps query strings under code review."
        ),
        "safety_class": "B",
        "files": [
            "libs/cypher/anchor_review_queries.py",
            "libs/cypher/candidate_queries.py",
            "libs/cypher/classification_vote_queries.py",
            "libs/cypher/cleanup_queries.py",
            "libs/cypher/device_queries.py",
            "libs/cypher/exclusion_queries.py",
            "libs/cypher/label_verification_queries.py",
            "libs/cypher/model_registry_queries.py",
            "libs/cypher/phrase_consistency_queries.py",
            "libs/cypher/post_processor_rule_queries.py",
            "libs/cypher/preset_queries.py",
            "libs/cypher/reference_range_queries.py",
            "libs/cypher/service_config_queries.py",
            "libs/cypher/synthetic_candidate_queries.py",
            "libs/cypher/terminology_queries.py",
            "libs/cypher/training_label_queries.py",
        ],
        "ac": [
            "Every Patient/Encounter MATCH parameterises org_id from the caller",
            "Helpers are unit-tested against a synthetic multi-tenant graph",
            "No helper string-formats user input into a Cypher clause",
        ],
        "candidate_risks": ["missing_org_scope"],
    },
    {
        "id": "libs/deid",
        "parent": "platform_infra",
        "title": "De-identification of clinical text before LLM submission",
        "shall": (
            "The system shall de-identify clinical text by removing direct "
            "identifiers (NHS number, names, dates of birth, addresses, "
            "phone numbers) before any third-party LLM call."
        ),
        "rationale": (
            "UK GDPR and NHS DSPT require minimisation of personal data "
            "exposed to sub-processors."
        ),
        "safety_class": "B",
        "files": ["libs/deid/deid.py"],
        "ac": [
            "NHS numbers, names, DoBs, postcodes, phones are masked",
            "De-id pipeline is unit-tested against a held-out gold set",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/llm_client",
        "parent": "platform_infra",
        "title": "LLM provider cache and Bedrock retry plumbing",
        "shall": (
            "The system shall cache deterministic LLM responses keyed by "
            "(model, prompt-hash) and retry transient Bedrock failures with "
            "exponential backoff while preserving cost telemetry."
        ),
        "rationale": (
            "Reduces per-patient cost and improves latency without changing "
            "model output."
        ),
        "safety_class": "B",
        "files": [
            "libs/llm_client/cache.py",
            "libs/llm_client/bedrock_retry.py",
        ],
        "ac": [
            "Cache hits emit telemetry with cache_read_input_tokens",
            "Retries cap at three attempts and surface the underlying error",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/llm_usage",
        "parent": "platform_infra",
        "title": "LLM usage cost configuration module",
        "shall": (
            "The system shall provide a single LLMCostConfig that encodes "
            "per-model pricing for input, output, and cached tokens so cost "
            "calculations are consistent across pipelines."
        ),
        "rationale": (
            "Pricing drift across services causes incorrect cost reports to "
            "tenants. One config eliminates that class of bug."
        ),
        "safety_class": "B",
        "files": ["libs/llm_usage.py"],
        "ac": [
            "from_env loads pricing from documented env vars with safe defaults",
            "Costs are computed at six-decimal precision",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/message_bus",
        "parent": "platform_infra",
        "title": "In-memory message bus adapter for development and tests",
        "shall": (
            "The system shall provide an in-memory message bus adapter that "
            "satisfies the production bus interface so unit tests and dev "
            "environments do not require Service Bus."
        ),
        "rationale": (
            "Lets CI run without external Azure dependencies; the contract "
            "matches Service Bus exactly to avoid drift."
        ),
        "safety_class": "A",
        "files": ["libs/message_bus/in_memory_adapter.py"],
        "ac": [
            "Adapter implements publish, subscribe, ack, dead-letter",
            "Adapter is interchangeable with the Service Bus adapter under tests",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/model_registry",
        "parent": "platform_infra",
        "title": "Model registry (Neo4j-backed) with manifest and training adapter",
        "shall": (
            "The system shall maintain a Neo4j-backed model registry that "
            "records every trained or imported model with its provenance "
            "(training data id, base model, hyperparameters, evaluation "
            "metrics, signed manifest), and shall serve only registered "
            "models through the training adapter."
        ),
        "rationale": (
            "Required for IEC 62304 software item identification and for "
            "incident triage when a model regression occurs."
        ),
        "safety_class": "B",
        "files": [
            "libs/model_registry/registry.py",
            "libs/model_registry/neo4j_registry.py",
            "libs/model_registry/training_adapter.py",
            "libs/model_registry/manifest_reader.py",
        ],
        "ac": [
            "Registry rejects models without a signed manifest",
            "Manifest records SHA-256 of the model artefact and its training data",
            "Training adapter refuses to use a model not present in the registry",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/model_store",
        "parent": "platform_infra",
        "title": "Model artefact blob store",
        "shall": (
            "The system shall persist trained model artefacts in an Azure "
            "Blob container with content-addressed paths so a manifest "
            "SHA can be verified at load time."
        ),
        "rationale": (
            "Content-addressed storage prevents silent overwrite of a "
            "released model."
        ),
        "safety_class": "B",
        "files": ["libs/model_store/store.py"],
        "ac": [
            "Stored objects are addressed by SHA-256 of the artefact",
            "Reads verify the SHA before returning the bytes",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/ner",
        "parent": "platform_infra",
        "title": "NER post-processing, lab-triple recovery, and seed ingestion",
        "shall": (
            "The system shall apply NER post-processing layers (observable "
            "normalisation, post-processor rules, span finder, training "
            "label writer, deid validator, domain loader, seed ingester) "
            "to extracted entities before they enter the knowledge graph."
        ),
        "rationale": (
            "Raw NER output contains overlapping spans, mis-typed entities, "
            "and partial lab triples. Post-processing is what makes it "
            "downstream-safe."
        ),
        "safety_class": "B",
        "files": [
            "libs/ner/deid_validator.py",
            "libs/ner/domain_loader.py",
            "libs/ner/observable_post_processor.py",
            "libs/ner/post_processor_rules.py",
            "libs/ner/seed_ingester.py",
            "libs/ner/span_finder.py",
            "libs/ner/training_label_writer.py",
        ],
        "ac": [
            "Overlapping entity spans are resolved deterministically",
            "Lab triples (test, value, unit) are linked or rejected",
            "Deid validator blocks any persistence containing direct identifiers",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/nlp",
        "parent": "platform_infra",
        "title": "Assertion inference helper",
        "shall": (
            "The system shall infer the assertion (present, negated, "
            "hypothetical, family, historical) for each extracted entity "
            "using a rules-first then context-engine fallback."
        ),
        "rationale": (
            "An entity asserted as 'family history' must not be coded as a "
            "patient diagnosis."
        ),
        "safety_class": "B",
        "files": ["libs/nlp/assertion_inference.py"],
        "ac": [
            "Negated entities are never auto-coded",
            "Family-history entities never become patient findings",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/ods",
        "parent": "platform_infra",
        "title": "ODS (Organisation Data Service) lookup client",
        "shall": (
            "The system shall fetch organisation metadata (name, type, "
            "active flag) from the NHS ODS API and cache it locally so "
            "tenant onboarding can map a practice ODS code to its display."
        ),
        "rationale": (
            "Authoritative org names prevent reviewer confusion across "
            "similarly named practices."
        ),
        "safety_class": "B",
        "files": ["libs/ods/client.py"],
        "ac": [
            "Returns name, type, active for valid ODS codes",
            "Caches successful responses with a TTL and revalidates",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/pipeline",
        "parent": "platform_infra",
        "title": "Pipeline label filter and extraction-response parser",
        "shall": (
            "The system shall filter LLM extraction labels against the "
            "domain entity-type allowlist and parse extraction responses "
            "into typed Python objects with strict schema validation."
        ),
        "rationale": (
            "Out-of-vocabulary labels must never reach the writeback layer."
        ),
        "safety_class": "B",
        "files": [
            "libs/pipeline/label_filter.py",
            "libs/pipeline/extraction_response_parse.py",
        ],
        "ac": [
            "Unknown entity types are dropped with a warning",
            "Response parser rejects payloads that fail schema validation",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/prompts",
        "parent": "platform_infra",
        "title": "LLM prompt asset registry (templates, examples, output schemas)",
        "shall": (
            "The system shall maintain a versioned registry of LLM prompt "
            "assets: system prompts (extraction, verification, "
            "disambiguation, encounter classification, episode building, "
            "exclusion detection, anchor domain review, guidance rule "
            "extraction, label disambiguation, label verification, model "
            "training labels, synthetic NER), few-shot example sets, and "
            "JSON output schemas. Every prompt and schema carries a "
            "version string."
        ),
        "rationale": (
            "Prompt drift is a silent cause of model regression. Treating "
            "prompts as versioned design outputs makes change auditable."
        ),
        "safety_class": "B",
        "files": [
            "libs/prompts/anchor_domain_review_examples.py",
            "libs/prompts/anchor_domain_review_output_schema.py",
            "libs/prompts/anchor_domain_review_v1.py",
            "libs/prompts/disambiguation_examples.py",
            "libs/prompts/disambiguation_output_schema.py",
            "libs/prompts/encounter_classify_examples.py",
            "libs/prompts/encounter_classify_output_schema.py",
            "libs/prompts/encounter_classify_v1.py",
            "libs/prompts/episode_builder_examples.py",
            "libs/prompts/episode_builder_output_schema.py",
            "libs/prompts/exclusion_detect_examples.py",
            "libs/prompts/exclusion_detect_output_schema.py",
            "libs/prompts/exclusion_detect_v1.py",
            "libs/prompts/extraction_examples.py",
            "libs/prompts/extraction_output_schema.py",
            "libs/prompts/few_shot_builder.py",
            "libs/prompts/guidance_rule_code_verifier_output_schema.py",
            "libs/prompts/guidance_rule_code_verifier_v1.py",
            "libs/prompts/guidance_rule_extraction_output_schema.py",
            "libs/prompts/guidance_rule_extraction_v1.py",
            "libs/prompts/label_disambiguation_examples.py",
            "libs/prompts/label_disambiguation_output_schema.py",
            "libs/prompts/label_disambiguation_v1.py",
            "libs/prompts/label_verification_examples.py",
            "libs/prompts/label_verification_output_schema.py",
            "libs/prompts/model_training_labels.py",
            "libs/prompts/synthetic_ner_sentences.py",
            "libs/prompts/verification_examples.py",
            "libs/prompts/verification_output_schema.py",
            "libs/prompts/verification_v1.py",
        ],
        "ac": [
            "Every prompt module exports a version constant",
            "Output-schema modules validate LLM responses against a Pydantic model",
            "Examples are drawn from the gold-standard labelled dataset",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/redis_client",
        "parent": "platform_infra",
        "title": "Redis-backed checkpoint and rebuild status",
        "shall": (
            "The system shall use Redis to persist long-running pipeline "
            "checkpoints and rebuild status indicators so a worker restart "
            "resumes safely."
        ),
        "rationale": (
            "Without checkpoints a Bedrock outage forces a full pipeline "
            "rerun, costing money and delaying patient results."
        ),
        "safety_class": "B",
        "files": [
            "libs/redis_client/checkpoint.py",
            "libs/redis_client/rebuild_status.py",
        ],
        "ac": [
            "Checkpoints carry a TTL and a worker-id",
            "Rebuild status exposes start/finish/error timestamps",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/telemetry",
        "parent": "platform_infra",
        "title": "OpenTelemetry tracing setup",
        "shall": (
            "The system shall initialise OpenTelemetry tracing on every "
            "service entry point so request flows can be reconstructed "
            "across the API, workers, and Neo4j."
        ),
        "rationale": (
            "Distributed tracing is required for production incident triage."
        ),
        "safety_class": "A",
        "files": ["libs/telemetry/tracing.py"],
        "ac": [
            "Every FastAPI route is auto-instrumented",
            "Trace IDs propagate to outgoing HTTP and Bolt calls",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/terminology",
        "parent": "platform_infra",
        "title": "Terminology preferred-term, surface normalisation, semantic tags",
        "shall": (
            "The system shall canonicalise extracted clinical terms by "
            "applying preferred-term lookup, surface normalisation, and "
            "semantic-tag inference before SNOMED mapping."
        ),
        "rationale": (
            "Surface variation is the dominant cause of missed coding "
            "matches; canonicalisation lifts recall significantly."
        ),
        "safety_class": "B",
        "files": [
            "libs/terminology/preferred_terms.py",
            "libs/terminology/semantic_tag.py",
            "libs/terminology/surface_normalize.py",
        ],
        "ac": [
            "Preferred-term lookup covers the active SNOMED UK release",
            "Surface normalisation is idempotent",
            "Semantic tag inference matches the SNOMED tag for the concept",
        ],
        "candidate_risks": [],
    },
    {
        "id": "libs/utils",
        "parent": "platform_infra",
        "title": "Shared utilities: device resolver and structured logging setup",
        "shall": (
            "The system shall provide shared utility modules for hardware "
            "device resolution (CUDA/MPS/CPU) and for structured JSON "
            "logging configuration so all services log in the same format."
        ),
        "rationale": (
            "Inconsistent logging blocks SIEM ingestion; inconsistent "
            "device choice slows training jobs."
        ),
        "safety_class": "A",
        "files": [
            "libs/utils/device_resolver.py",
            "libs/utils/logging.py",
        ],
        "ac": [
            "Device resolver returns CUDA when available, MPS on Apple, else CPU",
            "Logging setup emits single-line JSON with trace and tenant IDs",
        ],
        "candidate_risks": [],
    },
    {
        "id": "services/analysis_worker",
        "parent": "platform_infra",
        "title": "Episode-engine state and writer rollups for the analysis worker",
        "shall": (
            "The analysis worker shall maintain typed episode-engine state "
            "across LangGraph nodes, compute first-presentation rollups "
            "across encounters, and write per-episode rollups back to the "
            "knowledge graph."
        ),
        "rationale": (
            "Typed state prevents node ordering bugs from silently changing "
            "episode timing fields used in safety alerts."
        ),
        "safety_class": "B",
        "files": [
            "services/analysis_worker/app/episode_engine/state.py",
            "services/analysis_worker/app/analyzers/episode_builder/_first_presentation.py",
            "services/analysis_worker/app/episode_engine/writer_rollups.py",
        ],
        "ac": [
            "Episode-engine state is a Pydantic model with strict types",
            "First-presentation rollups are deterministic for a given input set",
            "Writer rollups are idempotent on re-run",
        ],
        "candidate_risks": [],
    },
    {
        "id": "services/analytics_api",
        "parent": "data_quality",
        "title": "Algorithm runner and audit-helper routers in analytics API",
        "shall": (
            "The analytics API shall expose algorithm-runner endpoints "
            "(condition-level, patient-level, helper utilities) and audit "
            "router helpers (audit helpers, comorbidities, org context) "
            "scoped by the caller's organisation."
        ),
        "rationale": (
            "Centralising analytics logic in one service makes its "
            "tenant-scoping easy to audit."
        ),
        "safety_class": "B",
        "files": [
            "services/analytics_api/app/services/algorithm_runner_condition.py",
            "services/analytics_api/app/services/algorithm_runner_helpers.py",
            "services/analytics_api/app/services/algorithm_runner_patient.py",
            "services/analytics_api/app/routers/_audit_helpers.py",
            "services/analytics_api/app/routers/_audit_comorbidities.py",
            "services/analytics_api/app/routers/org_context.py",
        ],
        "ac": [
            "Every endpoint requires an authenticated session with org scope",
            "Algorithm runners are unit-tested against synthetic patients",
            "Org context resolver returns the caller's tenant or 401",
        ],
        "candidate_risks": ["missing_org_scope"],
    },
    {
        "id": "services/api/contracts",
        "parent": "platform_infra",
        "title": "API request/response contract models",
        "shall": (
            "The API shall define typed Pydantic contract models for every "
            "request and response payload so the OpenAPI schema is "
            "machine-checkable."
        ),
        "rationale": (
            "Contract drift between the UI and API is a frequent source of "
            "regressions; typed contracts catch them at build time."
        ),
        "safety_class": "A",
        "files": ["services/api/app/models/contracts.py"],
        "ac": [
            "All public payloads are Pydantic models",
            "Schemas are exported via FastAPI's OpenAPI generator",
        ],
        "candidate_risks": [],
    },
    {
        "id": "services/fhir_api",
        "parent": "fhir_exposure",
        "title": "FHIR API: ActivityDefinition, Library, PlanDefinition, Schema, Benchmark",
        "shall": (
            "The FHIR API shall expose ActivityDefinition, Library, "
            "PlanDefinition, Schema, and Benchmark resources at versioned "
            "FHIR R4 endpoints, returning conformant JSON and Bundles for "
            "downstream interop."
        ),
        "rationale": (
            "FHIR conformance is required by NHS DTAC and by external "
            "vendors integrating Leo AI guidance outputs."
        ),
        "safety_class": "B",
        "files": [
            "services/fhir_api/app/main.py",
            "services/fhir_api/app/routers/activity_definition.py",
            "services/fhir_api/app/routers/benchmark.py",
            "services/fhir_api/app/routers/schema.py",
            "services/fhir_api/app/services/benchmark_service.py",
            "services/fhir_api/app/services/benchmark_loader.py",
            "services/fhir_api/app/services/library_service.py",
            "services/fhir_api/app/services/org_resolver.py",
            "services/fhir_api/app/config/scopes.py",
        ],
        "ac": [
            "Every endpoint returns FHIR R4-conformant JSON",
            "Org resolver enforces tenant scope from the caller's session",
            "Benchmark service emits a FHIR Bundle with one entry per measure",
        ],
        "candidate_risks": [],
    },
    {
        "id": "services/neo4j_mcp",
        "parent": "mcp_workflows",
        "title": "Neo4j MCP server for analyst and reviewer workflows",
        "shall": (
            "The Neo4j MCP server shall expose read-only tools (patients, "
            "episodes, encounters, coded links, surface forms, LLM usage, "
            "query packs for safety/training-quality/escalation/config/"
            "pathway, encounter candidates, resets, raw cypher) over the "
            "Model Context Protocol so analysts can investigate cohorts "
            "from Cursor or Claude without writing Cypher."
        ),
        "rationale": (
            "Direct database access bypasses tenant scoping and is risky. "
            "An MCP layer enforces the read-only contract and standardises "
            "responses."
        ),
        "safety_class": "B",
        "files": [
            "services/neo4j_mcp/server.py",
            "services/neo4j_mcp/_client.py",
            "services/neo4j_mcp/_http.py",
            "services/neo4j_mcp/tools/coded_links.py",
            "services/neo4j_mcp/tools/cypher.py",
            "services/neo4j_mcp/tools/encounter_candidates.py",
            "services/neo4j_mcp/tools/episodes.py",
            "services/neo4j_mcp/tools/llm_usage.py",
            "services/neo4j_mcp/tools/patients.py",
            "services/neo4j_mcp/tools/query_pack_common.py",
            "services/neo4j_mcp/tools/query_pack_config.py",
            "services/neo4j_mcp/tools/query_pack_escalation.py",
            "services/neo4j_mcp/tools/query_pack_training_quality.py",
            "services/neo4j_mcp/tools/resets.py",
            "services/neo4j_mcp/tools/surface_forms.py",
        ],
        "ac": [
            "Server exposes read-only tools only",
            "Every tool documents its input/output JSON schema",
            "Server enforces tenant scope from the caller's session",
        ],
        "candidate_risks": ["missing_org_scope"],
    },
    {
        "id": "services/ods_sync",
        "parent": "platform_infra",
        "title": "ODS sync worker entry point",
        "shall": (
            "The ODS sync worker shall periodically refresh organisation "
            "metadata from the NHS ODS API and update the knowledge graph."
        ),
        "rationale": (
            "Org metadata changes (mergers, closures); a stale local copy "
            "causes tenant routing errors."
        ),
        "safety_class": "B",
        "files": ["services/ods_sync/app/main.py"],
        "ac": [
            "Worker runs on a schedule with circuit-breaker on API failure",
            "Updates are wrapped in a single transaction per org",
        ],
        "candidate_risks": [],
    },
    {
        "id": "services/terminology",
        "parent": "terminology_loaders",
        "title": "Terminology loaders for SNOMED CT UK, dm+d, OPCS-4, ICD-10",
        "shall": (
            "The terminology service shall provide idempotent loaders for "
            "SNOMED CT UK (concept, description, language, relationship, "
            "attribute projection), dm+d drugs, and the related base loader "
            "primitives. Each loader records the source release version."
        ),
        "rationale": (
            "Versioned ingestion gives a defensible audit trail and lets us "
            "roll back a bad release."
        ),
        "safety_class": "B",
        "files": [
            "services/terminology/scripts/loaders/__main__.py",
            "services/terminology/scripts/loaders/base.py",
            "services/terminology/scripts/loaders/dmd_drugs.py",
            "services/terminology/scripts/loaders/snomed_attribute_projection.py",
            "services/terminology/scripts/loaders/snomed_concept.py",
            "services/terminology/scripts/loaders/snomed_description.py",
            "services/terminology/scripts/loaders/snomed_language.py",
            "services/terminology/scripts/loaders/snomed_relationship.py",
        ],
        "ac": [
            "Every loader records the source release version",
            "Loaders are idempotent on re-run",
            "A failed load leaves the graph in a consistent state",
        ],
        "candidate_risks": [],
    },
    {
        "id": "services/terminology_api",
        "parent": "data_quality",
        "title": "Terminology API: text embedder, ValueSet and ConceptMap queries",
        "shall": (
            "The terminology API shall expose a text-embedder service for "
            "semantic search and Cypher query helpers for FHIR ValueSet and "
            "ConceptMap reads."
        ),
        "rationale": (
            "Centralises text embedding and FHIR resource reads behind a "
            "single tenant-scoped API."
        ),
        "safety_class": "B",
        "files": [
            "services/terminology_api/app/services/text_embedder.py",
            "services/terminology_api/app/queries/valueset.py",
            "services/terminology_api/app/queries/conceptmap.py",
        ],
        "ac": [
            "Text embedder caches embeddings keyed by (model, text-hash)",
            "ValueSet/ConceptMap queries return FHIR R4-conformant JSON",
        ],
        "candidate_risks": [],
    },
    {
        "id": "services/training_worker",
        "parent": "platform_infra",
        "title": "Training worker entry point and spaCy training CLI",
        "shall": (
            "The training worker shall expose a worker entry point and a "
            "spaCy training CLI that runs configured training jobs and "
            "publishes the resulting model to the model registry."
        ),
        "rationale": (
            "Training is the longest-running, costliest workflow; "
            "consolidating its entry points makes monitoring tractable."
        ),
        "safety_class": "B",
        "files": [
            "services/training_worker/app/main.py",
            "services/training_worker/app/run_spacy_train_cli.py",
            "services/training_worker/app/spacy_listener_width.py",
        ],
        "ac": [
            "Worker publishes finished models to the registry with a manifest",
            "CLI fails closed if pricing config is missing",
        ],
        "candidate_risks": [],
    },
]

# ---------------------------------------------------------------------------
# Candidate risks (re-probed against live Atlas before creation)
# ---------------------------------------------------------------------------
CANDIDATE_RISKS: dict[str, dict] = {
    "missing_org_scope": {
        "title": "Cypher helper library returns cross-tenant data when caller omits org_id",
        "search": "multi-tenant cypher org_id scoping helper cross tenant leak",
        "hazard_description": (
            "Cypher query helpers in libs/cypher/ are parameterised on "
            "org_id but rely on the calling service to inject it. A new "
            "caller that wires a helper without supplying org_id receives "
            "results from every tenant in the graph."
        ),
        "hazardous_situation": (
            "A developer adds a new analytics endpoint that calls "
            "libs/cypher/cleanup_queries.py or similar without setting "
            "org_id in the parameter map. The endpoint deploys to "
            "production where it returns patient counts and clinical "
            "summaries from tenants the caller has no contract with."
        ),
        "harm_description": (
            "Disclosure of one tenant's patient cohort sizes, clinical "
            "summaries, or audit findings to staff at another tenant. "
            "UK GDPR Article 9 breach; potential clinical decisions "
            "influenced by data the clinician should not have seen."
        ),
        "harm_severity": "serious",
        "hazard_category": "security_breach",
        "init_sev": 3,
        "init_prob": 2,
        "init_det": 3,
        "control_type": "protective_measure",
        "effectiveness": "effective",
        "monitoring_plan": (
            "Quarterly review of new libs/cypher helpers and the call "
            "sites that consume them. Automated test in CI runs helpers "
            "against a synthetic two-tenant graph and fails the build "
            "if any helper returns data from the wrong tenant."
        ),
        "monitoring_metrics": [
            "Number of new libs/cypher helpers per quarter",
            "Cross-tenant leakage test pass rate",
            "Audit log count of cross-tenant data reads",
        ],
        "review_frequency": "Quarterly",
        "res_sev": 3,
        "res_prob": 1,
        "res_det": 2,
    },
    "raw_phi_logging": {
        "title": "Patient identifier appears in INFO and WARNING log lines",
        "search": "patient identifier logging info warning re-identification",
        "hazard_description": (
            "Several audit, analyzer, and worker modules log patient_id "
            "at INFO or WARNING level. patient_id is an opaque internal "
            "identifier (not NHS number) but, combined with timestamps "
            "and event metadata, it can be used to re-identify a patient "
            "by an operator with log-read access."
        ),
        "hazardous_situation": (
            "An on-call engineer or third-party log analyst correlates "
            "patient_id with audit event timestamps to reconstruct an "
            "individual patient's clinical journey from logs alone."
        ),
        "harm_description": (
            "Re-identification of patients from logs by staff outside "
            "the clinical care team. Breach of UK GDPR data minimisation "
            "and the NHS DSPT log-handling expectations."
        ),
        "harm_severity": "minor",
        "hazard_category": "security_breach",
        "init_sev": 2,
        "init_prob": 2,
        "init_det": 3,
        "control_type": "information_for_safety",
        "effectiveness": "effective",
        "monitoring_plan": (
            "Per-release grep over libs/audit and worker modules for "
            "logger.(info|warning) calls that pass patient_id. CI lint "
            "rule blocks new occurrences."
        ),
        "monitoring_metrics": [
            "Number of INFO/WARNING log lines containing patient_id per release",
            "CI lint failure rate for the pattern",
        ],
        "review_frequency": "Per release",
        "res_sev": 2,
        "res_prob": 1,
        "res_det": 2,
    },
}

# ---------------------------------------------------------------------------
# Ledger helpers (idempotent / resume-safe)
# ---------------------------------------------------------------------------


def load_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    return list(csv.DictReader(LEDGER_PATH.open()))


def append_ledger(rows: list[dict]) -> None:
    new = not LEDGER_PATH.exists()
    with LEDGER_PATH.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLS, lineterminator="\n")
        if new:
            w.writeheader()
        for r in rows:
            r.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            w.writerow({c: r.get(c, "") for c in LEDGER_COLS})


def is_done(ledger: list[dict], kind: str, bucket: str) -> bool:
    return any(
        r["kind"] == kind and r["bucket"] == bucket and r["decision"] in {"created", "reused"}
        for r in ledger
    )


def lookup(ledger: list[dict], kind: str, bucket: str) -> dict | None:
    for r in ledger:
        if r["kind"] == kind and r["bucket"] == bucket and r["decision"] in {"created", "reused"}:
            return r
    return None


# ---------------------------------------------------------------------------
# Atlas helpers
# ---------------------------------------------------------------------------


def search_existing(query: str, dc_type: str, threshold: float = 0.55) -> dict | None:
    """Return best Atlas match above threshold, else None."""
    try:
        out = call_tool(
            "search_design_controls",
            {
                "query": query,
                "dc_type": dc_type,
                "product_id": PRODUCT_ID,
                "limit": 5,
            },
        )
    except Exception as e:
        print(f"  search_design_controls failed: {e}")
        return None
    results = out.get("result", []) if isinstance(out, dict) else []
    best_score = 0.0
    best = None
    for r in results:
        title = r.get("title") or ""
        ratio = SequenceMatcher(None, query.lower(), title.lower()).ratio()
        if ratio > best_score:
            best_score = ratio
            best = r
    if best and best_score >= threshold:
        return {"node": best, "score": best_score}
    return None


def ensure_parent_un(key: str, ledger: list[dict]) -> str:
    """Return the dcId of the parent UN, creating it if needed."""
    bucket = f"un:{key}"
    existing = lookup(ledger, "un", bucket)
    if existing:
        return existing["atlas_id"]
    plan = PARENT_UNS[key]
    found = search_existing(plan["search"], "user-need", threshold=0.55)
    if found:
        dc_id = found["node"].get("dcId", "")
        append_ledger(
            [
                {
                    "kind": "un",
                    "bucket": bucket,
                    "atlas_id": dc_id,
                    "atlas_uuid": found["node"].get("id", ""),
                    "decision": "reused",
                    "note": f"matched existing UN '{found['node'].get('title', '')}' "
                    f"(score {found['score']:.2f})",
                }
            ]
        )
        return dc_id
    out = call_tool(
        "create_user_need",
        {
            "product_id": PRODUCT_ID,
            "title": plan["title"],
            "description": plan["description"],
            "stakeholder_types": plan["stakeholders"],
            "rationale": plan["rationale"],
            "acceptance_criteria": plan["ac"],
            "priority": plan["priority"],
            "safety_class": "B",
        },
    )
    dc_id = out.get("dcId") or out.get("dc_id") or ""
    uid = out.get("id") or ""
    append_ledger(
        [
            {
                "kind": "un",
                "bucket": bucket,
                "atlas_id": dc_id,
                "atlas_uuid": uid,
                "decision": "created",
                "note": plan["title"],
            }
        ]
    )
    return dc_id


def create_di(bucket: dict, parent_un_dcid: str, ledger: list[dict]) -> str:
    bid = bucket["id"]
    existing = lookup(ledger, "di", bid)
    if existing:
        return existing["atlas_id"]
    found = search_existing(bucket["title"], "design-input", threshold=0.65)
    if found:
        dc_id = found["node"].get("dcId", "")
        append_ledger(
            [
                {
                    "kind": "di",
                    "bucket": bid,
                    "atlas_id": dc_id,
                    "atlas_uuid": found["node"].get("id", ""),
                    "decision": "reused",
                    "note": f"matched existing DI '{found['node'].get('title', '')}' "
                    f"(score {found['score']:.2f})",
                }
            ]
        )
        return dc_id
    out = call_tool(
        "create_design_input",
        {
            "product_id": PRODUCT_ID,
            "title": bucket["title"],
            "description": bucket["shall"],
            "rationale": bucket["rationale"],
            "input_type": "Functional",
            "verification_method": "Test",
            "acceptance_criteria": bucket["ac"],
            "safety_class": bucket["safety_class"],
        },
    )
    dc_id = out.get("dcId") or out.get("dc_id") or ""
    uid = out.get("id") or ""
    append_ledger(
        [
            {
                "kind": "di",
                "bucket": bid,
                "atlas_id": dc_id,
                "atlas_uuid": uid,
                "decision": "created",
                "note": bucket["title"],
            }
        ]
    )
    if parent_un_dcid:
        try:
            call_tool(
                "link_design_controls",
                {
                    "source_ids": [parent_un_dcid],
                    "target_ids": [dc_id],
                    "relationship": "HAS_DESIGN_INPUT",
                },
            )
            append_ledger(
                [
                    {
                        "kind": "link",
                        "bucket": bid,
                        "atlas_id": dc_id,
                        "atlas_uuid": "",
                        "decision": "created",
                        "note": f"UN {parent_un_dcid} -[HAS_DESIGN_INPUT]-> DI {dc_id}",
                    }
                ]
            )
        except Exception as e:
            print(f"  link UN->DI failed for {bid}: {e}")
    return dc_id


def create_do(bucket: dict, di_dcid: str, ledger: list[dict]) -> str:
    bid = bucket["id"]
    existing = lookup(ledger, "do", bid)
    if existing:
        return existing["atlas_id"]
    src_block = "; ".join(bucket["files"])
    desc = (
        f"{bucket['shall']}\n\nImplementation files:\n- " + "\n- ".join(bucket["files"])
    )
    out = call_tool(
        "create_design_output",
        {
            "product_id": PRODUCT_ID,
            "title": f"{bucket['title']} (implementation)",
            "description": desc,
            "acceptance_criteria": bucket["ac"],
            "output_type": "software",
            "source_reference": src_block,
            "software_item": bid,
            "safety_class": bucket["safety_class"],
        },
    )
    dc_id = out.get("dcId") or out.get("dc_id") or ""
    uid = out.get("id") or ""
    append_ledger(
        [
            {
                "kind": "do",
                "bucket": bid,
                "atlas_id": dc_id,
                "atlas_uuid": uid,
                "decision": "created",
                "note": f"{len(bucket['files'])} files",
            }
        ]
    )
    if di_dcid:
        try:
            call_tool(
                "link_design_controls",
                {
                    "source_ids": [dc_id],
                    "target_ids": [di_dcid],
                    "relationship": "IMPLEMENTS",
                },
            )
            append_ledger(
                [
                    {
                        "kind": "link",
                        "bucket": bid,
                        "atlas_id": dc_id,
                        "atlas_uuid": "",
                        "decision": "created",
                        "note": f"DO {dc_id} -[IMPLEMENTS]-> DI {di_dcid}",
                    }
                ]
            )
        except Exception as e:
            print(f"  link DO->DI failed for {bid}: {e}")
    return dc_id


def create_vt(bucket: dict, di_dcid: str, do_dcid: str, ledger: list[dict]) -> str:
    bid = bucket["id"]
    existing = lookup(ledger, "vt", bid)
    if existing:
        return existing["atlas_id"]
    out = call_tool(
        "create_verification_test",
        {
            "product_id": PRODUCT_ID,
            "title": f"Verification of {bucket['title']}",
            "description": (
                "Automated unit and integration tests in tests/ that exercise "
                "the implementation files of " + bid + "."
            ),
            "test_type": "unit",
            "verification_method": "Test",
            "acceptance_criteria": bucket["ac"],
            "protocol_steps": [
                "Run pytest against the test paths covering the implementation files",
                "Assert all listed acceptance criteria pass",
                "Record the run via record_verification_run",
            ],
            "safety_class": bucket["safety_class"],
        },
    )
    dc_id = out.get("dcId") or out.get("dc_id") or ""
    uid = out.get("id") or ""
    append_ledger(
        [
            {
                "kind": "vt",
                "bucket": bid,
                "atlas_id": dc_id,
                "atlas_uuid": uid,
                "decision": "created",
                "note": f"shell VT for {bid}",
            }
        ]
    )
    if di_dcid:
        try:
            call_tool(
                "link_design_controls",
                {
                    "source_ids": [dc_id],
                    "target_ids": [di_dcid],
                    "relationship": "VERIFIES",
                },
            )
            append_ledger(
                [
                    {
                        "kind": "link",
                        "bucket": bid,
                        "atlas_id": dc_id,
                        "atlas_uuid": "",
                        "decision": "created",
                        "note": f"VT {dc_id} -[VERIFIES]-> DI {di_dcid}",
                    }
                ]
            )
        except Exception as e:
            print(f"  link VT->DI failed for {bid}: {e}")
    if do_dcid:
        try:
            call_tool(
                "link_design_controls",
                {
                    "source_ids": [dc_id],
                    "target_ids": [do_dcid],
                    "relationship": "TESTS",
                },
            )
            append_ledger(
                [
                    {
                        "kind": "link",
                        "bucket": bid,
                        "atlas_id": dc_id,
                        "atlas_uuid": "",
                        "decision": "created",
                        "note": f"VT {dc_id} -[TESTS]-> DO {do_dcid}",
                    }
                ]
            )
        except Exception as e:
            print(f"  link VT->DO failed for {bid}: {e}")
    return dc_id


def _link_already_logged(ledger: list[dict], bucket: str, note_substr: str) -> bool:
    return any(
        r["kind"] == "link" and r["bucket"] == bucket and note_substr in (r.get("note") or "")
        for r in ledger
    )


def _build_mitigation_plan(plan: dict, di_dcids: list[str]) -> str:
    di_refs = ", ".join(f"[{d}]" for d in di_dcids) or "[DI-ATLAS-pending]"
    return (
        f"Primary control ({plan['control_type']}): The mitigating Design "
        f"Inputs document the contract and require automated tests that "
        f"exercise the failure mode. Implemented by: {di_refs}. Verified "
        f"by: the VERIFIES-linked VTs of those DIs.\n\n"
        f"Information for safety: Engineers reviewing libs/* changes are "
        f"required to follow the design-controls-first.mdc rule which "
        f"references the DIs above.\n\n"
        f"Residual risk acceptance: After the controls above, residual "
        f"risk is acceptable because the failure mode is detectable in "
        f"CI (synthetic test fixtures), and the mitigation is enforced "
        f"by code review against the documented Design Input contracts.\n\n"
        f"Post-market monitoring (DCB0129): {plan['monitoring_plan']} "
        f"Reviewed {plan['review_frequency']} by Engineering Lead, "
        f"escalated to CSO if more than one cross-tenant leakage incident "
        f"is observed in a quarter."
    )


def create_risk(rkey: str, di_dcids: list[str], ledger: list[dict]) -> str:
    bid = f"risk:{rkey}"
    plan = CANDIDATE_RISKS[rkey]
    existing = lookup(ledger, "risk", bid)
    if existing:
        dc_id = existing["atlas_id"]
        for di_id in di_dcids:
            link_note = f"DI {di_id} -[MITIGATES]-> R {dc_id}"
            cur = load_ledger()
            if _link_already_logged(cur, bid, link_note):
                continue
            try:
                call_tool(
                    "link_design_controls",
                    {
                        "source_ids": [di_id],
                        "target_ids": [dc_id],
                        "relationship": "MITIGATES",
                    },
                )
                append_ledger(
                    [
                        {
                            "kind": "link",
                            "bucket": bid,
                            "atlas_id": dc_id,
                            "atlas_uuid": "",
                            "decision": "created",
                            "note": link_note,
                        }
                    ]
                )
            except Exception as e:
                print(f"  link DI->R failed (resume) for {rkey}/{di_id}: {e}")
        # NOTE: update_risk's mitigation_plan_description is rejected by the
        # Atlas server (server-side bug: both canonical and legacy aliases
        # camelCase to mitigationDescription which the PATCH endpoint does
        # not accept). The MITIGATES links above are the authoritative
        # traceability surface; the placeholder text on the Risk's
        # mitigation_plan_description is a known cosmetic issue tracked for
        # platform follow-up. Do not retry here.
        return dc_id
    plan = CANDIDATE_RISKS[rkey]
    found = search_existing(plan["search"], "risk", threshold=0.55)
    if found:
        dc_id = found["node"].get("dcId", "")
        append_ledger(
            [
                {
                    "kind": "risk",
                    "bucket": bid,
                    "atlas_id": dc_id,
                    "atlas_uuid": found["node"].get("id", ""),
                    "decision": "reused",
                    "note": f"matched existing risk '{found['node'].get('title', '')}' "
                    f"(score {found['score']:.2f})",
                }
            ]
        )
    else:
        mitigation = _build_mitigation_plan(plan, di_dcids)
        init_score = plan["init_sev"] * plan["init_prob"] * plan["init_det"]
        res_score = plan["res_sev"] * plan["res_prob"] * plan["res_det"]
        out = call_tool(
            "create_risk",
            {
                "product_id": PRODUCT_ID,
                "title": plan["title"],
                "hazard_description": plan["hazard_description"],
                "hazardous_situation": plan["hazardous_situation"],
                "harm_description": plan["harm_description"],
                "harm_severity": plan["harm_severity"],
                "hazard_category": plan["hazard_category"],
                "initial_severity": plan["init_sev"],
                "initial_probability": plan["init_prob"],
                "initial_detectability": plan["init_det"],
                "initial_risk_score": init_score,
                "mitigation_plan_description": mitigation,
                "mitigation_control_type": plan["control_type"],
                "mitigation_effectiveness": plan["effectiveness"],
                "monitoring_plan": plan["monitoring_plan"],
                "monitoring_metrics": plan["monitoring_metrics"],
                "review_frequency": plan["review_frequency"],
                "residual_severity": plan["res_sev"],
                "residual_probability": plan["res_prob"],
                "residual_detectability": plan["res_det"],
                "residual_risk_score": res_score,
                "residual_acceptability": "acceptable",
                "residual_justification": (
                    "Mitigations reduce probability via documented Design "
                    "Input contracts and CI tests against synthetic fixtures. "
                    "Residual risk is acceptable for IEC 62304 Class B."
                ),
                "identified_by": "Phase 8 reverse-traceability discovery",
                "identified_date": time.strftime("%Y-%m-%d", time.gmtime()),
                "tags": ["reverse-discovery", "phase8"],
                "status": "Analyzed",
                "safety_class": "B",
            },
        )
        dc_id = out.get("dcId") or out.get("dc_id") or ""
        uid = out.get("id") or ""
        append_ledger(
            [
                {
                    "kind": "risk",
                    "bucket": bid,
                    "atlas_id": dc_id,
                    "atlas_uuid": uid,
                    "decision": "created",
                    "note": plan["title"],
                }
            ]
        )
    for di_id in di_dcids:
        try:
            call_tool(
                "link_design_controls",
                {
                    "source_ids": [di_id],
                    "target_ids": [dc_id],
                    "relationship": "MITIGATES",
                },
            )
            append_ledger(
                [
                    {
                        "kind": "link",
                        "bucket": bid,
                        "atlas_id": dc_id,
                        "atlas_uuid": "",
                        "decision": "created",
                        "note": f"DI {di_id} -[MITIGATES]-> R {dc_id}",
                    }
                ]
            )
        except Exception as e:
            print(f"  link DI->R failed for {rkey}/{di_id}: {e}")
    return dc_id


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated bucket IDs to run (default: all)",
    )
    args = parser.parse_args()

    print(f"Phase 8b reverse migrate (dry_run={args.dry_run})")
    print(f"  buckets: {len(BUCKETS)}, candidate risks: {len(CANDIDATE_RISKS)}")

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    selected = [b for b in BUCKETS if not only or b["id"] in only]
    print(f"  selected: {len(selected)} bucket(s)")

    if args.dry_run:
        for b in selected:
            print(f"  - {b['id']}: {b['title']} ({len(b['files'])} files)")
        for rk in CANDIDATE_RISKS:
            print(f"  - candidate risk: {rk} -- {CANDIDATE_RISKS[rk]['title']}")
        return

    initialize()

    # Track which DI dcId is created per risk so we can link them at the end.
    risk_to_di: dict[str, list[str]] = {k: [] for k in CANDIDATE_RISKS}

    for i, bucket in enumerate(selected, 1):
        ledger = load_ledger()
        bid = bucket["id"]
        print(f"\n[{i}/{len(selected)}] Bucket {bid}: {bucket['title']}")
        try:
            un_dcid = ensure_parent_un(bucket["parent"], ledger)
            ledger = load_ledger()
            di_dcid = create_di(bucket, un_dcid, ledger)
            ledger = load_ledger()
            do_dcid = create_do(bucket, di_dcid, ledger)
            ledger = load_ledger()
            vt_dcid = create_vt(bucket, di_dcid, do_dcid, ledger)
            print(
                f"  DI={di_dcid} DO={do_dcid} VT={vt_dcid} "
                f"parent UN={un_dcid}"
            )
            for rk in bucket.get("candidate_risks", []):
                risk_to_di.setdefault(rk, []).append(di_dcid)
        except Exception as e:
            print(f"  ERROR for {bid}: {e}")
            append_ledger(
                [
                    {
                        "kind": "error",
                        "bucket": bid,
                        "atlas_id": "",
                        "atlas_uuid": "",
                        "decision": "failed",
                        "note": str(e)[:300],
                    }
                ]
            )

    # Risks
    for rk, di_ids in risk_to_di.items():
        ledger = load_ledger()
        print(f"\nRisk {rk}: {len(di_ids)} DI(s) to MITIGATES-link")
        try:
            create_risk(rk, di_ids, ledger)
        except Exception as e:
            print(f"  ERROR creating risk {rk}: {e}")
            append_ledger(
                [
                    {
                        "kind": "error",
                        "bucket": f"risk:{rk}",
                        "atlas_id": "",
                        "atlas_uuid": "",
                        "decision": "failed",
                        "note": str(e)[:300],
                    }
                ]
            )

    print("\nDone.")


if __name__ == "__main__":
    main()
