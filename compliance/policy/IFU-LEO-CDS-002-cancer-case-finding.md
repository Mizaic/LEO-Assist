# LEO CDS -- Instructions For Use: Cancer Case Finding (Day-Forward Tool)

| Field         | Value                                                        |
| ------------- | ------------------------------------------------------------ |
| Document ID   | IFU-LEO-CDS-002                                              |
| Version       | v0.1.0-draft                                                 |
| Status        | **DRAFT -- TARGET INTENDED USE. NOT AUTHORISED FOR CLINICAL USE.** See section 4. |
| Owner         | LEO Clinical Safety Officer (CSO)                             |
| Audience      | Customer clinical and IT leadership; QA/RA lead; CSO; GP practices piloting the capability |
| Related docs  | `compliance/policy/intended-use.md` (current NCDA classification); `IFU-LEO-CDS-001-referral-assessment-spoa.md` (reused SBAR/guideline engine) |
| Atlas trace   | None yet -- this is a new intended use. See section 15.       |

**Read section 4 before reading anything else in this document.** This
IFU describes a *target* intended use built from real, existing LEO
components, reframed into a prospective, day-forward cancer
case-finding tool. It is not a description of a shipped, validated
product. Do not present this document to a customer as evidence that
the capability is ready for clinical use.

---

## 1. Purpose

Today, LEO's cancer pathway engine (the National Cancer Diagnosis
Audit, NCDA, programme) runs **retrospectively**: it reconstructs
cancer pathways from historical GP records for population-level audit,
after the clinical episode is already closed. This document describes
reframing the same underlying engine -- coding, guideline matching,
episode/outcome classification, safety-netting detection -- into a
**day-forward tool**: a GP raises a cancer suspicion and gets an
assessment back the same day, or LEO runs an overnight sweep of
patients seen since the last run and hands the GP a review list the
next morning. In both cases, the aim is the same: help a GP notice a
possible cancer signal earlier, using the same clinical fact
extraction LEO already runs for audit, without waiting for a national
audit cycle to surface it.

## 2. What this reuses from the existing NCDA engine, and what is new

| Capability | Status today | Evidence |
| --- | --- | --- |
| SNOMED CT coding of GP encounter text | Exists | `compliance/policy/intended-use.md` section 2.1 |
| NG12 / local guideline rule matching | Exists (referral-assessment path); reusable engine | `services/terminology_api/app/services/guideline_evaluator.py`; `libs/pipeline_graph/subgraphs/compliance.py` |
| SBAR summary generation | Exists (referral-assessment path only, not yet wired into the NCDA/cancer-detection path) | `services/pipeline_worker/app/services/sbar_orchestrator.py`; `libs/sbar/events.py` |
| Outcome classification: confirmed cancer vs cancer excluded | Exists | `libs/episodes/lifecycle.py` (`HeroBucket.CONFIRMED_CANCER`, `HeroBucket.CANCER_EXCLUDED`); `libs/exclusion_detector/` |
| Safety-netting signal detection | Exists | `libs/oncology/safety_netting.py` |
| Human review / sign-off gate on episode status | Exists | `libs/episodes/lifecycle.py` (`ReviewVerdict`, sign-off endpoint) |
| GP record ingestion | Exists, but as a **batch / export** into the patient graph (FHIR R4), not a live single-patient pull | `compliance/policy/intended-use.md` section 5; no "IM1" integration found in the codebase |
| Real-time, clinician-initiated single-patient trigger | **New** -- no such trigger exists today | n/a |
| "Since last batch run" incremental delta scheduler | **New** -- the existing nightly NCDA job retrains ML classifiers (`services/training_worker/app/jobs/ncda_nightly.py`); NCDA episode detection itself runs as a full/retrospective batch (`scripts/ncda/run_full_cancer_episode_detection.py`), not an incremental "patients seen since last run" sweep | n/a |
| SBAR (or equivalent) wired into the cancer-detection path for a single live patient | **New** -- SBAR generation today only fires on the referral-assessment trigger | n/a |
| Evidence packaged for e-RS referral creation from the cancer path | **New** -- no outbound e-RS client exists in the codebase for any path; see `docs/marketing/playbooks/GAPS-AND-BLOCKERS.md`, `LEO-UM-ERS-001` row | n/a |
| Pre-go-live localisation/validation on a de-identified, outcome-stratified retrospective cohort | **New** -- Validation Lab today is a single-patient synthetic wizard (`docs/VALIDATION-LAB.md`), not a retrospective cohort validation programme | n/a |

