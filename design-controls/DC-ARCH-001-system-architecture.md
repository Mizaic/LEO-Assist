# DC-ARCH-001 — System Architecture Document

| Field | Value |
|---|---|
| Document ID | DC-ARCH-001 |
| Version | 0.1-draft |
| Status | Draft — awaiting review |
| Date | 2026-03-04 |
| Author | Engineering Team |
| Related DPIA | DPIA-LEO-AI-001 |
| Related Threat Model | DC-TM-SEC-002 |
| DTAC standard | DTAC Technical Assurance |

---

## 1  Purpose

This document provides the system architecture description for the LEO AI Clinical Pathway Audit Platform. It is intended to satisfy DTAC Technical Assurance (TA01) requirements and to support NHS PCN supplier due-diligence assessments (NCDA audit IS01, TA01).

---

## 2  Hosting Region Summary

| Component | Provider | Region | Data processed |
|---|---|---|---|
| Application Platform | Microsoft Azure (Container Apps) | UK South | All application traffic |
| Patient Graph database | Neo4j Aura | UK (EU tier) | Patient personal data (encrypted) |
| Knowledge Graph database | Neo4j Aura | UK (EU tier) | Anonymised terminology only |
| Redis (sessions, cache) | Azure Managed Redis | UK South | OAuth sessions, pipeline counters |
| Service Bus | Azure Service Bus | UK South | Job metadata (patient_id, encounter_id) |
| Blob Storage | Azure Blob Storage | UK South | NER model artefacts (no patient data) |
| Key Vault | Azure Key Vault | UK South | Secrets only (no patient data) |
| Container Registry | Azure Container Registry | UK South | Container images (no patient data) |
| Authentication | Microsoft Entra ID (Azure AD) | UK | User identity tokens |
| LLM inference — primary | AWS Bedrock (Claude) | eu-west-2 — London, UK | De-identified clinical text only |
| LLM inference — secondary | Azure OpenAI (GPT models) | Sweden Central — EEA | De-identified clinical text only |

> **Note on LLM regions:** AWS Bedrock model inference runs in eu-west-2 (London, UK). Azure OpenAI model inference runs in Sweden Central (European Economic Area). All Azure platform infrastructure (Container Apps, Redis, Service Bus, Key Vault, Blob Storage) is hosted in UK South. The distinction between Azure *platform* hosting (UK) and Azure OpenAI *model inference* (Sweden) is reflected in the data flow diagrams below and in the Transfer Risk Assessment (DC-TRA-001).

---

## 3  Deployment Architecture

### 3.1  Tenancy model

LEO AI operates a **logically separated multi-tenant** model at the application layer:

- Each NHS organisation (GP practice, PCN, trust) is assigned a unique Organisation ID on registration.
- All data queries are scoped to the authenticated user's Organisation ID at the API layer (`org_id` filter on every Neo4j query).
- No cross-organisation queries are possible through the API.
- The Patient Graph and Knowledge Graph are **physically separate Neo4j database instances**. Cross-database queries are blocked at the application layer.
- Automated tests (VT-LEO-AI-014) verify that no patient data crosses into the shared Knowledge Graph on every software release.

Each Controller's patient data is isolated as follows:

```
Controller A (Practice 1)           Controller B (Practice 2)
        │                                   │
        ▼                                   ▼
   org_id = "A"                       org_id = "B"
        │                                   │
        ▼                                   ▼
  [Neo4j Patient Graph]  ← single shared instance, but all nodes
                            carry org_id; all queries filter by org_id;
                            no cross-org traversal possible via API
```

> **Important:** This is logical isolation within a shared Neo4j instance, not physical database-per-tenant. If a physical-per-tenant deployment is required, this can be discussed with the engineering team.

### 3.2  Network architecture

