# LEO CDS Service Plan

| Field | Value |
| ----- | ----- |
| Document ID | SVP-LEO-CDS-001 |
| Version | 0.3.0-draft |
| Status | Draft - pending Quality Assurance, Clinical Safety Officer, and Engineering approval |
| Date | 2026-06-08 |
| Product | LEO Clinical Decision Support (LEO CDS) |
| Product ID | PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4 |
| Service class | Managed multi-tenant Software as a Service (SaaS) |
| Process owner | VP of Engineering |
| Regulatory basis | ISO 13485:2016 7.5.1; IEC 62304:2015 Clause 8; MDR 2017/745 Art. 83; DCB0129:2018 |
| Parent procedure | SOP-83 Software as a Medical Device (SaMD) Service Planning and Service Records |
| Related documents | LEO-OP-001; LEO-UM-ERS-001; LEO-UM-DO-001; LEO-UM-CG-001; LEO-UM-SF-001; IFU-LEO-CDS-001; DC-SMP-001; DC-DEP-001; DC-CM-001; DC-PR-001; DC-DPA-002; DC-DPA-002-B-RA; DPIA-LEO-AI-001; DC-DTAC-001; DC-RM-001; DC-SOUP-001; DC-PT-001; SOP-11; SOP-12; SOP-13; SOP-14; SOP-17; SOP-19; SOP-21; SOP-25; SOP-30; SOP-38; SOP-100 |

---

## 1. Purpose

This Service Plan explains how LEO CDS is put into service, kept running,
updated, monitored, rolled back, and switched off for customer deployments.
It is the SOP-83 service-planning deliverable for LEO CDS.

LEO CDS helps clinicians assess referrals and signpost care pathways using
artificial intelligence (AI). All outputs are advisory only. A clinician must
review and confirm outputs before any clinical action or write-back to source
systems.

---

## 2. Key terms

| Term | Meaning |
| ---- | ------- |
| Tenant | One customer organisation using the shared LEO CDS platform. Each tenant's data is kept separate. |
| SaaS | Software as a Service. Mizaic hosts and runs the software in the cloud. |
| Installation Record | Formal record that a product version has been placed into service for a customer. |
| Service Record | Formal record of any in-service event after initial installation. |
| Software Bill of Materials (SBOM) | List of all software parts in a build. Used to check security exposure. |
| Aikido | Mizaic's controlled tool for SBOM and vulnerability evidence. |
| Minimum dataset | Required clinical information that must be present before a referral is assessed as complete. |
| Surface form | Local clinical wording mapped to a SNOMED CT concept. |
| Write-back | Sending clinician-confirmed data back to a source system such as NHS e-Referral Service (e-RS). |
| Service Level Agreement (SLA) | Contractual service target promised to the customer. |
| Service Level Objective (SLO) | Internal engineering target. Usually stricter than the SLA. |
| Priority 1 (P1) | Highest priority. Clinical workflow is unavailable. |
| Priority 2 (P2) | Significant feature unavailable. |
| Priority 3 (P3) | Non-critical issue. |
| Recovery Time Objective (RTO) | Maximum time to restore service after a major failure. |
| Recovery Point Objective (RPO) | Maximum acceptable data loss window. |
| Corrective and Preventive Action (CAPA) | Formal process to fix problems and stop them recurring. |
| Post-Market Surveillance (PMS) | Ongoing review of service performance and safety after release. |
| Common Vulnerabilities and Exposures (CVE) | Published record of a known security flaw. |
| Common Vulnerability Scoring System (CVSS) | Standard score used to rate security flaw severity. |
| Organisation Data Service (ODS) code | NHS identifier for a healthcare organisation. |
| Care Identity Service 2 (CIS2) | NHS login used by healthcare workers for e-RS access. |
| Installation Qualification (IQ) | Evidence that the system is installed correctly. |
| Operational Qualification (OQ) | Evidence that the system works as intended in the target environment. |
| Instructions for Use (IFU) | Customer-facing document that explains how to use LEO CDS safely. |

---

## 3. Scope

This plan applies to all production and validation deployments of LEO CDS
operated by Mizaic for NHS or healthcare customers.

The plan covers:

- Customer onboarding and placement into service.
- Routine software updates, configuration changes, and security patches.
- Corrective service events, emergency fixes, rollback, and disaster recovery.
- Customer communication for planned and unplanned service events.
- Installation Records, Service Records, and post-market monitoring inputs.
- Customer offboarding and decommissioning.

