---
name: referral-pipeline-dry-run
description: >-
  Pulls referral documents, converts and chunks them locally, de-identifies
  the text, then dry-runs the referral pipeline with no Neo4j write-back.
  Use when verifying pipeline accuracy on a service, UBRN list, or specialty
  (GI and Liver, Lower GI, 2WW, gynae, breast), or when the user says dry-run,
  pull and chunk, or clinical review of extraction, coding, completeness,
  guidelines, or SBAR. If the organisation or :Service is unclear, ask
  before pulling.
---

# Referral pipeline dry-run

Reuse the scripts. Do not invent a second runner.

## Hard stops

- Never `--reset`. Never `clean_run_facts.py`. Never seed production.
- Never Azure Service Bus. The in-process runner unsets those env vars.
- Confirm `NEO4J_URI` before any graph read. Print it. If MCP fails, stop.
- MCP graphs: `user-leo-neo4j` and `user-user-leo-neo4j` are **dev**.
  `user-neo4j-mcp` is **prod**. Say which graph you are on. Do not
  mix them. Do not guess UBRNs or service ids.
- Match the MCP to the job: live RC9 / BedsFT review uses prod
  (`user-neo4j-mcp`). Local or seeded work uses dev.
- Do not start a pull until one `:Service.id` (or an explicit UBRN list)
  is confirmed.
- Fail-closed: a safety-layer error is `degraded`, not a successful no.
- Do not implement fixes unless asked. Do not commit. Do not push.
- Reports use UBRN only. No names, NHS numbers, or dates of birth.

## 1. Resolve the service (blocking)

Skip this section only when the user already gave UBRNs or patient ids.
Then resolve those ids with MCP and go to Act.

If they named a count, specialty, site, or vague label -- for example
"80 lower GI referrals", "GI and Liver", "Bedford gastro" -- **stop and
ask**. Do not pick a service.

### Ask first, if either is missing

Use the `AskQuestion` tool when it is available. Otherwise ask in chat.

1. Which organisation / site? (trust, RC code, hospital)
2. Which `:Service`? (routine vs 2WW, age band, RAS vs A&G)

A number in the request is ambiguous. "80 lower GI" may mean **80
referrals** or the **80+ years** service. Ask which.

### Then look up what they said

Read [resolve-service.md](resolve-service.md). Query Neo4j. Show every
match: id, name, `clinicalType`, referral count, chunk count.

If they say "Lower GI at Bedford", look up before you assume. That
phrase matches more than one node (RC9 2WW age bands, RC1 colorectal,
L&D GI and Liver stub). List them. Do not pick.

### Clarify if required

Ask again when:

- more than one `:Service` matches
- the name is RC1 but they asked for RC9, or the reverse
- they asked for routine GI and Liver and you only found 2WW
- the best name match has 0 referrals (a stub)
- age band, RAS vs A&G, or site (Bedford vs L&D) is still open

Proceed only after they confirm **one service id**, or a short explicit
list of ids. Then sample that service.

## 2. Act

Copy this list and tick it:

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

1. Converter must be up (`http://localhost:8012`). If not, stop.

2. Sample the confirmed service (default 5, or the count they meant
   as a sample size). Prefer referrals with a Clinical Information
   PDF or USC letter. Skip triage-outcome-only packs unless asked.

3. Pull, convert, chunk, de-id (read-only graph):

   `.venv/bin/python scripts/pull_and_chunk_referral.py --referral-id <UBRN> --deid`

4. Dry-run from the local bundle (no graph write):

   `.venv/bin/python scripts/run_referral_inprocess.py --referral-id <UBRN> --dry-run --from-bundle output/chunks/<UBRN>`

   If `--from-bundle` is missing from the script, stop after step 3
   and say so. Do not fall back to `--reset`.

5. If a referral has no usable documents, skip it and continue.

6. Assess every finished referral using [assessment.md](assessment.md).
   Judge LEO against the de-id chunks, not against itself.

## 3. Verify

- Each report is `tmp/referral-quality-dry-run/<UBRN>.json`.
- One-line verdict per referral: Pass / Issues / Fail.
- Batch close: count Pass / Issues / Fail / Skipped, then the
  1-3 defects that would change a clinician's next action.
