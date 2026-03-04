# DC-SP-001 — Sub-processor Evidence Register

| Field | Value |
|---|---|
| Document ID | DC-SP-001 |
| Version | 0.1-draft |
| Status | Draft — evidence items to be completed |
| Date | 2026-03-04 |
| Author | DPO / Legal |
| Related DPIA | DPIA-LEO-AI-001 |
| Related DPA | DC-DPA-002 Annex C |
| NCDA audit items | IS05, SI07, SI08 |

---

## 1  Purpose

This register records all sub-processors engaged by LEO AI (Mizaic Ltd) to process NHS patient personal data on behalf of NHS Controller organisations. It documents the evidence of compliance required under:

- UK GDPR Article 28(2) — written contract with each sub-processor
- NHS DSPT — sub-processor security and IG standards
- NCDA audit requirements IS05, SI07, SI08

---

## 2  Sub-processor register

### 2.1  Amazon Web Services (AWS Bedrock)

| Field | Detail |
|---|---|
| **Sub-processor** | Amazon Web Services, Inc. |
| **Service** | Amazon Bedrock (Claude models — Haiku, Sonnet) |
| **Role** | Primary LLM inference provider (de-identified clinical text) |
| **Data received** | De-identified clinical text (entity phrase ~200 chars, encounter context ~16,000 chars) |
| **Data retained** | None — AWS Enterprise DPA prohibits retention for training or any other purpose |
| **Processing location** | eu-west-2 — London, United Kingdom |
| **International transfer?** | No — UK to UK |
| **DPA / contract in place** | AWS Enterprise Data Processing Agreement (GDPR-compliant) |
| **No-training commitment** | Yes — confirmed in AWS Enterprise DPA |
| **DSPT status** | _[to be obtained from AWS — confirm NHS DSPT or equivalent]_ |
| **ISO 27001 / SOC 2** | AWS holds ISO 27001, SOC 2 Type II — certificates available at https://aws.amazon.com/compliance/ |
| **Penetration testing** | AWS conducts third-party penetration testing; results available under NDA via AWS Artifact |
| **Breach notification** | AWS Enterprise DPA includes breach notification — confirm 72-hour NHS-compatible timeline (DPA-REVIEW-001) |
| **Annual audit / change notification** | AWS updates sub-processor list at https://aws.amazon.com/compliance/sub-processors/ |
| **Used in Addenda** | A (EPR Audit), B (CDS) |

**Evidence items needed:**

| Evidence | Status | Notes |
|---|---|---|
| AWS Enterprise DPA copy | _[pending]_ | Available from AWS account management |
| ISO 27001 certificate | _[pending]_ | Available via AWS Artifact |
| SOC 2 Type II report | _[pending]_ | Available via AWS Artifact (NDA) |
| 72-hour breach notification confirmation | _[pending]_ | DPA-REVIEW-001 open action |
| AWS DSPT or equivalent evidence | _[pending]_ | Confirm with AWS account team |

---

### 2.2  Microsoft (Azure OpenAI)

| Field | Detail |
|---|---|
| **Sub-processor** | Microsoft Corporation |
| **Service** | Azure OpenAI Service (GPT models) |
| **Role** | Secondary LLM inference provider (de-identified clinical text) |
| **Data received** | De-identified clinical text (entity phrase ~200 chars, encounter context ~16,000 chars) |
| **Data retained** | None — Microsoft Enterprise DPA prohibits retention for training or any other purpose |
| **Processing location** | Sweden Central — European Economic Area |
| **International transfer?** | Yes — UK to EEA (Sweden). Lawful under UK Adequacy Regulations 2021. See DC-TRA-001. |
| **DPA / contract in place** | Microsoft Enterprise Data Processing Agreement / Online Services Terms (OST) |
| **No-training commitment** | Yes — confirmed in Microsoft OST (Azure OpenAI data, privacy and security) |
| **DSPT status** | _[Microsoft does not hold an NHS DSPT — equivalent assurance via ISO 27001 and SOC 2]_ |
| **ISO 27001 / SOC 2** | Microsoft holds ISO 27001, SOC 2 Type II — certificates at https://servicetrust.microsoft.com/ |
| **Penetration testing** | Microsoft conducts third-party penetration testing; results available via Service Trust Portal |
| **Breach notification** | Microsoft OST includes breach notification — confirm 72-hour NHS-compatible timeline (TRA-001) |
| **Annual audit / change notification** | Microsoft updates sub-processor list at https://aka.ms/Online-Services-Subprocessors |
| **Used in Addenda** | A (EPR Audit), B (CDS) |