```
Internet
  │
  │  HTTPS (TLS 1.3)
  ▼
┌──────────────────────────────────────────────────────────────┐
│ ZONE A — Public Ingress (Azure Container Apps external)      │
│                                                              │
│  ┌─────────────────┐     ┌─────────────────────────────┐    │
│  │  UI (Next.js)   │     │  Core API (FastAPI)          │    │
│  │  Port 3000      │────▶│  Port 8000                  │    │
│  │  External HTTPS │     │  External HTTPS              │    │
│  └─────────────────┘     └───────────────┬─────────────┘    │
│                                          │                   │
└──────────────────────────────────────────┼───────────────────┘
                                           │  ACA mTLS
                                           ▼
┌──────────────────────────────────────────────────────────────┐
│ ZONE B — Internal Network (Azure Container Apps internal)    │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ Terminology API │  │  FHIR API       │  │Analytics API│  │
│  │ Port 8001       │  │  Port 8002      │  │ Port 8003   │  │
│  └────────┬────────┘  └────────┬────────┘  └──────┬──────┘  │
│           │                   │                   │          │
│  ┌────────▼────────┐  ┌────────▼────────┐  ┌──────▼──────┐  │
│  │ Model Inference │  │ Coding Worker   │  │Analysis     │  │
│  │ Port 8004       │  │ (queue consumer)│  │Worker       │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
│                                                              │
└──────────────────────────────────────────┬───────────────────┘
                                           │
                    ┌──────────────────────┴────────────────────────┐
                    │  ZONE C — Azure PaaS (UK South)               │
                    │                                               │
                    │  Azure Key Vault │ Azure Service Bus          │
                    │  Azure Redis     │ Azure Blob Storage         │
                    │  Azure Entra ID  │ Azure Container Registry   │
                    └──────────────────┬────────────────────────────┘
                                       │
                    ┌──────────────────┴────────────────────────────┐
                    │  ZONE D — External SaaS                       │
                    │                                               │
                    │  Neo4j Aura (UK)  │ AWS Bedrock (eu-west-2)  │
                    │                   │ Azure OpenAI (Sweden)    │
                    └───────────────────────────────────────────────┘
```

### 3.3  Data flow architecture

```
GP FHIR R4 API (NHS network)
  │
  │  Patient, Encounter, DocumentReference resources
  ▼
Core API (ingestion endpoint)
  │
  │  Store patient + encounter data
  ▼
Neo4j Patient Graph (UK)
  │
  ├── Enqueue coding job ──▶ Azure Service Bus (UK)
  │                               │
  │                               ▼
  │                         Coding Worker
  │                               │
  │                    1. Read encounter from Neo4j
  │                    2. NER extraction (Model Inference, spaCy)
  │                    3. SNOMED resolution (Terminology API + Neo4j Knowledge Graph)
  │                    4. [If low confidence] De-identify + sanitise, then:
  │                         a. AWS Bedrock (eu-west-2, UK) ─────┐
  │                         b. Azure OpenAI (Sweden Central) ───┤ Consensus
  │                         c. AWS Bedrock Sonnet (arbitrator) ─┘
  │                    5. Write coded links back to Neo4j Patient Graph
  │                    6. [Optionally] Enqueue analysis job
  │
  ├── Enqueue analysis job ──▶ Azure Service Bus (UK)
  │                                │
  │                                ▼
  │                          Analysis Worker
  │                                │
  │                    1. Anchor detection
  │                    2. Episode building
  │                    3. Safety-net checks
  │                    4. Abnormal result detection
  │                    5. KPI calculation
  │                    6. Write results to Neo4j Patient Graph
  │
  └── UI / API (read, review, export)
        │
        ▼
      Core API ──▶ Neo4j Patient Graph (org-scoped) ──▶ UI
                                │
                                ▼
                          Export (admin only, approved labels)
```

---

## 4  What is sent to LLM sub-processors

Only de-identified clinical text is transmitted to LLM providers. The following fields are sent:

