# PB-E5 -- Cancer / NCDA mobilisation (outline)

Catalogue reference: Module E5, "Cancer / NCDA mobilisation" --
milestones, Alliance reporting, safety-netting
(`docs/marketing/build_coo_service_catalogue.py`, `module_menu()`). Bundled
into Package C (Cancer Audit Factory), alongside Module E6.

Tier: 2 (researched outline). Density: high product / low SOP -- the NCDA
UI (queues, timelines, safety-netting worklists) exists and is used in
production, but there is no dedicated customer-facing onboarding SOP for
starting an NCDA-style audit programme. This outline drafts an
operating-rhythm skeleton from the UI's own capability.

## Purpose

Stand up a working cancer-pathway audit operation for a customer: pathway
reconstruction, milestone tracking, and safety-netting review, reporting up
through an Alliance/ICB/PCN hierarchy.

## What exists today (product evidence)

- LEO reconstructs structured pathways from primary-care records for
  programmes such as the National Cancer Diagnosis Audit
  (`docs/marketing/build_coo_service_catalogue.py`, `product_plain()`).
- The pipeline flags missing safety-netting and pathway delays for audit
  and improvement -- explicitly "for audit ... not for unreviewed treatment
  decisions" (same source).
- Milestone-chain data quality is checked automatically -- the
  `dq_missing_milestone_chains` tool (see
  `.cursor/rules/patient-dq-first-pass.mdc`) is the standard first-pass
  check for any NCDA-style investigation and is a good template for what
  "milestone tracking" means operationally.

## Operating-rhythm skeleton

1. **Programme setup.** Confirm which cancer pathways are in scope (for
   example lower GI, upper GI, urology -- see the DPA addendum's
   "Configured guidelines" schedule field as the template for recording
   this per customer).
2. **Milestone chain review (weekly).** Run the milestone-chain data
   quality first pass for the customer's cohort; triage any missing-chain
   patients into a review queue.
3. **Safety-netting worklist (daily or per-shift).** Assign a named
   reviewer to action the safety-netting worklist; record actioned/not
   actioned status.
4. **Alliance / ICB / PCN reporting (monthly or per Alliance cadence).**
   Aggregate milestone and safety-netting status into a report structured
   by the customer's reporting hierarchy (Alliance -> ICB -> PCN).
5. **Faster Diagnosis Standard (FDS) insight.** Track pathway timeliness
   against the FDS as the headline metric for Alliance-level reporting
   (link to the E9 outline's benefit metric set).

## Roles

| Activity | Canonical app role |
|---|---|
| Pathway/milestone review | `auditor`, `clinical_coder` |
| Safety-netting worklist actioning | `referral_supervisor`, `clinical_administrator` |
| Programme oversight | `pathway_supervisor`, `org_admin` |

## Open gaps

There is no dedicated LEO-OP-style onboarding SOP for NCDA-style audit
programmes yet -- this skeleton should be validated against a live
Alliance/ICB reporting cycle before being presented as a fixed operating
rhythm. See [../GAPS-AND-BLOCKERS.md](../GAPS-AND-BLOCKERS.md).
