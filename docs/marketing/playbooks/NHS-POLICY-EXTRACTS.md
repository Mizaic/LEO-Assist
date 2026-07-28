# NHS policy extracts

Paraphrased obligations from NHS England policy, used to fill the parts of
the catalogue where the LEO CDS repo has product capability but no written
operating model. Each entry cites its own source document. Distinct
documents are cited separately even where they describe the same programme
(elective SPoA), so a reader can trace exactly which claim came from which
source.

This is not a copy of the source PDFs. Read the linked document for the
full, authoritative text before using any of this in a customer-facing
document.

## Elective Single Point of Access (SPoA)

### Elective SPoA Technical Guidance 2026/27

Source: [Elective SPoA Technical Guidance 2026/27](https://www.llrlmc.co.uk/wp-content/uploads/2026/03/202602_Elective-SPOA_Technical-Guidance_V1.0.pdf)

- Providers are expected to have an elective Single Point of Access
  operating for a defined list of priority specialties (the "priority-10")
  by a national deadline.
- From October 2026, e-Referral Service (e-RS) becomes the single entry
  route for in-scope elective referrals -- providers should not run parallel
  local referral routes alongside e-RS for those specialties.
- Referrals and Advice and Guidance requests routed through the SPoA should
  receive consultant-led (or equivalent senior clinician) review before a
  triage decision is made, not administrative sift alone.
- The guidance sets out which specialties are in scope first (the
  "priority-10") -- use this list to build the E0 specialty heat map and to
  choose the first Package A pilot specialty.

### "Specialist advice and elective Single Point of Access" -- NHS England letter to GPs

Source: [NHS England letter](https://www.england.nhs.uk/long-read/letter-specialist-advice-elective-single-point-of-access/)

This is a separate document from the Technical Guidance above, addressed to
GPs, and sets operational standards rather than the SPoA structure itself:

- Routine referrals: providers are expected to make a triage decision within
  5 working days of receipt.
- Urgent referrals: 2 working days.
- Specialist advice requests: 5 working days for a response.
- The GP's decision to refer is not overridden by the SPoA process -- SPoA
  triages and routes, it does not replace GP clinical judgement about
  whether to refer.

Use these response-time standards as the entry/exit criteria for the E1
outline's RACI and for E9's benefit metrics -- do not invent different
numbers.

### UEC Single Point of Access (out of scope note)

Source: [NHSE UEC SPoA long-read](https://www.england.nhs.uk/long-read/single-point-of-access-spoa/)

- Urgent and Emergency Care (UEC) SPoA covers ambulance, urgent community
  response (UCR), and virtual ward referral routing. It is a distinct
  programme from elective SPoA, run by different teams against different
  standards.
- LEO CDS and this catalogue address **elective** SPoA only. Every playbook
  and outline in this dossier must keep this distinction explicit and must
  not claim UEC SPoA capability. See the catalogue's own "what we will not
  promise" boundary slide (`docs/marketing/build_coo_service_catalogue.py`,
  `boundaries()`).

## Advice and Guidance (A&G)

### A&G operational delivery framework for Integrated Care Boards 2025/26

Source: [NHSE A&G framework PDF](https://www.england.nhs.uk/wp-content/uploads/2025/04/advice-and-guidance-operational-delivery-framework-for-integrated-care-boards-for-2025-26.pdf)

- The framework is organised into 7 sections covering governance, clinical
  engagement, specialty prioritisation, response standards, data and
  reporting, workforce, and continuous improvement.
- ICBs self-assess maturity on a 0-3 scale (broadly: not started, developing,
  established, exemplar) per specialty or pathway.
- Assessment is quarterly, feeding a local interface group (primary/
  secondary care clinical leads) and board-level reporting.
- Core metrics: utilisation ratio (A&G requests as a proportion of referrals
  for a specialty), diversion rate (proportion of A&G requests that avoid an
  outpatient referral), turnaround rate (response within standard), and
  unprocessed rate (requests without a recorded response).
- ICBs are expected to produce a delivery plan against the framework and
  report progress to their board.

Use the 7 sections and the 0-3 scale directly in the E2 outline's maturity
scorecard shell, and the four metrics directly in the E9 outline's benefit
metric set. Do not invent alternative maturity scales.

## Neighbourhood health

### Neighbourhood health guidelines 2025/26

Source: [NHSE Neighbourhood health guidelines 2025/26](https://www.england.nhs.uk/long-read/neighbourhood-health-guidelines-2025-26/)

- Sets out 6 components of neighbourhood health working (broadly: a
  neighbourhood population health approach, multidisciplinary neighbourhood
  teams, a single neighbourhood provider footprint, proactive and
  personalised care, better data and digital connection across providers,
  and a shift of resource from hospital to community settings).
- The overarching policy intent is a shift of care from hospital settings
  into community and primary care settings, with a particular focus on
  people with complex, multiple long-term conditions.

**Explicit non-scope for this catalogue:** LEO CDS does not provide urgent
community response (UCR) booking, virtual ward capacity management, or
Integrated Neighbourhood Team (INT) case management. The E7 outline and
Package D wrapper use this policy only to describe the *adjacency* between
elective SPoA outcomes (for example, "discharge to community physiotherapy"
rather than an outpatient slot) and the neighbourhood agenda -- not to claim
delivery of the neighbourhood programme itself. This mirrors the catalogue's
own boundary slide.

## How these extracts are used across the dossier

| Policy source | Used in |
|---|---|
| Elective SPoA Technical Guidance | E0 outline (heat map), Package A wrapper, PB-E4 (guideline scope framing) |
| NHSE letter to GPs (response standards) | E1 outline (RACI + response-time standards), E9 outline (benefit metrics) |
| A&G operational delivery framework | E2 outline, Package B wrapper, E9 outline (metrics) |
| Neighbourhood health guidelines | E7 outline, Package D wrapper |
| UEC SPoA long-read | Boundary/non-scope notes only, across E1, E7, and the README |
