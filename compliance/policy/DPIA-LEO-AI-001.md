# DPIA-LEO-AI-001 -- Data Protection Impact Assessment (LEO CDS)

| Field | Value |
|---|---|
| Document ID | DPIA-LEO-AI-001 |
| Version | 1.0-draft |
| Status | Draft -- awaiting DPO advice and sign-off |
| Date | 2026-07-21 |
| Processing | LEO Clinical Decision Support (LEO CDS) |
| Controller | NHS provider organisation under DC-DPA-002 |
| Processor | Mizaic Limited |
| Product risks | Atlas `PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4` (privacy and data security only) |
| Basis | UK GDPR Article 35; ICO DPIA process (7 steps) |

This DPIA follows the ICO's recommended process. It covers only LEO CDS privacy and data security risks to individuals. Clinical-safety and usability risks are managed in the Atlas product risk file and are out of scope here.

---

## Step 1 -- Need for a DPIA

A DPIA is required. The processing is likely to result in a high risk because it involves:

1. Large-scale special category health data (Article 9).
2. New technology (AI / NLP on clinical free text).
3. Evaluation of individuals in a healthcare setting (vulnerable data subjects).

DPO advice on need: _[record]_

---

## Step 2 -- Description of the processing

### Nature (what we do with the data)

| Item | Description |
|---|---|
| Collection | Clinical records / referral content supplied by the Controller |
| Storage | Controller-scoped Patient Graph (Neo4j Aura, UK) |
| Use | NLP and, where needed, AI model support to propose SNOMED CT coding, pathway / guideline signals, completeness checks, and structured summaries for human review |
| Access | Authenticated staff users with organisation scope and roles (Microsoft Entra ID) |
| Sharing | Sub-processors under DC-DPA-002 Annex C: Microsoft Azure, Azure OpenAI, AWS Bedrock, Neo4j Aura, Microsoft Entra ID |
| AI sub-processing | De-identified clinical text only; no NHS number / name / DOB sent to model providers; no provider training use under contract |
| Retention | As agreed in the Controller's Addendum / Schedule; delete or return on instruction or contract end |
| Security | Encryption in transit and at rest; Key Vault secrets; org-scoped RBAC; Mizaic DSPT; Cyber Essentials Plus; company GDPR policies |
| New / novel tech | Yes -- AI-assisted coding and referral assessment support |
| Article 22 | Not engaged -- all AI outputs are advisory and require human review |

### Scope (what the processing covers)

| Item | Description |
|---|---|
| Data subjects | Patients of participating NHS organisations; staff users of LEO CDS |
| Personal data | Demographics / identifiers as supplied by the Controller; clinical text; derived codes and CDS outputs; review decisions; access logs |
| Sensitivity | Special category health data |
| Volume / frequency | Multi-organisation NHS use; batch and on-demand |
| Duration | For the life of the Controller contract / agreed retention |
| Geography | UK primary hosting; AI sub-processing in UK and / or EEA |

### Context

- Source: Controller NHS systems under contract.
- Relationship: Processor acts only on Controller instructions (DC-DPA-002).
- Individuals: NHS patients (vulnerable); no patient-facing LEO interface.
- Expectations / transparency: Controller privacy notices; Processor provides accurate descriptions of AI-assisted processing.
- Processor company assurances: ICO registered; active NHS DSPT; Cyber Essentials Plus; GDPR policies and procedures.

### Purposes

| Purpose | Outcome |
|---|---|
| EPR Audit (Addendum A) | Retrospective pathway audit coding and quality flags for human review |
| Referral Assessment / CDS (Addendum B) | Advisory coding, guideline matching, completeness, and SBAR summaries for clinician review |
| Learning Loop (secondary) | Improve coding via clinician-approved, non-identifying mappings only |

Benefits: better audit quality and safer, faster referral triage support. Not used for marketing or unrelated research.

---

## Step 3 -- Consultation

| Who | Approach |
|---|---|
| DPO | Advice sought and recorded at Step 7 (mandatory) |
| Individuals (patients) | Direct consultation by the Processor is not practicable. Transparency sits with the Controller. Reason: Processor has no direct relationship with patients; Controllers already inform patients about audit / care-support processing. |
| Controllers | Informed via DPA and onboarding |
| Information security / internal | Product privacy and security risks managed in Atlas; company controls via DSPT and Cyber Essentials Plus |
| Sub-processors | Bound by written Article 28 terms (DC-DPA-002 Annex C) |

---

## Step 4 -- Necessity and proportionality

| Question | Assessment |
|---|---|
| Does the processing achieve the purpose? | Yes -- coding, pathway, and referral support require clinical content |
| Less intrusive alternative? | Manual-only coding is not practical at multi-site NHS scale; AI is used with de-identification, minimisation, and mandatory human review |
| Lawful basis (Controller) | Article 6(1)(e) public task; Article 9(2)(h) health/social care (DPA 2018 Sch 1 Pt 1 para 2). Consent not relied on (DPA 2018 ss.52--53) |
| Processor basis | Article 28 contract / Controller instructions (DC-DPA-002) |
| Function creep | Limited to contracted Use Cases |
| Data quality | Human review of AI proposals; Learning Loop uses approved mappings only |
| Data minimisation | De-identification before AI calls; scoped demographics; org-scoped access |
| Privacy information | Controller notices; Processor support wording |
| Individual rights | Controller-led; Processor supports access, correction, erasure, restriction, and objection on instruction |
| Processor compliance | DPA; sub-processor register; DSPT; Cyber Essentials Plus; GDPR policies |
| International transfers | UK / EEA regions; UK adequacy for EEA where applicable; register in DC-DPA-002 Annex C |

