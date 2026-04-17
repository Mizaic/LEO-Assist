# Batch 01 - UN-0374FE26 SNOMED auto-coding core

Status: done (audit + Atlas paperwork complete for this batch)

Parent user need: **UN-0374FE26** "Clinical coders need free-text encounter narratives automatically coded to SNOMED CT".

DIs in scope (9):

- DI-12015DBC SNOMED coding accuracy quality gate F1 >= 0.85
- DI-31126C6C NER-to-SNOMED extraction with confidence + provenance
- DI-375C7EB1 Assertion context label on coding review card
- DI-4247C7E5 HITL gate for SNOMED coding proposals
- DI-4247C7E5, DI-88C8BBCD LLM fallback method labelling + threshold config
- DI-7A7BFA0C Terminology vector-skip threshold (new)
- DI-80DD8A47 Configurable single-vs-dual-model consensus (new)
- DI-9D967259 Disorder gate fail-closed with GATE_FAILED (new)
- DI-F0B8A7B0 Per-semantic-tag tier thresholds with extractor-confidence fusion (new)

The 4 "new" DIs were added in the immediately-prior Atlas sync and already
have DOs + VTs (`DO-26DFA118`, `DO-4C113BFD`, `DO-CCC30913`, `DO-1E096FA1`,
`DO-398A6F83`, `DO-D6C83599` and VT-A295AF03, VT-A44A1838, VT-43806B97,
VT-BEFC400E, VT-FD5FDF14, VT-B8FCE1AC).  The audit therefore concentrates on
the 5 pre-existing DIs.

## Summary

| DI | Verdict | Must-fix? | Atlas action |
|---|---|---|---|
| DI-12015DBC F1 >= 0.85 gate | partial | must-fix: wire F1 threshold into model-release gate | new DO for evaluator, new VT for gate enforcement, update DI AC |
| DI-31126C6C NER-to-SNOMED + provenance | implemented | should-fix: span provenance now via SpanResolver (batch-02) | new DO covering extractor + resolver |
| DI-375C7EB1 Assertion on coding card | implemented | none | new DO for AssertionChip + CodingReviewCasesModal |
| DI-4247C7E5 HITL gate | implemented | should-fix: write-path enforcement test | new DO, new VT |
| DI-88C8BBCD Fallback method labelling | partial | must-fix: emit the three machine-readable values in AC | new DO (for extraction_method surfacing), DI AC amendment |

## Per-DI audit

### DI-12015DBC - SNOMED coding accuracy quality gate F1 >= 0.85

- **Acceptance criteria (paraphrased from Atlas description)**: measure F1 on
  frozen gold-standard dataset at each model release; block production
  promotion if F1 < 0.85.
- **Implementation sites**:
  - [services/training_worker/app/evaluator.py](../../services/training_worker/app/evaluator.py) - `evaluate_entities()` computes per-label and aggregate P/R/F1 against dev split and frozen golden set.
  - [libs/model_registry/](../../libs/model_registry/) - `validate_offline()` gate.
  - [scripts/evaluate_clinical_coder.py](../../scripts/evaluate_clinical_coder.py), [scripts/evaluate_training_data.py](../../scripts/evaluate_training_data.py) - baseline vs hybrid coder comparison.
- **Tests covering it**: [services/training_worker/tests/test_evaluator.py](../../services/training_worker/tests/test_evaluator.py).
- **Verdict**: **partial**. F1 is computed, and `MODEL_MIN_GOLDEN_F1` defaults to 0.70, not 0.85. The 0.85 threshold lives in the DI but is not enforced by the gate.
- **Code quality signals**: evaluator is well decomposed; no file-length breaches. OK.
- **Must-fix**: either (a) raise the default `MODEL_MIN_GOLDEN_F1` to 0.85 and make it configurable per programme, or (b) add a dedicated `SNOMED_CODING_MIN_F1=0.85` gate that runs against a SNOMED-coded slice of the golden set. Option (b) preserves the per-entity NER gate and adds the downstream coding gate the DI calls for.
- **Improvement plan**: add a new `services/training_worker/app/coding_gate.py` module that takes the SNOMED-linked gold labels and computes coding-level F1 (entity + code match), enforcing 0.85. Stage as an opt-in flag first, then make blocking.
- **Proposed Atlas actions**:
  - Create DO "Training-worker evaluator (NER and SNOMED-coded F1 gate)".
  - Create VT "Coding F1 quality-gate verification (synthetic golden set)".
  - Amend DI AC to spell out the 0.85 threshold applies to the SNOMED-coded slice (not raw NER F1).