This plan does not replace:

- Clinical incident and adverse event handling under SOP-14.
- Complaints handling under SOP-13.
- Corrective and Preventive Action (CAPA) under SOP-11.
- Customer-facing Instructions for Use in IFU-LEO-CDS-001.
- Internal customer pathway onboarding steps in LEO-OP-001.
- Change classification and design-control obligations under SOP-19 and SOP-25.
- Data erasure and retention controls under SOP-5 and DC-DPA-002.

---

## 4. Service model

### 4.1 Managed multi-tenant SaaS

LEO CDS runs as managed multi-tenant Software as a Service (SaaS) on Azure.
Mizaic is responsible for:

- Hosting the application.
- Deploying containers.
- Monitoring the platform.
- Applying security patches.
- Verifying backups.
- Creating and maintaining service records.

Each customer's data is kept separate by organisation scope in the application
and data layers. Every service event must state whether it affects one tenant,
one deployment group, one shared component, or all tenants.

Customer responsibilities are set out in the contract, Data Processing
Agreement (DPA), deployment pack, and DCB0160 deployment documentation.
They include local clinical governance, user access approval, local
configuration approval, and source-system access.

### 4.2 Edge or customer-hosted deployment

LEO CDS Edge or customer-hosted deployment is not covered by this plan unless
a customer contract explicitly adds it. Before any Edge deployment goes live,
this plan must be updated to define:

- Who is responsible for what between Mizaic and the customer.
- Installation Qualification (IQ) evidence for the customer environment.
- How updates, rollback, backup, and monitoring will work.
- Who creates service records on the customer side.

### 4.3 Service boundaries

| Area | Mizaic responsibility | Customer responsibility |
| ---- | --------------------- | ----------------------- |
| Application software | Build, test, deploy, monitor, and maintain LEO CDS | Read release notes and agree local go-live timing |
| Clinical configuration | Apply approved pathways and rules with version control | Approve local pathways, thresholds, and clinical use |
| AI outputs | Provide advisory summaries, flags, rationale, and audit trail | Clinician review and confirmation before action |
| Source systems | Maintain supported integrations and write-back controls where contracted | Provide access, local credentials, and local rollback support |
| User management | Provide role-based access controls and audit trail | Approve users and remove leavers promptly |
| Infrastructure | Operate the Azure-hosted service | Maintain local network, endpoints, and integration availability |

---

## 5. Roles and responsibilities

| Role | Service responsibility |
| ---- | ---------------------- |
| VP of Engineering | Owns this plan. Ensures service work is planned, done, and recorded. |
| Release Engineer | Runs deployments. Creates Service Records. Attaches Aikido SBOM and vulnerability evidence. Completes post-service checks. |
| Quality Assurance (QA) Lead | Reviews closed Installation Records and Service Records. Starts CAPA when required. |
| Clinical Safety Officer (CSO) | Reviews service events that affect clinical safety, pathway logic, guideline matching, triage, signposting, or write-back. |
| Security Engineering | Assesses CVEs. Validates Aikido findings. Sets security patch urgency. Confirms remaining vulnerability risk. |
| Customer Success Manager | Coordinates customer notice, maintenance windows, deployment updates, and closure messages. |
| Customer Clinical Safety Officer | Owns DCB0160 deployment risk management for the customer organisation. |
| Customer IT Lead | Coordinates source-system access, local network readiness, and integration availability. |

Anyone doing service work must have up-to-date training records for their
assigned standard operating procedures (SOPs) and role.

---

## 6. Installation and placement into service

Each customer go-live must have an Installation Record before the service is
used with production patient data.

### 6.1 Installation prerequisites

Before go-live, the Release Engineer and Customer Success Manager must
confirm:

- LEO-OP-001 onboarding phases are complete, or clearly marked as not
  applicable for this customer.
- Contract, DPA, and any LEO CDS addendum are signed or approved.
- Data Protection Impact Assessment (DPIA) and Digital Technology Assessment
  Criteria (DTAC) evidence status is agreed with the customer.
- DCB0129 manufacturer evidence has been provided.
- DCB0160 deployment responsibilities are confirmed with the customer.
- IFU-LEO-CDS-001 has been issued and training requirements communicated.
- User access model, roles, and initial authorised users are approved.
- Clinical configuration, pathways, guideline versions, and local thresholds
  are approved.
- Minimum dataset configuration is complete and approved under LEO-UM-DO-001
  and DC-GOV-001.
