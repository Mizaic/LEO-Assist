# DPA Learning Loop Clauses -- Suggested Wording

| Field           | Value                                                  |
| --------------- | ------------------------------------------------------ |
| Document ID     | DC-DPA-001                                             |
| Version         | 0.1.0-draft                                            |
| Status          | Draft -- for legal review                              |
| Date            | 2026-03-03                                             |
| Classification  | QMS -- Data Governance                                 |
| Prepared by     | Quality Engineering                                    |
| Parties         | Mizaic (Processor) and NHS GP Practices in England (Controller) |

## Purpose

This document contains suggested wording for clauses that must appear
in the Data Processing Agreement (DPA) between Mizaic and each NHS GP
Practice. These clauses cover the learning loop -- the process by which
human-reviewed coding corrections improve the system for all users.

These clauses are drafts for legal review. They are not final and must
be checked by a qualified legal adviser before use.

---

## Definitions to add to the DPA

The following terms should be added to the definitions section of the
DPA.

> **"Service"** means the Primary Care Clinical Pathway Audit Platform
> operated by Mizaic, including all software components, AI models, and
> terminology resources used to provide clinical coding and pathway
> audit services to the Controller.
>
> **"Patient Graph"** means the database that holds patient-identifiable
> clinical data, including encounter records, episode timelines, review
> tasks, and audit trail entries. Each Controller's Patient Graph is
> logically separated from other Controllers' data.
>
> **"Knowledge Graph"** means the shared terminology database that holds
> SNOMED CT concepts, clinical terms, value sets, and Derived Terminology
> Mappings. The Knowledge Graph does not hold any Personal Data relating
> to patients.
>
> **"Derived Terminology Mapping"** means a record in the Knowledge Graph
> that links a de-identified clinical phrase (for example "CXR", "2WW
> referral", or "raised PSA") to a SNOMED CT concept code. Each Derived
> Terminology Mapping stores only the following fields:
>
> (a) the clinical phrase (de-identified text);
> (b) a normalised form of the phrase;
> (c) the SNOMED CT concept identifier;
> (d) a confidence score;
> (e) a pseudonymised reviewer identifier;
> (f) a source tag (for example "hitl_approved");
> (g) a timestamp; and
> (h) a provenance tag identifying the pipeline run.
>
> A Derived Terminology Mapping does not contain any Patient Personal
> Data, any patient identifier, any encounter identifier, or any text
> from which a patient could be identified.
>
> **"Learning Loop"** means the process by which Derived Terminology
> Mappings created from one Controller's reviewed coding outputs are
> added to the Knowledge Graph and used to improve the accuracy of
> coding for all Controllers using the Service.
>
> **"De-identification"** means the automated removal of names, NHS
> numbers, postcodes, addresses, phone numbers, email addresses, dates,
> and organisation names from clinical text before that text is
> processed by any AI model or stored outside the Patient Graph.

---

## Clause 1 -- Authorised processing and the Learning Loop

This clause authorises Mizaic to create Derived Terminology Mappings as
part of the processing. Without it, creating mappings could be treated
as processing beyond the Controller's instructions.

> 1.1  The Controller instructs the Processor to process Patient
> Personal Data for the following purposes:
>
> (a) clinical coding of GP encounter records using AI-assisted
> extraction and SNOMED CT terminology resolution;
>
> (b) pathway reconstruction and clinical audit analysis;
>
> (c) presentation of coding proposals to human reviewers for
> approval, rejection, or correction; and
>
> (d) creation of Derived Terminology Mappings from approved coding
> outputs, for the purpose of improving coding accuracy across the
> Service (the Learning Loop).
>
> 1.2  The Controller acknowledges that the creation of Derived
> Terminology Mappings under paragraph 1.1(d) is a necessary part of
> the Service and consents to this processing as part of the
> Controller's instructions to the Processor.
>
> 1.3  For the avoidance of doubt, the Learning Loop processes only
> de-identified clinical phrases and SNOMED CT codes. No Patient
> Personal Data is written to the Knowledge Graph at any time.

---

## Clause 2 -- Cross-Controller benefit

This clause addresses that corrections from one GP Practice improve
results for other GP Practices.

> 2.1  The Controller acknowledges that Derived Terminology Mappings
> created from the Controller's reviewed coding outputs will be stored
> in the Knowledge Graph and will be available to improve the accuracy
> of coding for all Controllers using the Service.
>
> 2.2  The Controller acknowledges that Derived Terminology Mappings
> created from other Controllers' reviewed coding outputs will similarly
> be available to improve the accuracy of coding for the Controller.
>
> 2.3  Derived Terminology Mappings are clinical-phrase-to-SNOMED-code
> pairs. They do not identify any patient, any Controller, or any
> individual reviewer. The Processor shall ensure that no Derived
> Terminology Mapping can be linked back to a specific patient or
> Controller.

---

## Clause 3 -- Controller and Processor roles for the Knowledge Graph

This clause clarifies that Mizaic is an independent controller for the
shared terminology resource.

> 3.1  The parties agree that for the specific activity of maintaining
> the Knowledge Graph (including the creation, storage, and use of
> Derived Terminology Mappings), the Processor acts as an independent
> controller within the meaning of UK GDPR.
>
> 3.2  The Processor's lawful basis for maintaining the Knowledge Graph
> is that the Knowledge Graph does not contain Personal Data relating
> to patients. Where staff Personal Data is processed (pseudonymised
> reviewer identifiers), the Processor relies on its legitimate interest
> in maintaining an accurate clinical terminology resource
> (UK GDPR Article 6(1)(f)).
>
> 3.3  The Processor shall ensure that reviewer identifiers stored in
> the Knowledge Graph are pseudonymised before storage. The Processor
> shall not store reviewer names, email addresses, or any other
> directly identifying information in the Knowledge Graph.
>
> 3.4  For all other processing of Patient Personal Data (including
> storage in the Patient Graph, presentation to reviewers, and audit
> trail recording), the Processor acts as a processor on behalf of the
> Controller in accordance with UK GDPR Article 28.

---

## Clause 4 -- Data minimisation for the Learning Loop

This clause confirms that only the minimum data needed is written to
the Knowledge Graph.

> 4.1  The Processor shall ensure that Derived Terminology Mappings
> contain only the data elements listed in the definition of "Derived
> Terminology Mapping" in this Agreement.
>
> 4.2  The Processor shall not write to the Knowledge Graph any of the
> following:
>
> (a) patient names, NHS numbers, dates of birth, or any other patient
> identifier;
>
> (b) encounter identifiers or encounter dates;
>
> (c) the Controller's name or ODS code;
>
> (d) the full text of any clinical encounter; or
>
> (e) any information from which a patient or Controller could be
> identified.
>
> 4.3  The Processor shall apply the De-identification process to all
> clinical text before any Derived Terminology Mapping is created.
>
> 4.4  The Processor shall run automated checks to verify that no
> Patient Personal Data has been written to the Knowledge Graph. The
> Processor shall make the results of these checks available to the
> Controller on request.

---

## Clause 5 -- Reviewer identity (staff Personal Data)

This clause addresses the `approved_by` field.

> 5.1  When a reviewer employed or engaged by the Controller approves a
> coding proposal, the Processor records the reviewer's identity in the
> Patient Graph as part of the audit trail. This is processing of staff
> Personal Data carried out on behalf of the Controller as part of the
> Controller's clinical audit function.
>
> 5.2  When a Derived Terminology Mapping is created in the Knowledge
> Graph, the Processor shall pseudonymise the reviewer's identity before
> storage. The pseudonymised identifier shall be a one-way hash that
> cannot be reversed to reveal the reviewer's name or email address
> without access to the Patient Graph.
>
> 5.3  The mapping between pseudonymised identifiers and reviewer
> identities shall be held only in the Patient Graph and shall be
> subject to the same access controls and deletion obligations as other
> Patient Personal Data.

---

## Clause 6 -- Deletion and contract termination

This clause says what happens to each type of data when a GP Practice
leaves.

> 6.1  On termination or expiry of this Agreement, the Processor shall:
>
> (a) delete all Patient Personal Data held in the Controller's Patient
> Graph within 30 calendar days of the termination date;
>
> (b) confirm deletion in writing to the Controller;
>
> (c) delete all audit trail entries that identify the Controller's
> staff within 30 calendar days of the termination date; and
>
> (d) delete or anonymise any backup copies of Patient Personal Data
> within 90 calendar days of the termination date.
>
> 6.2  Derived Terminology Mappings in the Knowledge Graph shall not be
> deleted on termination of this Agreement. The Controller acknowledges
> that Derived Terminology Mappings:
>
> (a) do not contain Patient Personal Data;
>
> (b) cannot be linked to the Controller or to any patient; and
>
> (c) form part of a shared clinical terminology resource that other
> Controllers depend on.
>
> 6.3  If the Controller reasonably believes that a specific Derived
> Terminology Mapping contains information that could identify a patient,
> the Controller may notify the Processor in writing and the Processor
> shall investigate and, if the concern is substantiated, delete or
> correct the mapping within 14 calendar days.

---

## Clause 7 -- Audit and verification rights

This clause lets the Controller check that the boundary between
Patient Graph and Knowledge Graph is working.

> 7.1  The Controller (or its appointed auditor) may, on 30 days'
> written notice, inspect the following to verify compliance with this
> Agreement:
>
> (a) the Knowledge Graph schema, to confirm that no patient-identifier
> fields exist;
>
> (b) a random sample of Derived Terminology Mappings, to confirm that
> no Patient Personal Data is present;
>
> (c) the results of automated data governance tests (VT-LEO-AI-014)
> that verify separation of the Patient Graph and Knowledge Graph;
>
> (d) the De-identification pipeline configuration and test results; and
>
> (e) sub-processor agreements and data handling confirmations.
>
> 7.2  The Processor shall provide the results of its automated data
> governance verification tests to the Controller without charge on
> reasonable request.
>
> 7.3  The Processor shall notify the Controller without undue delay if
> it becomes aware that Patient Personal Data has been written to the
> Knowledge Graph in error.

---

## Clause 8 -- Sub-processors (AI model providers)

This clause covers the LLM providers that receive de-identified text
as part of the coding pipeline.

> 8.1  The Controller authorises the Processor to use the following
> sub-processors for the purpose of AI-assisted clinical coding:
>
> | Sub-processor                | Service                        | Data received                  | Region        |
> | ---------------------------- | ------------------------------ | ------------------------------ | ------------- |
> | Amazon Web Services (AWS)    | Bedrock (Anthropic Claude models) | De-identified clinical text | eu-west-2 (London) |
> | Microsoft (Azure)            | Azure OpenAI (GPT models)      | De-identified clinical text    | UK South      |
>
> 8.2  The Processor shall ensure that:
>
> (a) only de-identified clinical text is sent to sub-processors; no
> patient identifiers, NHS numbers, names, or postcodes shall be
> included in any request;
>
> (b) sub-processors do not retain input or output data for their own
> model training or any purpose other than providing the inference
> service;
>
> (c) sub-processors process data within the United Kingdom or European
> Economic Area only;
>
> (d) the Processor has a written agreement with each sub-processor that
> includes data protection obligations at least as protective as those
> in this Agreement; and
>
> (e) the Processor notifies the Controller of any change to the
> sub-processor list at least 30 days before the change takes effect.
>
> 8.3  For the avoidance of doubt, sub-processors receive de-identified
> text only and do not have access to the Patient Graph, the Knowledge
> Graph, or any patient identifier.

---

## Clause 9 -- Transparency

This clause makes sure the Controller knows about the Learning Loop
before signing.

> 9.1  The Processor shall provide the Controller with a plain-English
> description of the Learning Loop before this Agreement is signed. This
> description shall explain:
>
> (a) what a Derived Terminology Mapping is;
>
> (b) how Derived Terminology Mappings are created from approved coding
> outputs;
>
> (c) how De-identification protects patient data before any mapping is
> created;
>
> (d) that Derived Terminology Mappings are stored in a shared Knowledge
> Graph and used to improve coding for all Controllers;
>
> (e) what data is and is not included in a Derived Terminology Mapping;
> and
>
> (f) how the Controller can verify that no Patient Personal Data has
> been written to the Knowledge Graph.
>
> 9.2  The description referred to in paragraph 9.1 may be provided as
> an annex to this Agreement or as a separate document referenced by
> this Agreement.

---

## Implementation note -- remove `approved_by` from writeback

**ICO finding:** The ICO is clear that pseudonymised data IS still
personal data under UK GDPR. A hashed reviewer ID in the Knowledge
Graph would still be personal data from Mizaic's perspective (since
Mizaic holds both databases and can reverse the pseudonym).

