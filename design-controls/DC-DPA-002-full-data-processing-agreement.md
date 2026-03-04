# Data Processing Agreement

## Between Mizaic / Healthcare CoPilot and NHS Provider Organisations in England

| Field              | Value                                                    |
| ------------------ | -------------------------------------------------------- |
| Document ID        | DC-DPA-002                                               |
| Version            | 0.2.0-draft                                              |
| Status             | Draft -- for legal review before execution               |
| Date               | 2026-03-04                                               |
| Classification     | QMS -- Data Governance                                   |
| Applicable law     | UK GDPR, Data Protection Act 2018, Data (Use and Access) Act 2025 |

---

## PARTIES

**(1) The Organisation** (the "Controller"), being the NHS provider
organisation named in the applicable Schedule to this Agreement (which
may be a GP practice, NHS trust, NHS foundation trust, integrated care
board, community health provider, or other NHS body), holding an active
NHS Data Security and Protection Toolkit (DSPT) assessment.

**(2) Mizaic Limited / Healthcare CoPilot Limited** (the "Processor"),
a company registered in England and Wales, holding an active NHS DSPT
assessment.

Together the "Parties" and each a "Party".

---

## BACKGROUND

(A) The Controller holds patient clinical records as part of its NHS
functions.

(B) The Processor operates clinical software services (the "Services")
that use AI-assisted coding, pathway reconstruction, and rules-based
guideline matching to support retrospective clinical audit and clinical
decision support.

(C) The Controller wishes to engage the Processor to process Patient
Personal Data for the purposes set out in this Agreement.

(D) This Agreement sets out the master terms on which the Processor
will process Patient Personal Data on behalf of the Controller, in
line with UK GDPR Article 28 and the NHS Data Security and Protection
Toolkit.

(E) The specific processing activities, data types, data sources, and
outputs are defined in one or more Use Case Addendums appended to this
Agreement. Each Addendum forms part of this Agreement and is governed
by the master terms set out here.

---

## 1  DEFINITIONS

In this Agreement, the following terms have the meanings set out below.
Terms defined in UK GDPR have the same meaning as in that regulation.

**"Addendum"** means a Use Case Addendum appended to this Agreement
that defines the specific scope of processing for a particular use
case. As at the date of this Agreement, the Addendums are:

- Addendum A -- EPR Audit (retrospective clinical pathway audit); and
- Addendum B -- CDS (clinical decision support for referral triage
  and care-pathway signposting).

Each Addendum forms part of this Agreement.

**"Approved Mapping"** means a record that links a De-identified
Clinical Phrase to a SNOMED CT concept code, created when a user
approves a coding proposal through the Service.

**"Clinical Record Data"** means patient clinical information supplied
by the Controller to the Service, as further specified in the
applicable Addendum.

**"Data Protection Law"** means the UK General Data Protection
Regulation (UK GDPR), the Data Protection Act 2018, the Data (Use and
Access) Act 2025, and any subordinate legislation, guidance, or codes
of practice issued by the ICO, as amended from time to time.

**"De-identification"** means the automated removal of patient names,
NHS numbers, dates of birth, postcodes, addresses, phone numbers, email
addresses, dates, and organisation names from Clinical Record Data
before that text is processed by any AI model, displayed to a user, or
stored outside the Patient Graph. The De-identification process is
described in Annex B.

**"De-identified Clinical Phrase"** means a short fragment of clinical
text (for example "CXR", "2WW referral", "raised PSA") from which all
Patient Personal Data has been removed by De-identification. A
De-identified Clinical Phrase does not identify any patient.

**"DSPT"** means the NHS Data Security and Protection Toolkit published
by NHS England.

**"Knowledge Graph"** means the shared terminology database operated by
the Processor. It holds SNOMED CT concepts, clinical terms, value sets,
and Approved Mappings. The Knowledge Graph does not hold Patient
Personal Data.

**"Learning Loop"** means the process described in clause 5, by which
Approved Mappings are stored in the Knowledge Graph and used to improve
the accuracy of clinical coding across the Services.

**"Patient Graph"** means the database that holds Patient Personal Data
for the Controller, including encounter records, episode timelines,
referral data, review decisions, and audit trail entries. Each
Controller's Patient Graph is logically and physically separated from
other Controllers' data.

**"Patient Personal Data"** means personal data relating to the
Controller's patients that is processed under this Agreement, including
Clinical Record Data, NHS numbers, names, dates of birth, and any
other information from which a patient could be identified. The
specific categories are set out in the applicable Addendum.

**"Service"** means the clinical software platform operated by the
Processor, including all software, AI models, terminology resources,
and infrastructure used to provide the services described in the
applicable Addendum to the Controller.

**"Sub-processor"** means any third party engaged by the Processor to
carry out processing activities on behalf of the Controller.

**"Use Case"** means a specific processing purpose covered by an
Addendum, such as retrospective clinical audit or clinical decision
support.

---

## 2  SCOPE OF PROCESSING

### 2.1  Framework

The Processor will process Patient Personal Data in accordance with
the master terms set out in this Agreement and the specific processing
scope defined in each applicable Addendum. The Controller may subscribe
to one or more Addendums. Each Addendum sets out:

(a) the nature and purpose of processing;

(b) the types of personal data processed;

(c) the categories of data subjects;

(d) the data sources and outputs;

(e) any use-case-specific instructions; and

(f) a Schedule containing Controller-specific processing details.

### 2.2  Subject matter and duration

This Agreement applies for the duration of the service contract
between the Parties (set out in the applicable Schedule). Processing
begins on the date Patient Personal Data is first uploaded to the
Service and ends when all Patient Personal Data has been deleted or
returned in line with clause 11.

### 2.3  Precedence

If there is a conflict between the master terms in this Agreement and
a provision in an Addendum, the Addendum prevails to the extent of the
conflict for the Use Case it covers.

---

## 3  CONTROLLER'S INSTRUCTIONS

### 3.1  Documented instructions

