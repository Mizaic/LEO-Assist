# Handover: referral pipeline dry-run and Teach a paused form

**Audience:** the next person (or Cursor agent) who must review live referrals or teach a hospital form.
**What this is:** how to run the two Cursor skills, not how to click My Work.
**Product screens:** see [paused-extractions-and-teach-this-form.md](paused-extractions-and-teach-this-form.md) for the UI path.

---

## 1. What these two jobs are

They answer different questions. Use the right one.

| Job | Skill | Question it answers | Writes to Neo4j? |
| --- | --- | --- | --- |
| **Dry-run a referral** | `.cursor/skills/referral-pipeline-dry-run/` | Did LEO read this letter correctly? Extraction, coding, completeness, guidelines, SBAR. | No. Local report only. |
| **Teach a paused form** | `.cursor/skills/teach-paused-form/` | Can LEO learn this tick-box form so later letters of the same type do not pause? | Yes, but only after you say so, and only through the product save path. |

Typical sequence on a new trust or specialty:

1. Dry-run a small sample. See what fails.
2. If the letter is a structured 2WW form and ticks did not become facts, teach the form.
3. Dry-run a **second** letter of the same form. Confirm guidance stayed sealed.

Do not teach a form because a dry-run found a coding or guideline bug. Teaching only fixes form layout and tick seeding.

---

## 2. How to start a session

In Cursor, say the job in plain English. The agent should load the matching skill.

**Dry-run examples**

- "Dry-run 5 Lower GI 2WW referrals at Bedford."
- "Pull and chunk UBRN 000481914514 and assess extraction."
- "Clinical review of SBAR on RC9 GI and Liver."

**Teach examples**

- "Teach the paused form for UBRN 000481914514."
- "Fix the paused extraction on this patient."
- "Train the Kings Mill breast 2WW form."

If the agent starts pulling or writing without confirming the organisation and service, stop it.

---

## 3. Shared hard stops (both skills)

Copy these. They are not optional.

1. **Print `NEO4J_URI` before any graph read.** Say which graph you are on.
2. **Do not mix graphs.**
   - Live RC9 / BedsFT / SFH review: `user-neo4j-mcp` (**prod**).
   - Local or seeded work: `user-leo-neo4j` / `user-user-leo-neo4j` (**dev**).
3. **If MCP fails, stop.** Do not guess Unique Booking Reference Numbers (UBRNs) or service ids.
4. **Never `--reset`.** Never `clean_run_facts.py`. Never seed production.
5. **Never Azure Service Bus** unless the user asked to unlock or re-run that paused task. The in-process runner unsets those env vars on purpose.
6. **Reports use UBRN only.** No names, NHS numbers, or dates of birth.
7. **Do not implement fixes unless asked.** Do not commit. Do not push.
8. A safety-layer error is **degraded**, not a successful "no".

---

## 4. What you need running

| Need | Why | If missing |
| --- | --- | --- |
| Repo venv (`.venv`) | Runs the scripts. | Stop. |
| `NEO4J_URI` in env (`secrets/.env`, `secrets/.env.secrets`, or `.env`) | Every script reads this graph. | Print it. If it is the wrong graph, stop. |
| MCP for that same graph | Service lookup and patient reads. | Stop. Do not fall back to ad-hoc shell Cypher. |
| Document converter on `http://localhost:8012` | Dry-run pull converts PDFs to markdown. | Stop the pull. Dry-run of **existing** graph chunks can still run without it. |
| Core API (optional, teach only) | `PUT /api/form-schemas/{fingerprint}`. | Use `save_form_schema` in Python instead. Same function the API uses. |

The converter is the HCCP doc converter. Pull calls `POST /extract` on port 8012. If that service is down, say so and do not invent a second converter.

---

## 5. Skill A -- Referral pipeline dry-run

**Folder:** `.cursor/skills/referral-pipeline-dry-run/`

| File | Use |
| --- | --- |
| `SKILL.md` | Order of work and hard stops. |
| `resolve-service.md` | How to find one `:Service.id`. |
| `assessment.md` | How to judge each finished referral. |

### 5.1 Resolve the service first (blocking)

Skip this only when the user already gave UBRNs or patient ids. Then resolve those ids with MCP and go.

If they named a count, specialty, site, or vague label -- "80 lower GI", "GI and Liver", "Bedford gastro" -- **ask**. Do not pick a service.

Ask:

1. Which organisation / site? (trust, RC code, hospital)
2. Which `:Service`? (routine vs 2WW, age band, RAS vs A&G)

A number is ambiguous. "80 lower GI" may mean **80 referrals** or the **80+ years** service.

