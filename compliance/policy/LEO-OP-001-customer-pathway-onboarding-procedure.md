<!-- LEO-OP-001 -->
# LEO by Mizaic
## Customer Pathway Onboarding Procedure
### End-to-End Configuration, Clinical Governance, and Go-Live

| Field | Value |
|---|---|
| Document Reference | LEO-OP-001 |
| Implements | DC-GOV-001 |
| Version | 2.0 |
| Date | June 2026 |
| Status | Draft |
| Classification | QMS -- Clinical Safety / Configuration Governance |
| Atlas VT | VT-3685C1C5 |
| Playwright VAL | VAL-C73DD43E (see services/ui/e2e/val-leo-op-001-customer-pathway-onboarding.spec.ts) |
| Replaces | LEO-OP-001 v1.0 (May 2026) |

---

## 1. Purpose

This procedure defines the end-to-end process for onboarding a new customer
pathway onto the LEO Clinical Decision Support platform. It brings together
five activities -- platform readiness confirmation, clinical knowledge
configuration, minimum dataset setup, integration testing, and go-live -- into
a single governed workflow with clear handoffs, mandatory review gates, and
audit requirements.

The procedure is designed to be followed in sequence. Each phase produces
outputs that are prerequisites for the next. Skipping or reordering phases
risks incomplete configuration that may affect clinical safety.

Version 2.0 reflects the redesigned Knowledge hub introduced in the Wave E
release: a left sidebar, command palette (Cmd+K), and step-card layouts replace
the previous horizontal tab bar.

---

## 2. Scope

This procedure applies to the onboarding of any new customer pathway that will
use LEO's referral assessment pipeline, including completeness checking,
clinical coding, guideline compliance, and SBAR generation.

It covers configuration and clinical governance steps performed after platform
infrastructure is installed and operational. It does not cover infrastructure
provisioning (see LEO-IM-001 Installation Manual) or NHS e-RS per-customer
integration (see LEO-UM-ERS-001).

---

## 3. Related documents

| Reference | Title | Scope |
|---|---|---|
| LEO-IM-001 | Installation Manual: CDS Referral Assessment | Platform infrastructure |
| LEO-UM-SF-001 | User Manual: Surface Forms | Clinical terminology mappings |
| LEO-UM-CG-001 | User Manual: Clinical Guidelines (v2.0) | Guideline loading, rule review, compile |
| LEO-UM-DO-001 | User Manual: Domains | Completeness criteria configuration |
| DC-GOV-001 | Service Minimum Dataset Onboarding and Governance Procedure | Clinical governance, review gates, audit |
| DC-DEP-001 | Deployment Configuration | Infrastructure and secrets specification |
| LEO-UM-ERS-001 | NHS e-Referral Service Onboarding | Per-customer e-RS integration (when in scope) |

---

## 4. Roles and responsibilities

| Role | Responsibilities |
|---|---|
| Requester | Customer clinical lead or programme manager. Describes the pathway, proposes required information groups, supplies sample referrals, confirms clinical intent. |
| Platform Administrator | IT Admin. Creates domains and subdomains, drafts schema, configures surface forms and guidelines, runs preview and test evidence, executes configuration. |
| Clinical Reviewer | Pathway SME, CSO delegate, or designated clinician. Reviews proposed minimum dataset groups for clinical appropriateness; confirms required groups match pathway standards. |
| Approver | Quality Manager or Clinical Safety Officer. Approves activation after review and test evidence are complete. |
| Release Coordinator | Platform operations. Confirms production queue messages use approved domain/subdomain values; coordinates go-live timing with the customer. |

No minimum dataset may be activated in production until Clinical Reviewer and
Approver sign-off are recorded on the change record (DC-GOV-001 section 7).

A single person may hold multiple roles provided there is no conflict of
interest. The person who drafts the schema must not be the sole clinical
reviewer.

---

## 5. Onboarding workflow overview

The onboarding workflow has five sequential phases:

| # | Phase | Primary owner | Reference documents |
|---|---|---|---|
| 1 | Platform readiness | Platform Administrator | LEO-IM-001 |
| 2 | Clinical knowledge configuration | Platform Administrator | LEO-UM-SF-001, LEO-UM-CG-001 |
| 3 | Minimum dataset configuration | Platform Administrator + Clinical Reviewer | LEO-UM-DO-001, DC-GOV-001 |
| 4 | Integration and go-live | Release Coordinator | LEO-UM-ERS-001 (if e-RS), DC-DEP-001 |
| 5 | Post-activation monitoring | Platform Administrator + Approver | SVP-LEO-CDS-001 section 13 |

### Navigating the Knowledge hub

All configuration in phases 2 and 3 is performed in the Knowledge hub at
`/admin/knowledge`.

