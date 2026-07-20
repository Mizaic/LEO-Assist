# Validation Lab -- keep / retire matrix

Atlas: UN-4DCE95C8, DI-724CD8A5, DI-2289D095, DI-9138BAC9, DI-A898556B.

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

## Fold into Validation Lab

| Surface | Lab destination |
| --- | --- |
| Manual SBAR Playground | Lab run on case or attached patient |
| Scenario Runs + Consumer Validation | Lab suite run + CDN widget |
| Extraction Scenarios admin CRUD | Lab case list / editor |
| Coding Validation page | Lab gold code fields |
| Quick Test drawer | Lab scratch case |
| Test Patients Knowledge tab | Lab **Fixtures** view (build / copy / replay) |
| Test Patient expected SBAR / rules editors | Lab **Cases** gold (`matching_rules` + SBAR) |

## Single testing experience

Validation Lab is one Knowledge tab with two views:

1. **Cases** -- production-shaped `:ValidationCase`, phase runs, gold promote, CDN SBAR.
2. **Fixtures** -- former Test Patients library (`:TestPatient` build / replay).

Legacy `?tab=test-patients` redirects to `?tab=validation-lab&view=fixtures`.

## Retire (redirect)

Legacy routes redirect to `/admin/validation-lab` with a short notice.
Pathway probes remain on `/admin/pathways/[id]`.

## Locked run policy

- Default Lab run persist mode = `production` (graph writes allowed).
- Dry-run cannot promote gold (API 409).
- Production Lab runs write `:Assessment` when the SBAR phase is selected
  and enqueue the coding pipeline with `dry_run=false`.

## Pathway Builder probes (kept)

Pathway Builder probes remain for PlanDefinition authoring only.
They must not become the clinical gold corpus. Clinical regression gold
lives exclusively in Validation Lab (`:ValidationCase` + gold JSON).