The Processor shall process Patient Personal Data only in line with
the Controller's documented instructions as set out in this Agreement
and the applicable Addendum(s). The Processor shall not process Patient
Personal Data for any purpose not listed in the applicable Addendum
unless required to do so by law.

### 3.2  Instruction to operate the Learning Loop

The Controller instructs the Processor to create Approved Mappings
from reviewed coding outputs and to store them in the Knowledge Graph
for the purpose of improving coding accuracy across the Services. This
instruction covers all processing described in clause 5 and applies to
all Use Cases unless an Addendum states otherwise.

### 3.3  Notification of unlawful instructions

If the Processor believes that an instruction from the Controller
would break Data Protection Law, the Processor shall tell the
Controller straight away before carrying out that instruction, unless
the law stops it from doing so.

---

## 4  PROCESSOR'S OBLIGATIONS

### 4.1  Confidentiality

The Processor shall make sure that every person who has access to
Patient Personal Data is bound by a duty of confidentiality, whether
by contract or by law.

### 4.2  Security measures

The Processor shall put in place the technical and organisational
security measures described in Annex A (Security Measures). These
measures meet the requirements of UK GDPR Article 32 and include:

(a) encryption of data at rest using AES-256 or equivalent;

(b) encryption of data in transit using TLS 1.2 or higher;

(c) authentication of all users through Azure AD / Entra ID or
NHS-approved identity management systems;

(d) role-based access controls;

(e) separation of the Patient Graph and Knowledge Graph into
physically separate databases, with cross-database queries blocked;

(f) Managed Identity for service-to-service authentication (no
passwords stored in configuration);

(g) internal services not reachable from the internet (Azure Container
Apps internal ingress);

(h) security event logging and monitoring; and

(i) regular penetration testing and vulnerability scanning.

### 4.3  Data Protection Impact Assessment

The Processor shall help the Controller carry out a Data Protection
Impact Assessment (DPIA) where required under UK GDPR Article 35, by
providing information about the processing and the security measures
in place.

### 4.4  Data subject rights

The Processor shall help the Controller respond to requests from data
subjects to exercise their rights under Data Protection Law, including
rights of access, rectification, erasure, restriction, portability,
and objection.

The Processor shall tell the Controller about any data subject request
it receives directly within 2 working days.

### 4.5  Data breach notification

If the Processor becomes aware of a personal data breach affecting
Patient Personal Data, the Processor shall:

(a) notify the Controller without undue delay and in any event within
24 hours of becoming aware of the breach;

(b) provide the Controller with enough information to meet its own
notification obligations under UK GDPR Articles 33 and 34; and

(c) cooperate with the Controller and the ICO in investigating and
fixing the breach.

### 4.6  DSPT compliance

The Processor shall maintain an active DSPT assessment at all times
during this Agreement. The Processor shall provide a copy of its
current DSPT status to the Controller on request.

### 4.7  Records of processing

The Processor shall keep records of all processing activities carried
out on behalf of the Controller, as required by UK GDPR Article 30(2).

### 4.8  Data protection officer

The Processor shall make the contact details of its data protection
officer (or equivalent contact) available to the Controller.

---

## 5  THE LEARNING LOOP

### 5.1  What the Learning Loop does

When a user approves a coding proposal, the Service creates an
Approved Mapping. This is a pair: a De-identified Clinical Phrase
and its SNOMED CT concept code. The Approved Mapping is stored in the
Knowledge Graph and used to improve the accuracy of coding for all
Controllers using the Services, regardless of Use Case.

### 5.2  What an Approved Mapping contains

Each Approved Mapping contains only the following:

(a) the De-identified Clinical Phrase (for example "chest X-ray");

(b) a normalised form of the phrase (lowercase, stripped of special
characters);

(c) the SNOMED CT concept identifier (a numeric code);

(d) a confidence score (a number between 0 and 1);

(e) a source tag (for example "hitl_approved") recording how the
mapping was created;

(f) a timestamp recording when the mapping was created; and

(g) a provenance tag identifying the pipeline run.

### 5.3  What an Approved Mapping does not contain

An Approved Mapping shall not contain:

(a) any patient name, NHS number, date of birth, or other patient
identifier;

(b) any encounter identifier, referral identifier, or encounter date;

(c) the Controller's name, ODS code, or any identifier that could
link the mapping to the Controller;

(d) the user's name, email address, or any directly identifying
staff information;

(e) the full text of any clinical encounter, referral, or document; or

(f) any information from which a patient, user, or Controller
could be identified.

### 5.4  De-identification before the Learning Loop

The Processor shall apply the De-identification process (described in
Annex B) to all clinical text before any Approved Mapping is created.
The De-identification process removes patient names, NHS numbers,
postcodes, addresses, phone numbers, email addresses, dates, and
organisation names.

### 5.5  Automated checks

The Processor shall run automated tests to check that no Patient
Personal Data has been written to the Knowledge Graph. These tests
(identified as VT-LEO-AI-014 in the Processor's quality management
system) run as part of every software release. The Processor shall
make the results of these tests available to the Controller on
request.

### 5.6  Cross-Controller benefit

The Controller acknowledges that:

(a) Approved Mappings created from the Controller's reviewed coding
outputs will be stored in the Knowledge Graph and will be available
to improve coding accuracy for all Controllers using the Services;

(b) Approved Mappings created from other Controllers' reviewed coding
outputs will similarly be available to improve coding accuracy for the
Controller; and

(c) this mutual benefit is a core feature of the Services and is the
reason for the Controller's instruction under clause 3.2.

### 5.7  Controller and Processor roles for the Knowledge Graph

The Parties agree that:

(a) for the processing of Patient Personal Data in the Patient Graph,
the Processor acts as a data processor on behalf of the Controller
under UK GDPR Article 28;

(b) the Knowledge Graph does not contain Patient Personal Data. The
ICO's guidance confirms that the question of whether data is personal
data depends on whether any person is identifiable from the data.
Approved Mappings are generic clinical-phrase-to-SNOMED-code pairs
that do not identify any patient, user, or Controller; and