**Evidence items needed:**

| Evidence | Status | Notes |
|---|---|---|
| Microsoft Enterprise DPA copy | _[pending]_ | Available from Microsoft account / portal |
| ISO 27001 certificate | _[pending]_ | Available via Service Trust Portal |
| SOC 2 Type II report | _[pending]_ | Available via Service Trust Portal |
| 72-hour breach notification confirmation | _[pending]_ | TRA-001 / DPA-REVIEW-001 open actions |

---

### 2.3  Microsoft (Azure PaaS — Container Apps, Redis, Service Bus, Key Vault, Blob Storage, Entra ID)

| Field | Detail |
|---|---|
| **Sub-processor** | Microsoft Corporation |
| **Service** | Azure Container Apps, Azure Managed Redis, Azure Service Bus, Azure Key Vault, Azure Blob Storage, Microsoft Entra ID |
| **Role** | Application hosting, session storage, job messaging, secret management, model artefact storage, authentication |
| **Data received** | Encrypted Patient Graph data (via application); OAuth user tokens; secrets (Key Vault); model artefacts — no patient data (Blob Storage) |
| **Data retained** | Per retention policy — see DC-RET-001 |
| **Processing location** | UK South — United Kingdom |
| **International transfer?** | No — UK to UK |
| **DPA / contract in place** | Microsoft Enterprise Data Processing Agreement / Online Services Terms |
| **DSPT status** | _[Microsoft does not hold an NHS DSPT — equivalent assurance via ISO 27001 and SOC 2]_ |
| **ISO 27001 / SOC 2** | As above |
| **Used in Addenda** | A (EPR Audit), B (CDS) |

---

### 2.4  Neo4j Inc. (Neo4j Aura)

| Field | Detail |
|---|---|
| **Sub-processor** | Neo4j, Inc. |
| **Service** | Neo4j Aura (graph database — Patient Graph and Knowledge Graph) |
| **Role** | Primary data store for patient personal data and clinical outputs |
| **Data received** | Full Patient Graph (patient demographics, encounter text, coded outputs, review decisions, audit trail) |
| **Data retained** | Per retention policy — see DC-RET-001 |
| **Processing location** | UK/EU region (confirm specific region — see ARCH-002) |
| **International transfer?** | Depends on confirmed region — see DC-TRA-001 Section 4.2 |
| **DPA / contract in place** | Neo4j Data Processing Agreement |
| **DSPT status** | _[Neo4j does not hold an NHS DSPT — equivalent assurance to be confirmed]_ |
| **ISO 27001 / SOC 2** | _[to be confirmed — request from Neo4j account team]_ |
| **Penetration testing** | _[to be confirmed — request from Neo4j account team]_ |
| **Breach notification** | Neo4j DPA includes breach notification — confirm timeline |
| **Used in Addenda** | A (EPR Audit), B (CDS) |

**Evidence items needed:**

| Evidence | Status | Notes |
|---|---|---|
| Neo4j DPA copy | _[pending]_ | Available from Neo4j account management |
| ISO 27001 / SOC 2 certificate | _[pending]_ | Request from Neo4j account team |
| Specific Aura region confirmation | _[pending]_ | ARCH-002 open action |
| Penetration test summary | _[pending]_ | Request from Neo4j account team |

---

## 3  Sub-processor data flow diagram

The following diagram shows exactly which data each sub-processor receives, retains, and transmits:

