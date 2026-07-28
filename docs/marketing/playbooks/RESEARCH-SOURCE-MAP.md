# Research source map

Every module in the COO service catalogue (`docs/marketing/build_coo_service_catalogue.py`),
mapped to the repo evidence and NHS policy that back it. Use this file to find
the anchor sources before you open a playbook or outline.

Module numbering source of truth: the **E0-E9** scheme in
`docs/marketing/build_coo_service_catalogue.py` (the delivered pptx). The
earlier `deloitte-leo-cds-transformation-offers.canvas.tsx` used an E0-E11
scheme -- that canvas is superseded for module numbering and is not used as a
source for this dossier.

## How to read the density column

- **High** -- one or more QMS/product documents describe the exact steps a
  consultant would run. A full playbook is justified.
- **Medium** -- product capability exists (UI, API, Validation Lab scenario)
  but there is no procedure document. An outline synthesises an operating
  model from the product plus NHS policy.
- **Low** -- marketing claim only, or a single SLO/checklist. An outline
  states what exists today and flags the rest as consulting-only, informed by
  NHS policy.

## Module map

| Module | Catalogue name (pptx) | Density | Anchor sources | Output |
|---|---|---|---|---|
| E0 | Readiness diagnostic | Low | Elective SPoA Technical Guidance priority list; no repo diagnostic tool | Outline |
| E1 | Elective SPoA operating model | Medium | [services/design-system/src/roles/types.ts](../../../services/design-system/src/roles/types.ts); Validation Lab `ras_referral` scenario; NHSE SPoA letter | Outline |
| E2 | Advice and Guidance acceleration | Medium | Validation Lab `spo_ag` scenario ([docs/VALIDATION-LAB.md](../../VALIDATION-LAB.md)); [docs/REFERRAL-PIPELINE-INTEGRATION.md](../../REFERRAL-PIPELINE-INTEGRATION.md) `communication_thread` mode; NHSE A&G framework | Outline (Package B wrapper) |
| E3 | Integration and embed | High | [docs/REFERRAL-PIPELINE-INTEGRATION.md](../../REFERRAL-PIPELINE-INTEGRATION.md); [services/widget-sdk/README.md](../../../services/widget-sdk/README.md); [compliance/policy/leo-widget-ifu.md](../../../compliance/policy/leo-widget-ifu.md); [compliance/policy/DC-INST-001-installation-procedure.md](../../../compliance/policy/DC-INST-001-installation-procedure.md); [compliance/policy/DC-DEP-001-deployment-configuration.md](../../../compliance/policy/DC-DEP-001-deployment-configuration.md); [compliance/policy/DC-DPA-002-addendum-b-referral-assessment.md](../../../compliance/policy/DC-DPA-002-addendum-b-referral-assessment.md) | **Full playbook** |
| E4 | Pathway and guideline factory | High | [compliance/policy/LEO-OP-001-customer-pathway-onboarding-procedure.md](../../../compliance/policy/LEO-OP-001-customer-pathway-onboarding-procedure.md); [compliance/policy/LEO-UM-CG-001-clinical-guidelines-user-manual.md](../../../compliance/policy/LEO-UM-CG-001-clinical-guidelines-user-manual.md); [compliance/policy/DC-GOV-001-service-minimum-dataset-onboarding-procedure.md](../../../compliance/policy/DC-GOV-001-service-minimum-dataset-onboarding-procedure.md); Validation Lab VALs | **Full playbook** |
| E5 | Cancer / NCDA mobilisation | High product / low SOP | NCDA UI (queues, timelines, safety-netting worklists); no dedicated onboarding SOP | Outline (Package C wrapper) |
| E6 | Coding operations | High product / low SOP | Coding review UI, Ask LEO assist, terminology writeback loop; no dedicated operating-rhythm SOP | Outline (Package C wrapper) |
| E7 | Neighbourhood diversion design | Low | NHSE Neighbourhood health guidelines; catalogue's own "what we will not promise" boundary slide | Outline (Package D wrapper) |
| E8 | Clinical safety and regulatory (Safe Deploy Assure) | High | [compliance/policy/SVP-LEO-CDS-001-service-plan.md](../../../compliance/policy/SVP-LEO-CDS-001-service-plan.md); [compliance/policy/DC-INST-001-installation-procedure.md](../../../compliance/policy/DC-INST-001-installation-procedure.md); [compliance/policy/DC-DTAC-001-dtac-compliance-statement.md](../../../compliance/policy/DC-DTAC-001-dtac-compliance-statement.md); [docs/operations/pilot-go-no-go-checklist.md](../../operations/pilot-go-no-go-checklist.md); [compliance/GATE6-RELEASE-CHECKLIST.md](../../../compliance/GATE6-RELEASE-CHECKLIST.md) | **Full playbook** (doubles as Package E) |
| E9 | Benefits and evaluation | Low | [docs/operations/pilot-slos.md](../../operations/pilot-slos.md); NHSE A&G framework metrics; no benefits-realisation SOP | Outline |

