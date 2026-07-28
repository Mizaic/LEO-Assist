# LEO CDS -- Instructions For Use: Referral Assessment / Single Point of Access (SPoA)

| Field         | Value                                                        |
| ------------- | ------------------------------------------------------------ |
| Document ID   | IFU-LEO-CDS-001                                              |
| Version       | v0.1.0-draft                                                 |
| Status        | Draft -- pending Clinical Safety Officer (CSO) sign-off       |
| Owner         | LEO Clinical Safety Officer (CSO)                             |
| Audience      | Customer clinical and IT leadership; referring and receiving clinicians; SPoA / triage teams |
| Related IFU   | `compliance/policy/leo-widget-ifu.md` (widget component only) |
| Atlas trace   | To be created -- see section 12                              |

This document is the full-product Instructions For Use for LEO CDS in
its **Referral Assessment** intended use: AI-assisted triage support
for inbound elective-care referrals and Advice and Guidance (A&G)
requests, most commonly deployed as part of a Single Point of Access
(SPoA) operating model. It supersedes nothing; it sits alongside the
narrower `leo-widget-ifu.md`, which covers only the embeddable SBAR
component and is written for engineering teams integrating that
component.

---

## 1. Purpose

LEO CDS reads an inbound referral or A&G request, extracts and codes
the clinical information it contains, checks it against configured
national and local guidance, and produces a structured summary for a
human reviewer. This document tells a customer what LEO CDS does,
what it does not do, and what the customer's own service MUST do for
LEO CDS to operate safely inside their referral workflow.

## 2. Intended use and intended users

- LEO CDS is a clinical decision support tool. Every AI-generated
  output is advisory. A clinician confirms or rejects each proposal
  before any triage, referral, or care-pathway decision is acted on.
- Intended users are clinicians and trained non-clinical triage staff
  working inbound elective referral management, SPoA, or A&G
  workflows -- for example GPs, referral management centre staff,
  and specialty triage clinicians reviewing an inbound request.
- LEO CDS is not intended for direct patient use and has no
  patient-facing interface.
- Regulatory classification: UKCA Class I software as a medical
  device (SaMD) providing clinical decision support for NHS
  planned-care referral management and care-pathway signposting
  (`compliance/policy/DC-DPA-002-full-data-processing-agreement.md`
  clause B.8). IEC 62304 Class B maximum for every software item, per
  `.cursor/rules/atlas-vt-enforcement.mdc`.

## 3. What LEO CDS does

LEO CDS runs the same eleven-step pipeline for both referral triage
and A&G, described in full in
`docs/REFERRAL-PIPELINE-INTEGRATION.md`:

1. Extraction -- NLP entity extraction from the referral text or A&G
   thread.
2. Post-processing -- assertion, scope, and value linking.
3. Relation linking -- builds the entity-relation graph.
4. Extraction check -- an LLM accuracy pass over the extracted facts.
5. Terminology -- SNOMED CT UK resolution.
6. Coding verifier -- an LLM coding verification pass.
7. Clinical facts persisted -- coded facts are written to the patient
   graph with a full audit trail.
8. Compliance -- the coded presentation is matched against the
   configured NICE guideline (for example NG12) and any approved
   local threshold adaptations.
9. Completeness -- checks the referral against the configured
   information groups for that pathway and flags anything missing.
10. Referral reason -- extracts a structured reason for referral.
11. SBAR -- generates a structured Situation, Background, Assessment,
    Recommendation summary for the reviewing clinician.

### 3.1 Two operating scenarios

| Scenario | Trigger | What the reviewer sees |
| --- | --- | --- |
| Inbound referral triage (SPoA) | `referral-received` event with the referral document already in the patient graph | SBAR + completeness flags + matched guideline signals, for the triage decision |
| Advice and Guidance (A&G) | Same trigger and workflow, driven by a communication thread rather than a referral document | SBAR summarising the A&G conversation for the responding clinician |

