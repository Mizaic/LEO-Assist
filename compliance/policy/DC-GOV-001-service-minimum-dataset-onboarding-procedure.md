# Service Minimum Dataset Onboarding and Governance Procedure

| Field           | Value                                                  |
| --------------- | ------------------------------------------------------ |
| Document ID     | DC-GOV-001                                             |
| Version         | 1.0.0                                                  |
| Status          | Draft                                                  |
| Date            | 2026-05-22                                             |
| Classification  | QMS -- Clinical Safety / Configuration Governance      |
| Implements      | DI-44D0E115                                            |
| Mitigates       | R-A3BD3AC7                                             |
| Related UNs     | UN-3B25A20E, UN-AF530E8E                               |

---

## 1  Purpose

This procedure defines how healthcare service minimum datasets (completeness
schemas) are requested, clinically reviewed, approved, configured, tested,
activated, changed, and audited before they are used in production referral
assessment workflows.

Incorrect or unreviewed minimum datasets may cause the completeness checker
to miss clinically required referral information. This procedure is a
procedural control that reduces that risk.

---

## 2  Scope

This procedure applies to:

- New customer or pathway minimum datasets added to LEO Clinical Decision
  Support.
- Changes to existing minimum datasets after go-live.
- All environments where production referral assessment uses completeness
  checking (`completeness_domain` and `completeness_subdomain` on
  `referral-received` messages).

This procedure does **not** cover:

- Platform installation (infrastructure, terminology sync, guideline ingest).
  See `compliance/policy/DC-DEP-001-deployment-configuration.md`.
- Host system integration (pub/sub message contract and widget embedding).
  See customer technical onboarding materials.

---

## 3  Definitions

| Term | Meaning |
| ---- | ------- |
| Minimum dataset | The completeness schema for a healthcare service subdomain: required SNOMED concept groups used by the completeness checker. |
| Domain | A clinical programme container (e.g. `cancer_referrals`) stored as an `AuditDomain` node. |
| Subdomain | A pathway slice within a domain (e.g. `lower_gi`), stored as a linked `ValueSet` (`ncda-{name-with-hyphens}`). |
| Schema activation | Saving a completeness schema with `completeness_schema_active = true` via the Analytics API or admin UI. |
| Preview evidence | Output from `POST /analytics/domains/{id}/subdomains/{name}/schema/preview` showing matched and missing groups against sample patient facts. |
| Test evidence | Recorded results from AI summarisation scenario runs, sample referral batches, or documented clinical review of widget completeness output. |

---

## 4  Roles and responsibilities

| Role | Responsibilities |
| ---- | ---------------- |
| **Requester** (customer clinical lead or programme manager) | Describes the pathway, proposes required information groups, supplies sample referrals, confirms clinical intent. |
| **Platform Administrator** (IT Admin) | Creates or updates domains and subdomains, drafts schema JSON, runs preview, executes configuration in admin UI or Analytics API, retains audit evidence. |
| **Clinical Reviewer** (pathway SME, CSO delegate, or designated clinician) | Reviews proposed minimum dataset groups for clinical appropriateness; confirms required groups match pathway standards; rejects or requests changes before activation. |
| **Approver** (Quality Manager or Clinical Safety Officer) | Approves activation or release of a minimum dataset to production after review and test evidence are complete. |
| **Release Coordinator** (platform operations) | Confirms production queue messages use the approved `completeness_domain` and `completeness_subdomain`; coordinates go-live timing with the customer. |

No minimum dataset may be activated in production until **Clinical Reviewer**
and **Approver** sign-off are recorded on the change record.

---

## 5  New minimum dataset onboarding

Use this workflow when a new healthcare service subdomain needs a minimum
dataset for the first time.

### 5.1  Request and planning

1. Requester opens a configuration request (change record or approved
   ticket) describing:
   - Customer and pathway name
   - Intended `completeness_domain` and `completeness_subdomain` values
   - Clinical source for required information (pathway standard, NICE
     guidance, local policy)
   - Sample anonymised referrals for preview and testing