(c) for the maintenance of the Knowledge Graph (including the
creation, storage, and use of Approved Mappings), the Processor acts
as an independent data controller. The Processor determines the
purposes and means of this processing, which is to maintain a shared
clinical terminology resource that improves coding accuracy for all
users of the Services. This is consistent with the ICO's guidance that
controller or processor status is determined by the practical
realities of the processing, not by the contract alone.

### 5.8  Processor's obligations as Knowledge Graph controller

In its capacity as controller of the Knowledge Graph, the Processor
shall:

(a) ensure that no Patient Personal Data is stored in the Knowledge
Graph;

(b) apply the data minimisation principle (UK GDPR Article 5(1)(c))
so that Approved Mappings contain only the data listed in clause 5.2;

(c) maintain records of all Approved Mappings created; and

(d) respond to any request from the Controller to investigate whether
a specific Approved Mapping contains identifiable information, and
delete or correct the mapping within 14 calendar days if the concern
is substantiated.

---

## 6  USER STAFF DATA

### 6.1  Audit trail in the Patient Graph

When a user approves, rejects, or edits a coding proposal or confirms
a clinical decision, the Service records the user's identity (name and
email address), the decision made, and a timestamp in the Patient
Graph. This is processing of user staff personal data carried out by
the Processor on behalf of the Controller, as part of the Controller's
clinical audit and governance function.

### 6.2  No user identity in the Knowledge Graph

The Processor shall not store any user name, email address, or other
directly identifying information in the Knowledge Graph. The source
tag on each Approved Mapping (for example "hitl_approved") records the
method of creation but does not identify the user.

### 6.3  Lawful basis for user staff data

The Controller is the controller of user staff personal data processed
in the Patient Graph. The Controller is responsible for ensuring it
has a lawful basis for this processing (typically UK GDPR Article
6(1)(e) -- processing necessary for a task carried out in the public
interest, or Article 6(1)(f) -- legitimate interests of the Controller
in maintaining an audit trail).

---

## 7  SUB-PROCESSORS

### 7.1  Authorised Sub-processors

The Controller gives the Processor general written authorisation to
engage the Sub-processors listed in Annex C (Sub-processor Register).
Annex C indicates which Addendum(s) each Sub-processor serves.

### 7.2  Sub-processor obligations

The Processor shall ensure that:

(a) each Sub-processor is bound by a written contract that imposes
data protection obligations at least as protective as those in this
Agreement;

(b) only De-identified clinical text is sent to AI model
Sub-processors; no patient identifiers, NHS numbers, names, or
postcodes shall be included in any request;

(c) AI model Sub-processors do not retain input or output data for
their own model training or any purpose other than providing the
inference service to the Processor;

(d) Sub-processors process data within the United Kingdom or European
Economic Area only, unless the Controller has given prior written
consent and an appropriate transfer mechanism is in place under
UK GDPR Chapter V; and

(e) the Processor remains fully liable to the Controller for the acts
and omissions of its Sub-processors.

### 7.3  Changes to Sub-processors

The Processor shall give the Controller at least 30 days' written
notice before adding or replacing a Sub-processor. The notice shall
include the name of the Sub-processor, the processing it will carry
out, and its processing location.

The Controller may object to the proposed change by giving written
notice to the Processor within 14 days of receiving the Processor's
notice. The Parties shall discuss the objection in good faith. If
the Parties cannot resolve the objection within 30 days, the
Controller may terminate this Agreement on 90 days' written notice.

---

## 8  INTERNATIONAL TRANSFERS

### 8.1  Restriction on transfers

The Processor shall not transfer Patient Personal Data outside the
United Kingdom unless:

(a) the transfer is to a country that the UK Secretary of State has
decided provides an adequate level of data protection; or

(b) appropriate safeguards are in place under UK GDPR Chapter V
(such as UK Standard Contractual Clauses or UK Binding Corporate
Rules); and

(c) the Controller has given prior written consent to the transfer.

### 8.2  Current transfers

As at the date of this Agreement, all processing takes place within
the United Kingdom or European Economic Area. The AWS Bedrock service
operates in the eu-west-2 (London) region. The Azure OpenAI service
operates in the UK South region.

---

## 9  AUDITS AND INSPECTIONS

### 9.1  Controller's audit rights

The Controller (or an auditor appointed by the Controller) may, on
30 days' written notice, carry out an audit or inspection to verify
the Processor's compliance with this Agreement. This includes the
right to:

(a) inspect the Knowledge Graph schema to confirm that no
patient-identifier fields exist;

(b) review a random sample of Approved Mappings to confirm that no
Patient Personal Data is present;

(c) review the results of automated data governance tests
(VT-LEO-AI-014);

(d) review the De-identification pipeline configuration and test
results;

(e) review Sub-processor agreements and data handling confirmations;
and

(f) review the Processor's DSPT assessment and any supporting
evidence.

### 9.2  Cooperation

The Processor shall cooperate with any audit or inspection and shall
provide reasonable access to its premises, systems, and records. The
Processor may charge the Controller for its reasonable costs in
supporting an audit, except where the audit reveals a material breach
of this Agreement.

### 9.3  Automated test results

The Processor shall provide the results of its automated data
governance verification tests to the Controller without charge on
reasonable request.

### 9.4  Breach notification

The Processor shall notify the Controller without undue delay if it
becomes aware that Patient Personal Data has been written to the
Knowledge Graph in error.

---

## 10  DATA SUBJECT RIGHTS

### 10.1  Assistance

The Processor shall assist the Controller in responding to requests
from data subjects to exercise their rights under Data Protection
Law, including:

(a) right of access (UK GDPR Article 15);

(b) right to rectification (UK GDPR Article 16);

(c) right to erasure (UK GDPR Article 17);

(d) right to restriction of processing (UK GDPR Article 18);

(e) right to data portability (UK GDPR Article 20); and

(f) right to object (UK GDPR Article 21).

### 10.2  Response time

The Processor shall respond to any request from the Controller for
assistance with a data subject request within 5 working days.

### 10.3  Right to erasure

