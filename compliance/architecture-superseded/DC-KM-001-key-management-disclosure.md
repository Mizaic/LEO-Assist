# DC-KM-001 — Key Management Disclosure

| Field | Value |
|---|---|
| Document ID | DC-KM-001 |
| Version | 0.1-draft |
| Status | Draft — awaiting security review |
| Date | 2026-03-04 |
| Author | Engineering / Security |
| NCDA audit item | TA02 |
| Related documents | DC-ARCH-001, DC-TM-SEC-002, DPIA-LEO-AI-001 |

---

## 1  Purpose

This document discloses the key management arrangements for the LEO AI Clinical Pathway Audit Platform. It satisfies DTAC Technical Assurance requirement TA02 and supports NHS PCN NCDA due-diligence assessments.

---

## 2  Encryption keys in use

| Key type | Scope | Who controls it | Storage | Rotation |
|---|---|---|---|---|
| **Azure platform encryption keys** | All Azure-managed data at rest (Redis, Blob Storage, Service Bus) | Microsoft (platform-managed) | Azure Key Vault (Microsoft-managed) | Automatic — Microsoft-managed |
| **Neo4j Aura encryption keys** | Patient Graph and Knowledge Graph at rest | Neo4j (platform-managed) | Neo4j Aura key management | Per Neo4j Aura policy |
| **Application secrets** (connection strings, service tokens, API keys) | Application-layer credential material | LEO AI (Mizaic) | Azure Key Vault (customer-managed vault, per environment) | Manual — governed by LEO AI rotation schedule |
| **Session encryption** | Redis session store | LEO AI (Mizaic) | Azure Key Vault reference | Per session-secret rotation schedule |
| **TLS/SSL certificates** | All HTTPS connections | LEO AI (Mizaic) / Azure-managed | Azure Container Apps managed certificates | Automatic (Azure-managed) or per LEO AI policy |
| **SERVICE_AUTH_SECRET** | Inter-service Bearer token authentication | LEO AI (Mizaic) | Azure Key Vault (per environment) | Per secret rotation schedule |
| **Azure Managed Identity** | Service-to-service authentication (no passwords) | Azure (platform-managed) | No key material stored — identity-based | N/A — Managed Identity |

---

## 3  Azure Key Vault — customer-managed secrets

### 3.1  Architecture

LEO AI uses a dedicated **Azure Key Vault per environment** (development, validation, production):

- `kv-leoai-dev` — development environment secrets
- `kv-leoai-val` — validation environment secrets
- `kv-leoai-prod` — production environment secrets

All application secrets (database connection strings, API keys, service tokens) are stored as Key Vault Secrets. Container Apps reference them as Key Vault references — secrets are injected at container startup and are never written to configuration files, environment variables in plain text, or container images.

### 3.2  Who controls the keys

| Access level | Who has access |
|---|---|
| Key Vault administrative access | LEO AI platform administrators only (Azure RBAC) |
| Key Vault Secret read access | Application services via Managed Identity (least-privilege) |
| Key Vault audit logs | Available via Azure Monitor / Log Analytics |
| NHS Controller access | Controllers do not have direct Key Vault access. Controllers may request audit evidence via the audit rights in DC-DPA-002 clause 9. |

### 3.3  Rotation schedule

| Secret type | Rotation frequency | Rotation method |
|---|---|---|
| Application API keys (AWS, Azure OpenAI) | At least annually, or on suspected compromise | Manual rotation via Key Vault + application redeployment |
| SESSION_SECRET | At least annually, or on suspected compromise | Manual rotation; causes all active sessions to expire |
| SERVICE_AUTH_SECRET | At least annually, or on suspected compromise | Manual rotation; coordinated across all services |
| TLS certificates | Automatic (Azure-managed) or annually | Automatic renewal via Azure Container Apps |
| Legacy secrets / expired secrets | On identification | Audit and rotation within 30 days |

> **Current gap:** A 2026-03-03 audit of Azure app registrations identified 13 expired client secrets across 8 legacy LEO app registrations. These are tracked as a remediation item (see open action KM-001).

---

## 4  Database encryption

### 4.1  Neo4j Aura — at rest

All data in the Neo4j Patient Graph and Knowledge Graph is encrypted at rest using AES-256 encryption managed by Neo4j Aura's platform encryption. LEO AI does not hold Neo4j encryption keys directly — this is a platform-managed service.

### 4.2  Neo4j Aura — in transit

All connections from application services to Neo4j Aura use the Bolt protocol over TLS 1.3 (`bolt+s://`). Certificate verification is enforced.

### 4.3  Azure Managed Redis — at rest and in transit

- At rest: AES-256 encryption (Azure platform-managed).
- In transit: TLS 1.2+ (`rediss://` URL; Managed Identity access; no passwords).

---

## 5  No patient-level encryption keys

LEO AI does not implement patient-level or organisation-level encryption keys. Data is protected at the platform and transport layer. Organisational data isolation is enforced by application-layer org-scoping (all queries filtered by `org_id`), not by per-organisation encryption.

> If a Controller requires per-organisation encryption keys as a contractual requirement, this must be raised as an engineering work item. It is not currently implemented.

---

## 6  Managed Identity — no passwords in service-to-service communication

All inter-service communication between Azure services uses **Azure Managed Identity**:

- Application services authenticate to Azure Key Vault, Service Bus, Blob Storage, and Redis using Managed Identity app-role tokens.
- No connection strings or passwords are stored in application configuration.
- Managed Identities are per-environment (one user-assigned Managed Identity per ACA environment).

---

## 7  Penetration test findings relating to key management

The most recent independent penetration test assessed key management controls. Summary findings:

| Finding | Severity | Status |
|---|---|---|
| Expired client secrets on legacy app registrations | Medium | Open — see KM-001 |
| No plaintext secrets found in configuration | N/A — no finding | Passed |
| Key Vault access correctly scoped to Managed Identity | N/A — no finding | Passed |

See DC-PT-001 for the full penetration test summary.

---

## 8  Open actions

| ID | Action | Owner | Target date |
|---|---|---|---|
| KM-001 | Audit and decommission unused legacy Azure app registrations; rotate or remove expired client secrets (13 identified across 8 registrations) | Engineering | 2026-05-01 |
| KM-002 | Document and formalise secret rotation schedule as a written policy | Engineering / DPO | 2026-05-01 |
| KM-003 | Confirm Neo4j Aura encryption key management details with Neo4j account team | Engineering | 2026-05-01 |

---

## 9  References

| Reference | Document |
|---|---|
| DC-ARCH-001 | System Architecture Document (Section 5, 6) |
| DC-TM-SEC-002 | Security Threat Model (ACA threat reclassifications T-ACA-003) |
| DC-PT-001 | Penetration Testing Summary |
| DPIA-LEO-AI-001 | DPIA Step 6.1 (Azure Key Vault control) |
| NHS DSPT | Data Security and Protection Toolkit |