- Guideline rules are reviewed, tested, compiled, and published under
  LEO-UM-CG-001.
- Surface-form aliases for the customer pathway are reviewed, approved, and
  duplicate-checked under LEO-UM-SF-001.
- Where e-RS is in scope: application registration, NHS Initial Connection
  Approval, and Key Vault customer secret setup are complete under
  LEO-UM-ERS-001.
- Production environment settings match DC-DEP-001.
- Required integrations, source-system permissions, and audit logging are
  enabled.
- Installation Qualification (IQ) and Operational Qualification (OQ) checks
  are complete.
- Customer acceptance has been recorded.

### 6.2 Installation Record

The Installation Record is formal proof that a LEO CDS product version has
been placed into service for a customer.

| Field | Requirement |
| ----- | ----------- |
| Record type | InstallationRecord |
| Product | LEO CDS |
| Product version | Released version or approved container image reference |
| Customer | Organisation name and ODS code |
| Environment | Production, validation, or customer-hosted if later approved |
| Service class | Managed SaaS, or Edge only after plan revision |
| SBOM reference | Aikido SBOM export or Aikido build/project evidence |
| IQ/OQ evidence | References to installation and operational qualification evidence |
| Clinical configuration | Pathway, guideline, and local threshold version references |
| Onboarding evidence | LEO-OP-001 phase evidence and approvals |
| Customer instructions | IFU-LEO-CDS-001 issue and training evidence |
| Customer acceptance | Name, role, date, and acceptance status |
| Placed into service | Date and time |
| Outcome | successful, conditional, or failed |
| Deviations | Any unresolved deployment issues and agreed controls |

Installation Records must be created within 2 business days of go-live.
Corrections are added as new notes. Original records must not be deleted.

---

## 7. Software update and patch management

### 7.1 Change classification gate

Every update must pass the SOP-25 and SOP-19 classification gate before
production deployment.

| Class | What it means | Minimum service requirement |
| ----- | ------------- | --------------------------- |
| Cosmetic / Class A | No clinical or user-facing behaviour change | Run regression checks for the scope. Create a Service Record. |
| Class B | Behaviour change, including clinical workflow or safety controls with clinician review gate | Link a change request. Provide design-control and verification test evidence. Complete QA review. Create a Service Record. |
| Class C | Not manufactured under current LEO Core AI policy | Stop work. Escalate to CSO and QA/Regulatory Affairs before implementation or deployment. |

Treat the following as safety-relevant until assessed:

- Pathway logic.
- Guideline matching.
- Urgency flags.
- Information-completeness checks.
- Write-back controls.
- User permissions.
- Audit trail integrity.
- Security controls.
- Patient data processing.

### 7.2 Release cadence

| Release type | Target cadence | Customer notice |
| ------------ | -------------- | --------------- |
| Major release | Quarterly, or as approved by change control | 4 weeks |
| Minor release | Monthly scheduled release | 2 weeks |
| Patch release | As needed | 3 business days where planned |
| Emergency security or safety fix | As soon as approved for release | Within 24 hours of deployment, or earlier where practical |

### 7.3 Deployment procedure

1. Create a draft Service Record before deployment starts.
2. Attach or link the change request, release notes, Aikido SBOM and
   vulnerability evidence, and test evidence.
3. Deploy to validation or staging.
4. Run approved regression, smoke, and service-verification checks.
5. For Class B changes, confirm verification test evidence and QA review.
6. Confirm CSO review where clinical safety or pathway behaviour is affected.
7. Promote the approved build to production.
8. Run post-deployment smoke checks and review monitoring dashboards.
9. Update the Service Record outcome and deviations.
10. Send customer completion notice where required.
11. Close the Service Record after QA completeness review.

### 7.4 Service Record

Every in-service event after initial placement into service must have a
Service Record.

| Field | Requirement |
| ----- | ----------- |
| Record type | ServiceRecord |
| Service type | update, patch, repair, rollback, configuration, decommission, DR-test |
| Product version before | Previous released version or image reference |
| Product version after | New released version or image reference, if applicable |
| Customer or tenant scope | Affected customer, tenant, environment, or all tenants |
| SBOM reference | Aikido SBOM export or build/project evidence, if software changed |
| Change control reference | SOP-25 change request, Jira ticket, pull request, or release record |
| Safety classification | Cosmetic, Class A, or Class B. Class C requires escalation. |
| Verification evidence | Regression, smoke, verification test, OQ, or other evidence references |
| Customer notified | true, false, or not required, with reason if not required |
| Outcome | successful, conditional, failed, or rolled back |
| Deviations | Unexpected behaviour, workaround, customer impact, or CAPA trigger |
| CAPA reference | Required for failed service events or recurring deviations |
| Closed by | QA Lead or delegated quality reviewer |

