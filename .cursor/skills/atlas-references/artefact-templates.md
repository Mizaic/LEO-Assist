# Atlas Artefact Templates

Locked definitions for each Atlas design-control artefact type in
LEO Clinical Decision Support. Use these as the canonical structure
when drafting any UN, DI, DO, Risk, VT, or VAL. The product is
`PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4`.

For the underlying Atlas MCP tool arguments see
`atlas-mcp-workflow.md`. For wording rules see `vocabulary.md`.

---

## User Need (UN)

A UN states what a stakeholder needs from the device in plain
clinician English. It is the only artefact that names the
stakeholder explicitly.

### Required fields

- `title` - 4 to 8 words, clinician-readable, no acronyms.
- `description` - one sentence in the form
  "As a <stakeholder>, I need <capability> so that <outcome>."
- `rationale` - one to three sentences explaining why this need
  exists in the LEO CDS scope.
- `stakeholder_types` - one or more of: `Clinician`,
  `Quality Engineer`, `Developer`, `IT Admin`, `Quality Manager`,
  `External Auditor`, `Knowledge Base Author`.
- `acceptance_criteria` - 2 to 5 plain-English criteria the
  stakeholder would use to accept the capability.
- `priority` - one of `MUST`, `SHOULD`, `COULD`, `WONT`.
- `safety_class` - `A` or `B`. Class C requires Clinical Safety
  Officer escalation; do not use.

### Level of detail

Plain English at a reading age of 9 to 11. No implementation
references, no module names, no API endpoints. Outcomes only.

### Good example

```
title: Get clinical facts from a patient record
description: As a clinician, I need extracted clinical facts from
  the patient record so that I can quickly understand the case
  before triage.
rationale: Reviewing a full record by hand is slow and error prone.
  Reliable fact extraction lets the clinician focus on judgement.
stakeholder_types: ["Clinician"]
acceptance_criteria:
  - "I can see the facts the system pulled from the record."
  - "Each fact links back to the source text."
  - "Unclear or missing facts are clearly flagged."
priority: MUST
safety_class: B
```

### Bad example (do not use)

- Uses jargon: "Provide an LLM-backed entity extraction service."
- Names files: "Use `pipeline_worker/main.py` to extract."
- States non-need: "The platform shall persist results to Neo4j."

---

## Design Input (DI)

A DI is a SHALL statement that the platform must implement to meet
a UN. It is the contract a feature is verified against.

### Required fields

- `title` - 4 to 8 words; mirrors the SHALL statement.
- `description` - "The platform SHALL <capability> ... ."
  One sentence. No implementation detail. Must be testable.
- `rationale` - one to two sentences linking back to the UN.
- `input_type` - `functional`, `safety`, `performance`,
  `interface`, or `usability`.
- `acceptance_criteria` - 2 to 5 measurable criteria.
- `safety_class` - `A` or `B`. Match or exceed the parent UN.
- `verification_method` - usually `test`; may be `inspection`,
  `analysis`, or `demonstration`.

### Level of detail

One requirement per DI. If you need "and" between two distinct
capabilities, split into two DIs. No file paths. No vendor names
unless the vendor is part of the contract (e.g. Neo4j as an
interface boundary).

### Good example

```
title: Keep source evidence for each fact
description: The platform SHALL store the source text snippet,
  document reference, and timestamp for every extracted fact.
rationale: Clinicians and auditors must trace any displayed fact
  back to where it came from in the record.
input_type: functional
acceptance_criteria:
  - "Every fact has a non-empty source snippet."
  - "Every fact links to a document and timestamp."
  - "Removing the source breaks the trace and is rejected."
safety_class: B
verification_method: test
```

### Bad example (do not use)

- Compound requirement: "SHALL extract facts AND show dashboards."
- Out of scope claim: "SHALL convert PDFs to text via OCR."
- Implementation leak: "SHALL use `progress_publisher.py`."

---

## Design Output (DO)

A DO describes the implementation that satisfies a DI. It is the
bridge between the design controls and the codebase. See
`.cursor/rules/atlas-do-implementation-mapping.mdc`.

### Required fields

- `title` - implementation-cluster name plus "- implementation",
  e.g. "Source-evidence persistence - implementation".
- `description` - one to three sentences describing what the
  software actually does, with key modules and functions named.
- `output_type` - `software`, `documentation`, `test`, or
  `configuration`.
- `source_reference` - semicolon-separated list of real file paths
  in the repo. Every path must exist at audit time.
- `software_item` - short logical name, e.g. `pipeline_worker`,
  `coding_worker`, `ui_review_screen`.
- `acceptance_criteria` - 2 to 5 criteria a reviewer can check
  against the code or runtime behaviour.
- `safety_class` - `A` or `B`. Match the linked DI.

### Level of detail

Describe implemented behaviour, not intended behaviour. If a
behaviour is not coded, do not list it. Cluster DOs by real
implementation surface (e.g. `fact extraction pipeline`) rather
than one DO per DI.

### Good example

