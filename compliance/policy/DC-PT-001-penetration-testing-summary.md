# DC-PT-001 — Penetration Testing Summary

| Field | Value |
|---|---|
| Document ID | DC-PT-001 |
| Version | 0.1-draft |
| Status | Draft — to be completed following next test engagement |
| Date | 2026-03-04 |
| Author | Engineering / Security |
| NCDA audit items | TA04, SI04 |
| Related documents | DC-ARCH-001, DC-KM-001, DC-TM-SEC-002, DC-DTAC-001 |

---

## 1  Purpose

This document provides the penetration testing summary for the LEO AI Clinical Pathway Audit Platform. It satisfies:

- NCDA audit requirement TA04 — annual penetration testing by independent third party
- NCDA audit requirement SI04 — Cyber Essentials Plus (or equivalent assurance)
- NHS DSPT — annual penetration testing requirement
- DTAC Technical Assurance

This document provides the executive summary of findings and the remediation plan. The full technical report is held by the LEO AI security team and can be made available to NHS Controllers under NDA on request (DPA clause 9.1(f)).

---

## 2  Testing programme

| Field | Detail |
|---|---|
| **Testing frequency** | Annual minimum (or following significant architectural change) |
| **Test methodology** | Black-box and grey-box web application and API testing; infrastructure assessment |
| **Scope** | External-facing API (core-api), UI (Next.js), authentication flows, session handling, data flows |
| **Out of scope** | Internal ACA network (no external ingress); AWS Bedrock / Azure OpenAI (tested by providers) |
| **Testing provider** | CREST-accredited third party (name: _[to be confirmed]_) |
| **CREST accreditation** | _[confirm provider CREST number]_ |
| **Report classification** | Confidential — available to Controllers under NDA |

---

## 3  Most recent test

| Field | Detail |
|---|---|
| **Test date** | _[to be completed following next engagement]_ |
| **Provider** | _[CREST-accredited firm name]_ |
| **Test type** | Web application penetration test; API security assessment |
| **Platform version tested** | _[version/commit hash]_ |
| **Scope confirmed** | _[confirm scope match with DC-ARCH-001]_ |

> **Note:** A penetration test has not yet been completed as the platform is in pre-production. The first test is scheduled for _[target date: 2026-06-01]_. The controls described in this document reflect the current security posture as documented in DC-TM-SEC-002.

---

## 4  Known controls assessed

The following controls were verified during threat model review (DC-TM-SEC-002) and are candidates for formal pen test verification:

| Control | Description | Test status |
|---|---|---|
| OAuth 2.0 authentication | Azure Entra ID; JWKS verification; session-backed | To be tested |
| Session security | HttpOnly, Secure, SameSite=Lax cookies; Redis-backed; 12–24h TTL | To be tested |
| CSRF protection | OAuth nonce cookie + X-Requested-With header for mutations | To be tested |
| Rate limiting | slowapi per-IP rate limiting | To be tested |
| RBAC enforcement | Role-based access across all API endpoints | To be tested |
| Org-scoping | All queries filtered by org_id; cross-org isolation | To be tested |
| SQL/NoSQL injection | Parameterised Neo4j Cypher queries; no raw query construction | To be tested |
| Prompt injection | INJECTION_GUARD; sanitise_for_prompt(); cap_llm_response() | To be tested |
| TLS / HSTS | TLS 1.3 external; HSTS enforced; Secure cookie | To be tested |
| Content Security Policy | CSP, X-Frame-Options headers | To be tested |
| Secret management | Azure Key Vault references; no plaintext secrets | To be tested |
| Container security | Distroless images; non-root; no shell | Infrastructure test |
| Inter-service auth | ACA mTLS + SERVICE_AUTH_SECRET | Infrastructure test |

---

## 5  Known issues from threat model review

The following issues were identified during the DC-TM-SEC-002 threat model review. These are included here for completeness and will be formally assessed in the next penetration test.