The left sidebar groups tabs into four sections:

- **NLP and AI** -- Training Data, Surface Forms, Context Rules, AI Instructions, AI Summarisation
- **Clinical Knowledge** -- Domains, Clinical Guidelines, Pathways
- **Data Setup** -- Terminology, Results/Labs, Extraction Scenarios
- **Quality** -- Test Patients, Coding Validation

Press **Cmd+K** (Mac) or **Ctrl+K** (Windows) to open the command palette and
jump directly to any tab or search loaded guidelines and prompts.

---

## 6. Phase 1: Platform readiness

Before any customer-specific configuration begins, the Platform Administrator
must confirm that the LEO platform is installed and operational. This phase is
typically completed once per environment.

### 6.1 Prerequisites

1. Infrastructure provisioned and all services running (LEO-IM-001 Tracks 1-7).
2. SNOMED CT terminology synchronised via TRUD (LEO-IM-001 Track 8, Step 3).
3. Plan definitions and prompt configs seeded (LEO-IM-001 Track 8, Steps 1-2).
4. Admin UI accessible and authenticated user has platform administrator role.

### 6.2 Readiness confirmation in the UI

1. Open **Knowledge** from the main navigation.
2. Select **Terminology** in the Data Setup section of the sidebar.
3. Confirm terminology packages show as loaded (StatHero tiles and package cards).
4. Select **Clinical Guidelines** and confirm the summary header (StatHero)
   shows guideline and rule counts without error banners.
5. Record readiness confirmation on the customer's change record.

If terminology packages are missing or the guidelines page shows persistent
errors, resolve using LEO-IM-001 before continuing.

---

## 7. Phase 2: Clinical knowledge configuration

This phase configures the clinical knowledge base to support the customer's
pathway. Both surface forms and guideline rules are prerequisites for accurate
completeness checking and clinical decision support.

### 7.1 Surface forms: local terminology mappings

1. Open **Knowledge > Surface Forms** (NLP and AI section).
2. Search for key terms the pathway uses. Check whether approved aliases exist.
3. Add missing aliases for local terms, abbreviations, and synonyms. New aliases
   enter a pending state.
4. Review and approve pending aliases. Only approved aliases are used during
   clinical fact extraction.
5. Use the duplicate audit function to check for conflicting mappings.

See LEO-UM-SF-001 for detailed steps.

### 7.2 Clinical guidelines: loading and rule compilation

1. Open **Knowledge > Clinical Guidelines** (Clinical Knowledge section).
2. Confirm the StatHero header shows guideline and rule counts.
3. Use the sticky jump strip to navigate: **1. Load**, **Inspect**, **2. Review**, **3. Compile**.
4. If the required NICE guideline is not loaded:
   - Click **Refresh guideline list** in the Load card.
   - Search by NICE code (for example NG12) and click **Load this guideline**.
5. In the Inspect card, click **Generate rules** for the loaded guideline.
6. Jump to **2. Review**. Approve, edit, or reject each AI-generated rule.
7. Jump to **3. Compile**. Click **Compile rules**, then **Make this live**.

Rule compilation is mandatory. An uncompiled bitmap means empty Assessment in
every SBAR for this pathway. Both rule approval and compilation are required.

See LEO-UM-CG-001 v2.0 for detailed steps and screenshots.

---

## 8. Phase 3: Minimum dataset configuration

This phase defines what clinical information must be present in a patient
record for a referral to be assessed as complete. It follows DC-GOV-001 and
uses the Domains feature in the Knowledge hub.

This phase contains mandatory clinical review and approval gates. No minimum
dataset may be activated without Clinical Reviewer and Approver sign-off.

### 8.1 Request and planning

1. Requester opens a configuration request describing the customer, pathway,
   intended `completeness_domain` and `completeness_subdomain` values, clinical
   source for required information, and sample anonymised referrals.
2. Platform Administrator confirms Phase 1 and Phase 2 are complete.

### 8.2 Create domain and subdomain

1. Open **Knowledge > Domains** (Clinical Knowledge section).
2. Confirm the StatHero shows area counts (From NICE, Built-in, Your organisation).
3. Click **Create area** to add a new domain (for example "Cancer referrals"), or
   open an existing domain card.
4. On the domain detail page, click **Add subdomain** (PageHero CTA or subdomain
   list toolbar).
5. Enter the subdomain name (for example `lower_gi`) and description.
6. Do not activate completeness criteria yet -- the schema must pass clinical
   review first.

See LEO-UM-DO-001 for detailed steps.

### 8.3 Draft completeness schema

1. On the domain detail page, click the **Configure** (settings cog) button on
   the subdomain row. A sticky detail panel opens on the right.
2. Use the **Overview** tab to set milestone type (for example referral), time
   window, semantic tags, and assertion filters. Click **Save overview**.
