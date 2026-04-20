# Batch 03 - UN-06388412 ConText assertion rule maintenance

Status: done (audit + 1 code improvement landed + Atlas paperwork)

Parent user need: **UN-06388412** "Clinical content managers need to maintain the ConText assertion rules".

DIs in scope (4):

- DI-48AD06E5 LLM extractor emits self-rated assertion + confidence (new)
- DI-F298AE65 Assertion parity check between LLM and ConText (new)
- DI-DFAF200B ConText rule management: full parameter CRUD with test-run gate
- DI-48C13EB6 ConText rule change: pre-save assertion distribution impact report

## Summary

| DI | Verdict | Must-fix? | Atlas action |
|---|---|---|---|
| DI-48AD06E5 | implemented (new) | none | already documented (DO-4C113BFD) |
| DI-F298AE65 | implemented (new) | none | already documented (DO-1E096FA1) |
| DI-DFAF200B | partial | must-fix: /context-rules POST does not gate activation behind a passed test run | new DO for rule CRUD, update DI AC, open gap |
| DI-48C13EB6 | missing | must-fix: no pre-save distribution impact report is computed | new DO placeholder, open gap for implementation |

## Code improvement landed in this batch

**DI-23822663 (spillover from Phase 2)**: ConText engine now captures the verbatim assertion trigger window.

[libs/ner/context_engine.py](../../libs/ner/context_engine.py) changes:
- New helper `_trigger_window_from_span()` extracts the first ConTextModifier's text + absolute character offsets.
- `apply_context_detection_to_dicts()` now populates `assertion_trigger_text`, `assertion_trigger_start`, `assertion_trigger_end`, `assertion_trigger_category` on each mutated entity dict whenever a non-default assertion is assigned.

Because the dict path is the consumer for both the runtime pipeline
(`libs/pipeline/post_processing.py`) and the Ask LEO path, both inherit this
change (dual-path-consistency rule satisfied).

Follow-up (not in this batch, tracked in backlog):
- Cypher writer in `libs/cypher/documents_queries.py` to `SET r.assertion_trigger_text = $assertion_trigger_text` etc.
- UI card in `services/ui/src/components/AssertionChip.tsx` to render the trigger text next to the chip as a tooltip.

## Per-DI audit

### DI-DFAF200B - ConText rule CRUD with test-run gate

- **Implementation**: [services/api/app/routers/training.py](../../services/api/app/routers/training.py) at `GET/POST/PATCH /context-rules`. `ContextRuleRequest` captures literal, category, direction, max_scope, description, example. `UPSERT_CONTEXT_RULE` / `DEACTIVATE_CONTEXT_RULE` Cypher in `libs/cypher/training_rules_queries.py`. `reload_nlp()` picks up new rules.
- **Verdict**: **partial**. CRUD works but there is no test-run gate: on POST the rule activates immediately after Cypher write. The DI requires a passed verification test run before activation.
- **Must-fix**: introduce a two-step activation: (1) `POST /context-rules` creates the rule in a `status: 'draft'` state, (2) a new `POST /context-rules/{id}/activate` endpoint runs a regression test against the held-out corpus and only flips status to `active` when the test passes. Align with the rule-change mgmt pattern.
- **Atlas action**: DO "ConText rule CRUD API"; update DI AC to reflect two-step activation intent; gap recorded.

### DI-48C13EB6 - Pre-save distribution impact report

- **Implementation**: none. No endpoint computes the assertion distribution delta for a proposed rule change before save. `scripts/investigations/_inspect_context_rules.py` inspects rules offline but is not wired into the API.
- **Verdict**: **missing**.
- **Must-fix**: add `POST /context-rules/{id}/impact-report` that:
  1. Loads the held-out assertion test corpus from a Neo4j `(:AssertionTestSet)` node (or, temporarily, a JSON fixture).
  2. Runs ConText twice - once with the current active ruleset, once with the proposed change - and returns the delta in per-category counts.
  3. Persists the impact report as `(:ContextRuleImpactReport {rule_id, delta_counts, generated_at})`.
  This is a non-trivial but well-contained piece of work; target Phase 11/12 integration with the review queue.
- **Atlas action**: DO placeholder "ConText rule impact reporter (planned)"; gap recorded.

## Atlas mutations

Two DOs created below for the pre-existing DIs. Backlog updated with the two must-fix items.
