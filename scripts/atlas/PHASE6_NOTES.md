# Phase 6 - Software Architecture Document (SAD) consolidation

Status: COMPLETED
Date: 2026-04-19
Atlas SAD ID: `b1680b16-e977-418e-981e-ecd17d1f07a7`
Atlas product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`

## Goal

Consolidate the local architecture, safety classification, retention,
key management, threat model, and data schema documents into the single
Atlas Software Architecture Document (SAD) for the product, then move the
SAD to `approved` via `finalise_sad`.

## Sources consolidated

The following local documents were the input material for the SAD
sections. The technical content was rewritten into nurse-friendly plain
English (UK reading age 11) and merged into the six SAD sections in
Atlas. The originals will be moved to `compliance/` in Phase 10 (the
governance / policy versions remain useful as standalone evidence
documents).

| Local source | Section(s) populated in Atlas SAD |
|---|---|
| `design-controls/DC-ARCH-001-system-architecture.md` | architecture_overview, component_descriptions, interface_design |
| `design-controls/DC-SC-001-safety-classification.md` | architecture_overview ("Why it is built this way"), error_handling (foreseeable misuse), security_design |
| `design-controls/DC-RET-001-retention-schedule.md` | data_design (retention table + deletion process) |
| `design-controls/DC-KM-001-key-management-disclosure.md` | security_design (encryption table, Key Vault layout, secret rotation, pen test findings) |
| `design-controls/DC-TM-SEC-001-threat-model.yaml` | security_design (background); error_handling (mitigated failure modes) |
| `design-controls/DC-TM-SEC-002-threat-model.yaml` | security_design (zero-trust between pods, session hardening); error_handling (failure-to-risk mapping) |
| `design-controls/neo4j-nlp-terminology-schema.md` | data_design (records and relationships ER diagram, knowledge-graph description) |

## SAD section coverage

All six SAD sections are non-empty and approved:

1. `architecture_overview` -- 1 flowchart with 8+ named components, plus the audit-pipeline narrative.
2. `component_descriptions` -- one bullet per piece across UI, pipeline, data stores, and platform; plus a flowchart of where each piece lives.
3. `interface_design` -- table of every public + internal door, plus a sequenceDiagram of one complete coding journey.
4. `data_design` -- erDiagram of records, residency table, retention table, deletion process, residency picture (UK vs EEA).
5. `security_design` -- login sequenceDiagram, multi-tenant isolation, RBAC matrix, encryption table, Key Vault layout, secret rotation, pen test findings, LLM data minimisation.
6. `error_handling` -- four fail-safe rules and a table of 18 foreseeable failures, each linked to one or more Atlas risks (`R-XXX` dcIds).

## Linked design inputs (referenced by dcId in the SAD body)

`DI-87CCCB18`, `DI-84F44836`, `DI-31126C6C`, `DI-88C8BBCD`,
`DI-8804DA01`, `DI-1795254D`, `DI-C022E32C`, `DI-4DBE1A18`,
`DI-155BB31E`, `DI-B46AD5CE`, `DI-FE3FFE50`, `DI-35494904`,
`DI-94359E76`.

## Linked risks (referenced by dcId in `error_handling`)

`R-AEC97089` (LLM provider outage), `R-CA4C7579` (LLM consensus
failure), `R-25D42C4D` (incorrect SNOMED coding from NLP), `R-E1546339`
(data corruption from partial pipeline write), `R-BC8B783A`
(cross-tenant exposure / availability), `R-A49DE526` (unauthorised
access / privilege escalation / DoS), `R-867BC40C` (automation bias),
`R-7A310BD5` (degraded model accuracy), `R-EF36D546` (supply chain),
`R-112B76FC` (leaked or stale credentials), `R-D835A836` (failure to
complete subject erasure within statutory window).

## Finalisation

`finalise_sad` accepted the SAD on the first attempt. The SAD is
now `status: approved`. Any future edits will create a new draft
version (the QMS API auto-versions and field-change-audits every
update).

## Local files to be moved (Phase 10)

These are governance / policy documents that are useful as standalone
audit evidence and do not belong inside the SAD. They will be moved
under the new `compliance/` directory in Phase 10:

- `DC-ARCH-001-system-architecture.md` -> `compliance/architecture/dc-arch-001-system-architecture.md` (kept as DTAC TA01 evidence; the SAD is now the authoritative architecture record)
- `DC-SC-001-safety-classification.md` -> `compliance/safety/dc-sc-001-safety-classification.md`
- `DC-RET-001-retention-schedule.md` -> `compliance/data-protection/dc-ret-001-retention-schedule.md`
- `DC-KM-001-key-management-disclosure.md` -> `compliance/policies/dc-km-001-key-management.md`
- `DC-TM-SEC-001-threat-model.yaml` -> `compliance/security/dc-tm-sec-001-threat-model.yaml` (superseded; retained for audit history)
- `DC-TM-SEC-002-threat-model.yaml` -> `compliance/security/dc-tm-sec-002-threat-model.yaml`
- `neo4j-nlp-terminology-schema.md` -> `compliance/architecture/neo4j-nlp-terminology-schema.md` (engineering reference; the data model summary now lives in the SAD `data_design` section)

## Open items / follow-ups

- ARCH-001: produce a formal architecture diagram (Visio / draw.io) for DTAC submission. The SAD Mermaid diagrams render in the QMS Architecture tab and are sufficient for IEC 62304; the Visio version is a DTAC presentation-format ask.
- ARCH-002: confirm Neo4j Aura physical region (UK tier).
- KM-001: rotate the 13 expired client secrets identified in the 2026-03-03 audit.
- RET-001-ENG: implement automated retention enforcement jobs (currently manual on Controller instruction).
- KM-003: confirm Neo4j Aura encryption key management with the Neo4j account team.