Service Records must be created within 2 business days of the service event.
Failed service events must trigger CAPA assessment within 2 business days.

---

## 8. Cybersecurity patching

Security patching is governed by SOP-38 and DC-SMP-001. This section sets the
LEO CDS service targets.

| Severity | Trigger | Service target |
| -------- | ------- | -------------- |
| Critical | CVSS score 9.0 or above, active exploitation, or patient-data compromise risk | Assess immediately. Patch within 7 calendar days of CVE publication, or sooner if a validated fix is available. |
| High | CVSS score 7.0 to 8.9, or a material security control weakness | Patch within 30 calendar days |
| Medium | CVSS score 4.0 to 6.9 with no immediate exploit path | Address in the next scheduled minor release unless risk assessment needs earlier action |
| Low | CVSS score below 4.0, or limited exposure | Address in the next major release, or accept with documented rationale |

Security Engineering may require an emergency patch even when the CVSS score
is lower if the flaw affects:

- Authentication or authorisation.
- Patient data separation.
- Audit logging.
- Source-system write-back.
- Remote code execution.

Aikido is the controlled source for SBOM and vulnerability evidence. For
every production build, the Service Record must link the relevant Aikido
project or build evidence. This must include open Critical and High findings,
accepted findings, and remediation status. If a customer or regulator needs a
portable SBOM file, the Release Engineer exports it from Aikido and attaches
or links it from the Service Record.

Open action: align security patch timing language in DC-SMP-001 and
DC-DPA-002 with this plan and SOP-38 before release approval.

---

## 9. Quality standards: how achieved and monitored

### 9.0 Overview

LEO CDS is developed and operated under an ISO 13485:2016 Quality Management
System (QMS). Quality is built in at every stage of development and service,
not inspected in at the end.

Every change that affects clinical behaviour, safety controls, or patient data
must pass a formal classification gate before it reaches production. Class B
changes -- those affecting pathway logic, guideline matching, urgency flags,
information completeness, or write-back -- require a traceable evidence chain
in the Atlas QMS server linking the requirement to the implementation, the
test, and the test result. No Class B change is deployed without verification
test evidence and review by the QA Lead and, where clinical safety is
affected, the Clinical Safety Officer. All AI outputs are advisory only; a
clinician must confirm every proposal before any clinical action or write-back
occurs.

In service, quality is monitored continuously, at each release, and through
periodic review. Continuous monitoring uses Azure Monitor, Application
Insights, and automated audit trail checks that watch service health, error
rates, user access, and AI output behaviour around the clock. At each
deployment the Release Engineer runs post-deployment smoke checks and the QA
Lead reviews and closes the Service Record within five business days. Any
failed service event triggers a formal Corrective and Preventive Action
assessment within two business days. Monthly, service metrics are aggregated
into a Post-Market Surveillance report covering availability, incidents,
security patch timeliness, rollback events, complaints, and AI quality
indicators. A Disaster Recovery exercise is carried out at least annually.

For stakeholder communication at the Approved Organisation, Mizaic uses a
tiered approach matched to each group's responsibilities and decision-making
authority. At executive and information-governance level -- including the
Caldicott Guardian, Senior Information Risk Owner, and Chief Clinical
Information Officer -- Mizaic provides a formal confirmation when the service
goes live, a written service performance summary at least annually, and direct
notification within two hours of any P1 incident with patient safety
implications. The Customer Clinical Safety Officer receives advance notice of
every release that changes clinical behaviour, plain-English release notes
describing what has changed and why it is safe, and direct clinical safety
advisories from Mizaic's Clinical Safety Officer within the timescales set by
the IFU. Operational and IT contacts receive notice of every planned
maintenance window and deployment, technical summaries of security patches,
and real-time updates during incidents. End users -- clinicians and referral
coordinators -- receive the Instructions for Use before they begin using the
system, plain-English summaries of any workflow changes ahead of each release,
and notice of planned downtime through the Approved Organisation's own
internal channels. The Customer Success Manager is responsible for routing
communications to the correct contacts, whose names and preferred channels are
recorded in the Installation Record before go-live.

### 9.1 How quality standards are achieved