---

## Step 5 -- Identify and assess privacy and data security risks

Source of truth: Atlas product risks for LEO CDS, categories `data_protection` and `security_breach`, plus organisation-scope leakage that can disclose personal data (R-39B18C59).

Atlas score = severity x probability x detectability. Higher initial score = higher inherent risk.

| Atlas ID | Risk to individuals | Source of risk | Initial | Residual | Atlas residual |
|---|---|---|---|---|---|
| R-E7875064 | Unauthorised disclosure if a Microsoft user with no LEO role briefly sees clinical screens | Auth / session gate | 27 | 6 | acceptable |
| R-297379A1 | Unauthorised access to patient data outside a clinician's referral / org scope | Org-scope filter failure | 18 | 6 | acceptable |
| R-39B18C59 | Wrong organisation sees another population's aggregated patient data | Analytics scope error | 18 | 4 | acceptable |
| R-02D6E625 | Loss of confidentiality via patient data in logs / monitoring | Logging design | 6 | 4 | acceptable |
| R-AC768F5B | Security compromise or data exposure via malicious / adversarial clinical content (incl. LLM prompt attacks) | Unsafe inbound content | 6 | 4 | acceptable |
| R-11981E9C | Unauthorised disclosure if CDS APIs succeed without authentication | Auth failure | 4 | 4 | acceptable |
| R-5732C371 | Loss of confidentiality if clinical payloads sit in queue messages | Queue design | 4 | 4 | acceptable |
| R-AE6E2185 | Unauthorised access to patient CDS output via widget token misuse | Widget token scope | 4 | 4 | acceptable |
| R-E51E066D | Unauthorised access if RBAC fails for CDS outputs | Role / authorisation failure | 4 | 4 | acceptable |

Potential impacts considered (ICO list): loss of confidentiality; inability to exercise rights; reputational damage; regulatory non-compliance; re-identification risk on AI paths (mitigated by de-identification and contract terms).

---

## Step 6 -- Measures to mitigate the risks

| Atlas ID | Measures | Effect on risk |
|---|---|---|
| R-E7875064 | No LEO session without roles; block UI before clinical routes mount | Reduced -- residual accepted in Atlas |
| R-297379A1 | Referral / org-path patient filters; 403 if out of scope | Reduced -- residual accepted in Atlas |
| R-39B18C59 | Analytics scoped by org type; no individual records in aggregates | Reduced -- residual accepted in Atlas |
| R-02D6E625 | Metadata-only logging; RBAC on ops access; privacy incident monitoring | Reduced -- residual accepted in Atlas |
| R-AC768F5B | De-identification; prompt-injection guards; sanitisation; response caps; upstream malware expectations | Reduced -- residual accepted in Atlas |
| R-11981E9C | Authenticated CDS APIs; RBAC; release monitoring | Reduced -- residual accepted in Atlas |
| R-5732C371 | Queues carry identifiers / routing only; clinical content in Neo4j | Reduced -- residual accepted in Atlas |
| R-AE6E2185 | Short-lived, assessment-scoped server-minted widget JWTs | Reduced -- residual accepted in Atlas |
| R-E51E066D | Role checks on view / generate / citation; denied-access monitoring | Reduced -- residual accepted in Atlas |

### Measures that demonstrate GDPR compliance

| Theme | Evidence |
|---|---|
| Accountability | This DPIA; ICO registration; company GDPR policies; Atlas risk file; DC-DPA-002 |
| Security (Art. 32) | Technical controls above; DSPT; Cyber Essentials Plus |
| Processor duties (Art. 28) | DPA; sub-processor register; delete / assist on instruction |
| Data protection by design | Human review; org scoping; de-identification; least privilege |

---

## Step 7 -- Sign-off and outcomes

| Outcome | Record |
|---|---|
| Additional measures planned | None beyond Atlas mitigations already implemented or accepted |
| Each risk eliminated / reduced / accepted | All nine reduced and residual-accepted in Atlas (see Step 5) |
| Overall residual risk | Acceptable -- not high after measures |
| Consult ICO under Article 36? | No -- residual risk is not high (DPO to confirm) |

**DPO advice:** _[record advice on compliance and whether processing may proceed]_

**Decision:** _[proceed / proceed with conditions / do not proceed]_

**If DPO advice not followed:** _[reasons]_

| | |
|---|---|
| DPO name | |
| Signature | |
| Date | |
| Approver (if different) | |
| Signature / date | |

### Review

Review at least annually, or sooner if nature, scope, context, or purposes change; a new sub-processor or region is added; auth / de-identification changes; a personal data breach occurs; or solely automated decisions are proposed.

---

## References

- ICO: How do we do a DPIA? -- https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/data-protection-impact-assessments-dpias/how-do-we-do-a-dpia/
- UK GDPR Article 35
- DC-DPA-002 -- `compliance/policy/DC-DPA-002-full-data-processing-agreement.md`
- Atlas LEO CDS product risks (privacy / data security)