2. Platform Administrator confirms platform prerequisites are met:
   - SNOMED terminology loaded
   - Relevant guideline rules compiled (if assessment uses compliance)
   - Analytics API and admin UI accessible

### 5.2  Configure domain and subdomain (draft)

1. Create domain if needed: `POST /analytics/domains`
2. Create subdomain: `POST /analytics/domains/{domain_id}/subdomains`
3. Draft completeness schema groups. Each group MUST include:
   - `name` (plain English label)
   - `required` (boolean)
   - `semantic_categories` (e.g. `finding`, `disorder`, `observable_entity`)
   - and/or `concept_ids` (explicit SNOMED concept IDs)
4. Do **not** activate for production traffic yet.

Admin UI path: **Settings > Domains** (`/settings/domains`).

### 5.3  Clinical review (mandatory before activation)

1. Platform Administrator sends the draft schema and clinical rationale to
   the Clinical Reviewer.
2. Clinical Reviewer checks:
   - Each required group reflects clinically necessary information for triage
   - Groups are neither too broad (false completeness) nor too narrow
     (missed clinically required items)
   - Required flags match pathway policy
3. Clinical Reviewer records **Approved**, **Approved with conditions**, or
   **Rejected** on the change record.
4. If rejected or conditional, return to step 5.2. Do not proceed.

### 5.4  Preview and test evidence (mandatory before activation)

1. Run schema preview against sample patient facts:
   `POST /analytics/domains/{id}/subdomains/{name}/schema/preview`
2. Save preview output showing present and missing groups.
3. Run at least one of:
   - AI summarisation scenario batch with the target domain/subdomain
   - Sample referral batch through the referral assessment pipeline
   - Documented review of widget completeness panel on representative cases
4. Record test evidence on the change record (pass/fail per case, reviewer
   notes, assessment IDs or run IDs).
5. If preview or test results show systematic gaps, revise schema or surface
   forms before proceeding.

### 5.5  Approval and activation

1. Approver reviews:
   - Clinical Reviewer sign-off
   - Preview output
   - Test evidence
2. Approver records approval on the change record.
3. Platform Administrator activates schema:
   `PUT /analytics/domains/{domain_id}/subdomains/{name}/schema`
4. Confirm `completeness_schema_active` is true and audit entry
   `save_completeness_schema` was written.
5. Release Coordinator confirms production `referral-received` messages carry
   the approved `completeness_domain` and `completeness_subdomain`.

### 5.6  Post-activation monitoring

For the first 30 days after activation, monitor:

- Completeness panel results on live referrals
- Support tickets about missing or incorrect completeness flags
- Clinical safety escalations linked to completeness configuration

Escalate to the Clinical Safety Officer if a schema may have affected live
clinical review.

---

## 6  Change management for existing minimum datasets

Use this workflow when a customer requests a change to an active minimum
dataset.

### 6.1  Change request

1. Requester documents the change, clinical reason, and urgency.
2. Platform Administrator classifies change:
   - **Minor** (wording, non-clinical metadata) -- Clinical Reviewer may waive
     re-review if documented
   - **Clinical** (required flags, concept groups, semantic categories) --
     full review and test required
   - **Emergency** (patient safety concern) -- CSO approval required; follow
     expedited path in Section 6.5

### 6.2  Draft and assess

1. Export current schema: `GET .../schema`
2. Draft revised schema in a non-production environment when possible.
3. Run preview against:
   - Historical sample referrals
   - Cases that triggered the change request
4. Clinical Reviewer assesses clinical impact of the proposed change.

### 6.3  Test and approve

1. Re-run test evidence per Section 5.4 for **Clinical** changes.
2. Approver signs off on the change record.
3. Platform Administrator saves revised schema via PUT (creates audit entry).

### 6.4  Release and documentation

1. Record in the change record:
   - Previous schema version (JSON or hash)
   - New schema version
   - Clinical Reviewer and Approver identities and dates
   - Preview and test evidence references
2. Notify customer that the change is live.
3. Note: existing `:Assessment` nodes are not retroactively updated; only new
   referrals use the revised schema.

### 6.5  Emergency change

If immediate change is required for patient safety:

1. CSO or delegate approves expedited change in writing.
2. Platform Administrator applies change and records audit evidence.
3. Full retrospective clinical review and test evidence MUST be completed
   within 5 working days.

---

## 7  Clinical review requirements

Before any minimum dataset is activated in production:

- A named Clinical Reviewer MUST review the completeness schema.
- The review MUST confirm required groups match the agreed pathway standard.
- The review outcome MUST be recorded on the change record before activation.
- Platform Administrator MUST NOT activate a schema without recorded clinical
  review approval.

---

## 8  Preview and test evidence requirements

Before any minimum dataset is activated in production:

- Preview evidence MUST be captured using the schema preview API or
  equivalent admin UI function.
- Test evidence MUST demonstrate the schema behaves as expected on
  representative referral content.
- Test evidence MUST be linked to the change record before activation.
- Approver MUST verify both preview and test evidence before sign-off.

Acceptable test evidence includes:

| Evidence type | Minimum content |
| ------------- | --------------- |
| Schema preview output | Group names, present/missing status, patient fact sample reference |
| Scenario run | Run ID, child assessment IDs, completeness findings summary |
| Sample referral batch | Case IDs, reviewer notes, pass/fail against expectations |
| Widget review | Screenshots or exported assessment JSON showing completeness panel |

---

## 9  Audit records

The platform records configuration actions automatically in the knowledge
graph as `:DomainConfigAuditLog` nodes.

### 9.1  Automatically audited actions

| Action | Target | When recorded |
| ------ | ------ | ------------- |
| `create_domain` | AuditDomain | Domain created |
| `update_domain` | AuditDomain | Domain updated |
| `delete_domain` | AuditDomain | Domain deleted |
| `create_subdomain` | ValueSet | Subdomain created |
| `update_subdomain` | ValueSet | Subdomain updated |
| `delete_subdomain` | ValueSet | Subdomain deleted |
| `save_completeness_schema` | ValueSet | Schema saved or activated |
| `replace_constructs` | ValueSet | Construct list replaced |

Implementation: `services/analytics_api/app/routers/domains.py`
(`_record_domain_config_audit`).

### 9.2  Audit entry fields

Each entry includes:

- `id` (UUID)
- `action`
- `targetType`
- `targetId`
- `actor` (administrator email from authenticated session)
- `timestamp`
- `newValues` (JSON snapshot of change)

### 9.3  Procedure audit pack

For each onboarding or change release, the Platform Administrator MUST retain:

1. Change record with request, review, approval, and release dates
2. Schema JSON (before and after for changes)
3. Preview output
4. Test evidence
5. Confirmation that `save_completeness_schema` audit entry exists (Cypher
   query or export)

Example Cypher to verify audit entry after activation:

```cypher
MATCH (a:DomainConfigAuditLog {action: 'save_completeness_schema'})
WHERE a.targetId = 'ncda-lower-gi'
RETURN a.action, a.actor, a.timestamp, a.newValues
ORDER BY a.timestamp DESC
LIMIT 5
```

---

## 10  Production release checklist

Use this checklist before enabling production referral traffic for a new or
changed minimum dataset.

- [ ] Change record opened and linked to customer/pathway
- [ ] Domain and subdomain created
- [ ] Completeness schema drafted with at least one required group
- [ ] Clinical Reviewer sign-off recorded
- [ ] Preview evidence captured and attached
- [ ] Test evidence captured and attached
- [ ] Approver sign-off recorded
- [ ] Schema activated (`PUT .../schema`)
- [ ] `save_completeness_schema` audit entry verified
- [ ] Production queue messages use approved domain/subdomain names
- [ ] Post-activation monitoring plan agreed

---

## 11  Revision history

| Version | Date       | Author          | Changes                                      |
| ------- | ---------- | --------------- | -------------------------------------------- |
| 1.0.0   | 2026-05-22 | Platform team   | Initial procedure for DI-44D0E115            |

---

*This document is a procedural control for minimum dataset governance. It
should be reviewed when completeness configuration behaviour, admin UI
workflows, or clinical safety policy changes.*
