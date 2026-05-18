---
name: atlas-do-mapper
description: Maps Atlas Design Outputs (DOs) to real implementation in the LEO Clinical Decision Support repo. Enforces verifiable `source_reference` paths, rejects provisional or overstated DOs, and clusters DOs by implementation surface. Use when drafting, updating, or reviewing any DO, or when the user asks to ground design outputs in actual code.
---

# Atlas DO Mapper

## When to use

- The orchestrator (`atlas-control-author`) needs DOs drafted or
  updated.
- The user asks to "map a DO to code", "ground design outputs",
  "fix DO coverage", or "check DO source references".
- A DO is suspected of being provisional or overstated.

This skill is read-only on the codebase and write-prepared for
Atlas: it produces fully populated DO drafts (and updates) for
the orchestrator to apply.

## Hard rules

These mirror `.cursor/rules/atlas-do-implementation-mapping.mdc`:

- A DO describes implemented behaviour in this repo, not intended
  or planned behaviour.
- Before linking a DO to a DI, find the concrete implementation
  surface: source files, key functions/classes, API routes,
  Cypher queries, UI components, scripts, and relevant tests.
- `source_reference` MUST list specific file paths separated by
  `;`. Every path must exist at audit time (verified via `Glob`
  or `Read`).
- Provisional DOs are forbidden. If a DI is partial or not
  implemented, leave the `IMPLEMENTS` gap visible for QA.
- Cluster DOs by real implementation surface (e.g.
  `fact extraction pipeline`, `pub/sub pipeline and Neo4j result
  handoff`) rather than one DO per DI.
- Do not copy legacy DO wording when the codebase does not
  contain the same implementation.
- Do not claim binary file upload, OCR, conversion, thumbnails,
  text to speech, FHIR export, or compliance dashboards unless
  those exact surfaces are present.

## Mapping workflow

```
DO mapping progress:
- [ ] Receive the DI(s) and existing DO links
- [ ] Locate the implementation surfaces
- [ ] Verify each source_reference path exists
- [ ] Cluster DOs by surface
- [ ] Draft DO fields per the template
- [ ] Flag DIs with no implementation
- [ ] Hand drafts back to atlas-control-author
```

### Step 1 - Receive the DIs and existing DO links

The orchestrator passes in one or more DI dcIds. For each, call
`get_design_control(dc_type="design-input", dc_id=...)` and read
`traceability_edges.IMPLEMENTS` to find existing DOs.

### Step 2 - Locate the implementation surfaces

Use `Glob` and `Grep` to find the code that satisfies the DI.
Map directly to:

- API routes under `services/api/app/routers/`.
- Workers under `services/coding_worker/`, `services/pipeline_worker/`.
- Workflow engine under `libs/workflow/`.
- Pipeline graph subgraphs under `libs/pipeline_graph/`.
- Cypher under `libs/cypher/` and inline Cypher in worker files.
- Prompts under `libs/prompts/` and `libs/llm_client/`.
- UI under `services/ui/src/`.
- Tests under `tests/`, `services/*/tests/`, `services/ui/src/__tests__/`,
  `services/ui/e2e/`.

### Step 3 - Verify each source_reference path exists

For every candidate path, call `Glob` or `Read` to confirm it
exists. Drop any path that does not. Never paste a path you have
not verified.

### Step 4 - Cluster DOs by surface

Group the verified paths by implementation cluster. Examples
from the current LEO CDS controls:

- `Fact extraction pipeline - implementation`
- `Source-evidence persistence - implementation`
- `Pub/sub pipeline and Neo4j result handoff - implementation`
- `Pathway match decision - implementation`
- `Clinician summary generation - implementation`

A single DO can satisfy more than one DI when the implementation
surface is genuinely shared (worker pipeline, persistence,
review screen). Prefer one DO per cluster, not one per DI.

### Step 5 - Draft DO fields

Use the DO template in
`.cursor/skills/atlas-references/artefact-templates.md`:

- `title` - "<cluster> - implementation".
- `description` - one to three sentences naming key modules and
  functions and what they do at runtime.
- `output_type` - usually `software`; use `test` for test
  modules, `configuration` for config files, `documentation`
  for runbooks.
- `source_reference` - verified paths joined by `;`.
- `software_item` - short logical name (e.g. `pipeline_worker`).
- `acceptance_criteria` - 2 to 5 criteria a reviewer can check
  against runtime behaviour or the code.
- `safety_class` - match the linked DI.

### Step 6 - Flag DIs with no implementation

If a DI has no verifiable implementation, do not draft a DO. Add
the DI to a list of "unsupported DIs" in the audit report. The
orchestrator will surface the gap to the user.

### Step 7 - Hand drafts back

Return the drafts to `atlas-control-author`. The orchestrator
runs the language gate, executes the atomic plan, and (where
needed) calls `update_design_output` to set `source_reference`
when the initial create drops it.

## Examples

### Good DO draft

```
title: Pub/sub pipeline and Neo4j result handoff - implementation
description: The API publishes a pipeline trigger message via
  the message bus, the pipeline worker consumes it and runs the
  workflow engine, results are written to Neo4j by the persist
  subgraph, and the completion event is published only after the
  write returns.
output_type: software
source_reference: services/api/app/routers/pipeline.py;
  services/pipeline_worker/app/main.py;
  services/pipeline_worker/app/services/progress_callback.py;
  services/coding_worker/app/services/progress_publisher.py;
  libs/message_bus/base.py;
  libs/workflow/events.py;
  libs/workflow/engine.py;
  libs/pipeline_graph/subgraphs/persist.py
software_item: pipeline_worker
acceptance_criteria:
  - "Trigger publishes to the configured pipeline topic."
  - "Worker consumes the message and dispatches the workflow."
  - "Persist subgraph writes results to Neo4j before completion."
  - "Completion event fires only after the Neo4j write returns."
safety_class: B
```

### Bad DO draft (do not use)

- Lists `services/` as the path - too broad, not verifiable.
- Mentions OCR or dashboards - out of scope.
- Says "to be implemented in a later phase" - provisional.

## Related

- Rule: `.cursor/rules/atlas-do-implementation-mapping.mdc`
- Reference: `.cursor/skills/atlas-references/artefact-templates.md`
- Reference: `.cursor/skills/atlas-references/vocabulary.md`
- Orchestrator: `atlas-control-author`
