# Phase 16 - Cross-batch consolidation

Final consolidation pass of the retrospective DI audit. This pass aggregates
findings from batches 01-15, reconciles orphan DIs/DOs/VTs in Atlas,
enumerates duplicates, captures the risk-register retrofit backlog, and
records the updated traceability-matrix delta.

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`.

## 1. Atlas post-audit state

Source: `get_design_control_stats` on 2026-04-17.

| Artefact class | Count | Linked forward | Gap |
|---|---|---|---|
| User Needs | 73 | 73 -> DI, 1 -> VAL | 72 UNs lack validation linkage |
| Design Inputs | 221 | 84 -> DO, 8 -> VT | 137 DIs have no DO, 213 have no VT |
| Design Outputs | 23 | 23 -> DI, 6 -> VT | 17 DOs not linked to a VT |
| Verification Tests | 6 | 6 -> DI, 6 -> DO | 0 executed / passed |
| Validation Tests | 1 | 1 -> UN, 0 -> DI | Unlinked to DI; not executed |
| Risks | 0 | - | Full ISO 14971 register retrofit required |

## 2. Design Outputs created in this audit

| Batch | DO ID | Title | Themes |
|---|---|---|---|
| 01 | DO-E5A7E6AC | Encoder-engine telemetry + terminology coverage surface | SNOMED coding core |
| 01 | DO-9AE68B76 | Cascade consensus, disambiguator and LLM-as-judge runtime | SNOMED coding core |
| 01 | DO-7B32BAD4 | Terminology coverage + training-candidate telemetry | SNOMED coding core |
| 02 | DO-00820D8E | Deterministic span resolver + provenance persistence | Provenance |
| 02 | DO-7C8F0B06 | Immutable AI invocation logging | Provenance |
| 03 | DO-B49BC77F | ConText rule store with DualPath consistency | ConText rule mgmt |
| 04 | DO-69FC3974 | Multi-label NER schema mapper + normalisation | Multi-label NER |
| 04 | DO-F3A6F414 | Label-verification and training-export lossless writer | Multi-label NER |
| 05 | DO-75760CA6 | Relation linking subgraph with method-tagged model+LLM merge | Relation linking |
| 05 | DO-1EA8DF41 | Relation reviewer UI with policy-aware triplets | Relation linking |
| 07 | DO-FE9B7BFC | Model registry canary lifecycle and promotion gate | Canary rollout |
| 08 | DO-658A0D6F | Surface forms CRUD with duplicate audit + match frequency | Surface forms |
| 10 | DO-3F6D2664 | Per-type review-queue Cypher and role state | Coding correction |
| 11 | DO-3F6D2664 | Per-type review-queue (shared with 10) | Review queue |
| 12 | DO-D1F327CC | Rule-based encounter pre-classification with ClassificationResult | Encounter classification |
| 13 | DO-FFA66218 | SBAR generation subgraph | SBAR |
| 13 | DO-CAEB1411 | Safety-net detector, persistence + pipeline subgraph | Safety netting |
| 13 | DO-29B56008 | Audit-quality API and drift analytics surface | Audit quality |
| 14 | DO-01AB9835 | Episode builder subgraph with classification + DQ | Episodes |
| 14 | DO-4EA9699D | Pathway intervals, waiting times, benchmark + IMD analytics | Pathway analytics |
| 14 | DO-F5BDFD51 | Guideline conformance evaluator and rule extraction | Guideline conformance |
| 15 | DO-E97A7471 | De-identification library + deid validator guard | Data protection |
| 15 | DO-D17B9B10 | Auth, role-state and tenant-scope middleware | AuthN / AuthZ |
| 15 | DO-22BF1090 | Append-only audit emitter and security-event log | Audit trail |

Total new DOs: 23 (matches Atlas `designOutputs.total`).

## 3. Duplication sweep

No DI-level duplicates were surfaced during batch audits 01-15. Two UN/DI
overlaps were noted:

- UN-55011459 (clinical review queue, phase 11) and UN-7D740697 (coding
  correction review, phase 10) both implemented by the same `:CodingReview`
  + role-state surface -> intentionally shared; recorded as a single DO
  (DO-3F6D2664) linked to DIs from both UNs.
- Safety-netting (phase 13) and escalation-threshold DIs (phase 14
  guideline evaluator) both emit alert records; persistence layers kept
  separate per acceptance-criteria semantics, but future consolidation is
  a candidate for a `:ClinicalAlert` super-label.

No Atlas mutation required.

## 4. Orphan sweep

- **Orphan DIs (no DO)**: 137. Most sit under phase-15 umbrella themes
  (auth, FHIR, research workspace, KB currency, ops dashboards) where code
  is partial or missing. Tracked in `improvements-backlog.md`.
- **Orphan DOs (no VT)**: 17 of 23. VT backlog tracked per batch report.
- **Orphan VTs (no execution history)**: 6 of 6. Execution backlog.
- **Orphan UNs (no VAL)**: 72 of 73. Validation backlog.

No bulk Atlas deletion performed; all orphans represent real implementation
state.

## 5. Risk register retrofit

Atlas currently has zero `:Risk` entries. A proper ISO 14971 retrofit
requires, at minimum:

- One risk per Class B/C DI documenting hazard, hazardous situation, harm,
  initial estimate, mitigations (with `implemented_by` -> DIs and
  `verified_by` -> VTs), residual estimate, monitoring, metadata.
- Likely set size: 150-180 risks based on the current DI safety-class
  split once DIs are stamped with safety_class.

Approach (backlogged):

1. Use `design-controls/DC-RM-001-risk-management.md` and
   `design-controls/DC-TM-SEC-001-threat-model.yaml` as seed material.
2. Generate candidate risk payloads per DI using the existing
   `design-controls/risks/generate_atlas_risk_payloads.py` script
   (already in repo) with the full DI roster.
3. Review/amend candidate payloads offline.
4. Fire into Atlas with `fire_atlas_risks.py`, linking each risk to its
   implementing DI(s) and the DO(s) created in this audit.

Open backlog entry:

- `| 2026-04-17 | 16 | atlas-risks | must-build | Retrofit full ISO 14971 risk register across all Class B/C DIs using the existing payload-generation and fire scripts. | design-controls | open |`

## 6. Traceability matrix delta

All 23 new DOs and their IMPLEMENTS links are captured in Atlas via
`link_design_controls` calls recorded in each batch report.

`DC-TM-001-traceability-matrix.md` and `DC-TM-002-traceability-matrix.csv`
have not been individually updated for every new DO: the audit dumped
cumulative state into the Atlas MCP as the source of truth. A single
consolidation PR should snapshot the matrix from Atlas into these files
(tracked as backlog).

Backlog entry:

- `| 2026-04-17 | 16 | DC-TM-001 / DC-TM-002 | must-fix | Regenerate the traceability matrix markdown + CSV from Atlas using the standard export script. | design-controls | open |`

## 7. Rollup of outstanding work

The improvements backlog (`improvements-backlog.md`) is the authoritative
to-do list coming out of this audit. Totals at end of phase 15:

- must-fix: ~9 high-priority items (PHI recall CI, CIA attestation, pathway
  HITL gates, UK Core FHIR validation, tenant DB separation risk record,
  regulator export endpoint, post-approval artefact freeze, DC-TM refresh,
  audit-queue HITL gates for training-label audit).
- must-build: ~12 larger pieces of functionality (training-label audit
  agent, ICD-10/OPCS release diffing, SBAR finalisation gate, MDT summary
  editability, structured treatment display, cohort CRUD completion, full
  ISO 14971 risk register retrofit, and similar).
- should-fix: ~10 smaller improvements (docs, UI polish, KB currency
  dashboard, active learning warm-start, benchmark chart embedding, async
  job contract uniformity, etc.).

## 8. Audit trail

- Batches 01-15 committed as `design-controls/audits/batch-NN.md` with
  per-DI verdict summaries and Atlas action logs.
- Atlas state queried pre- and post-audit; `DO` count rose from 0 to 23;
  DI `linkedToDO` rose from 0 to 84.
- Code improvements landed in:
  - `libs/ner/span_resolver.py` (new deterministic span resolver)
  - `libs/pipeline/consensus.py` (cascade consensus result shape)
  - `libs/pipeline/terminology.py` / terminology resolver updates
  - `libs/llm_client/disorder_verifier.py` (fail-closed `GATE_FAILED`)
  - `libs/ner/context_engine.py`, `libs/ner/assertion.py`
    (assertion parity flag)
  - `libs/pipeline_graph/subgraphs/relation_linking.py`
    (method-tagged relation merge)
  - `libs/ner/schema_mapper.py` deduplication key update
  - `libs/pipeline/post_processing.py` shared post-processing surface
  - plus smaller cleanups across training and pipeline surfaces.

This retrospective audit is now complete.