Then look up what they said. Show every match: id, name, `clinicalType`, org (or "no org link"), referral count, chunk count. Group by 2WW vs routine, RC9 vs RC1, Bedford vs L&D, age band, RAS vs A&G.

Ask again when:

- more than one `:Service` matches
- the name is RC1 but they asked for RC9, or the reverse
- they asked for routine GI and Liver and you only found 2WW
- the best name match has 0 referrals (a stub)
- age band, RAS vs A&G, or site is still open

Proceed only after they confirm **one service id**, or a short explicit list.

Do not treat these as the same service:

- RC9 2WW Lower GI age bands (`8011574` 80+, `8011575` 18-29, `7957488` 30-79, `8012315` consultant-only)
- RC1 colorectal Lower GI (`133993`) -- routine, not 2WW
- RC1 gastro / upper GI / hepatology / gall bladder
- L&D `124511` "GI and Liver" -- name only, 0 referrals

Default sample size after a service is confirmed: **5**. Use their number only when they said it is a count. Prefer referrals with a Clinical Information PDF or USC letter. Skip triage-outcome-only packs unless asked.

### 5.2 Act

Tick this list:

```
Dry-run progress:
- [ ] Printed NEO4J_URI
- [ ] Org and :Service confirmed (or UBRN list given)
- [ ] Converter up on localhost:8012
- [ ] Sample resolved (MCP)
- [ ] Pulled + chunked + de-id
- [ ] Dry-run (no write-back)
- [ ] Assessed against the letter
```

Pull, convert, chunk, de-identify (read-only graph):

```bash
.venv/bin/python scripts/pull_and_chunk_referral.py --referral-id <UBRN> --deid
```

Writes `output/chunks/<UBRN>/`. That bundle is what you read when you judge LEO.

Dry-run (no graph write):

```bash
.venv/bin/python scripts/run_referral_inprocess.py --referral-id <UBRN> --dry-run
```

Report lands at `tmp/referral-quality-dry-run/<UBRN>.json`.

If a referral has no usable documents, skip it and continue.

### 5.3 Known gap: `--from-bundle`

The skill asks for:

```bash
.venv/bin/python scripts/run_referral_inprocess.py --referral-id <UBRN> --dry-run --from-bundle output/chunks/<UBRN>
```

**That flag is not on the script today.** `--dry-run` loads `:Chunk` nodes already on the graph. It does not re-read the local bundle.

So:

1. Pull-and-chunk gives you a **de-identified letter** to assess against.
2. Dry-run runs the plan in memory against **graph chunks** for that UBRN.
3. If `--from-bundle` is still missing, stop after the pull if the graph has no chunks, and say so. Do not fall back to `--reset`.

The runner unsets Azure Service Bus env vars. It refuses `--reset` with `--dry-run`.

### 5.4 Assess every finished referral

Read the de-id chunks first. Judge LEO against the letter, not against itself. Full rubric: `assessment.md`.

One line first: **Pass / Issues / Fail**.

Then check:

| Area | Pass means |
| --- | --- |
| Extraction | Every important fact is present. Ticked boxes are facts. Guidance is not. |
| Coding | SNOMED matches the span. Assertion is right (present / absent / historical / possible). |
| Completeness | Gaps are real gaps in the record, not facts LEO missed. |
| Guidelines | Pathway matches the suspected site. Already-done results suppress that action. |
| SBAR | Situation leads with this referral. No invented negatives. Failed SBAR is not a pass. |

Known failure modes to look for: guidance extracted as findings; packed boxes losing a neighbour; assertion inversion; wrong NICE NG12 pathway from a secondary symptom; FIT ignored; 2WW pathway on a routine GI and Liver referral.

### 5.5 Close the batch

Count Pass / Issues / Fail / Skipped.

Then name the **1-3 defects that would change a clinician's next action**.

Do not start coding a fix unless the user asked.

---

## 6. Skill B -- Teach a paused form

**Folder:** `.cursor/skills/teach-paused-form/`

| File | Use |
| --- | --- |
| `SKILL.md` | Order of work and hard stops. |
| `acceptance.md` | When you may call a letter **Trained**. |
| `watch-outs.md` | Live SFH breast and gynae failures. Read before you edit sections. |
| `scripts/probe_form_schema.py` | Local red/green probe. No Neo4j write. |

**Reuse the product teach path.** Do not invent a second store. Do not run `scripts/seed_* --write-graph`. Do not hand-write `MERGE (:FormSchema)`.

An earlier session taught SFH breast with `scripts/seed_sfh_breast_2ww_template.py --write-graph`. That is for engineers and fixtures. Day-to-day teaching uses this skill or My Work -> Save schema.