## 3. Intended use and intended users

- Intended users are GPs and primary care clinicians assessing a
  patient where they have a live clinical suspicion of cancer, and
  primary care teams reviewing a daily worklist of patients flagged
  by an overnight sweep.
- Every LEO output under this intended use is advisory. A clinician
  reviews and confirms every flagged patient before any referral,
  investigation, or other clinical action is taken. No patient is
  referred, coded, or closed automatically.
- LEO CDS under this intended use is not a screening programme. It
  does not decide who should be screened; it surfaces clinical facts
  already present in the GP record, coded and checked against
  guidance, for a clinician who is already exercising clinical
  judgement about that patient.

## 4. Regulatory status -- this is a change of intended use, not a feature flag

`compliance/policy/intended-use.md` section 7 currently lists the
following as **explicitly out of scope** for the NCDA programme:

> "Real-time clinical decision support -- The system is retrospective
> only; it analyses historical records after the clinical event."
>
> "Screening or triage of symptomatic patients -- The system does not
> process live patient presentations."

Both scenarios in this document (section 6 and section 7) fall
squarely inside those two exclusions. Reframing the cancer audit
engine into a day-forward tool is therefore **not** a configuration
change or a new UI on top of existing capability -- it is a change to
LEO's intended purpose for this patient population, and it must be
handled as one.

Per `.cursor/rules/atlas-vt-enforcement.mdc`:

- A mandatory clinician review gate is present in both scenarios (the
  GP confirms every flagged patient before any action), so this
  capability can, in principle, remain IEC 62304 Class B -- it does
  not require a Class C escalation on the review-gate test alone.
- However, the rule's Step 0 classification gate and the "Hard rules"
  section still require the full chain before any code is written:
  a new or updated User Need, Design Input, Design Output, Risk
  assessment, and Verification Test in Atlas, **and**, because this
  changes what LEO is allowed to be used for, a formal
  intended-purpose / safety-case change request reviewed by the
  Clinical Safety Officer and the QA/RA lead before this IFU can move
  from "Draft -- target intended use" to "Published".
- The risk profile is materially different from retrospective audit:
  a missed or delayed signal on the day-forward path can directly
  delay a live referral decision, whereas a miss on the retrospective
  audit path affects a quality metric on an episode that has already
  been treated. The risk assessment for this intended use MUST treat
  it as a new hazard analysis, not an extension of the existing NCDA
  risk file (`compliance/policy/DC-RM-001-risk-management.md`).

**Until that change request is approved and the localisation milestone
in section 10 has passed for a given practice, no part of this document
authorises live clinical use.**

## 5. What this does not do (contraindications, carried over and extended)

- It does not diagnose cancer. It extracts, codes, and checks GP
  record text against guidance; the GP makes the clinical judgement.
- It does not decide to refer. Every referral decision is the GP's.
- It does not submit a referral to NHS e-RS on its own. See section 7
  for exactly what "packaged for e-RS referral creation" means.
- It is not a population screening tool and must not be marketed or
  operated as one.
- It does not replace safety-netting advice already given by the GP;
  it surfaces documented safety-netting signals for audit and review,
  it does not generate new safety-netting advice for the patient.
- It must not be used at a practice that has not completed the
  localisation and validation milestone in section 10.

## 6. Scenario 1 -- real-time, clinician-initiated single-patient assessment

1. **Trigger.** A GP examining a patient's record has a clinical
   suspicion of cancer and asks LEO to assess that patient.
2. **Fetch.** LEO retrieves the patient's GP record content needed for
   assessment. Today, GP record content reaches LEO's patient graph
   through a batch/export FHIR R4 ingestion path, not a live
   sub-second pull from the GP system
   (`compliance/policy/intended-use.md` section 5). A genuinely
   real-time, single-patient fetch (the kind of integration a term
   like "IM1" implies) is new integration work; it does not exist in
   this codebase today. Until that integration exists, "real time"
   in this scenario should be understood as "on demand, using the
   most recently ingested GP record", not "live query against the GP
   system at the moment of asking."
