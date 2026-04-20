# Batch 02 - UN-B2C85448 Entity provenance and immutable source linking

Status: done (audit + Atlas paperwork for this batch)

Parent user need: **UN-B2C85448** "Clinical reviewers and auditors need every AI-extracted entity linked to its source text phrase with immutable provenance".

DIs in scope (8):

- DI-B2512CB3 Immutable source-span linkage with integrity hash
- DI-E81545BE Source-text highlight linking for reviewer entity selection
- DI-23822663 Assertion evidence text window stored alongside label
- DI-080A2454 Provenance retention policy enforcement (7-year minimum)
- DI-4F67189B Reviewer correction event schema linked to provenance
- DI-09E26C1D Audit trail API providing provenance access without PII
- DI-6A0B55A4 Clinical qualifier preservation (new in prior session)
- DI-A0C90595 Absolute character-offset resolver (new in prior session)

## Summary

| DI | Verdict | Must-fix? | Atlas action |
|---|---|---|---|
| DI-B2512CB3 | partial | must-fix: entity integrity hash is not stored per-entity; only Document.snippet_hash is available. Add `provenance_hash` per entity. | new DO for documents_queries, update DI AC or add new DI for entity hash |
| DI-E81545BE | implemented | none | new DO for EntitySidebar + span rendering |
| DI-23822663 | missing | must-fix: assertion trigger text window is not stored on the entity today. Add `assertion_trigger_window_start/_end` and `assertion_trigger_text` to Context engine output and Cypher writer. | new DO for context_engine, update DI AC, open improvement ticket |
| DI-080A2454 | policy-only | must-fix: no technical enforcement of 7-year retention on :DOCUMENTS or :Approval. Need Neo4j constraint + scheduled verifier. | new DO covering retention, update DI AC with technical details |
| DI-4F67189B | implemented | none | new DO for correction event writes |
| DI-09E26C1D | partial | should-fix: FHIR AuditEvent emitter exists but a dedicated auditor-scoped audit trail API that strips PII is not published. | new DO for FHIR AuditEvent emitter, open gap for PII-scoped audit API |
| DI-6A0B55A4 | implemented (new) | none | already documented (DO-4C113BFD) |
| DI-A0C90595 | implemented (new) | none | already documented (DO-26DFA118) |

## Per-DI audit

### DI-B2512CB3 - Immutable source-span linkage and provenance

- **Implementation**: [libs/cypher/documents_queries.py](../../libs/cypher/documents_queries.py) writes span + model name + model_version + contract_version + run_id to the `:EXTRACTED_FROM` or `:MENTIONED_IN` relationship. Integrity is provided by document-level `snippet_hash`.
- **Verdict**: **partial**. Per-entity `provenance_hash` is not stored; edit detection relies on the document hash. If an entity is tampered with directly (e.g. SNOMED code swapped), no hash on the provenance record would flag it. Could add `r.provenance_hash = sha256(term||span||code)`.
- **Must-fix**: Add `provenance_hash` property set at write time in documents_queries.py; expose a verification helper that returns mismatched entities.
- **Atlas actions**: DO "Entity provenance writer (documents_queries + audit append-only)"; update DI AC to clarify per-entity hash requirement.

### DI-E81545BE - Source-text highlight linking

- **Implementation**: [services/ui/src/components/EntitySidebar.tsx](../../services/ui/src/components/EntitySidebar.tsx) renders source text with `span_start`/`span_end` highlighted when reviewer selects entity. Tests: EntitySidebar.test.tsx, EntityCard.test.tsx.
- **Verdict**: **implemented**.
- **Atlas action**: DO "Source-text highlight UI (EntitySidebar span rendering)".

### DI-23822663 - Assertion evidence text window

- **Implementation**: ConText engine ([libs/ner/context_engine.py](../../libs/ner/context_engine.py)) emits `assertion` but does not currently attach the verbatim trigger window (`assertion_trigger_text`, `assertion_trigger_start`, `assertion_trigger_end`) to the entity.  Search confirms no such field is written or rendered.
- **Verdict**: **missing**.
- **Must-fix**: In `context_engine._assign_assertions()` compute trigger window using the rule match span; attach `assertion_trigger_start/_end/_text` to the entity; propagate through `documents_queries._assertion_context()` to Neo4j; surface next to `AssertionChip` in UI.
- **Atlas action**: DO "ConText assertion engine (gap: trigger text window)", link as IMPLEMENTS for DI-23822663 with acknowledged gap. Open improvement ticket for the fix (will land in Phase 3 - ConText assertion).

### DI-080A2454 - Provenance retention (7-year minimum)

- **Implementation**: [design-controls/DC-RET-001-retention-schedule.md](../../design-controls/DC-RET-001-retention-schedule.md) declares retention policy. No code enforcement found (no scheduled sweeper, no Neo4j constraint rejecting updates older than threshold).
- **Verdict**: **policy-only**.
- **Must-fix**: Add a scheduled `:ProvenanceRecord` integrity verifier that (a) asserts `created_at + 7yr > now` for all retained records, (b) enforces write-once via Cypher constraints. Phase 15 (data protection) is the natural home.
- **Atlas action**: DO "Retention schedule policy document (DC-RET-001)"; open backlog for technical enforcement.

### DI-4F67189B - Reviewer correction event schema

- **Implementation**: [services/api/app/routers/training.py](../../services/api/app/routers/training.py) accept/reject endpoints write `:CodingCorrection` nodes linking to `:CodingReview` and `:ExtractedEntity`, including original code, replacement code, rationale, reviewer identity and role, and timestamp. Append-only via [libs/audit/audit_emitter.py](../../libs/audit/audit_emitter.py) FHIR AuditEvent.
- **Verdict**: **implemented**.
- **Atlas action**: DO "Reviewer correction event writer (training router + audit emitter)".

### DI-09E26C1D - Audit trail API without PII

- **Implementation**: [services/fhir_api/app/routers/audit_event.py](../../services/fhir_api/app/routers/audit_event.py) exposes FHIR R4B AuditEvent CRUD. Entities stored in this stream are references (IDs) without free-text. Agent emails are recorded; no patient free-text is persisted in the AuditEvent.
- **Verdict**: **partial**. AuditEvent carries IDs but cross-reference into the actual provenance records still exposes clinical detail via the main API. There is no dedicated "auditor-scoped" endpoint that returns provenance + correction events without clinical record free-text.
- **Should-fix**: add `/api/v1/audit/provenance/{entity_id}` with auditor RBAC scope that strips free-text fields. Phase 15 naturally hosts this.
- **Atlas action**: DO "FHIR AuditEvent emitter"; open backlog for PII-scoped audit API.

## Atlas mutations

Executed below: create DOs for the 6 pre-existing Phase 2 DIs; the 2 new DIs (DI-6A0B55A4, DI-A0C90595) already have DOs (DO-4C113BFD, DO-26DFA118) from the prior session.
