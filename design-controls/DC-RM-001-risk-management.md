# Software Risk Management


| Field          | Value                                            |
| -------------- | ------------------------------------------------ |
| Document ID    | DC-RM-001                                        |
| Version        | 2.0.0                                            |
| Status         | Draft                                            |
| Date           | 2026-02-25                                       |
| Standard       | IEC 62304:2006+A1:2015, Clause 7; ISO 14971:2019 |
| Classification | QMS - Design Controls                            |


---

## 1. Purpose

This document describes the software risk management activities for the NLP Training and Inference Pipeline, linking IEC 62304 Clause 7 (Software risk management) to the principles of ISO 14971:2019.

---

## 2. Context

**Software Safety Class:** B (per DC-SC-001)

The system produces clinical audit data that feeds into national quality improvement programmes (e.g., NCDA). Systematic errors could propagate through an indirect harm pathway: incorrect audit conclusions leading to misdirected quality improvement and suboptimal care pathways for future patient populations.

All outputs are proposals subject to mandatory human review. The system cannot directly cause individual patient harm.

---

## 3. Risk Assessment Criteria

### 3.1 Severity


| Level      | Definition                                                                               | Example                                                                                        |
| ---------- | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Negligible | No impact on audit quality                                                               | UI rendering glitch                                                                            |
| Minor      | Minor inaccuracy in audit data, easily detected                                          | Single term miscoded, caught in review                                                         |
| Moderate   | Systematic inaccuracy that may affect audit conclusions or misdirect quality improvement | Consistent miscoding of a clinical domain; automation bias leading to rubber-stamped approvals |
| Major      | Significant impact on audit programme integrity                                          | Large-scale incorrect audit data accepted without detection; pathway failures masked           |


### 3.2 Probability


| Level      | Definition                                      |
| ---------- | ----------------------------------------------- |
| Improbable | Extremely unlikely to occur in normal operation |
| Remote     | Could occur but not expected                    |
| Occasional | May occur during the product lifetime           |
| Probable   | Expected to occur                               |


### 3.3 Risk Matrix


|                | Negligible | Minor  | Moderate | Major  |
| -------------- | ---------- | ------ | -------- | ------ |
| **Probable**   | Low        | Medium | High     | High   |
| **Occasional** | Low        | Medium | Medium   | High   |
| **Remote**     | Low        | Low    | Medium   | Medium |
| **Improbable** | Low        | Low    | Low      | Medium |


---

## 4. Risk Register

### 4.1 Clinical Risks


| ID       | Hazard                                            | Cause                                                                                     | Severity | Probability | Initial Risk | Control Measure                                                                                                 | Residual Risk |
| -------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------- | -------- | ----------- | ------------ | --------------------------------------------------------------------------------------------------------------- | ------------- |
| R-CL-001 | Incorrect SNOMED coding                           | LLM extracts wrong clinical entity                                                        | Moderate | Occasional  | Medium       | Human review required (FR-HR-005); validation checks (FR-TP-006)                                                | Low           |
| R-CL-002 | Missed clinical entity                            | LLM fails to extract relevant term                                                        | Moderate | Occasional  | Medium       | Human reviewer sees full de-identified text; can add missed entities manually                                   | Low           |
| R-CL-003 | Incorrect assertion (negation, uncertainty)       | LLM assigns wrong context to entity                                                       | Minor    | Occasional  | Medium       | Context flags visible in review UI; reviewer can correct                                                        | Low           |
| R-CL-004 | Incorrect SNOMED disambiguation                   | Resolver/disambiguator selects wrong concept                                              | Minor    | Occasional  | Medium       | Multiple candidates shown in review; hybrid search + semantic tag re-ranking; SurfaceForm boost for known terms | Low           |
| R-CL-005 | SurfaceForm writeback propagates error            | Reviewer approves incorrect mapping                                                       | Minor    | Remote      | Low          | SurfaceForm is a 1.2x suggestion boost, not authoritative; future reviewers can override                        | Low           |
| R-CL-006 | Automation bias in HITL review                    | Reviewer trusts system accuracy, reduces review rigour over time                          | Moderate | Occasional  | Medium       | Sampling audits of reviewer behaviour; discordance analysis; periodic gold re-review; reviewer training         | Low           |
| R-CL-007 | Systematic domain miscoding masks pathway failure | Entire clinical domain consistently miscoded (e.g., all referrals categorised as routine) | Moderate | Remote      | Medium       | Gold set regression testing; cross-domain quality sampling; comparison against external audit data              | Low           |


### 4.2 Data Governance Risks


| ID       | Hazard                              | Cause                               | Severity | Probability | Initial Risk | Control Measure                                                                   | Residual Risk |
| -------- | ----------------------------------- | ----------------------------------- | -------- | ----------- | ------------ | --------------------------------------------------------------------------------- | ------------- |
| R-DG-001 | Patient data in Coding graph        | Developer error in persistence code | Major    | Remote      | Medium       | Architectural separation (FR-DG-001); schema constraints; code review; unit tests | Low           |
| R-DG-002 | De-identification failure           | PHI not removed from encounter text | Major    | Remote      | Medium       | Deidentification step in pipeline; source text never written to Coding graph      | Low           |
| R-DG-003 | Unauthorised access to patient data | Insufficient access controls        | Moderate | Remote      | Medium       | Neo4j authentication; API access control; separate databases                      | Low           |