3. **Extract and code.** LEO runs the same extraction and SNOMED CT
   coding capability described in `intended-use.md` section 2.1 over
   the patient's record.
4. **Assess against guidance.** LEO matches the coded presentation
   against NICE NG12 and any approved local pathway rules, reusing
   the guideline evaluator already in production for the
   referral-assessment path (`services/terminology_api/app/services/guideline_evaluator.py`).
5. **Summarise back to the GP.** LEO generates a structured summary
   (reusing the SBAR pattern already in production for referral
   assessment) showing the coded facts, the matched guideline
   criteria, and any safety-netting signals already recorded. Wiring
   SBAR generation into the cancer-detection path for a single live
   patient is new work; the pattern is proven, the wiring is not.
6. **GP decision.** The GP reviews the summary and decides whether to
   refer.
7. **Evidence packaging for referral.** If the GP decides to refer,
   LEO prepares the SBAR summary, the coded clinical facts, and the
   matched guideline evidence in a form the GP can use to create the
   e-RS referral. **LEO does not submit the referral to e-RS.** The
   GP creates and submits the referral, either by hand using LEO's
   evidence package, or -- only where the customer's DPA Addendum B
   and `LEO-UM-ERS-001` onboarding explicitly cover write-back
   (`compliance/policy/DC-DPA-002-full-data-processing-agreement.md`
   clauses B.6 and B.12(d)) -- via LEO's governed, clinician-confirmed
   write-back capability. As of this version, no outbound e-RS API
   client exists in the codebase and `LEO-UM-ERS-001` has not been
   written (`docs/marketing/playbooks/GAPS-AND-BLOCKERS.md`); do not
   promise automatic e-RS submission to a customer.

## 7. Scenario 2 -- overnight batch, day-forward review worklist

1. **Trigger.** A scheduled batch run (for example nightly) identifies
   patients who have had a GP encounter since the last run. This is
   new: the existing nightly NCDA job retrains detection models
   (`services/training_worker/app/jobs/ncda_nightly.py`), and the
   existing episode-detection script runs across the whole cohort
   rather than an incremental delta
   (`scripts/ncda/run_full_cancer_episode_detection.py`). A
   "since-last-run" delta scheduler needs to be built; it is not a
   configuration of something that already runs this way.
2. **Same processing workflow.** Each identified patient goes through
   the same extract / code / guideline-match steps as Scenario 1,
   plus the existing outcome classification
   (`libs/episodes/lifecycle.py`) and safety-netting detection
   (`libs/oncology/safety_netting.py`) already used for NCDA audit.
3. **Next-day review list.** Flagged patients are presented to the GP
   the next day as a worklist, in the same spirit as the existing
   safety-netting worklist already used for NCDA review
   (`services/analysis_worker/app/analyzers/safety_net_persistence.py`;
   `services/analytics_api/app/routers/dashboards.py`
   `safety_net_worklist`), extended to carry a same-day-relevant
   suspicion flag rather than a retrospective audit signal.
4. **GP action.** For each patient on the list, the GP confirms,
   dismisses, or acts on the flag, using the same sign-off pattern
   already used for NCDA episode review (`ReviewVerdict` in
   `libs/episodes/lifecycle.py`). No patient is referred, closed, or
   coded without this step.

## 8. Warnings and precautions

### 8.1 Some guideline criteria are clinically subjective, not objective thresholds

Not every NG12 (or local guideline) criterion is a crisp,
machine-checkable threshold. Many are written as clinical judgement
calls -- for example "symptoms, results, or findings suggestive of
[cancer]", or "unexplained" weight loss / rectal bleeding / other
symptom -- where the guideline deliberately leaves the interpretation
to the clinician reading the record, rather than defining a fixed
list of qualifying phrases.

