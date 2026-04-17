# Phase 3 -- DI Merge Gap Report (matched DIs)

Generated automatically. For each matched local <-> Atlas DI pair, 
this report flags potential merge gaps. Phase 3 created 37 net-new 
DIs in Atlas with full local content embedded; this report covers 
the additional 109 matched DIs whose Atlas counterparts already 
carry acceptance criteria and require human triage before any 
additive merges.

## Update tool limitations

- `update_design_input` accepts: title, description, AC, input_type,
  verification_method, safety_class. It does NOT accept `rationale`.
- Atlas snapshot exposes `acTotal` count but not full AC strings, so
  detailed AC diffs require per-DI `get_design_control` calls.

## Recommended human action

1. For rows flagged 'local > atlas' on AC, fetch the Atlas DI, diff
   AC sets, and apply additive `update_design_input` with the union.
2. For rows flagged 'safety_class local=...' verify Atlas value via
   `get_design_control` and update where mismatched.
3. Rationale gaps require an Atlas platform change to expose the
   `rationale` field on `update_design_input`. Tracked separately.

## exact matches (9)

| Local ID | Atlas ID | Sim | Title | Notes |
|---|---|---|---|---|
| DI-LEO-AI-001 | DI-143F69EB | 0.650 | Multi-mode encounter shortlisting: keyword, full-text, and vector similarity sea | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-008 | DI-2AFF691F | 0.662 | Automated guideline conformance evaluation on coded encounters | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-030 | DI-155BB31E | 0.867 | Patient data encrypted at rest with AES-256 and in transit with TLS 1.2 minimum | AC: atlas=5 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-054 | DI-54D00E21 | 0.622 | Audit agent resource bounds: configurable iteration limit and token/cost budget  | AC: local=10 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-079 | DI-AE477327 | 0.562 | Training corpus stratification report with safety-critical entity count quality  | AC: local=7 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-107 | DI-6EFD68D0 | 0.686 | Lossless multi-label span export to model training format | AC: local=9 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-114 | DI-80DD8A47 | 0.760 | Configurable single-vs-dual-model LLM consensus runner | AC: local=6 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-115 | DI-F0B8A7B0 | 0.767 | Per-semantic-tag tier thresholds with extractor-confidence fusion | AC: local=6 > atlas=5 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-116 | DI-9D967259 | 0.615 | Disorder gate fail-closed with GATE_FAILED verdict | AC: parity (5); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |

## fuzzy matches (61)

