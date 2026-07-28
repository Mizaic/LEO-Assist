# PB-E9 -- Benefits and evaluation (outline)

Catalogue reference: Module E9, "Benefits and evaluation" -- measures that
stand up in board papers
(`docs/marketing/build_coo_service_catalogue.py`, `module_menu()`). Runs
alongside every package ("Always" in the module menu shape column).

Tier: 2 (researched outline). Density: Low -- no benefits-realisation SOP
exists in the repo; this outline is built from pilot SLOs, the NHSE A&G
metric set, and product safety-netting/completeness data.

## Purpose

Give the COO a benefits and evaluation pack that stands up to board
scrutiny: metrics defined before the pilot starts, sourced from systems
that already exist, with an honest statement of what cannot yet be proven.

## Benefits metric set

| Metric | Source | Used by |
|---|---|---|
| Utilisation ratio, diversion rate, turnaround rate, unprocessed rate | NHSE A&G operational delivery framework (see [../NHS-POLICY-EXTRACTS.md](../NHS-POLICY-EXTRACTS.md)) | Package B evaluation pack |
| Response-time compliance (routine 5 days, urgent 2 days, specialist advice 5 days) | NHSE letter to GPs (see [../NHS-POLICY-EXTRACTS.md](../NHS-POLICY-EXTRACTS.md)) | Package A benefits baseline |
| Job completion reliability, queue-to-start latency (P95) | `docs/operations/pilot-slos.md` (SLO 2, SLO 3) | Technical reliability evidence, all packages |
| Missing safety-netting count, actioned vs. not actioned | NCDA safety-netting worklist (Module E5) | Package C evaluation pack |
| Faster Diagnosis Standard timeliness | Milestone-chain tracking (Module E5) | Package C evaluation pack |
| Redirect-to-community rate, re-referral rate | Module E7 outline metrics | Package D evaluation pack |
| Coding review completion rate, escalation rate | Module E6 coding review queue | Package C evaluation pack |

## Baseline-before-pilot discipline

Capture every metric's baseline value **before** the pilot specialty goes
live (Module E0 diagnostic is the natural home for this). A benefits pack
that only shows post-pilot numbers will not survive board scrutiny.

## Counterfactual note

**Method TBD with customer.** There is no repo tooling or agreed
methodology for isolating LEO's causal effect from other concurrent changes
(for example, a wider SPoA rollout happening at the same time). Do not
present pilot-period metric movement as proof of causation. Recommend
agreeing a specific counterfactual approach (matched control specialty,
pre/post comparison with explicit caveats, or a formal evaluation partner)
with the customer before the pilot starts, and record the chosen method in
the benefits pack itself so the limitation is visible, not hidden.

## Reporting cadence

Align to `compliance/policy/SVP-LEO-CDS-001-service-plan.md` section 10.2's
existing stakeholder communication cadence rather than inventing a new one:
annual (or per major release) service performance summary for executive
contacts, with more frequent operational metrics for IT/operational
contacts.

## Open gaps

No benefits-realisation SOP exists in the repo. The counterfactual method is
explicitly unresolved -- see
[../GAPS-AND-BLOCKERS.md](../GAPS-AND-BLOCKERS.md).
