---
name: teach-paused-form
description: >-
  Loads a patient or paused extraction, iterates the Teach this form
  schema until ticked boxes become facts and guidance stays sealed,
  then saves the taught form through the product API. Use when the
  user names a patient, UBRN, paused extraction, or asks to teach a
  form, fix a paused referral, or train form extraction.
---

# Teach a paused form

Reuse the product teach path. Do not invent a second store.

Read [acceptance.md](acceptance.md) before you call a letter trained.
Read [watch-outs.md](watch-outs.md) before you edit sections.

## Hard stops

- Print `NEO4J_URI` before any graph read or write. If MCP fails, stop.
- Patient reads: `user-neo4j-mcp` first. Named tools before raw Cypher.
  `user-user-leo-neo4j` / `user-leo-neo4j` may be the wrong graph.
- Writes go through `save_form_schema` or `PUT /api/form-schemas/{fingerprint}`.
  Never `scripts/seed_* --write-graph`. Never hand-written `MERGE (:FormSchema)`.
- Ask before you write a schema to the graph that `NEO4J_URI` names.
- Never `--reset`. Never Azure Service Bus unless the user asked to
  unlock or re-run that paused task.
- Do not teach a tick-box schema onto a free-text Clinical Information
  Summary or a cover sheet only.
- Do not overwrite a library form for a different letter type
  (same clinic, different layout) without asking.
- Reports use UBRN only. No names, NHS numbers, or dates of birth.
- Cap: 5 local probe/edit cycles, then stop and report.

## Progress

Copy and tick:

```
Teach-form progress:
- [ ] Printed NEO4J_URI
- [ ] Target resolved (patient / UBRN / paused task)
- [ ] Letter type classified (2WW form / free text / wrapper)
- [ ] Current schema loaded (or none)
- [ ] Local probe red, then patched, then green
- [ ] User approved the write
- [ ] Schema saved via product path
- [ ] Acceptance checked
```

## 1. Resolve the target

The user may give a patient id, NHS number, UBRN, or a paused-task id.

1. Confirm `NEO4J_URI`.
2. Resolve to one `ReferralRequest` and its latest letter chunks.
   Prefer `user-neo4j-mcp` `read-cypher` with the UBRN or patient id
   they typed. Do not guess.
3. Collect: UBRN, `organization_id`, `service_id`, org name, service
   name, joined letter text, pause reason if an `HITLTask` exists.
4. If several referrals match, list them (UBRN, service, date) and ask.

If they said "a paused extraction" with no id, list open
`:HITLTask` rows (task id, UBRN, service, reason). Ask which one.

## 2. Classify the letter

Read the first and last 80 lines.

| Letter looks like | Action |
| --- | --- |
| Tick-box 2WW (Section A/B, `[X]`, ECOG) | Teach this form. |
| Free-text GP / Clinical Information Summary | Stop teach. Say so. Review facts only if asked. |
| Cover sheet + form | Teach the clinical form. Mark the cover sheet `admin` or `template_noise`. |
| Cover sheet only | Do not invent Section A boxes. |

If a library schema is already bound to this org + service, load it.
Say whether bind is `exact_hash` or `org_service`.
`org_service` on a free-text letter is a coarse bind -- do not "fix"
it by rewriting the 2WW template.

## 3. Iterate locally (no write)

Write the letter to `tmp/teach-form/<UBRN>-letter.txt` (de-identify
if you already have de-id text).
Write the current or drafted schema to `tmp/teach-form/<UBRN>-schema.json`.

```
.venv/bin/python .cursor/skills/teach-paused-form/scripts/probe_form_schema.py \
  --letter tmp/teach-form/<UBRN>-letter.txt \
  --schema tmp/teach-form/<UBRN>-schema.json
```

The probe is green only when:

- every `[X]` / `(X)` clinical tick has a seeded `entity_text`
- unticked boxes do not seed
- guidance / cover-sheet lines are sealed (`[NON_EXTRACTABLE]`)
- no skip-only schema (at least one clinical section with items or free text)

If red, patch the schema JSON:

- add or fix `start_pattern` (heading on the letter)
- set `section_type` (`checkbox_multi`, `checkbox_yesno`, `scale`,
  `free_text`, `admin`, `template_noise`, `ordered_tests`, `observable`)
- fix `pattern` so `A2` and `A.2` both match (`A\.?2`)
- write `entity_text` as a clinical sentence, not `A1`
- mark "Points to remember", mastalgia advice, NICE boxes as
  `template_noise`
- drop completeness groups that have no SNOMED `concept_ids`

Re-run the probe. Repeat up to 5 times.

Changing `section_type` clears items. Set the type first.

## 4. Save (only after ask + green probe)

Show the user: fingerprint, org, service, section count, seeded facts,
and what you sealed. Ask to write.

Then persist with the same payload the UI sends:

- `form_name`, `sections`, `organization_id`, `service_id`,
  `organization_name`, `service_name`, `completeness_groups`
- `PUT /api/form-schemas/{fingerprint}` if core-api is up, **or**
- `.venv/bin/python` calling `libs.pipeline.form_schema_store.save_form_schema`
  (the function the API uses)

Fingerprint must not be `unknown`.
At least one section needs a start pattern (label fills it if blank).

Do not save vacant completeness rules. Empty groups are safer.

## 5. Confirm trained

A form is trained when [acceptance.md](acceptance.md) is green.

If the user asked to unlock this paused letter, then
`POST /api/operations/extraction-reviews/rerun-extraction`
(same as Save schema on My Work). Otherwise leave the task in the list.

Optional check on a **second** letter of the same form (different UBRN,
same service): run the probe only. Do not rewrite the schema from a
free-text outlier.

## 6. Report

UBRN only. One line: Trained / Partial / Stopped.

Then:

1. Letter type and bind (`exact_hash` / `org_service` / `none`).
2. What was wrong on the first probe.
3. What you changed (sections, skip blocks, patterns).
4. Seeded facts after the last probe.
5. Whether the graph write happened.
6. What still needs a person (codes, a second letter, unlock).