| Issue ID | Finding | Severity | Status |
|---|---|---|---|
| TM-KM-001 | 13 expired client secrets across 8 legacy Azure app registrations | Medium | Open — KM-001 remediation in progress |
| TM-LOG-001 | Audit trail for patient record access via UI/API not yet implemented | Medium | Open — LOG-ACCESS-001 (target 2026-06-01) |
| TM-LOG-002 | Per-call audit log for LLM API calls not yet implemented | Low | Open — LOG-LLM-CALLS-001 (target 2026-05-15) |
| TM-AUTH-001 | authz.denied and data.access audit events not yet instrumented | Low | Open — tracked in DC-TM-SEC-002 GAP-012 |

---

## 6  Remediation plan template

This section will be completed following each penetration test engagement.

| Finding ID | Title | Severity | CVSS | Affected component | Remediation action | Owner | Target date | Status |
|---|---|---|---|---|---|---|---|---|
| _[PT-YYYY-NNN]_ | _[finding title]_ | _[Critical/High/Medium/Low/Informational]_ | _[score]_ | _[component]_ | _[action description]_ | _[owner]_ | _[date]_ | _[Open/In Progress/Resolved]_ |

**Remediation timelines (policy):**

| Severity | Target remediation period |
|---|---|
| Critical | 72 hours |
| High | 30 days |
| Medium | 90 days |
| Low | 180 days or next release cycle |
| Informational | Risk-accepted or scheduled |

---

## 7  Cyber Essentials Plus

| Element | Status |
|---|---|
| Cyber Essentials Plus certification | _[pending]_ |
| Certification body | _[to be confirmed]_ |
| Certificate expiry | _[to be confirmed]_ |
| Certificate number | _[to be confirmed]_ |

Until Cyber Essentials Plus is obtained, the following equivalent evidence is available to Controllers:

- DC-TM-SEC-002 — Security Threat Model (aligned to NCSC Cyber Assessment Framework)
- DC-ARCH-001 — System Architecture Document
- DC-KM-001 — Key Management Disclosure
- Threat model–verified controls (Section 4 above)

**Cyber Essentials Plus roadmap:**

| Milestone | Target date |
|---|---|
| Self-assessment (Cyber Essentials) | 2026-06-01 |
| Technical verification (Cyber Essentials Plus) | 2026-09-01 |
| Certificate issued | 2026-09-30 |

---

## 8  Requesting the full report

NHS Controllers may request the full penetration test technical report under non-disclosure agreement, as provided in DC-DPA-002 clause 9.1(f).

To request the report, contact: _[security contact email]_

---

## 9  Open actions

| ID | Action | Owner | Target date |
|---|---|---|---|
| PT-001 | Engage CREST-accredited pen test provider and schedule first test | Engineering | 2026-04-01 |
| PT-002 | Complete first penetration test | External provider | 2026-06-01 |
| PT-003 | Remediate findings per remediation timelines above | Engineering | Per finding |
| PT-004 | Obtain Cyber Essentials (self-assessment) | Engineering / DPO | 2026-06-01 |
| PT-005 | Obtain Cyber Essentials Plus | Engineering / DPO | 2026-09-30 |
| PT-006 | Remediate TM-KM-001 (expired client secrets) | Engineering | 2026-05-01 |
| PT-007 | Remediate TM-LOG-001 (access audit trail) | Engineering | 2026-06-01 |

---

## 10  References

| Reference | Document |
|---|---|
| DC-TM-SEC-002 | Security Threat Model |
| DC-ARCH-001 | System Architecture Document |
| DC-KM-001 | Key Management Disclosure |
| DC-DTAC-001 | DTAC Compliance Statement (Section 5.3, 5.4) |
| DPIA-LEO-AI-001 | Data Protection Impact Assessment |
| NHS DSPT | Annual penetration testing requirement |
| NCSC CAF | NCSC Cyber Assessment Framework |
| CREST | https://www.crest-approved.org/ |