Where the Controller receives a valid erasure request relating to a
patient whose data is held in the Patient Graph, the Processor shall
delete the relevant Patient Personal Data within 24 hours of receiving
the Controller's instruction. The Processor shall confirm deletion in
writing.

Approved Mappings in the Knowledge Graph are not affected by patient
erasure requests because they do not contain Patient Personal Data.

---

## 11  END OF AGREEMENT

### 11.1  Deletion of Patient Personal Data

On termination or expiry of this Agreement (or of an individual
Addendum), the Processor shall:

(a) delete all Patient Personal Data held in the Controller's Patient
Graph for the relevant Use Case within 30 calendar days of the end
date, unless a longer retention period is specified in the applicable
Addendum;

(b) delete all audit trail entries that identify the Controller's
staff within 30 calendar days of the end date, unless a longer
retention period is specified in the applicable Addendum;

(c) delete or destroy any backup copies of Patient Personal Data
within 90 calendar days of the end date; and

(d) confirm deletion in writing to the Controller, providing a
certificate of destruction.

### 11.2  Return of data

Before deletion, the Controller may request that the Processor
return all Patient Personal Data in a structured, commonly used,
machine-readable format. The Processor shall provide the data within
30 calendar days of the request.

### 11.3  Approved Mappings

Approved Mappings in the Knowledge Graph shall not be deleted on
termination of this Agreement. The Controller acknowledges that
Approved Mappings:

(a) do not contain Patient Personal Data;

(b) cannot be linked to the Controller, any patient, or any user; and

(c) form part of a shared clinical terminology resource that other
Controllers depend on.

### 11.4  Disputed mappings

If the Controller reasonably believes that a specific Approved Mapping
contains information that could identify a patient, the Controller may
notify the Processor in writing (before or after termination). The
Processor shall investigate and, if the concern is substantiated,
delete or correct the mapping within 14 calendar days.

### 11.5  Partial termination

The Controller may terminate an individual Addendum without
terminating this Agreement or any other Addendum. The termination
provisions of this clause apply to the terminated Addendum only.

---

## 12  TRANSPARENCY

### 12.1  Plain-English description of the Learning Loop

The Processor shall provide the Controller with Annex D (Learning
Loop Description) before this Agreement is signed. Annex D explains
in plain English:

(a) what an Approved Mapping is;

(b) how Approved Mappings are created from reviewed coding outputs;

(c) how De-identification protects patient data before any mapping is
created;

(d) that Approved Mappings are stored in a shared Knowledge Graph and
used to improve coding for all Controllers;

(e) what data is and is not included in an Approved Mapping; and

(f) how the Controller can check that no Patient Personal Data has
been written to the Knowledge Graph.

### 12.2  Changes to processing

The Processor shall tell the Controller about any material change to
the way Patient Personal Data is processed at least 30 days before the
change takes effect. Material changes include changes to
De-identification methods, AI models used, or the structure of
Approved Mappings.

---

## 13  LIABILITY AND INDEMNITY

### 13.1  Processor liability

The Processor shall be liable to the Controller for any damage caused
by processing that does not comply with this Agreement or with Data
Protection Law.

### 13.2  Indemnity

The Processor shall indemnify the Controller against all costs,
claims, damages, and expenses arising from any breach of this
Agreement by the Processor or its Sub-processors, including any fine
imposed by the ICO.

### 13.3  Limitation

The total liability of the Processor under this Agreement shall not
exceed [AMOUNT TO BE AGREED] in any 12-month period, except that
this limitation shall not apply to liability arising from a deliberate
or reckless breach, or from a personal data breach caused by the
Processor's failure to implement the security measures in Annex A.

---

## 14  GENERAL TERMS

### 14.1  Governing law

This Agreement is governed by the laws of England and Wales.

### 14.2  Jurisdiction

The courts of England and Wales have exclusive jurisdiction over any
dispute arising from this Agreement.

### 14.3  Entire agreement

This Agreement (including its Addendums, Annexes, and Schedules) sets
out the entire agreement between the Parties on the processing of
Patient Personal Data and replaces all previous agreements or
understandings on the same subject.

### 14.4  Amendment

This Agreement may only be changed in writing signed by both Parties.

### 14.5  Severability

If any part of this Agreement is found to be unenforceable, the rest
of the Agreement shall continue in full force.

### 14.6  Notices

All notices under this Agreement must be in writing and sent to the
addresses set out in the applicable Schedule.

---

## SIGNATURES

Signed for and on behalf of the **Controller**:

| | |
| --- | --- |
| Name: | _________________________________ |
| Role: | _________________________________ |
| Date: | _________________________________ |
| Signature: | _________________________________ |

Signed for and on behalf of the **Processor**:

| | |
| --- | --- |
| Name: | _________________________________ |
| Role: | _________________________________ |
| Date: | _________________________________ |
| Signature: | _________________________________ |

**Addendums subscribed to:**

| Addendum | Subscribed (Yes / No) |
| -------- | --------------------- |
| Addendum A -- EPR Audit | _________________ |
| Addendum B -- CDS (LEO) | _________________ |

---

---

# ADDENDUM A -- EPR AUDIT

## Use Case: Retrospective Clinical Pathway Audit

This Addendum forms part of the Data Processing Agreement (DC-DPA-002)
between the Controller and the Processor. It sets out the specific
processing scope for the EPR Audit Use Case.

---

### A.1  Nature and purpose of processing

The Processor will process Patient Personal Data for the following
purposes under this Addendum:

(a) AI-assisted clinical coding of Clinical Record Data (encounter
text, document text, and previously coded data) using named entity
recognition (NER) and SNOMED CT terminology resolution;

(b) clinical pathway reconstruction and retrospective audit analysis;

(c) presentation of coding proposals to Reviewers for human review
(approval, rejection, or correction);

(d) creation of Approved Mappings from reviewed coding outputs to
improve coding accuracy across the Services (the Learning Loop,
described in clause 5 of the master terms);

(e) generation and storage of audit trail records; and