LEO cannot compile a criterion like this into a rule the way it
compiles an objective threshold (for example, an age cut-off, or a
lab value crossing a defined limit). Instead, LEO recognises a
subjective criterion through a curated concept/term set: a list of
clinical phrasings that trained clinicians judge to represent the
guideline's intent. This is the same authoring pattern LEO already
uses elsewhere for domain-expert-curated term sets
(`libs/domains/ncda_concept_sets.py`; the site-specific symptom
keyword sets in `libs/oncology/first_presentation.py`); this document
extends that existing pattern to subjective NG12-style wording rather
than introducing a new one.

### 8.2 How the term set is built and kept current

1. **Initial set from clinical literature.** Trained clinicians and
   clinical linguists (clinical domain expertise combined with
   terminology and language expertise) build the initial term set for
   each subjective criterion from the medical literature -- the
   published case descriptions, guideline commentary, and terminology
   standards that describe how the criterion is usually documented in
   practice.
2. **Extended through validation and localisation.** That initial,
   literature-derived set is a starting point, not a finished
   product. It is extended and refined as real, de-identified,
   governed cases are reviewed during the validation and localisation
   milestone (section 10) and during ongoing local guideline authoring
   (`compliance/policy/LEO-UM-CG-001-clinical-guidelines-user-manual.md`):
   when a reviewer finds a local documentation style that clearly maps
   to the guideline's intent but is not yet in the term set, the term
   set is updated so the same phrasing is recognised going forward.
3. **Human review stays in the loop.** As with every other guideline
   rule in LEO, additions to a subjective criterion's term set go
   through the same review-and-approve workflow as any other rule
   change (`LEO-UM-CG-001` section 5) -- a term is never added to a
   live subjective criterion without a clinician checking it first.

### 8.3 Known limitation -- treat coverage as improving over time, not exhaustive

Because a subjective criterion is recognised through a curated term
set rather than an exhaustive objective rule, LEO's coverage of that
criterion should be understood as improving over time through
localisation, not complete from day one. A "no match" against a
subjective guideline criterion is evidence that the documented
wording did not match the current term set -- it is **not** evidence
that the clinical concept the criterion describes is absent from the
record. Reviewers must not treat a non-match on a subjective
criterion as ruling anything out; the reviewer's own reading of the
record remains the safety net for exactly this class of criterion.

### 8.4 Anatomy and gender-inclusive guideline matching

Some NG12 recommendations extend a population beyond a simple sex
category -- for example recommendation 1.5.6 covers "women, and trans
men and non-binary people with female reproductive organs" for
suspected ovarian cancer symptoms. A rule that collapsed this to a
binary `sex = female` demographic field would wrongly exclude exactly
the trans and non-binary patients the recommendation means to
include, because a trans man in this population is typically recorded
as `sex = male` in the patient record.

LEO has a specific, tested mitigation for this (Risk R-4E4F22EF;
DI-9AA2CDA5):

- **Authoring side.** When a NICE recommendation uses trans-inclusive
  or organ-presence wording, rule authoring routes the population
  scope to a reproductive-anatomy concept (SNOMED CT) rather than a
  binary sex field
  (`libs/pipeline_graph/subgraphs/guidance_rule_extraction_v2_impl.py`
  `_parse_organ_presence_constraint`). A deterministic safety net
  forces human review if a trans-inclusive-worded recommendation is
  extracted without both an age leaf and an anatomy/sex leaf, so a
  dropped population scope cannot go live silently
  (`_flag_missing_age_or_organ_constraint`; regression coverage in
  `tests/test_guidance_rule_organ_presence_demographic.py`).
- **Runtime side.** LEO does not assume a patient's reproductive
  anatomy from their recorded administrative (PDS) gender alone.
  Administrative gender of "other" or "unknown" against an
  anatomy-specific rule always requires clinician review.
  Administrative gender of "male" or "female" against an
  anatomy-specific rule is used, but with an attached limitation
  notice: "PDS administrative gender does not confirm reproductive
  anatomy. Check whether the patient has relevant reproductive organs
  before acting on anatomy-specific recommendations." If the
  patient's own coded clinical record contains reproductive anatomy
  that conflicts with their recorded administrative gender (for
  example male-recorded with coded female reproductive anatomy, or
  vice versa), LEO always routes to clinician review rather than
  guessing (`services/terminology_api/app/services/guideline_evaluator.py`
  `_check_anatomy_conflict`).