LEO CDS is developed and operated under an ISO 13485:2016 Quality Management
System (QMS). Quality is built in at each stage, not inspected in at the end.

**Design and development controls.** Every behaviour change requires a
traceable chain in the Atlas QMS server: User Need -> Design Input -> Design
Output -> Verification Test. No Class B change reaches production without
verified evidence recorded in Atlas. The SOP-25 and SOP-19 classification
gate prevents unreviewed changes from entering the deployment pipeline.

**Clinical safety gate.** All changes to pathway logic, guideline matching,
urgency flags, information-completeness checks, or write-back controls are
reviewed by the Clinical Safety Officer before deployment. All AI outputs
are advisory only. A clinician must confirm every proposal before any
clinical action or write-back to source systems.

**Verification and validation.** Automated regression, smoke, and service
verification checks run against every build. Class B changes require
verification test evidence linked to the relevant Design Output and
QA Lead review before production promotion.

**CAPA.** Failed service events and recurring deviations trigger formal
Corrective and Preventive Action under SOP-11. CAPA assessment begins
within 2 business days of a failed service event.

**Supplier and software component controls.** All third-party software
components are listed in the Software Bill of Materials (SBOM) maintained
in Aikido. Critical and High CVE findings are remediated to the timescales
in Section 8 of this plan and DC-SMP-001.

**Staff competence.** Anyone doing service work must have current training
records for their assigned SOPs and role. Training records are held in the
QMS under SOP-17.

### 9.2 How quality is monitored in practice

Quality monitoring operates at three time horizons.

**Continuous (automated, real-time).** Azure Monitor and Application
Insights watch service health, error rates, and latency. Azure Log Analytics
covers security and operational logs. Audit trail monitoring covers user
access, AI outputs, clinician decisions, and write-back events. Aikido
monitors the SBOM for new CVEs against every production build. Alerts route
to the on-call engineer and are reviewed at each stand-up.

**Per release (manual, each deployment).** The Release Engineer completes
post-deployment smoke checks and reviews monitoring dashboards immediately
after every production deployment. The QA Lead reviews and closes each
Service Record within 5 business days. Failed or conditional service events
trigger CAPA assessment.

**Periodic (scheduled reviews).** Post-Market Surveillance review under
SOP-30 aggregates service metrics monthly and per PMS review cycle. The
PMS report covers failed service events, SLA breaches, patch timeliness,
rollback events, customer-impacting incidents, complaints, service-related
CAPA, and AI output quality indicators. A Disaster Recovery exercise is
carried out at least annually. Backup verification is carried out monthly.

**Quality indicators reported to governance.** The following metrics are
reported in each PMS review:

| Metric | Target | Escalation trigger |
| ------ | ------ | ------------------ |
| Monthly availability | 99.5% SLA / 99.9% SLO | Any SLA breach |
| P1 response time | 30 minutes or less | Breach of SLA response target |
| Failed service events | Zero in reporting period | Any failed event |
| Critical CVE patching | Within 7 calendar days | Any overdue Critical CVE |
| CAPA on-time completion | 100% within agreed target | Any overdue CAPA |
| Class B changes without VT evidence | Zero | Any gap found in Atlas trace |

---

## 10. Customer communication

### 10.1 Communication by event

Customer communications are managed under SOP-12 and recorded in the Service
Record.

| Event | Minimum notice | Channel |
| ----- | -------------- | ------- |
| Planned maintenance with more than 5 minutes downtime | 7 calendar days | Status page and direct email to customer IT Lead and Clinical Safety Lead |
| Planned minor update with no expected downtime | 3 business days | Status page or agreed customer channel |
| Major release | 4 weeks | Release notes and direct customer communication |
| Emergency security or safety patch | As soon as practical. No later than 24 hours after deployment. | Direct email and status page where customer impact exists |
| P1 incident | Initial customer update within 30 minutes of incident declaration | Status page and direct customer communication |
| Root Cause Analysis (RCA) for P1 incident | Within 5 business days of resolution | Direct customer communication |

If customer notification is not required, record the reason in the Service
Record deviations or notification-justification field.

Log complaints from service events under SOP-13. Escalate clinical near
misses, incidents, or reportable events under SOP-14.

### 10.2 Communication by stakeholder level at the Approved Organisation

Different roles at the Approved Organisation need different information at
different frequencies. The Customer Success Manager is responsible for
routing communications to the right contacts. Contact names and notice routes
are confirmed and recorded in the Installation Record.

**Executive and Information Governance level**