```
                        ┌──────────────────────────────────────┐
                        │  NHS Patient Personal Data           │
                        │  (demographics, encounter text,       │
                        │   coded outputs, review decisions)    │
                        └──────────────────┬───────────────────┘
                                           │
                   ┌───────────────────────┼───────────────────────┐
                   │                       │                       │
                   ▼                       ▼                       ▼
         ┌─────────────────┐    ┌──────────────────┐   ┌────────────────────┐
         │ Neo4j Aura      │    │ Azure PaaS       │   │ AWS Bedrock        │
         │ (UK/EU)         │    │ (UK South)       │   │ (eu-west-2, UK)    │
         │                 │    │                  │   │                    │
         │ RECEIVES:       │    │ RECEIVES:        │   │ RECEIVES:          │
         │ Full Patient    │    │ Encrypted data   │   │ DE-IDENTIFIED      │
         │ Graph (all      │    │ via application  │   │ clinical text only │
         │ patient data,   │    │ layer; OAuth     │   │ (entity phrase +   │
         │ encrypted)      │    │ tokens; secrets; │   │ encounter context) │
         │                 │    │ model files      │   │                    │
         │ RETAINS:        │    │                  │   │ RETAINS:           │
         │ Per DC-RET-001  │    │ RETAINS:         │   │ NOTHING — no       │
         │                 │    │ Session TTL      │   │ retention per DPA  │
         │ TRANSMITS:      │    │ 12-24h (Redis);  │   │                    │
         │ Data back to    │    │ jobs ephemeral   │   │ TRANSMITS:         │
         │ application     │    │ (Service Bus)    │   │ Verdict only       │
         │ on request      │    │                  │   │ (closed value set) │
         └─────────────────┘    └──────────────────┘   └────────────────────┘
                                                                │
                                           ┌────────────────────┘
                                           │
                                           ▼
                                ┌──────────────────────┐
                                │ Azure OpenAI         │
                                │ (Sweden Central, EEA)│
                                │                      │
                                │ RECEIVES:            │
                                │ DE-IDENTIFIED        │
                                │ clinical text only   │
                                │ (same as Bedrock)    │
                                │                      │
                                │ RETAINS:             │
                                │ NOTHING — no         │
                                │ retention per DPA    │
                                │                      │
                                │ TRANSMITS:           │
                                │ Verdict only         │
                                │ (closed value set)   │
                                └──────────────────────┘
```

**Key principle:** Patient identifiers (name, NHS number, date of birth, address) are stored only in Neo4j Aura. They are never transmitted to any LLM sub-processor.

---

## 4  Annual audit and change-notification process

| Activity | Frequency | Owner |
|---|---|---|
| Review sub-processor list against current DPA Annex C | Annually | DPO |
| Obtain updated ISO/SOC certificates | Annually | DPO / Legal |
| Confirm no-training commitments still apply | Annually | Legal |
| Notify Controllers of sub-processor changes (30 days' notice per DPA clause 7.3) | On change | Legal |
| Review transfer risk assessment (DC-TRA-001) | Annually | DPO |

---

## 5  Open actions

| ID | Action | Owner | Target date |
|---|---|---|---|
| SP-001 | Obtain AWS Enterprise DPA copy and confirm 72h breach notification | Legal | 2026-05-01 |
| SP-002 | Obtain AWS ISO 27001 and SOC 2 certificates via AWS Artifact | DPO | 2026-05-01 |
| SP-003 | Obtain Microsoft Enterprise DPA copy | Legal | 2026-05-01 |
| SP-004 | Obtain Microsoft ISO 27001 and SOC 2 via Service Trust Portal | DPO | 2026-05-01 |
| SP-005 | Obtain Neo4j DPA copy | Legal | 2026-05-01 |
| SP-006 | Obtain Neo4j ISO/SOC certification evidence | DPO | 2026-05-01 |
| SP-007 | Confirm Neo4j Aura specific UK/EU region (linked to ARCH-002) | Engineering | 2026-05-01 |
| SP-008 | Confirm Microsoft 72h breach notification (linked to TRA-001) | Legal | 2026-05-01 |

---

## 6  References

| Reference | Document |
|---|---|
| DC-DPA-002 Annex C | Sub-processor Register (master DPA) |
| DC-TRA-001 | Transfer Risk Assessment |
| DC-ARCH-001 | System Architecture Document |
| DPIA-LEO-AI-001 | Data Protection Impact Assessment (Section 2.1, Step 3.3) |
| AWS compliance | https://aws.amazon.com/compliance/ |
| Microsoft Service Trust Portal | https://servicetrust.microsoft.com/ |
| Neo4j security | https://neo4j.com/trust/ |
