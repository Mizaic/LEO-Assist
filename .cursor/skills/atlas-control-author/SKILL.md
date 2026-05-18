---
name: atlas-control-author
description: Authors Atlas design controls end-to-end for the LEO Clinical Decision Support product. Owns the decision engine, search-before-create discipline, atomic write plan, and audit report. Use when the user asks to add, update, retire, or audit design controls (UN, DI, DO, Risk, VT, VAL), to wire traceability links, or to verify a change against ISO 14971 and IEC 62304 obligations.
---

# Atlas Control Author

## When to use

- The user asks to "add a design control", "create a UN/DI/DO/Risk/VT/VAL",
  "wire traceability", "retire a control", "record a verification run",
  or "make this change compliant".
- A pull request or feature change has just been audited by
  `atlas-codebase-audit` and now needs Atlas updates.
- A periodic compliance sweep finds gaps that need closing.

This skill is the only one that calls Atlas write tools. It runs
the decision engine, drives the search-before-create discipline,
executes the atomic write plan, and emits the final audit report.

## Hard rules

- Never create local YAMLs under `design-controls/`. Atlas MCP is
  the only store. See `.cursor/rules/atlas-design-controls-first.mdc`.
- Never use the legacy `*-LEO-AI-NNN` ID format for new artefacts.
- Never set `safety_class="C"` without prior Clinical Safety
  Officer and QA/RA approval. Mizaic's manufacturing policy does
  not permit Class C software in this product. See
  `.cursor/rules/atlas-vt-enforcement.mdc`.
- Never mark a VT or VAL `pass` without actually running or
  inspecting the evidence.
- Never call a write tool without first reading the matching tool
  descriptor in
  `.cursor/projects/.../mcps/user-atlas-design-controls/tools/`.
- Never skip the post-flight `get_traceability_gaps` check.
- Always produce the audit report at the end of the run.

## Workflow

Copy this checklist into the chat and tick items off:

```
Author progress:
- [ ] Get the evidence map (from atlas-codebase-audit)
- [ ] Run the decision engine
- [ ] Search before create
- [ ] Draft artefacts and run the language gate
- [ ] Ground DOs in real code
- [ ] Build the atomic write plan
- [ ] Read the relevant MCP tool descriptors
- [ ] Execute the plan top-to-bottom
- [ ] Record VT and VAL runs
- [ ] Run get_traceability_gaps
- [ ] Emit the audit report
```

### Step 1 - Get the evidence map

Use the output of `atlas-codebase-audit`. If none exists, ask
the user whether to run an audit first, or accept a smaller
scope they describe.

### Step 2 - Run the decision engine

Read `.cursor/skills/atlas-references/decision-engine.md` and
apply its table to the evidence map. Produce the required
artefact set (counts of UN, DI, DO, Risk, VT, VAL).

If `change_kind == out_of_scope`, stop. Ask the user before
drafting anything.

### Step 3 - Search before create

For every artefact type in the required set, call
`search_design_controls(query=..., dc_type=...)`. Inspect any
near-matches with `get_design_control`. Prefer update to create.

If the list endpoint for DO/VT/VAL returns empty, traverse from
the parent UN/DI via `traceability_edges` in the
`get_design_control` response.

### Step 4 - Draft artefacts and run the language gate

For each artefact, draft the fields per
`.cursor/skills/atlas-references/artefact-templates.md`. Then
run the language gate from
`atlas-language-and-scope-review` against the drafts. Reject any
banned terms or out-of-scope claims.

### Step 5 - Ground DOs in real code

For each DO, hand off to `atlas-do-mapper`. Confirm every
`source_reference` path exists with `Glob` or `Read`. Reject
provisional DOs.

### Step 6 - Build the atomic write plan

Draft the full plan in chat before any write. See the template
in `.cursor/skills/atlas-references/atlas-mcp-workflow.md`
(section "The atomic write plan"). The plan must include:

- All create or update steps in dependency order.
- All link steps with explicit relationship names.
- The `get_traceability_gaps` post-flight check.
- The `record_verification_run` / `record_validation_run` steps
  for every new VT and VAL.

### Step 7 - Read the MCP tool descriptors

Before each tool call, read the corresponding `.json` descriptor
under
`/Users/robsmith/.cursor/projects/Users-robsmith-Documents-github-LEO-AI-CORE/mcps/user-atlas-design-controls/tools/`
to confirm required fields and types. The repository's
`atlas-design-controls-validation.mdc` rule lists known pitfalls.

### Step 8 - Execute the plan

Run each step via `CallMcpTool` on the `user-atlas-design-controls`
server. Stop at the first failure. Do not retry silently. On
failure, surface the partial state in the audit report and
escalate to the user.

For partial fixes:

- If `create_design_output` drops `source_reference`, call
  `update_design_output` immediately to set it.
- If `update_design_input` cannot change a wrong `requirement`
  field, retire and replace via `retire_design_control` followed
  by a fresh create.
- If a relationship link fails, unlink any half-made links
  before reporting the failure.

### Step 9 - Record VT and VAL runs

After each new VT or VAL is created and linked, run the test or
inspection off-Atlas:

- Python: `pytest <path> -v`
- UI unit: `cd services/ui && npx jest --testPathPatterns "<pattern>" --no-coverage`
- UI e2e: `cd services/ui && npx playwright test <path>`
- Inspection: read the code surfaces and capture findings in
  `notes`.

Then resolve the UUID via `get_design_control(...).id` and call
`record_verification_run` / `record_validation_run`.

### Step 10 - Run get_traceability_gaps

Call
`get_traceability_gaps(product_id="PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4")`.
The new dcIds must not appear in `orphan_design_inputs` or
`orphan_design_outputs`. If they do, the link did not stick;
re-call `link_design_controls`.

### Step 11 - Emit the audit report

Print the audit report per
`.cursor/skills/atlas-references/audit-report-format.md`. This
is the final step; the run is not complete without it.

## Decision shortcuts

| Situation                                    | Action                                         |
|----------------------------------------------|------------------------------------------------|
| New behaviour added                          | Full chain: UN, DI, DO, Risk (if B), VT       |
| Behaviour changed                            | Update DI/DO, review Risk, new VT run         |
| Existing DI's `requirement` text is wrong    | Retire and replace                            |
| DO `source_reference` is stale               | Update DO with current paths                  |
| VT exists but never recorded                 | Run it, record `pass` or `fail`               |
| Out-of-scope feature requested               | Stop and ask the user                         |
| Class C would be needed                      | Stop and escalate to CSO and QA/RA            |

## Related

- Skill: `atlas-codebase-audit` produces the evidence map.
- Skill: `atlas-do-mapper` grounds DOs in real code.
- Skill: `atlas-language-and-scope-review` runs the wording gate.
- References:
  - `.cursor/skills/atlas-references/artefact-templates.md`
  - `.cursor/skills/atlas-references/decision-engine.md`
  - `.cursor/skills/atlas-references/atlas-mcp-workflow.md`
  - `.cursor/skills/atlas-references/vocabulary.md`
  - `.cursor/skills/atlas-references/audit-report-format.md`
- Rules:
  - `.cursor/rules/atlas-design-controls-first.mdc`
  - `.cursor/rules/atlas-design-controls-validation.mdc`
  - `.cursor/rules/atlas-vt-enforcement.mdc`
  - `.cursor/rules/atlas-do-implementation-mapping.mdc`
  - `.cursor/rules/health-literacy.mdc`
