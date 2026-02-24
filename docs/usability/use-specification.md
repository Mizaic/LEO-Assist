# Use Specification

| Field            | Value                          |
| ---------------- | ------------------------------ |
| Document ID      | USE-SPEC-001                   |
| Version          | 0.1.0-draft                    |
| Status           | Draft                          |
| Date             | 2026-02-24                     |
| Classification   | QMS — Usability Engineering    |
| Source           | DC-IU-001 (Intended Use)       |

---

## 1. User Groups

User groups are derived from DC-IU-001 Section 3 (Intended Users). Characteristics affecting usability are noted.

| User group                    | Primary interaction                    | Usability-relevant characteristics                          |
| ----------------------------- | -------------------------------------- | ----------------------------------------------------------- |
| **Clinical audit teams**      | Review episode timelines, coded data; approve/edit/reject | Familiar with audit workflows; may have varying SNOMED familiarity |
| **Pathway coordinators**      | Investigate breaches, outliers, alerts | Need to prioritise high-risk items; time-pressured          |
| **Primary care QI leads**      | Use aggregated outputs for improvement | Consume reports; less hands-on with review UI              |
| **Human reviewers (coders)**  | Validate SNOMED CT coding per encounter| Strong SNOMED/clinical coding knowledge; high-volume review |
| **Programme administrators** | Configure programmes, domains, rules   | Technical; configure via API or admin UI                    |
| **System administrators**     | Configure infrastructure, pipelines    | Technical; API and infrastructure focus                    |

---

## 2. Use Environment

From DC-IU-001 Section 5:

- **Setting:** NHS primary care organisations; national clinical audit programmes
- **Access:** Web-based HITL review UI; REST API for programme/system admins
- **Infrastructure:** Cloud-hosted (Azure Container Apps), multi-tenant
- **Authentication:** Azure AD, role-based access (builder, reviewer, releaser, operator)
- **Work context:** Reviewers work in office or remote; may process many tasks per session

---

## 3. User Interface Description

### 3.1 HITL Review UI (Human-in-the-Loop)

The primary user-facing interface for clinical coders and audit teams.

**Components:**
- **Review queue** — list of tasks requiring validation (encounter coding, episode approval)
- **Encounter view** — patient encounter text with highlighted spans (entities)
- **Entity cards** — per-term coding proposals (SNOMED concept, confidence, context)
- **Term search** — SNOMED lookup for corrections and manual coding
- **Corrections log** — audit trail of edits before submission
- **Action controls** — Approve, Edit, Reject, Escalate

**Workflows:**
1. Reviewer selects task from queue
2. Views encounter text with AI-proposed codes
3. Clicks spans to inspect/edit proposals; may search for alternative SNOMED terms
4. Applies corrections (span adjustment, context change, code replacement)
5. Submits decision (approve/edit/reject) with reason

### 3.2 API (Programme / System Administrators)

- REST API for pipeline triggers, programme configuration, data access
- No dedicated admin UI described in current scope; configuration via API or external tools

---

## 4. Training and Knowledge Assumptions

| Assumption                                      | Rationale                                                                 |
| ----------------------------------------------- | ------------------------------------------------------------------------- |
| Reviewers have SNOMED CT and clinical coding training | Required to validate coding proposals accurately                          |
| Reviewers understand audit programme context    | NCDA domains, milestones, and targets inform review decisions             |
| Programme admins understand FHIR/ValueSet concepts | Configuration uses programme-specific value sets and concept maps         |
| System admins have DevOps/cloud experience      | Deployment and pipeline configuration require technical expertise          |

---

## 5. Traceability

| Section | Traces to |
| ------- | --------- |
| User groups | DC-IU-001 §3 |
| Use environment | DC-IU-001 §5 |
| UI description | services/ui (HITL components) |
| Training | DC-IU-001 §8 (Assumptions) |
