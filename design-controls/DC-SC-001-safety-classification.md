# Software Safety Classification

| Field            | Value                                               |
| ---------------- | --------------------------------------------------- |
| Document ID      | DC-SC-001                                           |
| Version          | 2.0.0                                               |
| Status           | Draft                                               |
| Date             | 2026-02-25                                          |
| Standard         | IEC 62304:2006+A1:2015, Clause 4.3                  |
| Classification   | QMS - Design Controls                               |

---

## 1. Purpose

This document determines the software safety classification of the Primary Care Clinical Pathway Audit Platform in accordance with IEC 62304:2006+A1:2015 Clause 4.3.

The classification determines the rigour of software lifecycle activities required under the standard.

---

## 2. IEC 62304 Safety Classes

| Class | Definition | Description |
|-------|-----------|-------------|
| **A** | No injury or damage to health is possible | Software cannot contribute to a hazardous situation |
| **B** | Non-serious injury is possible | Software can contribute to a hazardous situation that would not result in serious injury |
| **C** | Death or serious injury is possible | Software can contribute to a hazardous situation that could result in serious injury or death |

---

## 3. Product Description

**Product:** Primary Care Clinical Pathway Audit Platform (NLP Training and Inference Pipeline subsystem)

**Purpose:** Retrospective, AI-assisted analysis of de-identified primary care encounter records to reconstruct structured clinical pathways for national clinical audit programmes.

**Key characteristics:**
- The system processes **historical** patient records, not real-time clinical data
- All AI-generated outputs are **proposals** subject to mandatory human review
- The system does **not** provide clinical decision support, diagnosis, or treatment recommendations
- Outputs are consumed by **audit professionals**, not directly by clinicians making treatment decisions
- The system has **no direct patient-facing interface**
- The system **does not control or monitor** medical devices or therapeutic processes
- Audit outputs feed into **national clinical audit programmes** (e.g., NCDA) that inform population-level quality improvement and resource allocation

---

## 4. Hazard Analysis for Classification

### 4.1 Can the software contribute to a hazardous situation?

| Question | Answer | Rationale |
|----------|--------|-----------|
| Does the software control or monitor a medical device? | No | The software is a standalone audit tool |
| Does the software provide information used for clinical decision-making? | Indirectly, yes | Audit outputs inform quality improvement programmes that may change clinical practice and resource allocation at organisational or national level |
| Could incorrect software output directly cause patient harm? | Not directly | All outputs require human review; however, systematic errors accepted through review could propagate into misleading audit conclusions |
| Does the software influence treatment decisions? | Not for current patients | However, audit findings inform future clinical pathway design, referral targets, and resource allocation decisions that affect future patients |
| Is the software used in emergency or time-critical scenarios? | No | The system processes historical records asynchronously |

### 4.2 Indirect harm pathway

The system contributes to a **causal chain** that could lead to non-serious harm:

```
Software error (e.g., systematic miscoding)
    -> Accepted through human review (reviewer trusts system)
    -> Incorrect audit data at population level
    -> Misleading quality improvement recommendations
    -> Misdirected resource allocation or pathway changes
    -> Delayed identification of genuine pathway failures
    -> Future patients experience suboptimal care pathways
```

While each link in this chain includes mitigations (human review, multiple data sources, existing clinical governance), the **possibility** of non-serious harm through this indirect pathway cannot be excluded, particularly when:

1. **The NCDA programme** specifically examines cancer diagnosis pathways. Incorrect audit data about diagnostic delays could mask real quality issues, delaying systemic improvements.
2. **Reviewer trust** may increase over time as the system demonstrates accuracy, potentially reducing the rigour of human review (automation bias).
3. **Population-level decisions** based on audit findings (e.g., staffing, pathway redesign, target setting) affect cohorts of future patients, not just individual cases.

### 4.3 Foreseeable misuse scenarios

| Scenario | Severity | Probability | Risk | Mitigation | Residual Risk |
|----------|----------|-------------|------|------------|---------------|
| User treats AI-generated coding as final without thorough review | Moderate | Occasional | Medium | Mandatory HITL review gate; approval_status workflow; role-based access | Low |
| Systematic miscoding of a clinical domain (e.g., all referral types miscategorised) | Moderate | Remote | Medium | Validation checks; quality gates; reviewer training; gold set regression | Low |
| Incorrect pathway duration metrics published in national audit | Moderate | Remote | Medium | Multi-level review before publication; comparison against external data sources | Low |
| Terminology writeback propagates incorrect SurfaceForm mappings at scale | Minor | Remote | Low | SurfaceForm is a 1.2x suggestion boost, not authoritative; human-approved only; spot-check monitoring | Low |
| MedSpaCy model trained on biased gold data | Moderate | Remote | Medium | F1 threshold validation (>= 0.90); dry-run comparison; ongoing gold set expansion | Low |
| Automation bias: reviewers rubber-stamp proposals due to high system accuracy | Moderate | Occasional | Medium | Sampling audits of reviewer behaviour; discordance analysis; periodic gold re-review | Low |

