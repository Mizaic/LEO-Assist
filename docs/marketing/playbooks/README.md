# LEO CDS delivery playbooks

Internal delivery / solutions-consultant playbooks that operationalise the
COO service catalogue
([../LEO-CDS-COO-Service-Catalogue.pptx](../LEO-CDS-COO-Service-Catalogue.pptx),
built by [../build_coo_service_catalogue.py](../build_coo_service_catalogue.py)).

These are internal working documents, written in professional plain
English for a delivery consultant, not customer-facing collateral. They are
not a substitute for customer QMS artefacts (IFU, DCB0160 pack) -- see
[GAPS-AND-BLOCKERS.md](GAPS-AND-BLOCKERS.md) for what is still missing.

**Module numbering note:** this dossier uses the E0-E9 scheme in
`build_coo_service_catalogue.py`, the source of the delivered pptx. An
earlier canvas, `deloitte-leo-cds-transformation-offers.canvas.tsx`, used a
different E0-E11 scheme for an earlier draft of the consulting offer. That
canvas is superseded for module numbering -- if you open it, expect the IDs
not to match the ones used here.

## Start here

| If you need... | Go to |
|---|---|
| Which repo/NHS source backs which module | [RESEARCH-SOURCE-MAP.md](RESEARCH-SOURCE-MAP.md) |
| Paraphrased NHS policy obligations, with citations | [NHS-POLICY-EXTRACTS.md](NHS-POLICY-EXTRACTS.md) |
| What is missing and how to work around it | [GAPS-AND-BLOCKERS.md](GAPS-AND-BLOCKERS.md) |
| A readiness traffic-light view for a COO conversation | [Readiness at a glance](#readiness-at-a-glance) below, or the `playbook-readiness` canvas |

## Readiness at a glance

Traffic light meaning: green = full playbook, runnable by a consultant
using only present docs plus flagged external steps. Amber = researched
outline, product capability exists but no written SOP. Red = outline built
mostly from NHS policy; little or no repo tooling yet.

| Module | Name | Readiness | File |
|---|---|---|---|
| E0 | Readiness diagnostic | Red | [outlines/PB-E0-diagnostic.md](outlines/PB-E0-diagnostic.md) |
| E1 | Elective SPoA operating model | Amber | [outlines/PB-E1-spoa-operating-model.md](outlines/PB-E1-spoa-operating-model.md) |
| E2 | Advice and Guidance acceleration | Amber | [outlines/PB-E2-ag-acceleration.md](outlines/PB-E2-ag-acceleration.md) |
| E3 | Integration and embed | **Green** | [playbooks/PB-E3-integration-and-embed.md](playbooks/PB-E3-integration-and-embed.md) |
| E4 | Pathway and guideline factory | **Green** | [playbooks/PB-E4-pathway-guideline-factory.md](playbooks/PB-E4-pathway-guideline-factory.md) |
| E5 | Cancer / NCDA mobilisation | Amber | [outlines/PB-E5-ncda-mobilisation.md](outlines/PB-E5-ncda-mobilisation.md) |
| E6 | Coding operations | Amber | [outlines/PB-E6-coding-operations.md](outlines/PB-E6-coding-operations.md) |
| E7 | Neighbourhood diversion design | Red | [outlines/PB-E7-neighbourhood-diversion.md](outlines/PB-E7-neighbourhood-diversion.md) |
| E8 | Clinical safety and regulatory (= Package E) | **Green** | [playbooks/PB-E8-safe-deploy-assure.md](playbooks/PB-E8-safe-deploy-assure.md) |
| E9 | Benefits and evaluation | Red | [outlines/PB-E9-benefits-evaluation.md](outlines/PB-E9-benefits-evaluation.md) |

| Package | Bundles | File |
|---|---|---|
| A -- Elective SPoA Accelerate | E0 + E1 + E3 + E4 (+ E8 in parallel) | [outlines/PKG-A-elective-spoa-accelerate.md](outlines/PKG-A-elective-spoa-accelerate.md) |
| B -- ICB Advice and Guidance Maturity | E2 (+ E9) | [outlines/PKG-B-icb-ag-maturity.md](outlines/PKG-B-icb-ag-maturity.md) |
| C -- Cancer Audit Factory | E5 + E6 (+ E9) | [outlines/PKG-C-cancer-audit-factory.md](outlines/PKG-C-cancer-audit-factory.md) |
| D -- Neighbourhood Diversion Pilot | E7 | [outlines/PKG-D-neighbourhood-diversion.md](outlines/PKG-D-neighbourhood-diversion.md) |
| E -- Safe Deploy Assure | E8 | No separate wrapper -- see [playbooks/PB-E8-safe-deploy-assure.md](playbooks/PB-E8-safe-deploy-assure.md) |

## Directory layout

```
docs/marketing/playbooks/
  README.md                          # this file
  RESEARCH-SOURCE-MAP.md
  NHS-POLICY-EXTRACTS.md
  GAPS-AND-BLOCKERS.md
  outlines/                          # Tier-2 researched outlines + package wrappers
  playbooks/                         # Tier-1 full playbooks (E3, E4, E8)
```

## Non-negotiable across every playbook and outline

All LEO CDS AI outputs are advisory. A clinician confirms every proposal
before any clinical action or write-back to a source system. No package,
timeline, or customer pressure changes this. See
`compliance/policy/leo-widget-ifu.md` and
`compliance/policy/SVP-LEO-CDS-001-service-plan.md` section 9.0.

## What this dossier is not

- Not a substitute for `IFU-LEO-CDS-001`, the DCB0160 deployer pack, or any
  other missing QMS artefact -- see
  [GAPS-AND-BLOCKERS.md](GAPS-AND-BLOCKERS.md). As of 2026-07-28,
  `IFU-LEO-CDS-001` (referral assessment / SPoA) has been drafted at
  `compliance/policy/IFU-LEO-CDS-001-referral-assessment-spoa.md`
  (Draft, pending CSO sign-off), and `IFU-LEO-CDS-002` (cancer case
  finding, day-forward tool) has been drafted at
  `compliance/policy/IFU-LEO-CDS-002-cancer-case-finding.md` as a
  **target-state document only** -- it is explicitly not authorised
  for clinical use. See the updated rows in
  [GAPS-AND-BLOCKERS.md](GAPS-AND-BLOCKERS.md).
- Not an Atlas design-control artefact. These are internal delivery
  documents with no product code or clinical-behaviour change, so the
  UN/DI/DO/VT chain does not apply to this dossier itself (it applies to
  the LEO CDS product features these playbooks describe).
- Not a claim of UEC SPoA or full Neighbourhood Health delivery -- see
  [NHS-POLICY-EXTRACTS.md](NHS-POLICY-EXTRACTS.md).