(f) export of approved audit data in formats requested by the
Controller.

### A.2  Types of personal data

- Patient encounter text (free-text consultation notes)
- Text extracted from clinical documents (clinic letters, discharge
  summaries, pathology reports, radiology reports, MDT outcome letters,
  referral letters, and other correspondence)
- Previously coded clinical data (SNOMED CT codes, Read codes, CTV3
  codes and their associated terms)
- Patient demographic identifiers (NHS number, name, date of birth,
  postcode, phone number, email address)
- Reviewer staff identifiers (name, email, role) for audit trail
  purposes

### A.3  Categories of data subjects

- Patients registered with the Controller
- Reviewers and staff employed or engaged by the Controller

### A.4  Data sources

- GP FHIR R4 API (Patient, Encounter, DocumentReference resources)
- UMLS Metathesaurus (filtered to UK SNOMED CT edition) as the
  terminology source
- Programme configuration resources (ValueSet, ConceptMap, Measure,
  PlanDefinition)

### A.5  Outputs

All outputs are proposals that require human review before they are
accepted as audit data:

- SNOMED CT-coded encounters
- Clinical episode timelines
- Abnormal investigation flags
- Guideline compliance alerts
- Quality validation reports
- Pathway duration metrics
- LLM-assisted clinical interpretations (with mandatory human review)
- Approved audit data exports

### A.6  Intended users

| User role                             | Interaction                                                                                     |
| ------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Clinical audit teams                  | Review AI-generated episode timelines and coded encounter data; approve, edit, or reject labels. |
| Pathway coordinators                  | Investigate wait-time breaches, outlier episodes, and alerts flagged by quality checks.          |
| Primary care quality improvement leads | Use aggregated audit outputs to identify systemic pathway delays and improvement opportunities. |
| Human reviewers (clinical coders)     | Validate SNOMED CT coding proposals per encounter; corrections feed back to improve the system.  |
| Programme administrators              | Configure programmes: domain definitions, milestone types, guideline rules, quality targets.     |
| System administrators                 | Configure platform infrastructure, pipeline definitions, and AI model parameters.               |

### A.7  Regulatory classification

The EPR Audit platform is classified as IEC 62304 Class B software.
It is retrospective only and does not provide real-time clinical
decision support. It does not influence individual patient treatment
decisions. Classification under MHRA / UKCA guidance for Software as
a Medical Device (SaMD) should be assessed, but the intended output
-- structured audit data for population-level quality improvement --
places it toward the lower-risk end of the SaMD spectrum.

### A.8  Retention

Patient Personal Data processed under this Addendum shall be retained
for the duration specified in Schedule A-1 and deleted in accordance
with clause 11 of the master terms.

### A.9  Addendum-specific definitions

**"Clinical Record Data"** for this Addendum means:

(a) encounter text (consultation notes, telephone contacts, home
visits, task entries);

(b) text extracted from clinical documents (clinic letters, discharge
summaries, pathology reports, radiology reports, MDT outcome letters,
referral letters, and other correspondence filed in the patient
record); and

(c) previously coded data (existing SNOMED CT codes, Read codes, CTV3
codes, and associated terms already recorded against the patient).

**"Reviewer"** means a person employed or engaged by the Controller who
reviews AI-generated coding proposals through the Service and approves,
rejects, or corrects them.

---

### SCHEDULE A-1 -- EPR AUDIT PROCESSING DETAILS

| Field                       | Detail                                              |
| --------------------------- | --------------------------------------------------- |
| Controller name             | [Organisation name]                                 |
| Controller type             | [GP practice / NHS trust / NHS foundation trust / integrated care board / community health provider / other] |
| Controller ODS code         | [ODS code]                                          |
| Controller CQC registration | [CQC registration number, or "N/A" if not applicable] |
| Controller DPO contact      | [Name, email]                                       |
| Controller Caldicott Guardian | [Name, email]                                     |
| Processor contact           | [Mizaic contact name, email]                        |
| Start date                  | [Date]                                              |
| Duration                    | [Duration or "until terminated"]                    |
| DSPT status (Controller)    | [Standards met / approaching standards]              |
| DSPT category (Controller)  | [Category 1 / 2 / 3 / 4]                           |
| DSPT status (Processor)     | [Standards met]                                     |
| Clinical system(s)          | [SystmOne / EMIS / other -- list all source systems] |
| Retention period            | [Period or "as agreed"]                             |
| Notice address (Controller) | [Address]                                           |
| Notice address (Processor)  | [Address]                                           |

---

---

# ADDENDUM B -- CDS (LEO)

## Use Case: Clinical Decision Support for NHS Planned-Care Referral Triage and Care-Pathway Signposting

This Addendum forms part of the Data Processing Agreement (DC-DPA-002)
between the Controller and the Processor. It sets out the specific
processing scope for the LEO Clinical Decision Support Use Case.

---

### B.1  Nature and purpose of processing

The Processor will process Patient Personal Data for the following
purposes under this Addendum:

(a) extraction and SNOMED CT UK coding of clinical information from
electronic referrals, requests, and care records;

(b) rules-based matching of coded patient presentations against
inclusion/exclusion criteria specified in nationally approved clinical
guidelines (including NICE, RCR iRefer, Royal College guidance, and
NHS England pathways);

(c) presentation of clinician-facing summaries, information quality
flags, and guideline-concordant signposting options for review and
confirmation by qualified healthcare professionals;

(d) creation of Approved Mappings from clinician-reviewed coding
outputs to improve coding accuracy across the Services (the Learning
Loop, described in clause 5 of the master terms);

(e) post-confirmation write-back of clinician-confirmed triage
decisions to source systems (NHS e-RS, PAS, EPR);

(f) generation and storage of audit trail records (including user
identity, system recommendations, clinician decisions, and rationale
capture); and

(g) generation of aggregated operational dashboards (non-clinical,
non-patient-identifiable metrics) for service improvement purposes.

### B.2  Types of personal data

- Referral content (NHS e-RS referrals, consultant-to-consultant
  referrals, follow-up requests, advice and guidance submissions,
  self-referral presentations where locally approved)