### 4.4 Worst-case outcome

The worst foreseeable outcome from software failure is **systematically incorrect national clinical audit data** that could lead to:

- Failure to identify genuine diagnostic pathway delays (e.g., cancer patients waiting beyond FDS 28-day target)
- Misdirected quality improvement efforts based on incorrect audit findings
- Incorrect performance metrics for NHS organisations, affecting commissioning decisions
- Delayed systemic improvements to care pathways that would have benefited future patients

This could result in **non-serious harm** through delayed pathway improvements at population level. It does **not** constitute serious injury because:
- No individual treatment decisions are directly driven by the system output
- Multiple independent governance layers exist between audit data and clinical practice changes
- The harm pathway is indirect and population-level, not immediate or individual

---

## 5. Classification Determination

### 5.1 Assessment

Following IEC 62304 Clause 4.3:

1. The software system is **not** part of a medical device that directly affects individual patients
2. The software **can** contribute to a hazardous situation through an indirect pathway:
   - Systematic coding errors could propagate into national clinical audit data
   - Incorrect audit findings could misdirect quality improvement efforts
   - Future patients could experience suboptimal care pathways as a result
3. The harm from this pathway is **non-serious**: it is indirect, population-level, delayed, and mitigated by multiple governance layers
4. **Serious injury or death** is not a foreseeable consequence of software failure because:
   - The system does not drive individual treatment decisions
   - Clinical governance processes exist independently of the audit system
   - Audit data is one input among many for quality improvement decisions

### 5.2 Classification

| | |
|---|---|
| **Software Safety Class** | **Class B** |
| **Rationale** | Non-serious injury is possible. The software produces clinical audit data that informs national quality improvement programmes. Systematic errors could lead to incorrect audit conclusions, misdirected quality improvement, and indirectly suboptimal care pathways for future patient populations. The harm pathway is indirect and mitigated, but cannot be excluded. Class C is not appropriate because the system cannot contribute to serious injury or death — it does not drive individual treatment decisions and multiple independent governance layers intervene between audit output and clinical practice. |

### 5.3 Class B Requirements under IEC 62304

For Class B software, the following lifecycle activities are required:

| IEC 62304 Clause | Activity | Required for Class B | Document |
|-------------------|----------|---------------------|----------|
| 4.4 | Software development planning | Yes | DC-SDP-001 |
| 5.1 | Software development process | Yes | DC-SDP-001 |
| 5.2 | Software requirements analysis | Yes | DC-SRS-001 |
| 5.3 | Software architectural design | Yes | docs/nlp-pipeline/02-*.md |
| 5.4 | Software detailed design | Not required | docs/nlp-pipeline/03-*.md (voluntary) |
| 5.5 | Software unit implementation and verification | Yes | 58+ unit tests; DC-STP-001 |
| 5.6 | Software integration and integration testing | Yes | DC-ITP-001 |
| 5.7 | Software system testing | Yes | DC-STP-001 |
| 5.8 | Software release | Yes | DC-SDP-001 Section 11 |
| 6 | Software maintenance | Yes | DC-SMP-001 |
| 7 | Software risk management | Yes (linked to ISO 14971) | DC-RM-001 |
| 8 | Software configuration management | Yes | DC-CM-001 |
| 9 | Software problem resolution | Yes | DC-PR-001 |

### 5.4 Additional Documentation (beyond Class B minimum)

This project maintains documentation beyond the minimum required for Class B:

- Software Detailed Design (docs/nlp-pipeline/03-software-detailed-design.md) — not required for Class B
- SOUP list (DC-SOUP-001) — recommended, not strictly required for Class B
- Traceability matrix (DC-TM-001) — recommended, not strictly required for Class B

---

## 6. Reclassification Triggers

The safety classification shall be reassessed if any of the following occur:

1. The system is used for real-time clinical decision support
2. Output is used to influence individual patient treatment decisions without independent clinical governance review
3. The mandatory human review gate is removed or automated
4. The system is integrated into a clinical workflow where incorrect output could delay diagnosis or treatment for individual patients
5. Regulatory guidance changes (e.g., MHRA reclassification of AI audit tools)
6. Evidence emerges that audit data from this system is used as the sole basis for clinical pathway changes

**Upgrade to Class C** would be considered if the system's output could directly contribute to serious injury — for example, if individual patient treatment decisions were automated based on system output without independent clinical review.

---

## 7. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | | | |
| Quality Manager | | | |
| Clinical Lead | | | |

---

## References

- IEC 62304:2006+A1:2015 Medical device software - Software life cycle processes
- ISO 14971:2019 Medical devices - Application of risk management to medical devices
- MHRA Software and AI as a Medical Device Change Programme (2024)
- DC-IU-001 Intended Use Statement v0.2.0
