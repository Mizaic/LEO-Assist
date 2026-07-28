# PB-E1 -- Elective SPoA operating model (outline)

Catalogue reference: Module E1, "Elective SPoA operating model" -- roles,
outcomes, senior review design
(`docs/marketing/build_coo_service_catalogue.py`, `module_menu()`). Part of
Package A (Elective SPoA Accelerate).

Tier: 2 (researched outline). Density: Medium -- LEO product capability
exists (RBAC, Validation Lab `ras_referral` scenario) but there is no
written operating-model SOP; this outline synthesises one from NHS policy.

## Purpose

Design the operating model for elective SPoA at the pilot specialty:
who does what, in what order, against what response-time standard.

## RACI (from canonical app roles)

Draw the RACI from `services/design-system/src/roles/types.ts`. LEO's RBAC
model gives you the digital half of the RACI; the customer supplies the
named individuals.

| Activity | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Referral / A&G intake | `admin_triage` | `referral_supervisor` | -- | `triage_clinician` |
| SBAR review and confirm | `triage_clinician` | `referral_supervisor` | Customer Clinical Safety Officer (for near-miss review) | -- |
| Completeness / guideline configuration | `platform_admin` | Clinical Reviewer (see PB-E4) | Requester (customer clinical lead) | `referral_supervisor` |
| Pathway monitoring | `pathway_supervisor` | `org_admin` | -- | COO |
| Coding quality review | `clinical_coder`, `auditor` | `referral_supervisor` | -- | -- |

Adjust labels to the customer's local job titles, but keep the underlying
app-role mapping so training (PB-E8 Phase 4) lines up with who actually
logs in as what.

## NHSE outcome taxonomy

Every SPoA triage decision should map onto one of these outcomes (from the
national A&G/SPoA policy set, not a LEO-specific list -- see
[../NHS-POLICY-EXTRACTS.md](../NHS-POLICY-EXTRACTS.md)):

- **Advice given** -- specialist responds with guidance; no referral
  needed.
- **Specialist to Specialist Triage (STT)** -- referral accepted and
  triaged directly to the right team.
- **Accept** -- referral accepted onto the specialty's normal pathway.
- **Redirect** -- referral routed to a different specialty, service, or
  (where safe) a community/primary-care option (link to Module E7).

Confirm with the customer which of their own systems records this outcome
field today -- LEO's SBAR presents a recommended action; the outcome record
itself is typically the customer's referral-management system, not LEO.

## Response-time standards

Use the standards from the NHS England letter to GPs directly --
do not invent alternative numbers:

| Referral type | Standard |
|---|---|
| Routine referral triage decision | 5 working days |
| Urgent referral triage decision | 2 working days |
| Specialist advice request response | 5 working days |

Source: [../NHS-POLICY-EXTRACTS.md](../NHS-POLICY-EXTRACTS.md) ("Specialist
advice and elective Single Point of Access" letter).

## Senior review design

The Technical Guidance expects consultant-led (or equivalent senior
clinician) review at SPoA, not administrative sift alone. Design the
operating model so the `triage_clinician` role in the RACI above is filled
by a senior clinician for the pilot specialty, with `admin_triage` handling
intake and completeness checks only.

## Validation Lab rehearsal

Before go-live, rehearse the operating model against the Validation Lab's
`ras_referral` scenario (SPoA-shaped referral through GP consult), per
[../../../../docs/VALIDATION-LAB.md](../../../../docs/VALIDATION-LAB.md).
This is the same rehearsal used in PB-E8 Phase 4 training.

## Open gaps

No written SOP exists for the SPoA operating model itself -- this outline
is the starting point. See [../GAPS-AND-BLOCKERS.md](../GAPS-AND-BLOCKERS.md).
Keep UEC SPoA (ambulance, urgent community response, virtual ward) out of
scope -- it is a different national programme (see
[../NHS-POLICY-EXTRACTS.md](../NHS-POLICY-EXTRACTS.md)).
