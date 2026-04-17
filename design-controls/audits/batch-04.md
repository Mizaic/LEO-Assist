# Batch 04 -- UN-14FA847A Multi-label NER

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Scope: 6 DIs covering multi-label NER, overlapping same-label spans with
divergent terminology, LLM semantic-tag scope constraint, API response schema,
label-verification fidelity, and lossless multi-label training export.

## Inventory

| DI | Title (short) | Verdict | Primary evidence |
|----|---------------|---------|------------------|
| DI-DC61F5B6 | Multi-type span classification for overlapping SNOMED concepts | implemented | `libs/ner/schema_mapper.py` (multi-entity per span), `libs/pipeline/post_processing.py` normalisation |
| DI-378F987A | Preserve overlapping same-label spans with divergent `lookup_term` | partial | `libs/ner/schema_mapper.py` dedupe key uses `(start, end, label)`; divergent `lookup_term` NOT part of dedupe key |
| DI-6E6C9336 | Inference API schema: one result per span-label pair | implemented | `services/coding_worker/app/pipeline/pipeline_service.py` returns per-entity list; each `(span, label)` emitted independently |
| DI-C899D282 | LLM semantic-tag scope constraint to NER-validated set | partial | `libs/ner/scope_guard.py` filters LLM-emitted tags; no explicit enforcement that LLM set is subset of NER-produced tags for the same document |
| DI-EE80C271 | Label-verification step multi-label annotation fidelity | partial | `services/api/app/services/label_verifier.py` iterates per entity; no explicit invariant asserting count-in == count-out for span-label pairs |
| DI-6EFD68D0 | Lossless multi-label span export to training format | partial | `libs/ner/training_label_writer.py` writes one record per span-label; no test-backed invariant guarding collapse on export |

## Findings and code-level detail

### DI-DC61F5B6 -- Multi-type span classification (implemented)

`libs/ner/schema_mapper.py::_stable_entity_id` hashes on
`(document_id, start, end, label)`, so two different labels on the same span
produce two entities. The runtime pipeline in
`services/coding_worker/app/pipeline/pipeline_service.py` passes each through
`run_post_processing()` and terminology resolution independently.

### DI-378F987A -- Overlapping same-label with divergent lookup_term (partial)

Gap: the dedupe key in `schema_mapper.py` and in the post-processing stack does
not branch on `lookup_term`. Two spans with the same `(start, end, label)` but
different clinically-relevant `lookup_term` values (e.g. "HbA1c" vs
"HbA1c level") will be collapsed before terminology resolution. This is a
real regression risk for qualifier-bearing surface forms.

Action: promote `lookup_term` into the dedupe tuple when two entries share
`(start, end, label)` but differ on `lookup_term`. Add regression test.

### DI-C899D282 -- LLM scope-guard subset invariant (partial)

`libs/ner/scope_guard.py` blocks LLM-introduced labels that are outside the
validated SNOMED-semantic-tag vocabulary, but does NOT enforce that the set of
labels emitted by the LLM for a document is a subset of the set emitted by the
NER model for that document. The DI wording requires a per-document subset
invariant.

Action: extend `scope_guard.apply()` to accept the NER label set for the
document and drop LLM tags that are not present in it, unless the LLM pass
is the sole extractor (configurable). Add a unit test.

### DI-EE80C271 / DI-6EFD68D0 -- Label-verification and training-export fidelity (partial)

`libs/ner/training_label_writer.py` writes one JSONL record per entity. There
is no counter-invariant that asserts the number of span-label pairs going in
equals the number coming out of the label-verification + export pipeline.
Silent label collapse would not be detected by existing tests.

Action: add an in-process counter in `training_label_writer.write_records()`
and in `label_verifier._process_label()`, fail closed when output count is
less than input count, and add a regression test for multi-label inputs.

## Atlas actions

- DO placeholder "Multi-label NER schema mapper + post-processing normalisation"
  covering `schema_mapper.py`, `post_processing.py`.
- DO placeholder "Label-verification and training-export lossless writer"
  covering `label_verifier.py`, `training_label_writer.py`.
- Improvements-backlog entries for the three `partial` items.

## Verdict summary

| Verdict | Count |
|---------|-------|
| implemented | 2 |
| partial | 4 |
| missing | 0 |
| policy-only | 0 |
