# Atlas MCP Workflow

The `user-atlas-design-controls` MCP server is the only place
design controls live. This reference lists the calls the
orchestrator uses, in the order it uses them.

For the schema of each tool, always call the tool descriptor
first (the MCP folder under
`.cursor/projects/.../mcps/user-atlas-design-controls/tools/`).
Atlas validates server-side; this reference covers the local
discipline.

Product ID for every call:
`PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4`.

## 1. Look before you write

For every artefact the decision engine says you need:

```
search_design_controls(
  query="<plain English of the change>",
  dc_type="user-need" | "design-input" | "design-output"
          | "risk" | "verification-test" | "validation-test",
)
```

`dc_type` values use hyphens, not underscores. Search returns
candidate matches with dcIds. If something close exists, fetch
it:

```
get_design_control(dc_type=..., dc_id="UN-XXXXXXXX")
```

The response contains the artefact AND `traceability_edges` for
its parents and children. Use those edges to find linked DOs,
VTs, VALs, and Risks even when the corresponding list endpoints
return empty.

## 2. Discovery for the broader graph

| Goal                                | Call |
|-------------------------------------|------|
| All active UNs for a product        | `list_user_needs(product_id=...)` |
| All active DIs                      | `list_design_inputs(product_id=...)` |
| All active Risks                    | `list_risks(product_id=...)` |
| Acceptance criteria coverage        | `list_acceptance_criteria(product_id=...)` |
| Orphan UN/DI/DO                     | `get_traceability_gaps(product_id=...)` |
| Counts and health                   | `get_design_control_stats(product_id=...)` |

Note: `list_design_outputs`, `list_verification_tests`, and
`list_validation_tests` can return empty even when artefacts
exist. Always confirm by traversing from the parent DI.

## 3. Create calls

Use these only after search-before-create returns no good match.
Each create returns a fresh dcId in the 8-hex format.

- `create_user_need(...)`
- `create_design_input(...)`
- `create_design_output(...)`
- `create_risk(...)`
- `create_verification_test(...)`
- `create_validation_test(...)`

Required fields per type are in `artefact-templates.md`. Validation
rules are in `.cursor/rules/atlas-design-controls-validation.mdc`.

## 4. Update calls

`update_*` tools mostly take the internal UUID, not the dcId.
Resolve via `get_design_control(...).id` first.

- `update_user_need(dc_id=<UUID>, ...)`
- `update_design_input(dc_id=<UUID>, ...)` - note: the legacy
  `requirement` field is NOT exposed. If a DI's `requirement`
  text is wrong, retire and replace.
- `update_design_output(dc_id=<UUID>, ...)` - use this after
  `create_design_output` if `source_reference` does not stick on
  initial creation.
- `update_verification_test(dc_id=<UUID>, ...)`
- `update_validation_test(dc_id=<UUID>, ...)` - note:
  `protocol_preconditions` is a single string, not a list.
- `update_risk(risk_id=<UUID>, ...)`

## 5. Link and unlink

```
link_design_controls(
  source_ids=["..."], target_ids=["..."],
  relationship="HAS_DESIGN_INPUT" | "IMPLEMENTS"
             | "VERIFIES" | "TESTS"
             | "MITIGATES" | "VALIDATES",
)
unlink_design_controls(source_ids=..., target_ids=..., relationship=...)
```

`source_ids` and `target_ids` are arrays of dcIds. The direction
matters; see the linking cheat sheet in `artefact-templates.md`.

## 6. Retire instead of delete

For artefacts that are wrong (bad `requirement` text, out of
scope, duplicate):

```
retire_design_control(
  dc_type=..., dc_id="DI-XXXXXXXX",
  retirement_reason="<one paragraph; cite replacement dcId>",
)
```

Always unlink the artefact from its parents and children before
retiring, then verify with `get_traceability_gaps`.

## 7. Record runs

A VT or VAL is not done until its run is in Atlas.

```
record_verification_run(
  vt_id=<VT UUID>,
  result="pass" | "fail",
  executed_by="<who or ci>",
  notes="<counts, log refs>",
  environment="ci" | "local" | "staging",
)

record_validation_run(
  val_id=<VAL UUID>,
  result="pass" | "fail",
  executed_by="<clinician / panel>",
  notes="<sample size, sites, headline result>",
  environment="local" | "staging" | "production",
)
```

Both use the UUID from `get_design_control(...).id`, not the dcId.

## 8. The atomic write plan

Before calling any write tool, draft the full plan in chat or in
a scratch note. Do not skip steps; do not reorder steps.

```
plan:
  - search: <query> on dc_type=user-need
  - create_or_update: UN-XXXX (title=..., description=...)
  - search: <query> on dc_type=design-input
  - create_or_update: DI-YYYY (description=SHALL ...)
  - link: UN-XXXX -> DI-YYYY HAS_DESIGN_INPUT
  - search: <query> on dc_type=design-output
  - create_or_update: DO-ZZZZ with source_reference=...
  - link: DO-ZZZZ -> DI-YYYY IMPLEMENTS
  - search: <query> on dc_type=risk
  - create_or_update: R-WWWW with full ISO 14971 fields
  - link: DI-YYYY -> R-WWWW MITIGATES
  - search: <query> on dc_type=verification-test
  - create_or_update: VT-VVVV with protocol_steps=...
  - link: VT-VVVV -> DI-YYYY VERIFIES
  - link: VT-VVVV -> DO-ZZZZ TESTS
  - run VT off-Atlas (pytest/jest/inspection)
  - record_verification_run: VT-VVVV result=pass
  - (if clinical outcome visible) create VAL-UUUU
  - link: VAL-UUUU -> UN-XXXX VALIDATES
  - record_validation_run: VAL-UUUU result=pass
  - get_traceability_gaps: confirm none orphaned
```

Execute top-to-bottom. Stop at the first failure and report the
partial state. Do not retry silently. Do not skip the
post-flight `get_traceability_gaps` call.

## 9. Post-call sanity

After every batch:

1. `get_traceability_gaps(product_id=...)` - the new dcIds must
   not appear in `orphan_design_inputs` or
   `orphan_design_outputs`.
2. `get_design_control(...)` on each new artefact - confirm
   `traceability_edges` show the links you made.
3. For VTs: confirm the latest run is the one you recorded.
4. For Risks: confirm the `MITIGATES` link to each DI is present
   on the DI's neighbour list.

## 10. Failure modes seen in this repo

- **List endpoint returns empty**: traverse from the DI's
  `traceability_edges` instead.
- **`source_reference` lost on create**: call
  `update_design_output` immediately after to set it.
- **`protocol_preconditions` rejected as list**: join with `; `
  into a single string.
- **`update_design_input` cannot change `requirement`**: retire
  and replace.
- **`record_verification_run` rejects dcId**: use the UUID from
  `get_design_control(...).id`.
- **`literal_error` on `dc_type`**: use hyphenated values
  (`user-need`, not `user_need`).