**Corrected approach:** Do not store any reviewer identifier in the
Knowledge Graph at all. The `approved_by` field on the SurfaceForm
`MAPS_TO` relationship should be set to the source tag
(e.g. "hitl_approved") rather than the reviewer's identity.

The full DPA (DC-DPA-002) adopts this corrected approach in clause
5.3(d) and clause 6.2. The Patient Graph retains the original
reviewer identity for the Controller's audit trail.

The writeback service
(`services/terminology_api/app/services/writeback_service.py`) must
be updated to stop passing the reviewer identity to the Knowledge
Graph write. Change line 77 from:

    "approved_by": reviewer,

to:

    "approved_by": "hitl_approved",

---

## Open questions for legal review

1. **Deletion timeline.** The suggested wording uses 30 days for
   Patient Graph deletion and 90 days for backups. Are these
   acceptable to NHS GP Practices, or should the primary deletion
   period be shorter (e.g. 14 days)?

2. **Independent controller vs joint controller.** Clause 3 proposes
   that Mizaic is an independent controller for the Knowledge Graph.
   An alternative is joint controllership under UK GDPR Article 26.
   Legal should advise which is more appropriate given the NHS context.

3. **Sub-processor region.** Clause 8.2(c) says UK or EEA only. If
   AWS Bedrock or Azure OpenAI route through non-UK EEA regions, is
   an adequacy decision or transfer mechanism needed? The current code
   uses `eu-west-2` (London) for Bedrock.

4. **Right to object to Learning Loop.** Should the DPA include a
   mechanism for a Controller to opt out of the Learning Loop entirely?
   This would mean their reviewers' corrections are not written back to
   the Knowledge Graph. The system could support this with a per-tenant
   flag, but it would reduce the benefit to that Controller (they still
   receive other Controllers' improvements but do not contribute).

5. **Notification of new sub-processors.** Clause 8.2(e) gives 30 days'
   notice. Is this sufficient, or do NHS frameworks require a longer
   period or an opt-out right?

---

*This document is a starting point for legal drafting. All clause
wording must be reviewed by a solicitor qualified in UK data protection
law before it is included in an executable agreement.*