- Care record data (clinic letters, consultation notes, discharge
  summaries, investigation reports -- pathology, radiology, diagnostic
  imaging, endoscopy, cardiac investigations -- scanned attachments)
- Structured EPR fields (demographics, problem lists, medications,
  allergies, vital signs)
- Patient demographic identifiers (NHS number, name, date of birth,
  postcode, phone number, email address)
- Clinical features (presenting symptoms, medical history, family
  history, performance status, lifestyle risk factors, medications,
  investigation results with values and reference ranges, temporal
  information including key clinical dates)
- Referral metadata (source system identifiers, document types,
  authoring date, urgency indicators, pathway context)
- Clinician user identifiers (name, email, role, professional
  registration) for audit trail purposes

### B.3  Categories of data subjects

- Patients referred to NHS secondary care and diagnostic services
- Clinician users (Clinical Nurse Specialists, General Practitioners,
  specialty-trained clinical administrators, Consultant medical staff
  and specialty doctors)
- Clinical governance leads and service managers (secondary users
  accessing operational dashboards only)

### B.4  Data sources

- NHS e-Referral Service (e-RS) -- primary referral source
- Electronic Patient Record (EPR) systems (including but not limited
  to Epic, Cerner Millennium, System C, TPP SystmOne, EMIS,
  InterSystems TrakCare)
- Picture Archiving and Communication System (PACS) / Radiology
  Information System (RIS) -- radiology reports (text)
- Pathology Laboratory Information Management System (LIMS)
- Clinical documents in structured (HL7 v2/v3/FHIR), semi-structured
  (PDF, Word), and unstructured (plain text, scanned images with OCR)
  formats
- NHS-approved connectors and integration engines within NHS network
  boundaries

### B.5  Outputs

All clinical outputs are advisory and require qualified clinician
review before any clinical action:

(a) **Structured digital representation** -- normalised case record
with SNOMED CT UK-coded clinical features and provenance metadata;

(b) **Clinician summaries** -- concise case synopsis highlighting key
presenting symptoms, relevant history, recent investigations, and
pathway context;

(c) **Quality and safety flags** -- information completeness flags,
urgency mismatch alerts, pathway mis-selection alerts;

(d) **Suggested triage and signposting options** -- guideline-aligned
care pathway recommendations with supporting rationale, presented as
selectable options (never auto-applied);

(e) **Transparency and verification indicators** -- guideline
traceability (source, section, version), criteria matching detail,
source excerpts from referral/record;

(f) **Rationale capture** -- structured prompts and free-text fields
for clinician to document decision reasoning;

(g) **System-of-record write-backs** (post-confirmation only) --
updates to NHS e-RS (status, specialty, priority, clinical notes),
PAS (waiting list, appointment booking), and EPR (triage decision,
clinical actions). All write-backs require clinician authentication,
rollback capability is maintained, and a full audit trail is recorded;

(h) **Audit trail and governance artefacts** -- comprehensive logging
of user identity, actions, system recommendations, clinician
decisions, and rationale; and

(i) **Operational dashboards** -- aggregated non-patient-identifiable
metrics (referral volumes, turnaround times, guideline concordance
rates, override patterns) for quality improvement and capacity
planning.

### B.6  Write-back provisions

The Processor shall only write data back to source systems (NHS e-RS,
PAS, EPR) after explicit clinician confirmation. The Processor shall:

(a) require clinician authentication before any write-back;

(b) maintain rollback capabilities for all write-back operations;

(c) record a full audit trail of all write-back actions including
user identity, timestamp, data written, and source system; and

(d) provide the Controller with the ability to disable write-back
functionality at any time.

### B.7  Intended users

| User role | Interaction |
| --------- | ----------- |
| Clinical Nurse Specialists | Referral triage and pathway signposting within scope of practice |
| General Practitioners | Triage or vetting responsibilities within secondary care contexts |
| Specialty-trained clinical administrators | Working under clinical supervision per local SOPs and delegation frameworks |
| Consultant medical staff and specialty doctors | Referral pathway oversight and complex case review |
| Clinical governance leads and service managers | Aggregated operational dashboards (non-clinical metrics only) |

### B.8  Regulatory classification

LEO is UKCA Class I software as a medical device (SaMD) that provides
clinical decision support for NHS planned-care referral management and
care-pathway signposting. The Processor maintains:

- UKCA Class I Medical Device registration (MHRA)
- ISO 13485:2016 Quality Management System for Medical Devices
- IEC 62304:2006 Medical Device Software lifecycle processes
- ISO 14971:2019 Application of risk management to medical devices
- DCB0129 Clinical Risk Management (manufacturer compliance)
- DCB0160 Clinical Risk Management (deployment -- Controller
  responsibility; Processor provides supporting documentation)

### B.9  Retention

Patient Personal Data processed under this Addendum shall be retained
for a minimum of 8 years in accordance with NHS records management and
Information Governance requirements, unless a different period is
agreed in Schedule B-1. On expiry of the retention period, data shall
be deleted in accordance with clause 11 of the master terms.

### B.10  Third-party clinical content

The Service uses third-party clinical content to support guideline-
based decision-making. The Controller is responsible for:

(a) holding valid licences or Rights to Use (RTU) for all third-party
clinical content accessed via the Service, including NICE guidelines,
RCR iRefer imaging guidelines, Royal College guidance, NHS England
pathways, and SNOMED CT UK Edition;

(b) ensuring compliance with licence terms (user restrictions,
geographical scope, permitted uses);

(c) renewing licences before expiry; and

(d) selecting which national guidelines and pathways are clinically
appropriate for their services and approving local threshold
adaptations through their clinical governance processes.

The Processor is responsible for:

(a) translating nationally approved guidelines into structured rules
and SNOMED CT mappings;

(b) maintaining version control and provenance for all content
configurations;

(c) making updated configurations available within 90 days of
source guideline publication (subject to licensing, governance, and
technical feasibility); and