### 4.3 System Risks


| ID       | Hazard                       | Cause                                | Severity   | Probability | Initial Risk | Control Measure                                                                        | Residual Risk |
| -------- | ---------------------------- | ------------------------------------ | ---------- | ----------- | ------------ | -------------------------------------------------------------------------------------- | ------------- |
| R-SY-001 | LLM service unavailable      | AWS Bedrock outage                   | Minor      | Occasional  | Medium       | Hard fail with clear error; no degraded fallback; retry available                      | Low           |
| R-SY-002 | Neo4j database unavailable   | Infrastructure failure               | Minor      | Remote      | Low          | Error handling; graceful error messages                                                | Low           |
| R-SY-003 | Incorrect MedSpaCy inference | Model undertrained or overfitted     | Moderate   | Occasional  | Medium       | F1 >= 0.90 validation threshold; dry-run comparison; human review of inference results | Low           |
| R-SY-004 | LLM prompt injection         | Malicious content in encounter text  | Minor      | Improbable  | Low          | De-identification strips names; structured JSON output format; output validation       | Low           |
| R-SY-005 | Data loss during sync        | Sync fails mid-operation             | Minor      | Remote      | Low          | Sync is per-encounter; delete + create in sequence; re-run is safe                     | Low           |
| R-SY-006 | Incorrect LLM cost tracking  | Token count or pricing miscalculated | Negligible | Remote      | Low          | Cost config externalised in .env; unit tests for cost calculation                      | Low           |


### 4.4 SOUP Risks


| ID       | Hazard                                    | Cause                                 | Severity | Probability | Initial Risk | Control Measure                                             | Residual Risk |
| -------- | ----------------------------------------- | ------------------------------------- | -------- | ----------- | ------------ | ----------------------------------------------------------- | ------------- |
| R-SP-001 | spaCy/MedSpaCy produces incorrect NER     | Model bug or regression               | Moderate | Remote      | Medium       | Pinned versions; regression testing against gold set        | Low           |
| R-SP-002 | Bio_ClinicalBERT embedding drift          | Model update changes embedding space  | Minor    | Improbable  | Low          | Document model version; re-index on model change            | Low           |
| R-SP-003 | SNOMED terminology update breaks resolver | New concepts or changed relationships | Minor    | Occasional  | Medium       | Terminology version tracked; regression tests on update     | Low           |
| R-SP-004 | Security vulnerability in SOUP            | Known CVE in dependency               | Variable | Occasional  | Medium       | SOUP monitoring (DC-SOUP-001 Section 7.2); quarterly review | Low           |


---

## 5. Risk Control Verification


| Control Measure                                                 | Verification Method                                                      | Status            |
| --------------------------------------------------------------- | ------------------------------------------------------------------------ | ----------------- |
| Human review required (FR-HR-005)                               | approval_status workflow enforced; sync only processes 'approved'        | Verified          |
| No patient data in Coding graph (FR-DG-001)                     | Schema split; unit tests; VERIFICATION-REPORT.md Section 2               | Verified          |
| Validation checks (FR-TP-006)                                   | Unit tests for validator; hard_fail/warning gates                        | Verified          |
| LLM hard fail (FR-TP-008)                                       | ExtractionError raised; no regex fallback                                | Verified          |
| F1 threshold for MedSpaCy                                       | Documented in V&V procedures (05-*.md Section 5.5)                       | Procedure defined |
| SOUP version pinning                                            | requirements.txt, package-lock.json                                      | Verified          |
| Automation bias mitigation (R-CL-006)                           | Sampling audit procedure defined; discordance analysis method documented | Procedure defined |
| Integration tests verify cross-component behaviour (Clause 5.6) | DC-ITP-001 test cases                                                    | Verified          |


---

## 6. Residual Risk Assessment

All identified risks have been reduced to Low through the control measures described above. The overall residual risk is **acceptable** given:

1. The system is **Class B** - the indirect harm pathway (incorrect audit data leading to misdirected quality improvement) is mitigated at multiple levels
2. All outputs require mandatory human review before acceptance
3. The system processes historical data only - no real-time clinical decisions
4. Architectural controls prevent patient data leakage to the Coding graph
5. The harm pathway from software error to patient impact traverses multiple independent governance layers (human review, audit programme governance, NHS clinical governance, commissioning decisions)
6. Automation bias (R-CL-006) is monitored through sampling audits

The residual risk is **not zero** - it is acknowledged that population-level quality improvement decisions could be influenced by incorrect audit data. However, the probability and severity of this outcome, given the control measures, does not warrant Class C classification.

---

## 7. Risk Management Review

The risk register shall be reviewed:

- When new features are added
- When SOUP components are updated
- When the intended use changes
- At each release
- Annually at minimum
- When evidence suggests automation bias is increasing (e.g., approval rates consistently > 95% without correction)

---

## 8. Approval


| Role            | Name | Date | Signature |
| --------------- | ---- | ---- | --------- |
| Author          |      |      |           |
| Clinical Lead   |      |      |           |
| Quality Manager |      |      |           |


