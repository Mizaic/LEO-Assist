# Decision Engine

Use this engine to decide which Atlas artefacts a change requires.
It is deterministic: the same inputs always produce the same set
of required artefacts. Skip it only for pure documentation work
that does not touch shipped code.

## Inputs

1. **change_kind** - what the change actually does. Pick one:
   - `cosmetic` - copy, CSS, comment, internal refactor with no
     observable behaviour change.
   - `internal_tooling` - dev script, lint config, CI only.
   - `class_a_feature` - non-clinical UI plumbing or developer
     utility shipped to users.
   - `class_b_feature` - clinical decision support behaviour or
     anything safety-relevant in the LEO CDS scope.
   - `class_b_fix` - safety-relevant bugfix or hardening.
   - `interface_change` - new or changed message contract, Neo4j
     writeback shape, pubsub topic, API surface.
   - `out_of_scope` - dashboards, OCR, document conversion,
     thumbnails, read-aloud, FHIR export, or anything the user
     has not explicitly approved.

2. **safety_class** - `A` or `B`. Default to `B` whenever the
   change can influence clinician decisions, patient data, or
   pipeline correctness. Never use `C` without Clinical Safety
   Officer escalation; treat it as a stop.

3. **UN_cluster** - which of the five LEO CDS UN clusters does
   this touch? If none fits, the work is probably out of scope.
   The clusters are:
   - `clinical_facts` - extract facts from the record.
   - `clinical_terminology` - code the facts with SNOMED.
   - `pathway_match` - is the case a fit for the requested
     pathway / referral / request reason?
   - `information_completeness` - has the clinician got enough
     to triage? what is missing or unclear?
   - `clinician_summary` - a short summary for clinician review.
   - `interface` - cross-cutting; pipeline triggers, Neo4j
     handoff, completion events.

## Required artefacts table

| change_kind        | UN              | DI              | DO              | Risk            | VT              | VAL                                  |
|--------------------|-----------------|-----------------|-----------------|-----------------|-----------------|--------------------------------------|
| cosmetic           | look up only    | look up only    | look up only    | no              | no              | no                                   |
| internal_tooling   | optional        | optional        | yes if shipped  | no              | yes if shipped  | no                                   |
| class_a_feature    | yes (update)    | yes (update)    | yes             | optional        | yes             | no                                   |
| class_b_feature    | yes             | yes             | yes             | required (>=1)  | required        | required if clinical outcome visible |
| class_b_fix        | look up         | update existing | update existing | review existing | required        | required if outcome changed          |
| interface_change   | optional        | yes             | yes             | review          | yes             | no                                   |
| out_of_scope       | refuse          | refuse          | refuse          | n/a             | n/a             | n/a                                  |

Look-up means: find the nearest existing artefact and confirm it
already covers this change. Do not create a new artefact.

## Decision order

Work top to bottom. Do not skip a step.

1. **Classify change_kind**. If `out_of_scope`, stop and ask the
   user. Do not draft anything.
2. **Pick safety_class**. If unsure, default to `B`.
3. **Pick UN_cluster**. If none of the five LEO CDS UN clusters
   fit, surface this as a scope question.
4. **Search before create**. Call
   `search_design_controls(query=<plain English of the change>,
   dc_type=<UN|DI|DO|Risk|VT|VAL>)` for every artefact type the
   table requires. Update before create.
5. **Apply the table** to produce the required artefact set.
6. **For every required artefact**, check the templates in
   `artefact-templates.md` and the wording rules in
   `vocabulary.md`.
7. **Write the atomic plan** (see `atlas-mcp-workflow.md`).
8. **Execute the plan top-to-bottom**, stopping at the first
   failure.
9. **Run `get_traceability_gaps`** and report any orphans.
10. **Emit the audit report** (see `audit-report-format.md`).

## Hard stops

Stop and ask the user when any of these are true:

- `change_kind == out_of_scope`.
- `safety_class` would need to be `C`.
- The change does not fit any UN cluster.
- A required artefact would need a banned term that has not been
  explicitly approved.
- A Class B DI cannot be linked to at least one Risk.
- A VT would need to be marked `pass` without an actual run.

## Minimum closure for Class B work

A Class B change is not finished in Atlas until all of these are
true:

- The DI has `HAS_DESIGN_INPUT` from at least one UN.
- The DI has `IMPLEMENTS` from at least one DO with real
  `source_reference` paths that exist in the repo.
- The DI has `MITIGATES` from at least one Risk whose
  `safety_class` is >= the DI's `safety_class`.
- The DI has `VERIFIES` from at least one VT that has a recorded
  `pass` run.
- If the change is clinically visible, a VAL exists, links via
  `VALIDATES` to the UN, and has a recorded run.
- `get_traceability_gaps(product_id=...)` does not list any of
  the new dcIds in `orphan_design_inputs` or
  `orphan_design_outputs`.

## Examples

### Example 1: bug fix that affects displayed facts

- change_kind: `class_b_fix`
- safety_class: `B`
- UN_cluster: `clinical_facts`
- Required: update existing DI and DO; review the linked Risk;
  add or update a VT and record a `pass` run; add a VAL only if
  the displayed outcome changed.

### Example 2: new pubsub topic for batch reprocessing

- change_kind: `interface_change`
- safety_class: `B`
- UN_cluster: `interface`
- Required: new DI for the topic contract, new DO referencing the
  worker code, review the existing interface Risks, new VT with
  a protocol that inspects the publisher and subscriber paths.

### Example 3: refactor that renames a helper

- change_kind: `cosmetic`
- safety_class: `A`
- UN_cluster: not applicable
- Required: no new artefacts; spot-check that existing DOs do
  not reference the renamed file under `source_reference`. If
  they do, update those DOs.

### Example 4: add an OCR step to the upload screen

- change_kind: `out_of_scope`
- Stop. The LEO CDS release does not include OCR. Ask the user
  whether the release scope has changed.