This matters directly for cancer case finding: several NG12
cancer-symptom recommendations use exactly this trans-inclusive,
organ-presence wording. Any day-forward worklist or single-patient
assessment under this IFU MUST preserve this mitigation unchanged --
do not replace anatomy-based matching with a simpler sex-only check
for performance or simplicity reasons, and do not build a new
gender-handling mechanism for the day-forward path when this one
already exists and is tested.

### 8.5 Site-specific and presentation-specific limitations (to be completed)

*TBC -- known limitations, error modes, or precautions specific to
particular presentation types or documentation styles, arising from
the localisation and validation milestone results at a given site.
This subsection needs clinical/QA input once validation completes for
the first site, and MUST be completed before this IFU can move from
"Draft" to "Published" for that site.*

## 9. Performance characteristics and limitations

These figures describe the underlying extraction, coding, guideline
matching, and reasoning engine listed as "Exists" in section 2 -- the
components this day-forward intended use reuses. They are not yet a
validated end-to-end measurement of the day-forward workflow itself
(the real-time trigger and overnight delta batch in sections 6 and 7).
The localisation and validation milestone in section 10 is what
confirms these figures hold for cancer case finding specifically, and
for a given practice's own documentation style.

*Source evaluation report reference: TBC -- add the specific
manufacturer evaluation report and date this section is drawn from
before this IFU moves to "Published".*

### 9.1 Extraction and coding

95% sensitivity / specificity on a curated set of synthetic patient
records.

**Limitations:**

- This test can only be run on patient scenarios that have a
  gold-standard outcome defined by clinicians.
- Pre-clinical validation is based on a curated set of patient cases,
  rather than an exhaustive study using real patient data.
- The figure is expanded through the manufacturer's post-market
  surveillance (PMS) as edge cases are detected in live use.
- This metric should be considered as improving over time through PMS
  rather than complete from day one.

### 9.2 Guideline matching

100% (rules-based) -- subject to the Warnings and precautions in
section 8. Rules-based matching against an approved, compiled
guideline model is deterministic for any criterion the model can
evaluate; section 8 explains why some criteria (subjective wording
such as "suggestive of" or "unexplained") depend on a curated term
set that is itself still being extended, rather than the matching
logic being uncertain.

### 9.3 CDS output quality -- qualitative evaluation (r-IDEA)

For the CDS outputs (the reasoning behind a recommendation, not just
the coded facts), qualitative data in the form of free-text comments
and verbal feedback was requested from evaluators, specifically for
test cases that achieved a revised r-IDEA score of less than 6, or
where there was concern around the potential safety of LEO's
recommendations. Qualitative feedback provides rich, detailed
information that goes beyond numerical data, and offers a deeper
understanding of user experience. It also emphasises user
perspectives, enabling LEO to be tailored to better meet user needs
and expectations. This mixed-methods approach used an evaluation
framework based on the r-IDEA score (Schaye et al, 2022) to improve
validity and reliability.

**Evaluation framework (adapted from Schaye et al, 2022):**

| Domain | Score range | Adapted question and guidance for reviewer |
| --- | --- | --- |
| Interpretive Summary | 0-4 | Has all relevant patient information and clinical detail been included? Highlights key patient details using semantic vocabulary; focuses on key risk factors, chief complaint, reason for referral, and semantic qualifiers. Evaluators assess how well LEO extracts and summarises relevant clinical information, considering how easy the output was to read, and its completeness, conciseness, and coherence. |
| Differential Recommendation | 0-2 | Did LEO identify a range of potential recommendations that could be pursued based on the patient information provided? Presents relevant diagnosis/recommendation probabilities for the chief complaint, prioritising the most likely and considering significant alternatives. |
| Explanation of Primary Recommendation | 0-2 | Was it possible to understand how the recommendation was reached? Details the reasoning for the lead diagnosis/recommendation, linking it to patient presentation and data. Evaluators assess how effectively LEO integrates patient details, NICE guidelines, and local protocols into its reasoning. |
| Explanation of Alternative Recommendation | 0-2 | What was the quality and clinical validity of alternative recommendations provided by the device? Justifies alternative diagnoses/recommendations, comparing them to the patient's situation. |
| Revised-IDEA (r-IDEA) score | 0-10 (total) | A total score of 6 or more indicates high-quality reasoning. |
| Safe? | Yes / No | A response of "Yes" indicates that no predictable harm could come to the patient by following LEO's outputs. |

