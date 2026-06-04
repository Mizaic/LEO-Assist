# ADDENDUM B -- REFERRAL ASSESSMENT (LEO)

| Field           | Value                                              |
| --------------- | -------------------------------------------------- |
| Document ID     | DC-DPA-002-B-RA                                    |
| Parent DPA      | DC-DPA-002 v0.2.0-draft                            |
| Version         | 0.1.0-draft                                        |
| Status          | Draft -- for legal review before execution         |
| Date            | 2026-05-29                                         |
| Applicable law  | UK GDPR Art. 28, Data Protection Act 2018          |

This Addendum forms part of the Data Processing Agreement DC-DPA-002
between the Controller and the Processor. It defines the processing
scope for the LEO Referral Assessment Use Case. The master terms of
DC-DPA-002 (including all Article 28(3) obligations) apply in full
alongside this Addendum.

---

## 1  Subject matter and duration

The Processor will process Patient Personal Data to provide AI-assisted
clinical decision support for the assessment of inbound GP referrals,
covering extraction, SNOMED CT coding, guideline-rule matching, and
structured SBAR summary generation.

Processing begins on the Start Date in Schedule 1 and ends when the
service contract between the Parties expires or is terminated.

---

## 2  Nature and purpose of processing

The Processor will process Patient Personal Data to:

(a) extract and SNOMED CT UK code clinical information from inbound
referral text and any accompanying clinical documents;

(b) match coded clinical presentations against rules derived from
nationally approved clinical guidelines (as configured and approved
by the Controller) to identify applicable care pathways;

(c) check the completeness of documented information against
configured information groups for the relevant pathway;

(d) generate a structured SBAR (Situation, Background, Assessment,
Recommendation) summary for presentation to a Clinician User;

(e) present the summary, completeness flags, and pathway signals to
a Clinician User for review -- all outputs are advisory and require
clinician confirmation before any clinical action; and

(f) record an audit trail of Clinician User identity, AI outputs,
and clinician decisions.

---

## 3  Types of personal data

- Referral text and any accompanying clinical documents submitted to
  the Service for the patient
- Inline investigation results (blood tests, vital signs) within the
  referral content
- Patient demographic identifiers (NHS number, name, date of birth,
  postcode) as they appear in the source referral record; removed from
  clinical text before AI model processing per Annex B of DC-DPA-002
- Referral metadata: source system ID, referral date, urgency
  indicator, referring clinician name and ODS code
- Clinician user identifiers: name, email, role; recorded in the
  audit trail only

---

## 4  Categories of data subjects

- Patients whose referral content is submitted to the Service
- Clinician users employed or engaged by the Controller who review
  AI-generated assessments

---

## 5  Controller's instructions

The Controller instructs the Processor to:

(a) extract and code clinical information from submitted referral
content using SNOMED CT UK;

(b) apply rules-based guideline matching against the guidelines
configured and approved by the Controller (listed in Schedule 1);

(c) generate SBAR summaries and completeness flags and present them
to Clinician Users for review;

(d) operate the Learning Loop in accordance with clause 5 of
DC-DPA-002 using clinician-reviewed coding outputs from this Use Case;
and

(e) not write back to source systems (NHS e-RS, PAS, or EPR) under
this Addendum.

---

## 6  Retention and deletion

The Processor will retain Patient Personal Data for as long as the
Controller instructs. The Controller is responsible for determining the
appropriate retention period in line with its own records management
obligations (including the NHS Records Management Code of Practice
2021). The Processor will delete or return all Patient Personal Data
promptly on receipt of the Controller's written instruction, and in any
event on expiry or termination of this Addendum, in accordance with
clause 11 of DC-DPA-002.

Where the Controller requests return of data before deletion, the
Processor will provide a complete export of all Patient Personal Data
held for the Controller as a machine-readable archive (NDJSON format),
delivered via a time-limited secure download link, within 30 calendar
days of the written request.

The expected retention period is set out in Schedule 1 for reference,
but it does not limit the Controller's right to instruct earlier
deletion.

---

## SCHEDULE 1 -- PROCESSING DETAILS

| Field                         | Detail                        |
| ----------------------------- | ----------------------------- |
| Controller name               | [Organisation name]           |
| Controller ODS code           | [ODS code]                    |
| Controller DPO contact        | [Name, email]                 |
| Controller Caldicott Guardian | [Name, email]                 |
| Processor contact             | [Healthcare CoPilot contact]  |
| Start date                    | [Date]                        |
| Duration                      | [Duration or "until terminated"] |
| Referral source system(s)     | [SystmOne / EMIS / other]     |
| Configured guidelines         | [e.g. NICE NG12 -- suspected cancer lower GI, upper GI, urology] |
| Local threshold adaptations   | [e.g. local FIT threshold, or "None"] |
| Retention period              | [8 years / as agreed]         |
| DSPT status (Controller)      | [Standards met / approaching] |
| DSPT status (Processor)       | Standards met                 |

---

*IMPORTANT: This is a draft for legal review before execution.
The master terms of DC-DPA-002 and its Annexes A-D apply in full.*
