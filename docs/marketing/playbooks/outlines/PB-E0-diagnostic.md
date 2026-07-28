# PB-E0 -- Readiness diagnostic (outline)

Catalogue reference: Module E0, "Readiness diagnostic" -- heat map,
specialty order, benefits hypothesis
(`docs/marketing/build_coo_service_catalogue.py`, `module_menu()`). First
step of Package A (Elective SPoA Accelerate), typically 4-6 weeks.

Tier: 2 (researched outline, not a full SOP). Density: Low -- no repo
diagnostic tool exists; this outline is built from NHS policy plus
consulting judgement.

## Purpose

Produce a specialty heat map, a recommended pilot order, and a benefits
hypothesis the COO can take to the board, before committing to Package A.

## Interview guide skeleton

Run structured interviews with the COO's elective, primary care, and
digital leads. Suggested sections:

1. **Current referral routes.** Which specialties still run local
   referral-management workarounds outside e-RS? (This maps directly onto
   the e-RS single-entry deadline in
   [../NHS-POLICY-EXTRACTS.md](../NHS-POLICY-EXTRACTS.md).)
2. **Advice and Guidance usage today.** Utilisation, turnaround, and
   unprocessed rates per specialty, if the ICB already tracks them against
   the A&G framework.
3. **Clinical safety readiness.** Who is (or will be) the customer's
   Clinical Safety Officer? Is a DCB0160 process already running for any
   digital tool?
4. **Integration landscape.** Which EPR/PAS is in use? Is e-RS the
   referral source of truth, or is there a parallel local system?
5. **Workforce.** Is senior/consultant-led review available for SPoA
   triage in the candidate specialties (a Technical Guidance requirement)?
6. **Benefits appetite.** What would the COO consider proof the pilot
   worked -- referral time, A&G diversion, waiting list size, or something
   else?

## Specialty heat-map fields

Score each candidate specialty (0-3, low to high) on:

| Field | Source |
|---|---|
| Priority-10 status | Elective SPoA Technical Guidance 2026/27 (see [../NHS-POLICY-EXTRACTS.md](../NHS-POLICY-EXTRACTS.md)) |
| Referral volume | Customer data |
| A&G maturity today | ICB self-assessment, if available (Module E2 framework) |
| Local RAS-style workaround in place | Interview finding |
| Guideline coverage available in LEO (NICE guideline exists and is loadable) | Ask the LEO clinical team; cross-check against `LEO-UM-CG-001` guideline catalogue |
| Senior clinician capacity for SPoA review | Interview finding |

Recommend the pilot specialty as the highest-scoring candidate that also
has usable NICE guideline coverage -- do not pick a specialty LEO cannot yet
support clinically (Module E4 dependency).

## Benefits hypothesis

Draft a one-page hypothesis using the E9 outline's metric set
([outlines/PB-E9-benefits-evaluation.md](PB-E9-benefits-evaluation.md)) as
the measurement frame, so the diagnostic and the eventual evaluation use
the same language from day one.

## Open gaps

No repo tooling exists for this module -- it is entirely a consulting
exercise informed by NHS policy. See
[../GAPS-AND-BLOCKERS.md](../GAPS-AND-BLOCKERS.md) ("Specialty readiness
diagnostic tooling").