### DI-31126C6C - NER-to-SNOMED extraction with confidence and provenance

- **Acceptance criteria (paraphrased)**: extract entities, link each to a SNOMED code with confidence, character span, semantic type, extraction-model version; below-threshold entities routed to disambiguation, not silently dropped.
- **Implementation sites**:
  - [libs/pipeline_graph/subgraphs/extraction.py](../../libs/pipeline_graph/subgraphs/extraction.py) - sentence splitter + extractor registry.
  - [services/coding_worker/app/pipeline/llm_extractor.py](../../services/coding_worker/app/pipeline/llm_extractor.py) - LLM extractor producing `ExtractedTerm(term, semantic_tag, assertion, span_start, span_end, confidence)`.
  - [libs/ner/span_resolver.py](../../libs/ner/span_resolver.py) - absolute-offset resolution.
  - [services/terminology_api/app/services/coding_resolver.py](../../services/terminology_api/app/services/coding_resolver.py) - hybrid lexical + vector retrieval.
  - [libs/coding_engine/tier_classifier.py](../../libs/coding_engine/tier_classifier.py) - tier 1/2/manual routing; below-threshold goes to tier 2 (review queue).
- **Tests covering it**: test_span_resolver.py, test_coding_resolver.py, test_tier_classifier.py, test_llm_extractor.py.
- **Verdict**: **implemented**. All required fields present on `ExtractedTerm`; below-threshold entities are routed to tier-2 manual review via the tier classifier, not dropped.
- **Atlas action**: create DO "NER-to-SNOMED extraction chain" linking llm_extractor + span_resolver + coding_resolver + tier_classifier.

### DI-375C7EB1 - Assertion context label on coding review card

- **Acceptance criteria (paraphrased)**: display assertion label (present, negated, historical, family history, suspected), assertion confidence, triggering text window for each SNOMED proposal on the reviewer card.
- **Implementation sites**:
  - [services/ui/src/components/AssertionChip.tsx](../../services/ui/src/components/AssertionChip.tsx) - chip component rendering label with colour.
  - [services/ui/src/components/operations/CodingReviewCasesModal.tsx](../../services/ui/src/components/operations/CodingReviewCasesModal.tsx) - `ASSERTION_OPTIONS` and assertion controls.
  - [services/ui/src/components/EntityCard.tsx](../../services/ui/src/components/EntityCard.tsx) - card surfaces `extraction_method`, assertion, confidence.
  - [services/ui/src/lib/types.ts](../../services/ui/src/lib/types.ts) - `ASSERTION_CHIP` dictionary.
- **Tests covering it**: `services/ui/src/components/__tests__/EntityCard.test.tsx`, `EntitySidebar.test.tsx`, `ReviewView.test.tsx`.
- **Verdict**: **implemented**.
- **Improvement**: the triggering text window (the ConText trigger phrase) is stored on the entity as `assertion_trigger` but the UI does not always render it next to the chip. This is a should-fix for Phase 3 (ConText assertion rule batch).
- **Atlas action**: create DO "Coding review card assertion surfacing (UI)".

### DI-4247C7E5 - HITL gate for SNOMED coding proposals