Both scenarios use the same `pd-referral-assessment` workflow; only
the source content differs (`text_segmentation_mode: document_chunks`
for referrals, `communication_thread` for A&G).

**Precaution -- subjective guideline wording.** Not every guideline
criterion LEO checks in step 8 is an objective threshold. Some NICE
criteria are written as clinical judgement calls (for example
"symptoms, results, or findings suggestive of" a condition, or
"unexplained" symptoms) rather than a fixed list of qualifying
phrases. LEO recognises these through a curated clinical term set
built by trained clinicians and clinical linguists from the medical
literature, extended over time through guideline authoring review
(`LEO-UM-CG-001`) and, for cancer pathways specifically, through the
localisation and validation milestone described in
`IFU-LEO-CDS-002-cancer-case-finding.md` section 8. A "no match" on a
subjective criterion means the documented wording did not match the
current term set -- it is not evidence the underlying clinical
concern is absent. Reviewers must not treat a non-match on a
subjective criterion as ruling anything out.

**Precaution -- anatomy and gender-inclusive matching.** Some NICE
recommendations extend a population beyond a simple sex category (for
example NG12 1.5.6, covering "women, and trans men and non-binary
people with female reproductive organs"). LEO routes these to a
reproductive-anatomy SNOMED concept rather than a binary sex field,
and always routes to clinician review when a patient's administrative
gender and coded anatomy conflict, or when administrative gender is
recorded as "other" or "unknown" against an anatomy-specific rule
(Risk R-4E4F22EF; DI-9AA2CDA5;
`services/terminology_api/app/services/guideline_evaluator.py`
`_check_anatomy_conflict`). See
`IFU-LEO-CDS-002-cancer-case-finding.md` section 8.4 for the full
mitigation, including the authoring-side safety net that prevents a
trans-inclusive population scope from being silently dropped.

### 3.2 Reviewing the output

The generated SBAR is rendered through the LEO widget
(`<leo-sbar>`), which discloses its source records and requires the
reviewing clinician to explicitly accept or reject the AI proposal.
See `compliance/policy/leo-widget-ifu.md` for the widget's own
Instructions For Use.

## 4. What LEO CDS does not do

- It does not diagnose. It reconstructs and codes the clinical
  narrative already present in the referral or A&G thread; it does
  not generate a diagnosis.
- It does not decide to refer, reject, or reprioritise a referral on
  its own. Every signposting suggestion is advisory and requires
  clinician confirmation.
- It does not replace clinical judgement. The reviewing clinician
  remains accountable for the triage decision.
- It does not write back to source systems (NHS e-RS, PAS, or EPR)
  by default. See section 5.
- It does not operate outside the configured guideline and
  completeness rules for the pathway it has been onboarded for.

## 5. Write-back to NHS e-RS, PAS, or EPR (governed, optional)

Two contract documents describe write-back differently, and a
customer conversation MUST use the correct one for the actual signed
agreement in place:

- `DC-DPA-002-addendum-b-referral-assessment.md` (the standalone
  Referral Assessment addendum) clause 5(e) explicitly **excludes**
  write-back to source systems under that addendum.
- `DC-DPA-002-full-data-processing-agreement.md` clauses B.6 and
  B.12(d) describe a governed, clinician-gated write-back capability
  (post-confirmation only, with mandatory clinician authentication,
  rollback capability, full audit trail, and a Controller-side kill
  switch).

Confirm which addendum applies to the customer in question before
describing write-back as in-scope. As of this version, no outbound
NHS e-RS API client has been located in the codebase (see
`docs/marketing/playbooks/GAPS-AND-BLOCKERS.md`, `LEO-UM-ERS-001`
row) -- write-back is a governed contractual capability, not yet an
operationally proven one. Do not promise a go-live date for
e-RS write-back without confirming `LEO-UM-ERS-001` (the missing NHS
e-RS onboarding manual) is available and complete.

## 6. Data flow and safeguards

- Referral or A&G content, once submitted, must already exist in the
  LEO patient graph as a `ReferralRequest` or `CommunicationRequest`
  with linked document chunks (`docs/REFERRAL-PIPELINE-INTEGRATION.md`
  prerequisites).
- Before any AI model sees the text, LEO removes patient names, NHS
  numbers, dates of birth, postcodes, addresses, phone numbers, email
  addresses, dates, and organisation names
  (`DC-DPA-002-full-data-processing-agreement.md` Annex B,
  "De-identification").
- A full audit trail records clinician identity, every AI output, and
  every clinician decision.
- Corrections a clinician makes when reviewing an output feed the
  Learning Loop (Approved Mappings of de-identified phrase to SNOMED
  CT code) to improve future coding accuracy -- this never re-adds
  patient identifiers.

## 7. Roles and responsibilities

| Activity | Canonical app role (`services/design-system/src/roles/types.ts`) |
| --- | --- |
| Referral / A&G review and triage decision | `referral_supervisor`, `clinical_administrator` |
| Guideline and completeness configuration | `pathway_supervisor`, clinical guideline authors (`LEO-UM-CG-001`) |
| Widget / host integration | Host product engineering, per `services/widget-sdk/README.md` |
| Clinical safety oversight | LEO Clinical Safety Officer (CSO) |

## 8. Onboarding artefacts (mandatory before production)

Before a customer's SPoA or A&G workflow goes live on LEO CDS, LEO
MUST hold:

- (a) A signed Data Processing Agreement with the correct Addendum B
  variant for the customer's actual write-back scope (section 5).
- (b) The customer's DCB0129 deployment safety case covering the
  workflow LEO CDS appears in.
- (c) Acknowledgement of `leo-widget-ifu.md` if the LEO widget is
  embedded in the customer's own product, with host onboarding
  artefacts complete per that document's section 5.
- (d) Signed-off guideline and completeness configuration for every
  pathway in scope (`LEO-OP-001` customer pathway onboarding
  procedure, `LEO-UM-CG-001` clinical guidelines user manual).
- (e) Acknowledgement of this Instructions For Use document, with the
  version string recorded against the customer.

## 9. Versioning and change control

- This IFU is versioned. Material changes (new operating scenarios,
  changes to what LEO CDS does or does not do, changes to write-back
  scope) require a new version and re-acknowledgement before the next
  production go-live under the new version.
- Editorial changes increment the patch number only and do not
  require re-acknowledgement.

## 10. Reporting

Report any of the following to the LEO Clinical Safety Officer
within the documented response window:

- A reviewer accepts or rejects an AI proposal that the reviewer
  believes was clinically incorrect.
- LEO CDS produces an SBAR, completeness flag, or guideline signal
  that the reviewer believes contains a patient-safety-relevant error.
- A release introduces a regression visible to the reviewer.

Channel: [clinical-safety@leo.mizaic.io](mailto:clinical-safety@leo.mizaic.io)

## 11. Open items before this IFU can move to "published"

- Confirm which `DC-DPA-002` Addendum B variant is the authoritative
  one going forward, and reconcile the two documents (section 5).
- `LEO-UM-ERS-001` (NHS e-RS onboarding manual) does not exist yet --
  see `docs/marketing/playbooks/GAPS-AND-BLOCKERS.md`. Any customer
  conversation that assumes e-RS write-back is turnkey is not
  supported by current evidence.
- Atlas traceability for this IFU (User Need, Design Input, Design
  Output, Risk, Verification Test) has not yet been created --
  `search_design_controls` against the Atlas MCP server returned an
  authentication error at drafting time. Create the chain per
  `.cursor/rules/atlas-vt-enforcement.mdc` before this document is
  marked "published", and record the resulting dcIds in the header
  table above.

## 12. Atlas trace (to be completed)

This document currently has no Atlas trace. Before publication, run
the workflow in `.cursor/rules/atlas-vt-enforcement.mdc` starting from
`search_design_controls(query="referral assessment SPoA advisory CDS",
dc_type="user_need")`, and populate the header table with the
resulting UN / DI / DO / Risk / VT dcIds.
