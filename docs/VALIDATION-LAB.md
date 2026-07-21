# Validation Lab -- single patient flow

Atlas: UN-4DCE95C8, DI-724CD8A5, DI-2289D095, DI-9138BAC9, DI-A898556B,
DI-D01C6EC8 (A&G), DI-D6E5F94E (SPoA scenarios).

**Governance gate:** Do not add new admin playground, scenario-run,
quick-test, or parallel extraction-validation pages. Extend Validation
Lab (`/admin/validation-lab`) instead, unless a DI exception is filed.

## Keep

| Surface | Role |
| --- | --- |
| Pathway Builder probes | PlanDefinition authoring dry-run only; not clinical gold |
| Operations Run | Production / gold-training job queue |
| Gold Dataset (sentence GoldLabels) | NER sentence gold; link from Lab cases when needed |
| Prompt Simulator | Single-prompt authoring |
| Coding Review / Ask LEO | Production review |
| Local guideline import verify | Guidance authoring |
| `libs/referral_simulator` | Lab write path for referral-shaped graphs |
| Historic guideline shadow-diff (`/guidance/shadow`) | Candidate vs baseline on real, already-coded patients |

## Retired -- all synthetic-data surfaces

The `:TestPatient` knowledge-graph library, its code-level bitmap-replay
harness, the AI Summarisation manual playground / scenario runs, the
Coding Validation quick-check page, and the Quick Test drawer have all
been **deleted**, not just redirected. There is no "Fixtures" view any
more -- fixtures never matched a real encounter or referral shape, so
they have been replaced entirely by the single patient flow below.

| Retired surface | Deleted files |
| --- | --- |
| Test Patients Knowledge tab | `services/ui/src/app/admin/knowledge/test-patients/**` |
| `:TestPatient` backend | `services/api/app/routers/test_patients.py`, `app/services/test_patient_*.py`, `libs/cypher/test_patient_queries.py` |
| Code-level bitmap replay for fixtures | `services/api/app/services/test_patient_shadow.py` (real-patient shadow-diff survives in `app/services/guideline_shadow.py`) |
| AI Summarisation manual playground + scenario runs, Coding Validation, Quick Test | Pages are now redirect stubs; see `scripts/reset_validation_lab.py` for the graph-side purge |

Run `scripts/reset_validation_lab.py --yes` to purge any leftover
`:TestPatient` nodes, `:ValidationCase` cases, and
`source in ('ai_summarisation_scenario', 'quick-test')` patient graphs.

## Single testing experience: one patient, one flow

Validation Lab (`/admin/validation-lab`, or the "Validation Lab"
Knowledge tab) is **one guided wizard**, not a Cases/Fixtures split:

1. **New test patient** -- choose a scenario, title, optional
   name/age/sex (SPoA scenarios also accept NHS number and GP practice).
2. **Build profile** -- optional, repeatable PMH rows (condition /
   medication / allergy), each SNOMED-coded via the concept picker.
3. **Encounters or GP consultation** -- generic scenarios use optional
   prior encounter notes; SPoA scenarios require a typed GP consultation
   encounter (`encounter_kind=gp_consultation`). Neither is pipeline
   input.
4. **Clinical text / submission** -- referral letter chunks, or an
   Advice and Guidance (A&G) communication thread. SPoA scenarios add a
   reason-for-submission field and inject seeded verbalised PMH into
   that submission text only (not into the GP consult note).
5. **Submit** -- enqueues the same production event (referral-received
   or A&G thread assessment), polls the real pipeline run, and renders
   the genuine SBAR via the CDN widget (`LeoSbarHost`). Nothing here is
   fabricated or echoed back from the case's own gold values.

This replaces the old `mode` + `clinical_text` single-shot case form
and the separate code-replay-only Fixtures library. See
`libs/validation_lab/models.py` (`ValidationCaseSpec`: `pmh`,
`encounters`, `referral_text`, `scenario_type`) and
`services/ui/src/app/admin/validation-lab/CreatePatientWizard.tsx`.

## Scenario templates (SPoA-aligned)

| Scenario | `scenario_type` | `case_type` | Graph path | Pipeline input |
| --- | --- | --- | --- | --- |
| Generic referral | `generic` | `referral` | Minimal patient + optional encounters + referral chunks | `document_chunks` |
| Generic A&G | `generic` | `ag` | Minimal patient + CommunicationRequest thread | `communication_thread` |
| SPoA: A&G request | `spo_ag` | `ag` | EPC-shaped patient -> GP consult -> A&G thread | `communication_thread` |
| RAS: Referral | `ras_referral` | `referral` | EPC-shaped patient -> GP consult -> referral chunks | `document_chunks` |

**PMH verbalisation** (SPoA only, submission text only): for each
structured PMH concept, pick a seeded surface form, else a SNOMED
synonym (non-FSN), else the preferred term with the semantic tag
stripped. Structured PMH nodes remain on the patient graph for
gold/display. See `libs/validation_lab/pmh_verbalisation.py` and
`POST /validation-lab/preview-pmh-narrative`.

Cross-link: [REFERRAL-PIPELINE-INTEGRATION.md](./REFERRAL-PIPELINE-INTEGRATION.md).

## Candidate ruleset testing (Bitmap Lifecycle)

The Bitmap Lifecycle "Test candidate on Lab patients" step resubmits
saved Validation Lab patients' referrals through the **real** pipeline
with `guideline_ruleset_version` pinned to the candidate bitmap
(`libs/referral_simulator/message.py` ->
`libs/workflow/durable_steps.py` ->
`libs/pipeline_graph/subgraphs/compliance.py`). This is a per-run
override only -- it never touches the Redis "current version" pointer
used by real traffic. "Historic shadow" is a separate, purely
read-only comparison against real already-coded patients and is
unaffected by any of this.

## Retire (redirect)

Legacy routes redirect to `/admin/validation-lab` with a short notice.
Pathway probes remain on `/admin/pathways/[id]`.

## Locked run policy

- Default Lab run persist mode = `production` (graph writes allowed).
- Dry-run cannot promote gold (API 409).
- Production Lab runs enqueue the real coding pipeline
  (`dry_run=false`); the run is scored against gold only once the
  real pipeline outputs are available -- never before.

## Pathway Builder probes (kept)

Pathway Builder probes remain for PlanDefinition authoring only.
They must not become the clinical gold corpus. Clinical regression gold
lives exclusively in Validation Lab (`:ValidationCase` + gold JSON).