A case scoring below 6 on the revised r-IDEA scale, or flagged "No" on
the Safe? question, triggers the qualitative follow-up described
above regardless of how the extraction and coding metrics in section
9.1 scored for that case -- reasoning quality and factual-extraction
accuracy are evaluated, and reported, separately.

## 10. Mandatory pre-use milestone: localisation and validation

This section captures the requirement raised when this IFU was
drafted, and it is a precondition for clinical use at any site, not
an optional enhancement.

### 10.1 Why

Clinical fact extraction accuracy depends on recognising how a
practice actually writes its notes -- spelling, grammar,
abbreviations, shorthand, terminology, templates, and sentence
structure vary between practices and professional groups. Before LEO
is used clinically for cancer case finding at a practice, it must be
validated and localised against a representative, appropriately
governed sample of that practice's own documentation style. This
reduces the risk that relevant signs, symptoms, test results, or
other clinical information are missed or misread because of how they
were recorded, and it is a deliberate equity choice: without
localisation, the tool's accuracy could vary unfairly between
practices and patient groups depending on how closely their
documentation style matches whatever data the underlying models were
originally trained on.

### 10.2 What the milestone requires

1. **De-identified retrospective sample.** Assemble a sample of the
   intended GP population's records, de-identified using the existing
   three-layer de-identification process already used for training
   and export
   (`compliance/policy/DC-DPA-002-full-data-processing-agreement.md`
   Annex B; `compliance/policy/DPIA-LEO-AI-001.md`). No LLM or coding
   step sees an identified record at any point in this milestone.
2. **Stratified by outcome, not just diagnosed cases.** The sample
   MUST include both patients who went on to receive a cancer
   diagnosis and patients whose cancer pathway was excluded. LEO
   already classifies exactly these two outcome groups for audit
   reporting -- reuse the same classification rather than building a
   new one:
   - `HeroBucket.CONFIRMED_CANCER` / `libs/exclusion_detector/`
     "cancer confirmed" cases (`libs/episodes/lifecycle.py`)
   - `HeroBucket.CANCER_EXCLUDED` / "cancer excluded" cases (same
     module)
   Validating only on confirmed-cancer cases would tell you nothing
   about false positives or over-flagging on patients whose
   presentation looked similar but was not cancer -- both outcome
   groups matter for a fair assessment of the tool.
3. **Run the real pipeline, not a synthetic one.** The existing
   Validation Lab (`docs/VALIDATION-LAB.md`) is a single-patient,
   mostly-synthetic wizard today; it explicitly is not the same thing
   as a retrospective, outcome-stratified cohort validation. Per the
   Lab's own governance gate ("extend Validation Lab instead of
   building a parallel surface"), this milestone should be delivered
   as a new mode of Validation Lab, not a separate tool -- but that
   mode does not exist yet and must be built.
4. **Clinical review of every case.** A clinician (or clinical coder
   with second-reviewer sign-off) reviews LEO's extraction, coding,
   and guideline-match output for every case in the sample, using the
   same `GoldLabel` review and Approved Mapping mechanism already
   used for the Learning Loop
   (`compliance/policy/DC-DPA-002-full-data-processing-agreement.md`
   section 5.4; `compliance/policy/DC-MTP-001-model-training-platform.md`).
5. **Local documentation patterns feed back before go-live.** Any
   abbreviation, template, or shorthand pattern that caused a miss or
   misread during review is corrected in the extraction/coding
   configuration for that practice before go-live, not after.
6. **Go/no-go gate.** The day-forward capability MUST NOT be enabled
   for live clinical use at a practice until this milestone has been
   completed and signed off by the CSO/QA-RA lead against a defined
   accuracy threshold. The specific threshold is not defined in this
   document and must be set by the CSO/QA-RA lead as part of the risk
   assessment in section 4 -- do not quote a numeric accuracy target
   to a customer until that threshold is formally agreed.