Includes: Caldicott Guardian, Senior Information Risk Owner (SIRO),
Chief Clinical Information Officer (CCIO), Chief Information Officer (CIO),
and equivalent board-level data, digital, or clinical leads.

| When | What | How |
| ---- | ---- | --- |
| At go-live | Confirmation that LEO CDS is in service: version, clinical configuration scope, and DCB0129 and DCB0160 responsibilities confirmed | Formal letter or email from the Customer Success Manager, with a copy of the Installation Record summary |
| Annually (or at each major release) | Service performance summary: availability, incidents, CAPA status, PMS highlights, and any safety-relevant changes | Written summary report from the Customer Success Manager, shared via agreed channel |
| Any P1 incident with patient safety implications | Notification of the incident, impact on patient workflow, and actions taken | Direct email from the Customer Success Manager within 2 hours of incident declaration |
| Any reportable safety event | Notification under DCB0129 and DCB0160 obligations | Clinical Safety Officer to Customer Clinical Safety Officer, within timescales required by the standard |

**Clinical Safety and Governance level**

Includes: Customer Clinical Safety Officer (DCB0160 owner), Clinical Lead or
Clinical Champion, Information Governance Lead.

| When | What | How |
| ---- | ---- | --- |
| Every Class B release affecting pathway logic, guideline matching, urgency flags, or write-back | Release notes covering clinical behaviour changes, safety assessment summary, and verification evidence summary | Email from the Customer Success Manager, with release notes attached or linked, at least 2 weeks before deployment |
| Emergency safety patch | Summary of the safety risk, the fix applied, and any required clinical action | Direct email from the Customer Success Manager, no later than 24 hours after deployment |
| P1 incident | Real-time updates during the incident and a Root Cause Analysis report within 5 business days of resolution | Status page updates and direct email from the Customer Success Manager |
| Planned downtime or maintenance | Notice of the window, expected impact on clinical workflow, and contact for urgent queries | Email from the Customer Success Manager, at least 7 calendar days in advance |
| Any LEO CSO clinical safety advisory | Advisory content, affected workflow, and required response | Direct email from the Mizaic Clinical Safety Officer to the Customer Clinical Safety Officer, within the advisory response window (target: 24 hours for safety-class; 1 hour for critical-class) |
| Annual review | Service performance, AI output quality indicators, and any changes to intended use or pathway scope | Meeting or written summary, arranged by the Customer Success Manager |

**Operational and IT level**

Includes: IT Lead, Integration Lead, Service Manager, Operations Lead.

| When | What | How |
| ---- | ---- | --- |
| Every planned maintenance window or scheduled update | Maintenance window dates and times, expected impact, contact for issues | Email from the Customer Success Manager or status page, at least 3 business days before a minor update or 7 calendar days before maintenance with downtime |
| Every production deployment | Confirmation of deployment completion, version deployed, and any known issues | Email or status page update from the Customer Success Manager |
| Security patch | Summary of the CVE addressed, patch applied, and any required local action (for example, IP allowlist or integration change) | Email from the Customer Success Manager or Security Engineering, within 24 hours of deployment for emergency patches |
| P1 incident | Real-time incident updates and technical summary of the resolution | Status page and direct communication from the Customer Success Manager |
| Integration or source-system change | Technical change summary and any required action on the customer side | Email from the Customer Success Manager or Release Engineer, at agreed notice period |

**End-user (clinical staff) level**

Includes: Clinicians, Referral Coordinators, and other users of LEO CDS.

| When | What | How |
| ---- | ---- | --- |
| At go-live | Instructions for use, training on how to review and confirm AI outputs, and how to report issues | IFU-LEO-CDS-001 issued by the Customer Success Manager, training delivered by the Approved Organisation's Clinical Lead or IT Lead |
| Any change to the clinical user interface or workflow | Plain-English summary of what has changed and what users need to do differently | Release notes in plain English shared by the Approved Organisation's Clinical Lead, timed to land before the change goes live |
| Planned downtime during clinical hours | Notice of the window and alternative workflow for the period | Circulated by the Approved Organisation's IT Lead or Service Manager, using internal communication channels |
| New IFU version | Updated instructions and any changes to how AI proposals should be reviewed | Mizaic issues the new IFU to the Customer Success Manager; the Approved Organisation distributes it and records acknowledgement |

---

## 11. Monitoring, SLA, and SLO

### 11.1 External service targets