| Local ID | Atlas ID | Sim | Title | Notes |
|---|---|---|---|---|
| DI-LEO-AI-002 | DI-1501326A | 0.314 | Programme inclusion criteria stored as versioned configuration applied without c | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-003 | DI-31126C6C | 0.445 | NER-to-SNOMED entity extraction with confidence score and full provenance metada | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-006 | DI-88C8BBCD | 0.363 | LLM fallback method labelling and threshold configuration for NER coding proposa | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-007 | DI-21E93377 | 0.438 | Safety netting: result-to-reference-range comparison with three-band severity cl | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-010 | DI-37DDAADE | 0.368 | Episode classification status schema (confirmed, excluded, inconclusive) | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-012 | DI-1206D9E8 | 0.481 | Episode temporal quality checks: duration outliers, missing milestones, and sequ | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-013 | DI-F3FD2B63 | 0.360 | Configurable pathway interval calculation and waiting time target breach detecti | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-014 | DI-66F1B177 | 0.300 | Plain-language interpretation of coded findings for reviewers | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-015 | DI-8804DA01 | 0.280 | SBAR: mandatory human review gate before finalisation with AI-original/edit delt | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-016 | DI-1B8AC856 | 0.368 | Coding correction review with dependency and terminology validation | AC: local=9 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-017 | DI-A90B19EB | 0.273 | All pipeline and workflow logic defined as graph data and executed by a single g | AC: atlas=5 > local=4 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-020 | DI-87CCCB18 | 0.312 | Multi-tenancy: tenant token validation before query execution with architectural | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-022 | DI-B46AD5CE | 0.333 | Safety netting: immutable action recording with clinician identity and timestamp | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-023 | DI-84F44836 | 0.381 | Physical separation of patient data and terminology data into distinct database  | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-024 | DI-6079EC71 | 0.282 | Non-blocking investigation deviation acknowledgement with logged rationale and v | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-026 | DI-FE3FFE50 | 0.274 | Cohort builder: rule-based inclusion/exclusion across coded entities, pathway st | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-027 | DI-94359E76 | 0.489 | IMD deprivation analysis panel for pathway performance with health equity monito | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=A; Atlas not exposed in snapshot |
| DI-LEO-AI-028 | DI-35494904 | 0.274 | Waiting time target performance panel (FDS 28d, DTT 31d, RTT 62d) with breach hi | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=A; Atlas not exposed in snapshot |
| DI-LEO-AI-031 | DI-710D5213 | 0.375 | FHIR R4: coded findings as Observation, milestones as EpisodeOfCare, audit resul | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=A; Atlas not exposed in snapshot |
| DI-LEO-AI-032 | DI-1795254D | 0.294 | FHIR R4 compliant API for all patient record ingestion and audit result export | AC: atlas=5 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-040 | DI-922114AE | 0.269 | Safety gate: SNOMED coding defects in training labels always routed to human rev | AC: local=9 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-042 | DI-375C7EB1 | 0.404 | Assertion context label and evidence display on SNOMED coding review card | AC: local=20 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-048 | DI-30D9CC61 | 0.261 | SBAR: AI-generated structured summary from coded encounters, pathway stage, and  | AC: local=11 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-049 | DI-5EECDA58 | 0.300 | Reviewer self-approval prevention and administrator-only credential profile mana | AC: local=11 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-050 | DI-3FDBB57B | 0.310 | Unified LangGraph coding agent as the single execution path for all coding and p | AC: local=6 > atlas=5 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-051 | DI-990C0AFA | 0.250 | Versioned error reference table with three-category classification and remediati | AC: atlas=4 > local=0 -> Atlas richer; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-052 | DI-E6A32FF5 | 0.250 | DQ sitrep dashboard: pass rate aggregation by rule/programme/tenant with trend a | AC: atlas=4 > local=0 -> Atlas richer; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-053 | DI-C899D282 | 0.324 | LLM semantic tag scope constraint to validated NER model output set | AC: local=10 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-063 | DI-693FFEEA | 0.261 | Async fire-and-track job pattern with consistent status model for all long-runni | AC: atlas=5 > local=0 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-066 | DI-0C8FBAF7 | 0.320 | Change history pattern surfacing and systematic guideline divergence flagging in | AC: local=17 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-067 | DI-9FD54AD6 | 0.333 | Surface form change gate: staging, review approval, versioning, and rollback | AC: local=12 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-068 | DI-19B08FFC | 0.481 | Per-tenant AI usage accounting and configurable commercial rates | AC: local=14 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=A; Atlas not exposed in snapshot |
| DI-LEO-AI-069 | DI-2C56591B | 0.278 | AI model configurations stored as graph nodes with runtime resolution and no har | AC: local=6 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=A; Atlas not exposed in snapshot |
| DI-LEO-AI-073 | DI-1126FFD1 | 0.378 | Continuous coding quality metrics with regression alerting | AC: local=7 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-074 | DI-5E1BA369 | 0.489 | Overcoded encounter urgent review queue with SLA and escalation | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-077 | DI-E7AFFDA5 | 0.286 | Span realignment and offset validation on training export with misaligned annota | AC: local=5 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-078 | DI-BB64E479 | 0.468 | De-identified training corpus with immutable holdout separation | AC: local=5 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-081 | DI-6A0B55A4 | 0.297 | Clinical qualifier preservation in LLM extraction for SNOMED specificity | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-083 | DI-30D95132 | 0.307 | Surface form CRUD interface with match frequency display and duplicate rejection | AC: local=7 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-084 | DI-4885D9FF | 0.280 | Episode timeline generation with pathway gap highlighting | AC: local=12 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-089 | DI-FC80B65A | 0.300 | DQ engine: configurable rules with per-episode persistence of pass/fail and reme | AC: local=5 > atlas=3 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-091 | DI-CF03E4EA | 0.294 | Clinic list preparation view with pathway status and comparators | AC: local=11 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-092 | DI-6EA84931 | 0.290 | Deployment status panel on approved change records visible from review interface | AC: local=9 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-093 | DI-B2512CB3 | 0.292 | Immutable source-span linkage and provenance for extracted entities | AC: local=5 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-097 | DI-5A802C83 | 0.267 | Quality regression alert escalation with automatic pipeline pause on unacknowled | AC: local=14 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-103 | DI-48AD06E5 | 0.265 | LLM extractor emits self-rated assertion and confidence per entity | AC: local=6 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-104 | DI-4247C7E5 | 0.276 | HITL gate: SNOMED coding proposals require individual reviewer decision before e | AC: local=7 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-105 | DI-BE09736F | 0.544 | Unified Intelligence Console with stage health and next action | AC: local=7 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=A; Atlas not exposed in snapshot |
| DI-LEO-AI-106 | DI-37B3DC71 | 0.533 | Model improvement cycle with active learning, metrics, golden gate, and warm sta | AC: local=9 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-108 | DI-2D9F5064 | 0.445 | Runtime relation linking method disclosure (model prediction vs LLM fallback) to | AC: local=7 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-109 | DI-58988BF2 | 0.535 | Research workspace single-action structured export with method metadata and no p | AC: local=6 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-110 | DI-9DCBC4BA | 0.509 | Persona lens control reframing workspace language for different user roles witho | AC: local=6 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-112 | DI-A0C90595 | 0.484 | Absolute character-offset resolver for LLM-extracted entities | AC: parity (5); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-113 | DI-F298AE65 | 0.405 | Assertion parity check between LLM extractor and ConText post-processing | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-117 | DI-7A7BFA0C | 0.517 | Terminology hybrid retrieval skips vector search only when top lexical score >=  | AC: atlas=6 > local=5 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=A; Atlas not exposed in snapshot |
| DI-LEO-AI-125 | DI-EE4E6477 | 0.259 | HITL gate: pathway interval calculations use only reviewer-accepted milestone da | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-134 | DI-BA2C8F3E | 0.267 | Population pathway dashboards with national benchmark overlays | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-137 | DI-FF9C74E2 | 0.353 | Deterministic episode construction from related encounters | AC: local=7 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-144 | DI-E7609DD8 | 0.292 | Reference ranges included in content currency dashboard with review status | AC: local=6 > atlas=3 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-146 | DI-3035F221 | 0.357 | Reviewer interface for relation assessment with SNOMED structural policy guidanc | AC: local=6 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-153 | DI-CD931485 | 0.278 | Data-driven audit programme configuration without deployment | AC: local=11 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |

