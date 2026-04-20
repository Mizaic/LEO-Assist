# Batch 12 -- UN-8663A98C Encounter classification

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Scope: 2 DIs covering the managed rules + per-encounter decision persistence,
and the misclassification training-label feedback loop with model registry.

## Inventory

| DI | Title (short) | Verdict | Evidence |
|----|---------------|---------|----------|
| DI-8CE01B3E | Managed rules with per-encounter decision persistence + test-pack validation | partial | `libs/classifiers/encounter_classifier.py` + `libs/classifiers/encounter_textcat.py` implement deterministic rule-based classification with `ClassificationResult` persistence. No management UI for keyword triggers / programme assignment / confidence threshold; no test-pack gate before rule activation. |
| DI-0ADE6A8E | Misclassification labelling feedback loop + model registry integration | partial | Encounter re-classification exists (`EncounterList.tsx` surfaces misclassified state); no explicit "flag as labelled training example" action; no wiring to `libs/model_registry/` to bump the classification model version from reviewer flags. |

## Finding

Encounter pre-classification is implemented as a rule-first textcat that
bypasses the LLM to avoid prompt injection (comment in
`encounter_classifier.py` references threat `NER-T-001`). Classification
decisions are persisted as `ClassificationResult` with `content_type`,
`domains`, and consensus metadata.

Missing: (1) a management UI for the rule set with test-pack gate; (2) an
explicit misclassification flag that writes a training example and surfaces
it to `training_worker`; (3) classification-model version management in
`libs/model_registry/`.

## Atlas actions

- DO documenting current rule-based encounter pre-classification.
- Backlog entries for management UI + test-pack gate, and feedback loop.

## Verdict summary

| Verdict | Count |
|---------|-------|
| implemented | 0 |
| partial | 2 |