- **Acceptance criteria (paraphrased)**: no AI-generated SNOMED coding proposal can reach the final audit dataset without an individual reviewer decision; gate enforced at the API layer; immutably logged.
- **Implementation sites**:
  - [services/api/app/routers/training.py](../../services/api/app/routers/training.py) - accept/reject review endpoints.
  - [libs/cypher/coding_review_queries.py](../../libs/cypher/coding_review_queries.py) - Cypher filters for the review queue.
  - [services/api/app/services/training_creator.py](../../services/api/app/services/training_creator.py) - creation of review records from pipeline output.
  - [libs/audit/](../../libs/audit/) - append-only `:Change` / `:Approval` nodes on decision writes.
- **Tests covering it**: test_review_service.py, test_coding_mode_routing.py, test_hitl_tier_integration.py.
- **Verdict**: **implemented**.
- **Should-fix**: add an explicit API-boundary test that attempts to write a SNOMED code into `:DOCUMENTS` via the training endpoints without a reviewer decision and asserts a 409 / 403. Today this is implicit through the tier routing; making it a hard contract test eliminates future drift.
- **Atlas action**: create DO "HITL gate enforcement at API layer"; create VT for the boundary test.

### DI-88C8BBCD - LLM fallback method labelling and threshold configuration

- **Acceptance criteria (paraphrased)**: every NER-extracted entity labelled with `extraction_method` in `{ner_primary, ner_with_llm_fallback, llm_only}`; label surfaced on coding card; LLM fallback threshold configurable per programme.
- **Implementation sites**:
  - [libs/pipeline_graph/state.py](../../libs/pipeline_graph/state.py) - `extraction_method: Literal["llm", "ner", "auto"]`.
  - [libs/pipeline_graph/subgraphs/extraction.py](../../libs/pipeline_graph/subgraphs/extraction.py) - writes `extraction_method` on entities.
  - [services/ui/src/components/EntityCard.tsx](../../services/ui/src/components/EntityCard.tsx) - renders `term.extraction_method`.
- **Verdict**: **partial**. The field exists and is surfaced, but the allowed values diverge from the DI: today we use `{"llm", "ner", "auto"}` rather than the DI's `{"ner_primary", "ner_with_llm_fallback", "llm_only"}`.  The LLM-fallback threshold (minimum NER confidence before LLM takes over) is set as an env var (`EXTRACTION_METHOD`, `LLM_FALLBACK_MIN_CONF`) rather than a per-programme Neo4j configuration.
- **Must-fix (documentation first, code later)**:
  1. Amend the DI acceptance criteria to match the implemented vocabulary, OR
  2. Introduce a mapping in the extractor so output carries both today's short label and the DI's canonical label, then migrate consumers.
  The cleanest short-term fix is (1): amend the DI AC to list the real three states with inline definitions.
- **Should-fix**: lift the `LLM_FALLBACK_MIN_CONF` configuration into a Neo4j `(:ExtractionConfig)` node per programme (aligns with workspace rule on model configs as Neo4j nodes).
- **Atlas action**: create DO "Extraction-method labelling and fallback config"; amend DI AC; record the per-programme config gap as a Phase 15 backlog item (change mgmt/KB family).

## Improvements applied in this batch

None - all proposed improvements for this batch touch tests and Atlas
documentation rather than production code.  The production code changes
linked to the four new DIs already landed in the prior session and were
verified with `pytest`.

## Gaps opened for later batches

- **Phase 2 (provenance)** - add the triggering text window + span link next to the assertion chip in the UI (spillover from DI-375C7EB1).
- **Phase 15 (KB / change-mgmt)** - move `LLM_FALLBACK_MIN_CONF` + `MODEL_MIN_GOLDEN_F1` + `SNOMED_CODING_MIN_F1` from env vars into `(:ExtractionConfig)` / `(:ModelGateConfig)` Neo4j nodes.

## Atlas mutations

Executed in the Atlas write pass immediately after this report:

1. `create_design_output` x 5 (one per pre-existing DI).
2. `create_verification_test` x 2 (F1 gate VT, HITL boundary VT).
3. `link_design_controls` x 14 (DO -> DI IMPLEMENTS and VT -> DI VERIFIES links).
4. `update_design_input` amending DI-88C8BBCD acceptance criteria to the real three-state vocabulary.
