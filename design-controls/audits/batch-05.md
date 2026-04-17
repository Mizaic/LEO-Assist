# Batch 05 -- UN-83D9A46D Relation linking

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Scope: 6 DIs covering ontology-constrained relation linking, per-relation-type
quality gates, persistence model, reviewer UI, method disclosure, and
end-to-end relation integrity.

## Inventory

| DI | Title (short) | Verdict | Evidence |
|----|---------------|---------|----------|
| DI-3EA60D5A | Ontology-constrained relation extraction | implemented | `libs/relations/policy.py::is_relation_allowed`, `relation_linking.py` applies allowlist |
| DI-318B864C | Persistence as typed tuples with confidence + multi-link | implemented | `libs/ner/relation_builder.py`, `libs/cypher/documents_queries.py` writes typed edges |
| DI-2D9F5064 | Method disclosure (model vs LLM fallback) + confidence | partial -> FIXED in this batch | Merge step previously dropped source label; see code change below |
| DI-3035F221 | Reviewer interface with SNOMED policy guidance + actions | partial | UI surfaces triplets (`RelationRow.tsx`); accept/reject/undo flows present via gold-dataset UI; SNOMED policy guidance rendered as text only, not per-pair explanation |
| DI-80BD2F86 | Per-relation-type precision/recall/F1 gate for promotion | partial | `services/training_worker/app/relation_exporter.py` emits metrics; no blocking gate wired into canary promotion flow |
| DI-08DE2CF3 | E2E integrity (extraction -> review -> training -> inference -> audit) | partial | Typed edges preserved in graph but no end-to-end parity check; dual-path consistency rule covers post-processing only |

## Code improvement delivered (DI-2D9F5064)

Edited `libs/pipeline_graph/subgraphs/relation_linking.py::_merge_model_and_llm`
to preserve a per-row `extraction_method` of "model", "llm", or "model+llm",
and propagate it into the persisted relation dict via `_apply_relation_linking`.
Without this change, reviewer-facing relations lacked method disclosure
required by the DI.

Remaining work (backlog):
- Extend the reviewer UI (`RelationRow.tsx`) to render the method as a chip
  (gold/LLM/both) and display the confidence score.
- Persist `extraction_method` through the graph edge in
  `libs/cypher/documents_queries.py`.

## Other findings

### DI-3EA60D5A -- Ontology-constrained (implemented)

`libs/relations/policy.py` defines `RELATION_POLICY_RULES` (5 rules mapping
source-label x target-label x relation-type to SNOMED relationships) and
`is_relation_allowed()`. `relation_linking._apply_relation_linking()` discards
rows whose relation type is outside `allowed_relation_types()`.

Gap: `libs/ner/schema_mapper.py::VALID_RELATION_TYPES` lists 11 types but
`libs/relations/policy.py::_ALLOWED_RELATION_TYPES` only covers 5. The runtime
allowlist is the policy set, but the schema mapper would happily ingest 6
additional types with no policy check. Recorded as should-fix.

### DI-80BD2F86 -- Per-relation-type F1 gate (partial)

`services/training_worker/app/relation_exporter.py` computes metrics per
relation type but no call site blocks promotion. There's no connection to
the canary rollback logic in `libs/model_registry/`.

### DI-08DE2CF3 -- End-to-end relation integrity (partial)

No explicit count/integrity assertion crosses the extraction -> review ->
training -> inference boundary for relations. This mirrors the gap surfaced
for multi-label spans in batch-04 (DI-EE80C271). Recommend a single "pipeline
invariants" test module covering both span-label pairs and relations.

## Atlas actions

- DO: "Relation linking subgraph with method-tagged merge" (covers
  DI-3EA60D5A, DI-2D9F5064, DI-08DE2CF3 partial, DI-318B864C).
- DO: "Relation reviewer UI with policy-aware triplets" (covers
  DI-3035F221 partial).
- Backlog entries for the remaining gaps.

## Verdict summary

| Verdict | Count |
|---------|-------|
| implemented | 2 |
| partial -> improved this batch | 1 (DI-2D9F5064) |
| partial (backlog) | 3 |
| missing | 0 |
