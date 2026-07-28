# Gaps and blockers

Cited-but-missing artefacts that stop a playbook being a complete,
stand-alone SOP. Each row says what is missing, which module(s) it blocks,
and what a consultant should use meanwhile.

This register does not invent or draft the missing documents. It is a
tracked list for QA/RA and the Clinical Safety Officer to action.

## QMS / product manuals

| Missing artefact | Cited by | Blocks | Interim workaround |
|---|---|---|---|
| `IFU-LEO-CDS-001` (customer-facing Instructions For Use for LEO CDS itself, as opposed to the widget IFU) | SVP-LEO-CDS-001 section 6.1, 9.1, 13; PB-E8 | Full customer go-live sign-off; end-user training evidence | **Drafted** 2026-07-28 as `compliance/policy/IFU-LEO-CDS-001-referral-assessment-spoa.md`, covering the referral-assessment/SPoA and A&G intended use. Status is Draft pending CSO sign-off and Atlas traceability (Atlas auth was unavailable at drafting time) -- it is not yet "published". Use alongside `leo-widget-ifu.md` in the meantime. |
| `IFU-LEO-CDS-002` (cancer case finding, day-forward tool -- new intended use, not yet built) | User request, 2026-07-28; reframes the retrospective NCDA/cancer-audit engine (PB-E5) into a prospective, day-forward tool | Any go-live claim for real-time or overnight cancer case finding | **Drafted as a target-state document only**: `compliance/policy/IFU-LEO-CDS-002-cancer-case-finding.md`. It documents what is genuinely new (real-time single-patient trigger, "since-last-run" delta batch, SBAR wired into the cancer path, e-RS evidence packaging, and a de-identified outcome-stratified localisation/validation milestone) versus what the existing retrospective NCDA engine already provides. It explicitly states this is a change of intended use under `intended-use.md` section 7 and is **not authorised for clinical use** until the CSO/QA-RA change-request, Atlas chain, and localisation milestone are complete. Do not quote this as a shipped capability to a customer. |
| `LEO-UM-SF-001` (Surface Forms user manual) | LEO-OP-001 section 7.1; PB-E4 | Written procedure evidence for surface-form onboarding | Use the Validation Lab spec `services/ui/e2e/val-surface-forms-d681ea88.spec.ts` (Atlas VAL-D681EA88) as rehearsed-workflow evidence, plus the UI's own in-page guidance at `/admin/knowledge` > Surface Forms. |
| `LEO-UM-DO-001` (Domains / minimum dataset user manual) | LEO-OP-001 section 8.2; DC-GOV-001 section 5.2; PB-E4 | Written procedure evidence for minimum dataset onboarding | Use `services/ui/e2e/val-completeness-domains-4d70e63c.spec.ts` (Atlas VAL-4D70E63C) plus DC-GOV-001 itself, which already contains step-by-step API and UI instructions even without a separate user manual. |
| `LEO-UM-ERS-001` (NHS e-RS per-customer onboarding manual) | LEO-OP-001 section 9.1; SVP-LEO-CDS-001 section 13.1; PB-E3 | Any customer go-live where e-RS write-back or e-RS-sourced referrals are in scope | Mark e-RS steps as "external QMS / TBD" in the customer plan. Do not attempt e-RS onboarding without this manual -- it covers NHS Initial Connection Approval, CIS2 app registration, and Key Vault secret setup, none of which are safe to freelance. |
| `LEO-IM-001` (Installation Manual, referenced by LEO-OP-001 Phase 1 prerequisites) | LEO-OP-001 section 6.1 | Platform readiness confirmation before any customer onboarding starts | Use `compliance/policy/DC-INST-001-installation-procedure.md` and `compliance/policy/DC-DEP-001-deployment-configuration.md`, which cover the same ground (infrastructure, terminology sync, plan seeding) in enough detail to proceed. |
| DCB0160 deployer support pack | SVP-LEO-CDS-001 section 6.1, 13.1; DC-DTAC-001 section 3.2 | Customer-side clinical risk management sign-off (this is the customer's own deliverable, but Mizaic must supply supporting evidence) | DC-DTAC-001 section 3.2 lists what Mizaic intends to provide (DCB0160 supporting documentation pack, System Risk Assessment, hazard log) but marks the pack itself as "Pending -- to be prepared by Clinical Safety Officer". Track as a CSO action, not a consultant deliverable. |
| LEO SaaS Embedding Agreement | `compliance/policy/leo-widget-ifu.md` section 5 | Production widget token issuance to a new host (blocks PB-E3 step "gated write-back" for any embed scenario) | Confirm with Commercial/Legal whether this agreement exists for the target host before promising a go-live date. `services/api/app/routers/sdk_auth.py` enforces this at the token-exchange endpoint -- it is not just a paperwork formality, the system will refuse to mint tokens without it. |

## Regulatory and assurance items still in progress (from DC-DTAC-001)

These are not blockers for running a Tier-1 playbook internally, but they
are blockers for representing LEO CDS as fully DTAC-compliant in a customer
pack. List them in any COO-facing readiness conversation.

| Item | Status (per DC-DTAC-001, 2026-03-04) | Target date |
|---|---|---|
| DCB0129 declaration (manufacturer clinical risk management) | Pending formal preparation | 2026-06-01 |
| NHS DSPT "Standards Met" submission | Pending submission | 2026-07-01 |
| Cyber Essentials Plus certification | Pending | 2026-09-01 |
| WCAG 2.1 AA accessibility audit and statement | Pending | 2026-09-01 |
| Formal architecture diagram for DTAC submission | Pending | 2026-05-01 |
| Summative usability testing | Pending | 2026-09-01 |

Check `compliance/policy/DC-DTAC-001-dtac-compliance-statement.md` directly
before quoting these dates in a customer conversation -- they may have moved
since this dossier was written.

## Naming-convention assumption not independently verified

The plan that produced this dossier assumed Validation Lab spec files follow
a `val-<feature>-<dcid-suffix>.spec.ts` naming convention and that
`val-audit-template-builder-17dc94a2.spec.ts` therefore corresponds to Atlas
VAL-C73DD43E. This assumption has **not** been checked against Atlas
directly (Atlas lookups were out of scope for this delivery-playbook
authoring session, per `atlas-design-controls-first.mdc`). Before citing
VAL-C73DD43E in a customer-facing document, confirm the mapping with
`get_design_control(dc_type="validation_test", dc_id="VAL-C73DD43E")`.

## Consulting-only gaps (no missing document -- just no repo evidence)

These are not "missing QMS documents" so much as areas where LEO CDS has no
built-in tooling and the consultant must bring an external method. They are
flagged in the relevant outline rather than repeated here in full:

| Gap | Flagged in |
|---|---|
| Benefits counterfactual / attribution method | PB outline E9, "method TBD with customer" |
| Specialty readiness diagnostic tooling (E0) | PB outline E0 |
| ICB-wide A&G maturity scoring tool | PB outline E2 / PKG-B |
| Neighbourhood diversion outcome tracking beyond LEO's own referral data | PB outline E7 / PKG-D |

## Escalation

If a customer engagement is blocked by any row above and there is no
workaround, escalate through the Customer Success Manager and, for any
safety-relevant gap (DCB0160, DCB0129, IFU), the Clinical Safety Officer --
per `compliance/policy/SVP-LEO-CDS-001-service-plan.md` section 5 (Roles and
responsibilities).