## 11. Roles and responsibilities

| Activity | Canonical app role (`services/design-system/src/roles/types.ts`) |
| --- | --- |
| Live single-patient assessment request, review, referral decision | GP / clinician (end user, not a system role) |
| Overnight worklist review and sign-off | `auditor`, `clinical_coder`, `referral_supervisor` |
| Localisation milestone case review | `clinical_coder` (second-reviewer sign-off required) |
| Programme and localisation oversight | `pathway_supervisor`, `org_admin` |
| Regulatory change request, risk assessment, go/no-go sign-off | LEO Clinical Safety Officer (CSO), QA/RA lead |

## 12. Data flow and safeguards

Same de-identification, audit trail, and retention safeguards as the
existing NCDA and referral-assessment paths apply in full
(`compliance/policy/DC-DPA-002-full-data-processing-agreement.md`
Annex B; `compliance/policy/DPIA-LEO-AI-001.md`). No new data
safeguard is introduced by this intended use; the localisation
milestone in section 10 reuses the existing de-identification
pipeline rather than creating a new one.

## 13. Onboarding and go-live preconditions

This IFU does not authorise clinical use at any site until **all** of
the following are complete:

- (a) The intended-purpose / safety-case change request in section 4
  is approved by the CSO and QA/RA lead.
- (b) A new or updated Atlas chain (User Need, Design Input, Design
  Output, Risk, Verification Test, and -- because this changes a
  clinical outcome visible to users -- a Validation Test) exists for
  this intended use, per `.cursor/rules/atlas-vt-enforcement.mdc`.
- (c) The build items listed as "New" in section 2 are implemented
  and verified: the single-patient trigger, the incremental
  day-forward scheduler, SBAR wiring into the cancer-detection path,
  and the evidence-packaging step for referral creation.
- (d) The localisation and validation milestone in section 10 has
  passed for the specific practice or population going live.
- (e) If e-RS write-back is in the customer's contracted scope,
  `LEO-UM-ERS-001` (the NHS e-RS onboarding manual) exists and has
  been completed for that customer.
- (f) The customer's own DCB0129 deployment safety case has been
  updated to cover this intended use.
- (g) Section 8.5 (site-specific and presentation-specific
  limitations) has been completed with real clinical/QA input for the
  site going live.

## 14. Versioning and change control

- This document is versioned. It must move through a formal review
  (not an editorial patch) before its Status changes from "Draft --
  target intended use" to "Published", and that review must confirm
  section 13 is fully satisfied.
- Any change to what counts as "new" versus "exists" in section 2
  (for example, once the day-forward scheduler is built) requires a
  new version.

## 15. Atlas trace

None yet. This is a new intended use, not an extension of an existing
Design Input. Do not link this document's future Atlas artefacts under
the existing NCDA audit Design Input without confirming with the CSO
that the safety case genuinely extends rather than replaces the
current retrospective-only classification. Start from
`search_design_controls(query="cancer case finding day forward",
dc_type="user_need")` once Atlas authentication is available, per
`.cursor/rules/atlas-vt-enforcement.mdc`.

## 16. Reporting

Report any of the following to the LEO Clinical Safety Officer
immediately:

- Any use of this capability in live clinical care before section 13
  is fully satisfied.
- A GP or reviewer believes a flagged patient (Scenario 1 or 2) was
  clinically incorrect, or that a patient who should have been
  flagged was missed.
- Any localisation milestone case (section 10) that reveals a
  systematic documentation pattern causing missed or misread clinical
  facts.
- Any subjective-criterion term (section 8) that a reviewer believes
  is over-matching (too permissive) or under-matching (missing clear
  cases) in practice.
- Any case where the anatomy/gender-inclusive mitigation in section
  8.4 appears not to have fired correctly -- for example a trans or
  non-binary patient who should have been included in an
  anatomy-based cancer pathway but was not flagged for review.

Channel: [clinical-safety@leo.mizaic.io](mailto:clinical-safety@leo.mizaic.io)