### 6.1 Resolve the target

The user may give a patient id, NHS number, UBRN, or a paused-task id.

1. Print `NEO4J_URI`.
2. Resolve to one `ReferralRequest` and its latest letter chunks. Prefer `user-neo4j-mcp` `read-cypher`. Do not guess.
3. Collect: UBRN, `organization_id`, `service_id`, org name, service name, joined letter text, pause reason if an `HITLTask` exists.
4. If several referrals match, list them (UBRN, service, date) and ask.

If they said "a paused extraction" with no id, list open `:HITLTask` rows (task id, UBRN, service, reason). Ask which one.

Patient reads: `user-neo4j-mcp` first. Named tools before raw Cypher. The local leo Neo4j MCPs may be the wrong graph.

### 6.2 Classify the letter

Read the first and last 80 lines.

| Letter looks like | Action |
| --- | --- |
| Tick-box 2WW (Section A/B, `[X]`, ECOG) | Teach this form. |
| Free-text GP / Clinical Information Summary | **Stop teach.** Say so. Review facts only if asked. |
| Cover sheet + form | Teach the clinical form. Mark the cover sheet `admin` or `template_noise`. |
| Cover sheet only | Do not invent Section A boxes. |

Run `scripts/recognise_form.py` on the letter first. Say the outcome per document: `recognised` (load that schema), `unrecognised` (teach it; the closest form and missing headings are in the evidence), or `not_a_form` (a letter; do not teach).

There is no organisation-and-service bind and no letter-hash bind. A service may use several forms. Do not "fix" an unrecognised letter by rewriting another form's template.

### 6.3 Iterate locally (no write)

Cap: **5** probe/edit cycles, then stop and report.

Write:

- `tmp/teach-form/<UBRN>-letter.txt` (de-identify if you already have de-id text)
- `tmp/teach-form/<UBRN>-schema.json`

```bash
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
- set `section_type` (`checkbox_multi`, `checkbox_yesno`, `scale`, `free_text`, `admin`, `template_noise`, `ordered_tests`, `observable`)
- set `pattern` to the **printed** token (`A1.`, `A.2`). Seeding looks up that string in the letter. A regex such as `A\.?2` can rewrite the line and still fail to seed. If the form prints both `A2` and `A.2`, add two rows with the same `entity_text`
- write `entity_text` as a clinical sentence, not `A1`
- mark "Points to remember", mastalgia advice, NICE boxes as `template_noise`
- drop completeness groups that have no SNOMED `concept_ids`

Changing `section_type` **clears items**. Set the type first.

### 6.4 Save (only after ask + green probe)

Show the user: fingerprint, org, service, section count, seeded facts, and what you sealed. **Ask to write.**

Then persist with the same payload the UI sends:

- `form_name`, `sections`, `organization_id`, `service_id`, `organization_name`, `service_name`, `completeness_groups`
- `PUT /api/form-schemas/{fingerprint}` if core-api is up, **or**
- `.venv/bin/python` calling `libs.pipeline.form_schema_store.save_form_schema`

Fingerprint must not be `unknown`.
At least one section needs a start pattern (label fills it if blank).
Do not save vacant completeness rules. Empty groups are safer.

Do not overwrite a library form for a different letter type (same clinic, different layout) without asking.

### 6.5 Confirm trained

A form is **Trained** only when `acceptance.md` is green. In short:

- structured form, not a 2WW schema forced onto free text
- probe green on the saved schema
- real fingerprint, live org and service ids
- completeness groups empty or every leaf has codes / semantic categories
- save returned the schema
- a later letter of the **same** form should resolve `known_schema=true`

These are **Partial**, not Trained:

- Probe green but you have not written the graph
- Graph written but completeness still has empty members
- Only this letter works; a second same-form letter still leaks guidance
- You reviewed facts on one letter and did not save a schema

If the user asked to unlock this paused letter, then
`POST /api/operations/extraction-reviews/rerun-extraction`
(same as Save schema on My Work). Otherwise leave the task in the list.

Optional check: probe a **second** letter of the same form. Do not rewrite the schema from a free-text outlier.

### 6.6 Report

UBRN only. One line: **Trained / Partial / Stopped**.

Then:

1. Letter type and recognition (`recognised` / `unrecognised` / `not_a_form` / `failed`).
2. What was wrong on the first probe.
3. What you changed (sections, skip blocks, patterns).
4. Seeded facts after the last probe.
5. Whether the graph write happened.
6. What still needs a person (codes, a second letter, unlock).

---

## 7. Watch-outs that already hurt patients

These failed on live SFH breast and gynae letters. Check them on every new form. Detail: `watch-outs.md` and the product manual section 6.

1. **"Points to remember" became patient facts.** Guidance listed bloating, constipation, abdominal pain. Those words were coded. Guidelines then fired ovarian tests, FIT, and a prostate rule. Mark that block `template_noise`.
2. **Coarse org/service bind.** A schema on organisation + service attaches to every letter for that clinic: 2WW form, Clinical Information Summary, cover sheet. Do not invent Section A boxes that are not on that letter.
3. **Printed codes drift.** Same row may print `A2` or `A.2`. Add two items with the same entity text. Do not use a regex that is not on the page.
4. **Packed boxes.** Several Yes boxes on one line (A3-A6) pair in order. A tick on A5 must not become A3. Short pattern `0` matches the ECOG heading. Use `0` plus "Fully active".
5. **Completeness vacancy.** Site names often have no SNOMED codes. A group with no `concept_ids` can score as met. Delete those rules or add codes before save.
6. **Ask LEO again / detect.** Fresh detect replaces every section. Patch the saved sections instead.
7. **Wrapper vs form.** Pause reason `wrapper_admin_only` means the first page is a cover sheet. Teach the clinical form. Seal the wrapper.
8. **Denied text.** "No known family history" must not seed as present. That is a Review facts / guard issue, not a missing tick-box row.

---

## 8. How the two skills join

```
User names a service or UBRN
        |
        v
   Dry-run skill
   (read letter, run pipeline, no write)
        |
        +-- Pass --> report and stop
        |
        +-- Form ticks missed / guidance leaked
        |         |
        |         v
        |    Teach-paused-form skill
        |    (local probe, ask, then product save)
        |         |
        |         v
        |    Dry-run a second same-form letter
        |
        +-- Coding / guideline / SBAR defect
                  |
                  v
             Report the defect. Do not teach.
             Wait for the user to ask for a code fix.