(d) expediting safety-critical updates through prioritised change
control.

Third-party clinical content remains the intellectual property of the
originating organisation. The Processor does not author, modify, or
warrant the clinical validity of third-party content.

### B.11  Addendum-specific definitions

**"Clinical Record Data"** for this Addendum means:

(a) referral content from NHS e-RS and other locally approved referral
sources;

(b) care record data from EPR systems, including clinic letters,
consultation notes, discharge summaries, investigation reports, and
scanned attachments;

(c) structured EPR fields (demographics, problem lists, medications,
allergies, vital signs); and

(d) referral metadata (source system identifiers, document types,
authoring date, urgency indicators, pathway context).

**"Clinician User"** means a registered healthcare professional
responsible for referral triage, request vetting, and care-pathway
management who reviews LEO outputs and confirms clinical decisions.

**"Write-back"** means the process by which clinician-confirmed
triage decisions are written back to source systems (NHS e-RS, PAS,
EPR) following explicit clinician authentication and confirmation.

### B.12  Addendum-specific instructions

The Controller instructs the Processor to:

(a) extract and code clinical information from referrals and care
records using SNOMED CT UK;

(b) apply rules-based guideline matching against nationally approved
clinical guidelines as configured and approved by the Controller;

(c) present advisory outputs (summaries, flags, signposting options)
to Clinician Users for review;

(d) write back clinician-confirmed decisions to source systems in
accordance with clause B.6; and

(e) operate the Learning Loop in accordance with clause 5 of the
master terms.

---

### SCHEDULE B-1 -- CDS (LEO) PROCESSING DETAILS

| Field                       | Detail                                              |
| --------------------------- | --------------------------------------------------- |
| Controller name             | [Organisation name]                                 |
| Controller type             | [NHS trust / NHS foundation trust / integrated care board / other] |
| Controller ODS code         | [ODS code]                                          |
| Controller CQC registration | [CQC registration number]                           |
| Controller DPO contact      | [Name, email]                                       |
| Controller Caldicott Guardian | [Name, email]                                     |
| Controller SIRO             | [Name, email]                                       |
| Processor contact           | [Healthcare CoPilot contact name, email]            |
| Start date                  | [Date]                                              |
| Duration                    | [Duration or "until terminated"]                    |
| DSPT status (Controller)    | [Standards met / approaching standards]              |
| DSPT category (Controller)  | [Category 1 / 2 / 3 / 4]                           |
| DSPT status (Processor)     | [Standards met]                                     |
| EPR system(s)               | [Epic / Cerner / SystmOne / EMIS / other -- list all] |
| Integration type            | [HL7 v2 / HL7 FHIR / Secure file transfer / other] |
| e-RS integration            | [Yes / No]                                          |
| Configured pathways         | [List configured clinical pathways and guidelines]  |
| Retention period            | [8 years / as agreed]                               |
| Notice address (Controller) | [Address]                                           |
| Notice address (Processor)  | [Address]                                           |

---

---

# ANNEX A -- SECURITY MEASURES

The Processor applies the following technical and organisational
measures to protect Patient Personal Data across all Use Cases, as
required by UK GDPR Article 32:

**Encryption**

- Data at rest: AES-256 (Azure Managed Redis, Azure Blob Storage,
  Neo4j Aura encryption at rest)
- Data in transit: TLS 1.2 or higher on all connections; TLS 1.3 for
  Neo4j Bolt connections

**Authentication and access control**

- All users authenticate through Azure AD / Entra ID (OAuth 2.0) or
  NHS-approved identity management systems (NHS Single Sign-On via
  Microsoft Entra ID)
- Role-based access control with defined roles per Use Case
- Managed Identity for service-to-service authentication (no
  connection strings or passwords in configuration files)
- Non-root containers with no shell access (distroless images)
- Multi-factor authentication where NHS-mandated or risk-assessed as
  required
- Session timeout after period of inactivity

**Network security**

- Azure Container Apps with internal ingress for backend services
  (not reachable from the internet)
- External ingress (HTTPS only) for the API and UI services
- ACA peer-to-peer traffic encryption (mTLS)
- Service-to-service authentication via shared-secret Bearer tokens
  and Managed Identity app-role validation
- Access via NHS-approved network infrastructure (N3/HSCN or NHS
  secure remote access solutions) where applicable

**Database separation**

- Patient Graph and Knowledge Graph are physically separate Neo4j
  database instances
- Cross-database queries are blocked at the application layer
- Automated tests (VT-LEO-AI-014) verify separation on every release

**Secret management**

- All secrets stored in Azure Key Vault (per environment)
- Secrets injected as Key Vault references at container start; never
  stored in image or plain-text configuration

**Monitoring and incident response**

- Security event logging to Azure Log Analytics
- Audit events emitted as FHIR R4B AuditEvent resources
- Comprehensive logging of all user access, actions, and system events
- Incident response procedures aligned with DSPT requirements
- Retained per NHS records management requirements (minimum 8 years
  for CDS audit trail)

**Resilience**

- Multi-environment deployment (development, validation, production)
- Container image pinning via SHA-256 digest
- Automated CI/CD pipeline with security scanning
- Target uptime: 99.9% (measured monthly; excludes planned
  maintenance windows)
- Disaster recovery: Recovery Time Objective (RTO) < 4 hours;
  Recovery Point Objective (RPO) < 1 hour

**Vulnerability management**

- Regular security patching (critical patches within 30 days,
  high-priority within 90 days)
- Annual penetration testing by independent third party
  (CREST-accredited or equivalent)
- Vulnerability scanning and remediation per ISO 27001 controls

---

# ANNEX B -- DE-IDENTIFICATION PROCESS

The Processor applies a three-layer De-identification process to all
free-text Clinical Record Data (encounter text, referral text, and
text extracted from documents) before it reaches any AI model, is
displayed to a user, or is stored outside the Patient Graph.
Previously coded data (SNOMED/Read codes and their terms) does not go
through De-identification because coded terms do not contain patient-
identifiable information.