| Metric | Managed multi-tenant SaaS target |
| ------ | -------------------------------- |
| Monthly availability SLA | 99.5%, excluding agreed planned maintenance |
| Monthly availability SLO | 99.9%, excluding agreed planned maintenance |
| P1 response - clinical workflow unavailable | 30 minutes or less |
| P2 response - significant feature unavailable | 4 business hours or less |
| P3 response - non-critical issue | 2 business days or less |
| Recovery Time Objective (RTO) | Less than 4 hours |
| Recovery Point Objective (RPO) | Less than 1 hour |

Customer contracts may set stricter targets. Contractual targets take
precedence for that customer and must be recorded in the Installation Record.

### 11.2 Internal service objectives

| Objective | Target |
| --------- | ------ |
| P1 restoration target | 4 hours or less |
| Monthly availability operating target | 99.9% |
| Monthly request error budget | 0.5% of requests or less in error state |
| Failed service event CAPA assessment | Within 2 business days |
| Backup verification | Monthly |
| Disaster recovery (DR) exercise | At least annually |
| Service record closure review | Within 5 business days of service event completion |

### 11.3 Monitoring sources

Operational monitoring includes:

- Azure Monitor and Application Insights for service health.
- Azure Log Analytics for security and operational logs.
- Application health endpoints and smoke checks.
- Audit trail monitoring for user access, AI outputs, clinician decisions,
  and write-back events.
- Dependency and CVE monitoring through Aikido SBOM and vulnerability findings.
- Customer support and complaint trends.

Service metrics feed Post-Market Surveillance (PMS) review under SOP-30,
including:

- Failed service events.
- SLA breaches.
- Patch timeliness.
- Rollback events.
- Customer-impacting incidents.
- Complaints and service-related CAPA.
- Update adoption and tenant exposure where multiple deployment groups exist.

---

## 12. Rollback and disaster recovery

### 12.1 Rollback triggers

Consider rollback immediately if a deployment causes:

- A P1 or P2 service outage.
- Failure of patient data separation, authentication, authorisation, or audit
  integrity.
- Incorrect pathway, guideline, urgency, or write-back behaviour with
  potential clinical safety impact.
- A large rise in error rates or failed clinical workflow completion.
- A release-blocking defect accepted by the customer.

### 12.2 Rollback procedure

1. Declare the rollback decision in the incident channel.
2. Confirm rollback scope, affected tenants, and data considerations.
3. Revert to the previous approved container image, configuration version, or
   database snapshot as appropriate.
4. Disable affected write-back or clinical workflow functions if needed while
   rollback completes.
5. Run post-rollback smoke and data-integrity checks.
6. Update the Service Record with outcome, rollback details, deviations, and
   change-control reference.
7. Notify affected customers under Section 10.
8. Open CAPA assessment within 2 business days for failed service events.

### 12.3 Disaster recovery

| Target | Managed SaaS |
| ------ | ------------ |
| RTO | Less than 4 hours for P1 service restoration |
| RPO | Less than 1 hour |
| DR test frequency | At least annually |
| DR evidence | Service Record with service_type = DR-test |

Record DR test failures as deviations and assess them for CAPA.

---

## 13. Tenant onboarding and offboarding

### 13.1 Onboarding

Customer onboarding follows LEO-OP-001, Customer Pathway Onboarding Procedure.
Use SOP-100 where e-RS integration applies. LEO-OP-001 covers pathway
configuration, clinical governance review, integration testing, and go-live.

The onboarding workflow has five required phases:

| Phase | Required evidence |
| ----- | ----------------- |
| Platform readiness | Platform installed and working. Terminology synced. Required guidelines and config seeds available. Admin access confirmed. |
| Clinical knowledge configuration | Approved surface forms (LEO-UM-SF-001). Guideline rules loaded, reviewed, tested, compiled, and published (LEO-UM-CG-001). |
| Minimum dataset configuration | Domains, subdomains, completeness criteria, preview evidence, clinical reviewer sign-off, and approver sign-off (LEO-UM-DO-001 and DC-GOV-001). |
| Integration and go-live | Source-system access. e-RS onboarding where needed. Smoke test evidence. Production queue configuration. Customer go-live approval. |
| Post-activation monitoring | Early-life monitoring evidence. Issue review. Failed-message checks. Closure approval. |

No customer pathway or minimum dataset may go live in production until
Clinical Reviewer and Approver sign-off are recorded on the change record.
Where possible, keep roles independent. The person who drafts the schema must
not be the only clinical reviewer.

For customers using NHS e-RS, complete LEO-UM-ERS-001. Evidence must
include:

- Customer ODS code.
- NHS Initial Connection Approval status.
- Application-restricted app registration.
- Healthcare-worker CIS2 app registration.
- Callback URL confirmation.
- Key Vault secret name.
- Evidence that NHS England approved the API connections.

The Installation Record may not be closed until:

- Customer identity, ODS code, contacts, and notice routes are confirmed.
- Clinical and information-governance contacts are recorded.
- DPA, DPIA, DTAC, DCB0129, and DCB0160 responsibilities are confirmed.
- IFU-LEO-CDS-001 has been issued and training requirements communicated.
- LEO-OP-001 phase evidence is complete, or deviations are justified.
- Surface-form, guideline, and minimum-dataset evidence is linked to the
  change record.
- e-RS onboarding evidence is linked where e-RS is in scope.
- Production configuration and integration checks are complete.
- Initial authorised users and roles are approved.
- IQ/OQ evidence is linked.
- Customer acceptance is recorded.

### 13.2 Offboarding

Offboarding requires a Service Record with service_type = decommission.

The Customer Success Manager and Release Engineer must:

1. Confirm termination, expiry, or migration instruction.
2. Disable customer access at the agreed time.
3. Stop or remove source-system integrations.
4. Export or return data where instructed by the Controller.
5. Delete data where instructed and allowed by the retention schedule.
6. Record data erasure or return evidence in the Service Record.
7. Archive the customer or tenant record.
8. Include final service metrics in PMS review where applicable.

---

## 14. Records and retention

| Record | Owner | Created when | Retention |
| ------ | ----- | ------------ | --------- |
| InstallationRecord | Release Engineer / Customer Success Manager | Customer environment placed into service | Product lifetime plus 15 years, unless contract or law requires longer |
| ServiceRecord | Release Engineer | Any in-service update, patch, repair, rollback, configuration change, DR test, or decommissioning | Product lifetime plus 15 years, unless contract or law requires longer |
| Aikido SBOM and vulnerability evidence | Release Engineer / Security Engineering | Every production build and security review | Linked from InstallationRecord or ServiceRecord |
| Customer notification evidence | Customer Success Manager | Planned or unplanned customer-impacting service event | Linked from ServiceRecord |
| CAPA reference | QA Lead | Failed service event or recurring deviation | Per SOP-11 and SOP-5 |
| PMS service metrics | QA Lead / Product Safety Review | Monthly and per PMS review cycle | Per SOP-30 and SOP-5 |

Records are append-only. Add corrections as new notes or linked records. Do
not delete or overwrite the original service record.

---

## 15. Open actions before release approval

| ID | Action | Owner | Target |
| -- | ------ | ----- | ------ |
| SVP-001 | Confirm named approvers for VP Engineering, QA Lead, CSO, Security Engineering, and Customer Success | VP Engineering | Before first approved issue |
| SVP-002 | Confirm the authoritative Atlas QMS record schema for InstallationRecord and ServiceRecord | QA Lead | Before first customer go-live |
| SVP-003 | Align security patch SLAs across DC-SMP-001, DC-DPA-002, SOP-38, and this plan | Security Engineering / QA Lead | Before first approved issue |
| SVP-004 | Confirm customer notification channels and status-page ownership | Customer Success Manager | Before first customer go-live |
| SVP-005 | Confirm DR exercise evidence format and annual test schedule | VP Engineering | Before first production release |
| SVP-006 | Add Edge deployment appendix if a customer-hosted deployment is contracted | VP Engineering | Before any Edge go-live |

---

## 16. Approval

| Role | Name | Date | Approval |
| ---- | ---- | ---- | -------- |
| VP of Engineering |  |  |  |
| Quality Assurance Lead |  |  |  |
| Clinical Safety Officer |  |  |  |
| Security Engineering |  |  |  |
| Customer Success Manager |  |  |  |

---

## 17. Revision history

| Version | Date | Author | Summary |
| ------- | ---- | ------ | ------- |
| 0.1.0-draft | 2026-06-08 | Engineering | Initial LEO CDS service plan aligned to SOP-83. |
| 0.2.0-draft | 2026-06-08 | Engineering | Plain English rewrite. Added glossary. Spelled out acronyms on first use. |
| 0.3.0-draft | 2026-06-19 | Engineering | Added Section 9 (quality standards achievement and monitoring). Added Section 10.2 (stakeholder communication by level at the Approved Organisation). Renumbered Sections 10-16 to 11-17. |