```

---

## 9. What "done" looks like

**Dry-run is done when**

- `NEO4J_URI` was printed and the graph matches the job
- one service id or UBRN list was confirmed
- each sampled referral has Pass / Issues / Fail / Skipped
- reports are under `tmp/referral-quality-dry-run/`
- the close names the 1-3 clinician-facing defects
- nothing was written to Neo4j
- no commit, no push, no unsolicited fix

**Teach is done when**

- letter type was classified (and free-text was not forced into a tick-box schema)
- local probe is green (or you stopped after 5 cycles and said Partial)
- the user approved the write
- save went through `save_form_schema` or `PUT /api/form-schemas/{fingerprint}`
- acceptance.md is green before you say **Trained**
- the report is UBRN-only

---

## 10. If something looks wrong

| You see | Do this |
| --- | --- |
| MCP auth fails | Stop. Ask to fix MCP. Do not query Neo4j from a random shell. |
| `NEO4J_URI` is localhost but the user asked for live RC9 | Stop. You are on the wrong graph. |
| Converter down on :8012 | Stop the pull. Say so. |
| `--from-bundle` missing and graph has no chunks | Stop after pull. Do not `--reset`. |
| Several `:Service` rows match | List them. Ask for one id. |
| Best name match has 0 referrals | It is a stub. Ask again. |
| Letter is free-text CIS | Do not teach. Review facts only if asked. |
| Library form is gynae on a breast letter | Stop. Wrong bind. |
| Probe still red after 5 cycles | Stop. Report Partial. Hand back to a person. |
| User did not approve the write | Leave the graph alone. |
| Next letter of the same clinic still pauses | It may be a different layout (CIS vs 2WW). Teach only if it is the same form. |

---

## 11. Files and scripts (do not invent others)

| Path | Role |
| --- | --- |
| `scripts/pull_and_chunk_referral.py` | Pull docs, convert, chunk, optional `--deid`. Read-only graph. |
| `scripts/run_referral_inprocess.py` | In-process pipeline. `--dry-run` = no write-back. |
| `libs/referral_quality/inprocess_dry_run.py` | Dry-run engine. Write guard on Cypher. |
| `libs/pipeline/form_schema_store.py` | Product save used by the API and this skill. |
| `.cursor/skills/teach-paused-form/scripts/probe_form_schema.py` | Local teach probe. |
| `docs/operations/paused-extractions-and-teach-this-form.md` | My Work UI manual. |

Banned for routine work:

- `scripts/run_referral_inprocess.py --reset`
- `scripts/clean_run_facts.py`
- `scripts/seed_sfh_breast_2ww_template.py --write-graph`
- `scripts/seed_sfh_gynae_2ww_template.py --write-graph`
- hand-written `MERGE (:FormSchema)`