**Layer 1 -- Pattern matching** (`libs/utils/deidentify.py`)

Scans clinical text for common personal detail patterns and replaces
them with safe placeholder tags:

| What is removed                    | Replacement tag  |
| ---------------------------------- | ---------------- |
| Patient names (multiple formats)   | `[PERSON]`       |
| Named hospitals and clinics        | `[LOCATION]`     |
| Local organisation names           | `[ORGANISATION]` |
| NHS numbers (10 digits)            | `[NHS_NUMBER]`   |
| UK postcodes                       | `[POSTCODE]`     |
| UK phone numbers                   | `[PHONE]`        |
| Email addresses                    | `[EMAIL]`        |
| UK street addresses                | `[ADDRESS]`      |
| Dates                              | `[DATE]`         |

Clinical terms, medicine names, test values, and units are kept
because they are needed for clinical processing.

**Layer 2 -- Pipeline cleaning** (`libs/deid/deid.py`)

Runs before the NER extraction step. Handles NHS numbers, postcodes,
dates, phone numbers, emails, and local organisation names. Tracks
which parts of the text were changed so character positions can be
adjusted.

**Layer 3 -- Export safety net** (`services/api/app/services/export_service.py`)

Runs the De-identification step again at export time. This catches
any text that was processed by an older version of the patterns.

**Validation**

- Strict validator (`libs/ner/deid_validator.py`) checks training
  records for any personal details that survived the cleaning steps
- Automated test suite checks De-identification against known
  personal detail patterns
- Outputs and logs are scanned for personal details every month

**Known limitation**

First names inside free text (for example "discussed with
Christopher") cannot always be caught by pattern matching. The
Processor is developing an NER-based name detection step to address
this.

---

# ANNEX C -- SUB-PROCESSOR REGISTER

| Sub-processor             | Service                           | Data received               | Location            | Contract in place | Addendum(s) |
| ------------------------- | --------------------------------- | --------------------------- | ------------------- | ----------------- | ----------- |
| Amazon Web Services (AWS) | Bedrock (Anthropic Claude models) | De-identified clinical text | eu-west-2 (London)  | Yes               | A, B        |
| Microsoft (Azure)         | Azure OpenAI (GPT models)         | De-identified clinical text | UK South            | Yes               | A, B        |
| Microsoft (Azure)         | Container Apps, Key Vault, Redis, Blob, Service Bus | Encrypted Patient Graph data, secrets, model files | UK South | Yes | A, B |
| Neo4j Inc.                | Neo4j Aura (graph database)       | Patient Graph (encrypted), Knowledge Graph | EU / UK | Yes | A, B |
| Microsoft (Azure)         | Entra ID (authentication)         | User identity tokens        | UK                  | Yes               | A, B        |

For each Sub-processor, the Processor holds a written contract that
includes data protection obligations at least as protective as those
in this Agreement. The Processor confirms that AI model Sub-processors
(AWS Bedrock and Azure OpenAI) do not retain input or output data for
their own model training.

---

# ANNEX D -- LEARNING LOOP DESCRIPTION (PLAIN ENGLISH)

*This annex is written in plain English so that anyone at your
organisation can understand how the Learning Loop works.*

**What data does the system look at?**

The system reads clinical information from your records. Depending on
which services you use, this may include:

1. **Encounter text** -- the notes written during consultations, phone
   calls, and home visits.
2. **Document text** -- text from clinic letters, discharge summaries,
   pathology reports, radiology reports, MDT outcomes, and other
   correspondence filed in the patient record.
3. **Previously coded data** -- SNOMED and Read codes that are already
   recorded against the patient.
4. **Referral content** -- electronic referrals and associated care
   record extracts.

All personal details (names, NHS numbers, addresses, dates, and so on)
are removed from the text before the system processes it.

**What is the Learning Loop?**

When a clinician or clinical coder at your organisation reviews a
coding suggestion from the system and approves it, the system learns
from that decision. It saves a link between a clinical phrase (for
example "chest X-ray" from a radiology report, or "2WW referral" from
a consultation note) and the correct SNOMED code. Next time the system
sees that phrase in any patient's record, it is more likely to suggest
the right code.

**What information is saved?**

Only the clinical phrase and its SNOMED code. For example:

- "chest X-ray" -> SNOMED 399208008
- "2WW referral" -> SNOMED 306206005

No patient names, NHS numbers, dates, addresses, or any other personal
details are saved. The system removes all personal details from the
text before any link is created.

**Who benefits?**

All NHS organisations using the system benefit, regardless of whether
they use the audit service, the clinical decision support service, or
both. If a coder at Organisation A approves "raised PSA" as a match
for the PSA test SNOMED code, then Organisation B's coding will also
improve for that same phrase. Your organisation benefits from
corrections made by other organisations in the same way.

**Can you tell which organisation a link came from?**

No. The saved links do not include any organisation name, ODS code,
clinician name, or patient identifier. There is no way to tell which
organisation or which patient the phrase came from.

**How do we check this is working safely?**

The system runs automated tests on every software release to make sure
no patient data has crossed into the shared terminology database. Your
organisation can ask to see the results of these tests at any time.

**What happens if your organisation leaves the service?**

All patient data held for your organisation is deleted within 30 days
(or in accordance with the retention period in your Addendum). The
clinical-phrase-to-SNOMED links that were created while your
organisation used the service are kept, because they do not contain
any patient or organisation information and other organisations depend
on them. If you believe a specific link contains information that could
identify a patient, you can ask us to investigate and we will fix it
within 14 days.

**What about the AI models?**

The system uses AI models (from AWS and Microsoft) to help with coding.
These models only see clinical text after all personal details have
been removed. The AI providers do not keep any of the text we send
them.

---

*IMPORTANT: This document is a draft for review. It must be checked
by a solicitor qualified in UK data protection law before it is signed.
The liability cap in clause 13.3 must be agreed between the Parties.
The applicable Schedule(s) must be completed for each NHS provider
organisation. Each Controller should sign the master terms and the
Addendum(s) that apply to their use of the Services.*