## Package wrappers

Packages A-D bundle module playbooks/outlines for a specific buyer. Package E
has no separate wrapper: it is module E8 plus the pptx's "Validation Lab as a
rehearsal space" training line, so `PB-E8-safe-deploy-assure.md` already
covers Package E in full.

| Package | Bundles | Wrapper file |
|---|---|---|
| A | Elective SPoA Accelerate | E0 + E1 + E3 + E4 (+ E8 in parallel) | [outlines/PKG-A-elective-spoa-accelerate.md](outlines/PKG-A-elective-spoa-accelerate.md) |
| B | ICB Advice and Guidance Maturity | E2 (+ E9 for the evaluation pack) | [outlines/PKG-B-icb-ag-maturity.md](outlines/PKG-B-icb-ag-maturity.md) |
| C | Cancer Audit Factory | E5 + E6 (+ E9) | [outlines/PKG-C-cancer-audit-factory.md](outlines/PKG-C-cancer-audit-factory.md) |
| D | Neighbourhood Diversion Pilot | E7 | [outlines/PKG-D-neighbourhood-diversion.md](outlines/PKG-D-neighbourhood-diversion.md) |
| E | Safe Deploy Assure | E8 (no wrapper file -- see [playbooks/PB-E8-safe-deploy-assure.md](playbooks/PB-E8-safe-deploy-assure.md)) | n/a |

## Cross-cutting sources (used by more than one module)

| Source | Used by |
|---|---|
| [services/design-system/src/roles/types.ts](../../../services/design-system/src/roles/types.ts) | E1, E3, E4, E5, E6 (role mapping) |
| [docs/VALIDATION-LAB.md](../../VALIDATION-LAB.md) | E1, E2, E4, E8 (rehearsal evidence) |
| [compliance/policy/DC-DPA-002-full-data-processing-agreement.md](../../../compliance/policy/DC-DPA-002-full-data-processing-agreement.md) and its Addendum B | E3, E8 |
| [compliance/policy/intended-use.md](../../../compliance/policy/intended-use.md) | All modules (scope boundary) |
| [docs/operations/pilot-slos.md](../../operations/pilot-slos.md), [docs/operations/monitoring-alerts.md](../../operations/monitoring-alerts.md), [docs/operations/incident-runbook-pipeline-jobs.md](../../operations/incident-runbook-pipeline-jobs.md) | E8, E9 |

## Validation Lab evidence used as interim procedure evidence

These Playwright VAL specs exist in `services/ui/e2e/` and are cited in the
Tier-1 playbooks as rehearsal/test evidence where a written user manual
(`LEO-UM-*`) is still missing:

| Spec file | Atlas VAL | Covers |
|---|---|---|
| `val-surface-forms-d681ea88.spec.ts` | VAL-D681EA88 | Surface Forms workflow (stands in for missing LEO-UM-SF-001) |
| `val-completeness-domains-4d70e63c.spec.ts` | VAL-4D70E63C | Domains / completeness workflow (stands in for missing LEO-UM-DO-001) |
| `val-guideline-workflow-1963da04.spec.ts` | VAL-1963DA04 | Clinical Guidelines three-step workflow (mirrors LEO-UM-CG-001, which does exist) |
| `val-audit-template-builder-17dc94a2.spec.ts` | VAL-C73DD43E* | Audit template builder |
| `val-leo-op-001-customer-pathway-onboarding.spec.ts` | n/a | End-to-end LEO-OP-001 onboarding rehearsal |
| `val-validation-lab.spec.ts`, `val-validation-lab-spoa-referral.spec.ts`, `val-validation-lab-ag.spec.ts` | n/a | SPoA referral and A&G scenario rehearsal used by E1/E2/E4 outlines |
| `val-g5-9-validation-lab-durable.spec.ts` | VAL-2A1EDC22 | Durable pipeline end-to-end rehearsal, cited in PB-E8 |

*The plan's earlier note assumed VAL-C73DD43E maps 1:1 to
`val-audit-template-builder-17dc94a2.spec.ts` by file-naming convention
(`val-<feature>-<dcid-suffix>.spec.ts`); this has not been independently
confirmed against Atlas and is flagged in
[GAPS-AND-BLOCKERS.md](GAPS-AND-BLOCKERS.md).

## Reconciliation with the delivered pptx

Cross-checked against `docs/marketing/build_coo_service_catalogue.py` on
2026-07-28: module IDs (E0-E9), module names, package names (A-E), and
package timelines in every playbook and outline in this dossier match the
`packages()` and `module_menu()` functions in that script. No wording drift
was found; no changes were needed to the pptx.