3. Use the **Concepts** tab to search for and add SNOMED concepts to the
   subdomain.
4. Use the **Rules** tab to review completeness criteria groups. Each group
   shows name, required flag, SNOMED concepts, and semantic categories.
5. Draft schema groups via the Analytics API or admin tooling (see DC-GOV-001
   section 5.2). Preview using
   `POST /analytics/domains/{id}/subdomains/{name}/schema/preview`.

### 8.4 Clinical review (mandatory)

1. Platform Administrator sends the draft schema and clinical rationale to the
   Clinical Reviewer.
2. Clinical Reviewer checks each required group reflects clinically necessary
   information for triage.
3. Clinical Reviewer records **Approved**, **Approved with conditions**, or
   **Rejected** on the change record.
4. If rejected, return to section 8.3. Do not proceed.

### 8.5 Preview and test evidence (mandatory)

1. Run schema preview against sample patient facts (API or admin UI).
2. Save preview output showing present and missing groups.
3. Run at least one of:
   - AI Summarisation scenario batch with the target domain/subdomain
   - Sample referral batch through the referral assessment pipeline
   - Documented review of widget completeness panel on representative cases
4. Record test evidence on the change record.

### 8.6 Approval and activation

1. Approver reviews Clinical Reviewer sign-off, preview output, and test evidence.
2. Approver records approval on the change record.
3. Platform Administrator activates schema via
   `PUT /analytics/domains/{domain_id}/subdomains/{name}/schema`.
4. Confirm `completeness_schema_active` is true and audit entry
   `save_completeness_schema` was written (DC-GOV-001 section 9).
5. Release Coordinator confirms production `referral-received` messages carry
   the approved `completeness_domain` and `completeness_subdomain`.

---

## 9. Phase 4: Integration and go-live

This phase confirms the configured pathway works end-to-end before production
traffic is enabled.

### 9.1 Integration smoke test

1. Open **Knowledge > AI Summarisation** (NLP and AI section).
2. Select the **Scenario runs** tab.
3. Run a scenario batch using the target domain and subdomain configured in
   Phase 3.
4. Confirm completeness findings appear in the run results.
5. If e-RS is in scope, complete LEO-UM-ERS-001 per-customer onboarding.

### 9.2 Production queue configuration

1. Release Coordinator confirms production `referral-received` messages include:
   - `completeness_domain` matching the approved domain
   - `completeness_subdomain` matching the approved subdomain
2. Confirm widget embedding and host governance onboarding are complete (see
   docs/REFERRAL-PIPELINE-INTEGRATION.md).

### 9.3 Go-live approval

1. Approver confirms Phases 1-3 evidence is complete on the change record.
2. Customer clinical lead confirms go-live date.
3. Release Coordinator enables production traffic for the pathway.

---

## 10. Phase 5: Post-activation monitoring

For the first 30 days after go-live, monitor:

- Completeness panel results on live referrals
- Support tickets about missing or incorrect completeness flags
- Clinical safety escalations linked to completeness or guideline configuration
- Failed message counts in the operations queue

Escalate to the Clinical Safety Officer if a schema or guideline configuration
may have affected live clinical review.

Record monitoring outcomes on the change record and obtain Approver closure
sign-off before marking the onboarding complete.

---

## 11. Production release checklist

Use this checklist before enabling production referral traffic:

- [ ] Change record opened and linked to customer/pathway
- [ ] Phase 1: Terminology loaded; Knowledge hub accessible
- [ ] Phase 2: Surface forms approved for pathway terms
- [ ] Phase 2: Guideline loaded, rules approved, compiled, and live
- [ ] Phase 3: Domain and subdomain created
- [ ] Phase 3: Completeness schema drafted with at least one required group
- [ ] Phase 3: Clinical Reviewer sign-off recorded
- [ ] Phase 3: Preview evidence captured and attached
- [ ] Phase 3: Test evidence captured and attached
- [ ] Phase 3: Approver sign-off recorded
- [ ] Phase 3: Schema activated; `save_completeness_schema` audit entry verified
- [ ] Phase 4: Scenario run smoke test passed
- [ ] Phase 4: Production queue messages use approved domain/subdomain names
- [ ] Phase 4: e-RS onboarding complete (if in scope)
- [ ] Phase 5: Post-activation monitoring plan agreed

---

## 12. Revision history

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-05 | Platform team | Initial procedure |
| 2.0 | 2026-06 | Platform team | Updated for Knowledge hub sidebar, command palette, StatHero headers, step-card Clinical Guidelines layout, and domain split-panel UI |

---

*This document is a procedural control for customer pathway onboarding. Review
when Knowledge hub workflows, completeness configuration UI, or clinical safety
policy changes.*