## low-confidence matches (39)

| Local ID | Atlas ID | Sim | Title | Notes |
|---|---|---|---|---|
| DI-LEO-AI-004 | DI-DA7584D8 | 0.217 | Confidence level displayed alongside each AI-generated interpretation | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-005 | DI-9843D732 | 0.241 | NICE catalogue: domain taxonomy classification and three-state coverage status a | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-021 | DI-4DBE1A18 | 0.200 | OAuth2/OIDC-aligned authentication with documented scopes and token lifetimes | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-025 | DI-49403C92 | 0.214 | Post-treatment recovery markers and comparable trajectories | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-029 | DI-620FE631 | 0.217 | End-to-end single-patient pipeline processing within 10 seconds at the 95th perc | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=A; Atlas not exposed in snapshot |
| DI-LEO-AI-034 | DI-4746A178 | 0.188 | Ranked patient shortlist with fused relevance score and supporting evidence span | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-038 | DI-C7A810AA | 0.217 | Low-confidence entity flagging and intra-episode coding contradiction detection | AC: local=11 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-039 | DI-740BE510 | 0.240 | SBAR: source encounter and coded entity provenance links on every clinical state | AC: local=6 > atlas=3 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-043 | DI-425CA252 | 0.200 | Structured override taxonomy capture on every coding correction | AC: local=22 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-045 | DI-F66A7239 | 0.241 | Mandatory pre-LLM de-identification safety gate enforced in LLM client wrapper w | AC: local=9 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-046 | DI-3EA60D5A | 0.200 | Ontology-constrained clinical relation extraction | AC: local=12 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-055 | DI-AF5A1668 | 0.240 | Multi-tenancy: dedicated Neo4j patient graph per tenant with automated provision | AC: local=5 > atlas=3 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-061 | DI-8CE01B3E | 0.197 | Encounter classification: managed rules with per-encounter decision persistence  | AC: local=8 > atlas=3 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-064 | DI-69C29EEF | 0.220 | Clinical significance framing: interpretation content bounded to structured inpu | AC: local=11 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-065 | DI-5E25E872 | 0.217 | Guideline evaluation completion within 5 seconds per patient at p95 | AC: local=8 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-070 | DI-916BD8C8 | 0.182 | Benchmark comparison charts in audit exports | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=A; Atlas not exposed in snapshot |
| DI-LEO-AI-072 | DI-3613871E | 0.200 | Per-programme AI processing kill switch activatable without code deployment | AC: local=8 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-075 | DI-A0579B64 | 0.231 | Episode quality gate: flagged episodes blocked from reporting until flags are re | AC: local=7 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-080 | DI-12015DBC | 0.191 | SNOMED coding accuracy quality gate: minimum F1 0.85 on gold-standard dataset | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-082 | DI-09E26C1D | 0.241 | Audit trail API providing provenance access without clinical record exposure | AC: local=6 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-085 | DI-ED3A89F5 | 0.217 | Guideline monitoring registry under clinical change control with full alert cont | AC: local=5 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-090 | DI-23822663 | 0.182 | Assertion evidence text context stored alongside assertion label | AC: local=5 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-095 | DI-B8674FBF | 0.222 | Sandbox tenant with synthetic data and fault injection controls | AC: local=5 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-096 | DI-702F4583 | 0.235 | Programme configuration hot-reload: changes take effect at next run without serv | AC: local=4 > atlas=3 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-098 | DI-F2C18D2E | 0.217 | UI-only pipeline configuration editing with override gate for failed test mode p | AC: local=8 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-099 | DI-DD67ACFF | 0.208 | Guided population research workspace with plain-English scoping | AC: local=8 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-101 | DI-04105500 | 0.217 | Coding correction request structured display schema (original, replacement, conc | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-120 | DI-B0832A64 | 0.205 | Deprecation and sunset response headers with integrator notification subscriptio | AC: local=7 > atlas=3 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-122 | DI-B95A73E9 | 0.217 | Plain-language coverage indicator explanation reachable in one action | AC: atlas=4 > local=3 -> Atlas richer; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-127 | DI-CE0A08E5 | 0.211 | Per-entity-type precision/recall/F1 metrics stored per training job and accessib | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-129 | DI-D49BCE55 | 0.200 | Structured approval capture with immutable audit and deploy interlock | AC: local=6 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-135 | DI-5E7E8CEF | 0.200 | Global active training job indicator visible from all admin pages | AC: local=5 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=A; Atlas not exposed in snapshot |
| DI-LEO-AI-139 | DI-900CB621 | 0.182 | Prominent data completeness and reliability indicators on clinician outputs | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=A; Atlas not exposed in snapshot |
| DI-LEO-AI-142 | DI-C5A523A7 | 0.220 | Reference range change control gate: activation blocked without approval record | AC: local=7 > atlas=3 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=A; Atlas not exposed in snapshot |
| DI-LEO-AI-145 | DI-080A2454 | 0.192 | Provenance record immutable retention policy enforcement (7-year minimum) | AC: local=5 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-147 | DI-340279C1 | 0.221 | Reference range CRUD: structured entry with mandatory source traceability and un | AC: local=6 > atlas=3 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-148 | DI-553F50A2 | 0.200 | Active SNOMED CT version endpoint for downstream integrator technical file docum | AC: local=8 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-150 | DI-6C5D77CA | 0.188 | Referral triage view with eligibility rules and comparable outcomes | AC: local=6 > atlas=4 -> consider merge; Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
| DI-LEO-AI-154 | DI-A3107424 | 0.192 | Diagnostic and treatment recommendation exclusion from generated interpretations | AC: parity (4); Rationale: local has it; Atlas tool cannot store; safety_class local=B; Atlas not exposed in snapshot |