| Field | Maximum size | Content | De-identified? |
|---|---|---|---|
| `entity_text` | ~200 characters | Extracted clinical phrase (e.g. "type 2 diabetes mellitus") | Yes |
| `encounter_text` | 16,000 characters | Surrounding clinical context | Yes — names, NHS numbers, postcodes, dates removed |

**What is never sent to LLMs:**

- Patient name
- NHS number
- Date of birth
- Full address
- Contact details

**What LLMs return:** A structured verdict from a closed permitted-values set (e.g. `active_diagnosis`, `informational`, `historical`, `uncertain`). No raw clinical text is returned by LLMs.

---

## 5  Authentication and access control architecture

```
User (browser)
  │
  │  HTTPS
  ▼
UI (Next.js) ──▶ Core API
                    │
                    │  OAuth 2.0 PKCE flow
                    ▼
              Microsoft Entra ID (Azure AD)
                    │
                    │  JWT (JWKS verified)
                    ▼
              Core API — session created
                    │
                    │  HttpOnly cookie (SameSite=Lax, Secure, Redis-backed)
                    ▼
              Redis session store (UK South, AES-256 at rest)
                    │
                    │  org_id extracted from session
                    ▼
              All database queries scoped to org_id
```

Role-based access control (RBAC) roles:

| Role | Permissions |
|---|---|
| `builder` | Create and configure programmes |
| `reviewer` | Review and approve coding proposals |
| `releaser` | Approve final audit data for export |
| `operator` | Operational monitoring |
| `platform_admin` | Platform-level administration; model registry changes |

---

## 6  Key security controls summary

| Control | Implementation |
|---|---|
| Encryption at rest | AES-256 (Neo4j Aura, Azure Redis, Azure Blob Storage) |
| Encryption in transit | TLS 1.2+ on all connections; TLS 1.3 for Neo4j Bolt |
| Authentication | Azure Entra ID OAuth 2.0; NHS SSO |
| Session management | Server-side Redis sessions; HttpOnly, Secure, SameSite=Lax cookies; 12–24h TTL |
| Inter-service auth | ACA mTLS + SERVICE_AUTH_SECRET Bearer tokens + Managed Identity |
| Secret management | Azure Key Vault (all secrets); never in config files or images |
| Network isolation | Backend services on ACA internal ingress (not internet-reachable) |
| Rate limiting | slowapi (per-IP, configurable) |
| MFA | Configurable via SystemConfig; NHS-mandated MFA supported |
| Container security | Distroless images, non-root, SHA-256 pinned |
| De-identification | Three-layer process before any LLM call (see DPA Annex B) |

---

## 7  SLA and availability targets

| Metric | Target |
|---|---|
| Uptime | 99.9% (measured monthly, excluding planned maintenance) |
| Recovery Time Objective (RTO) | < 4 hours |
| Recovery Point Objective (RPO) | < 1 hour |
| Planned maintenance window | [To be agreed with Controller] |

---

## 8  Open items

| ID | Item | Owner | Target date |
|---|---|---|---|
| ARCH-001 | Produce formal architecture diagram in Visio/draw.io format for DTAC submission | Engineering | 2026-05-01 |
| ARCH-002 | Confirm Neo4j Aura physical region (UK tier confirmation from Neo4j) | Engineering/Legal | 2026-05-01 |
| ARCH-003 | Clarify physical-vs-logical tenant isolation model with Neo4j | Engineering | 2026-05-01 |

---

## 9  References

| Reference | Document |
|---|---|
| DPIA-LEO-AI-001 | Data Protection Impact Assessment |
| DC-TM-SEC-002 | Security Threat Model |
| DC-TRA-001 | Transfer Risk Assessment |
| DC-SP-001 | Sub-processor Evidence Register |
| DC-KM-001 | Key Management Disclosure |
| DTAC | NHS Digital Technology Assessment Criteria |
| NHS DSPT | NHS Data Security and Protection Toolkit |
