# Batch 10 -- UN-7D740697 Coding correction review

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Scope: 6 DIs covering the structured coding-correction review UI + gates:
correction display, secondary review threshold gate, dependency + terminology
validation, historical frequency, terminology currency check, and surface-form
dependencies.

## Inventory

| DI | Title (short) | Verdict | Evidence |
|----|---------------|---------|----------|
| DI-04105500 | Coding correction request structured display schema | partial | `source="coding_correction"` exists as a training-data source (services/api/app/routers/patients.py, training.py, libs/ner/training_label_writer.py). No dedicated correction-request node schema or UI page matching the DI (original/replacement/concept/rationale). |
| DI-13F340B9 | Large-scale correction mandatory secondary review threshold gate | missing | No programme-level counter or dual-approval gate found |
| DI-1B8AC856 | Review with dependency and terminology validation | missing | No dependents lookup in correction flow |
| DI-22F4E3CE | Historical code frequency display (12mo + full) | missing | No frequency aggregation endpoint for a target SNOMED code on the correction review |
| DI-26CBDB16 | Terminology currency validation for replacement codes | missing | Active/current SNOMED release endpoint is itself missing (see batch-09) |
| DI-4221A226 | NLP surface form dependency display | missing | Surface-form lookups by concept_id exist (GROUPED_SURFACE_FORMS) but are not wired into a correction review page |

## Finding

Coding-correction review is present only as a training-data source tag. None
of the six DIs is implemented as specified. The training worker uses
`"coding_correction"` to accept reviewer labels but there is no dedicated
correction request + review workflow with the structured gates this UN
requires.

## Atlas actions

- No DOs created.
- Six backlog entries (one per DI).

## Verdict summary

| Verdict | Count |
|---------|-------|
| implemented | 0 |
| partial | 1 |
| missing | 5 |
