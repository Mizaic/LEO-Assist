# PB-E2 -- Advice and Guidance acceleration (outline)

Catalogue reference: Module E2, "Advice and Guidance acceleration" --
specialty rollout and quality sampling
(`docs/marketing/build_coo_service_catalogue.py`, `module_menu()`). Bundled
into Package B (ICB Advice and Guidance Maturity).

Tier: 2 (researched outline). Density: Medium -- the LEO pipeline supports
A&G (`communication_thread` mode) and the Validation Lab has an `spo_ag`
scenario, but there is no ICB maturity-scoring tool; this outline maps LEO
capability onto the national framework's 7 sections.

## Purpose

Give an ICB elective lead a maturity baseline against the national A&G
framework, and a rollout plan for specialties where LEO can accelerate
quality and turnaround.

## Maturity scorecard shell (0-3 scale)

Use the national framework's own 7 sections and 0-3 maturity scale --
do not invent an alternative scale (see
[../NHS-POLICY-EXTRACTS.md](../NHS-POLICY-EXTRACTS.md)). Add a "LEO
evidence" column so the scorecard shows what LEO can already support versus
what remains a local process matter.

| Framework section | 0-3 score (customer self-assessment) | LEO evidence column |
|---|---|---|
| Governance | | LEO does not provide governance structure; supports audit trail evidence for it |
| Clinical engagement | | SBAR review workflow gives clinicians a consistent artefact to engage around |
| Specialty prioritisation | | Use the E0 heat map fields as a starting input |
| Response standards | | LEO pipeline SLOs (queue-to-start P95, see `docs/operations/pilot-slos.md`) support turnaround measurement, not the clinical response itself |
| Data and reporting | | Completeness panel, guideline match, and audit trail data feed reporting |
| Workforce | | Training use of the Validation Lab (see PB-E8 Phase 4) |
| Continuous improvement | | Terminology writeback / learning loop (`DC-SMP-001` section 7) gives a concrete improvement mechanism |

## Specialty rollout plan

1. Start from the E0 heat map's priority specialties.
2. For each, confirm the guideline and completeness configuration exists or
   can be built (Module E4 dependency).
3. Sequence rollout by combined score: national priority x local A&G
   volume x current maturity gap (biggest gap where LEO can help first).

## Quality sampling design

Use the four national metrics directly:

| Metric | Definition | LEO data source |
|---|---|---|
| Utilisation ratio | A&G requests as a proportion of referrals for a specialty | Customer referral-management system + LEO trigger counts |
| Diversion rate | Proportion of A&G requests avoiding an outpatient referral | Customer-recorded outcome (see E1 outline's outcome taxonomy) |
| Turnaround rate | Response within the national standard | Pipeline run timestamps (trigger to SBAR completion) plus clinician response time in the customer's system |
| Unprocessed rate | Requests without a recorded response | Customer referral-management system |

Source: [../NHS-POLICY-EXTRACTS.md](../NHS-POLICY-EXTRACTS.md).

## Validation Lab rehearsal

Rehearse A&G scenarios end to end using the Validation Lab's `spo_ag`
scenario and the `val-validation-lab-ag.spec.ts` Playwright spec before
any specialty goes live, per
[../../../../docs/VALIDATION-LAB.md](../../../../docs/VALIDATION-LAB.md).

## Open gaps

No ICB-wide maturity scoring tool exists in the repo -- the scorecard above
is a manual artefact for now. See
[../GAPS-AND-BLOCKERS.md](../GAPS-AND-BLOCKERS.md).