```
title: Source-evidence persistence - implementation
description: Each extracted fact is written to Neo4j with its
  source snippet, document id, and capture timestamp by
  `libs/pipeline_graph/subgraphs/persist.py`. The writeback runs
  before the completion event is published.
output_type: software
source_reference: libs/pipeline_graph/subgraphs/persist.py;
  libs/workflow/engine.py;
  services/pipeline_worker/app/services/progress_callback.py
software_item: pipeline_worker
acceptance_criteria:
  - "Persist subgraph stores snippet, doc id, and timestamp."
  - "Completion event fires only after the write returns."
  - "Failures during write prevent the completion event."
safety_class: B
```

### Bad example (do not use)

- Provisional: "Persistence to be implemented in a later phase."
- Overstated: lists `services/` as a path with no specific files.
- Drift: claims OCR or dashboard behaviour that does not exist.

---

## Risk (ISO 14971)

A Risk describes a hazard, the hazardous situation, the harm, and
the mitigating controls. Required for any Class B DI.

### Required fields

The full set is enforced by
`.cursor/rules/atlas-design-controls-validation.mdc`. The
must-have fields are:

- `title`, `hazard_description`, `hazard_category` (controlled
  vocabulary).
- `hazardous_situation` - >=20 chars; describes the sequence from
  hazard to harm.
- `harm_description`, `harm_severity` (text), `initial_severity`,
  `initial_probability`, `initial_detectability` (each 1..5),
  `initial_risk_score` = severity * probability * detectability.
- `mitigation_plan_description` - lists the DI dcIds that
  implement controls and the VT dcIds that verify them.
- `mitigation_control_type`, `mitigation_effectiveness`.
- `residual_severity/probability/detectability/score` and
  `residual_acceptability`, `residual_justification`.
- `monitoring_plan`, `monitoring_metrics`, `review_frequency`.
- `identified_by`, `identified_date`, `status` (controlled vocab,
  legacy `Mitigated` not allowed - use `Control Implemented`).
- `safety_class` >= linking DI's `safety_class`.

### Level of detail

A Risk is concrete. It names the failure mode, the patient or
operator situation, and the harm. If you cannot describe the
harm, the risk is too vague to ship.

### Good example summary

- title: "Missing source evidence misleads clinician triage"
- hazard_description: A fact is shown to the clinician with no
  source snippet, so the clinician cannot verify it.
- hazardous_situation: During triage of a suspected lower-GI case
  the clinician reads an unsupported fact and accepts it as
  fully evidenced, missing a true contradiction in the record.
- harm_description: Triage decision made on unverified data.
- mitigation_plan: implemented by DI-6309C0E1; verified by
  VT-... ; runtime monitoring metric: orphan_fact_rate.

---

## Verification Test (VT)

A VT verifies that a DI is met by the corresponding DO(s). It is
not finished until a run is recorded in Atlas.

### Required fields

- `title` - "<feature> - acceptance verification".
- `description` - one to two sentences on what is verified.
- `test_type` - `unit`, `integration`, `system`, or `inspection`.
- `verification_method` - `test`, `inspection`, `analysis`,
  `demonstration`.
- `acceptance_criteria` - one-for-one with the DI's acceptance
  criteria.
- `protocol_steps` - ordered list of plain-English steps a
  reviewer could follow, ending with "Record pass/fail evidence
  via record_verification_run."
- `safety_class` - match the DI.

### Required follow-up

After running the test:

```
record_verification_run(
  vt_id=<VT UUID from get_design_control(...).id>,
  result="pass" | "fail",
  executed_by="<who or ci>",
  notes="<counts, log refs>",
  environment="ci" | "local" | "staging",
)
```

Until a `pass` run is recorded, the VT is not considered
verified. Never call this without actually executing or
inspecting the evidence.

### Level of detail

Each `protocol_steps` step should be doable by someone with
working knowledge of the repo. Reference real paths to test
files (`tests/...`, `services/ui/src/__tests__/...`).

---

## Validation Test (VAL)

A VAL validates that a UN is met in real clinical conditions or
against a clinical outcome the user will see. Required only for
features whose output reaches a clinician decision (coding
decisions, safety thresholds, tier classifications, alert
escalation rules).

### Required fields

- `title` - "<UN topic> - clinician validation".
- `description` - what clinical outcome is being validated.
- `validation_method` - usually `clinical_evaluation` or
  `usability_test`.
- `protocol_preconditions` - single string describing the data
  set, clinicians involved, and environment.
- `acceptance_criteria` - clinical outcome criteria.
- `safety_class` - match the parent UN.

### Required follow-up

`record_validation_run(...)` with the real run evidence. Same
discipline as VTs: no record, no validation.

### Level of detail

A VAL is the clinician-facing proof. It must describe the
clinician population, the sample size, and the outcome metric.
"Clinicians liked it" is not a valid acceptance criterion.

---

## Linking Cheat Sheet

| Direction                              | Relationship       |
|----------------------------------------|--------------------|
| UN -> DI                               | `HAS_DESIGN_INPUT` |
| DO -> DI                               | `IMPLEMENTS`       |
| DI -> Risk                             | `MITIGATES`        |
| VT -> DI                               | `VERIFIES`         |
| VT -> DO                               | `TESTS`            |
| VAL -> UN                              | `VALIDATES`        |

Every Class B DI MUST end with: one UN parent, one DO child, one
Risk it mitigates, and one VT with a recorded run.
