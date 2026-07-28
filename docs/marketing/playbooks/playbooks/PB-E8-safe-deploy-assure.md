# PB-E8 -- Safe Deploy Assure

Catalogue reference: Module E8, "Clinical safety and regulatory" --
DCB0160 support, training, go-live gate
(`docs/marketing/build_coo_service_catalogue.py`, `module_menu()`). This
module **is** Package E ("Safe Deploy Assure") -- there is no separate
Package E wrapper file. The pptx's Package E "includes" list (local clinical
safety case support, DPA/contract completion, installation and operational
checks, role-based training via the Validation Lab, go/no-go criteria) maps
directly onto the phases below.

Tier: 1 (full playbook). Audience: internal delivery / solutions
consultants, working with the customer's Clinical Safety Officer and IT
Lead, running a go-live readiness workstream. Not a substitute for the
customer's own DCB0160 safety case, which remains the customer's
responsibility.

## 1. Purpose and buyer outcome

**For the CSO / Digital lead / COO:** by the end of this playbook, the
customer has a signed local clinical safety position, a completed
Installation Record, trained triage and admin roles, and an agreed go/no-go
decision -- so go-live is a planned event, not a critical-path surprise.

**What "done" looks like:**

- Local clinical safety case responsibilities are confirmed between Mizaic
  and the customer.
- DPA, DPIA, DTAC evidence status is agreed and recorded.
- Installation and Operational Qualification checks are complete.
- Named users are trained, using the Validation Lab as a rehearsal space.
- A go/no-go decision is recorded, with rollback and support contacts
  agreed.

## 2. Preconditions and non-negotiable safety gate

- Modules E3 (Integration and embed) and E4 (Pathway and guideline
  factory) are functionally complete for at least the pilot pathway --
  this playbook assures the deployment, it does not build the pathway.
- **DCB0129 is Mizaic's obligation; DCB0160 is the customer's.** Mizaic
  provides supporting evidence (System Risk Assessment, hazard log,
  installation pack) but the customer's Clinical Safety Officer owns their
  own deployment risk management
  (`compliance/policy/DC-DTAC-001-dtac-compliance-statement.md` section 3.2).
  Do not represent this playbook as satisfying the customer's DCB0160
  obligation on its own.
- **All AI outputs remain advisory.** A clinician must confirm every
  proposal before any clinical action or write-back
  (`compliance/policy/SVP-LEO-CDS-001-service-plan.md` section 9.0). No
  go/no-go decision can waive this.

## 3. Roles

| Playbook role | Canonical app role / QMS role | Responsibility here |
|---|---|---|
| Release Engineer (Mizaic) | -- (QMS role) | Runs the deployment, creates the Installation Record, attaches SBOM evidence |
| QA Lead (Mizaic) | -- (QMS role) | Reviews closed Installation and Service Records; starts CAPA when required |
| Clinical Safety Officer (Mizaic) | -- (QMS role) | Reviews clinical-safety-relevant service events; issues advisories |
| Customer Success Manager (Mizaic) | -- (QMS role) | Coordinates customer notice, training scheduling, closure messages |
| Customer Clinical Safety Officer | -- (customer-side) | Owns DCB0160 deployment risk management for the customer organisation |
| Customer IT Lead | -- (customer-side) | Coordinates source-system access, local network readiness, integration availability |
| Trainees (customer staff) | `triage_clinician`, `admin_triage`, `referral_supervisor`, `platform_admin` (as applicable) | Complete role-based training before go-live |

## 4. Step-by-step phases

### Phase 1 -- Local safety case and data protection alignment

**Entry criteria:** contract or Letter of Intent in place for the
engagement.

1. Confirm contract, DPA, and any LEO CDS addendum (currently the Referral
   Assessment addendum,
   [compliance/policy/DC-DPA-002-addendum-b-referral-assessment.md](../../../../compliance/policy/DC-DPA-002-addendum-b-referral-assessment.md))
   are signed or in legal review, and record status.
2. Agree DPIA and DTAC evidence status with the customer. Share the current
   DTAC compliance summary
   ([compliance/policy/DC-DTAC-001-dtac-compliance-statement.md](../../../../compliance/policy/DC-DTAC-001-dtac-compliance-statement.md)
   section 2) and flag any open items (DCB0129 declaration, DSPT
   submission, Cyber Essentials Plus, WCAG audit -- see
   [../GAPS-AND-BLOCKERS.md](../GAPS-AND-BLOCKERS.md)) that are still in
   progress rather than complete.
3. Confirm DCB0129 manufacturer evidence has been provided to the customer,
   and that DCB0160 deployment responsibilities are explicitly confirmed
   with the customer's Clinical Safety Officer
   (`compliance/policy/SVP-LEO-CDS-001-service-plan.md` section 6.1).

**Exit criteria:** contract/DPA/DPIA/DTAC status agreed and recorded on the
Installation Record draft; DCB0129/DCB0160 responsibilities confirmed in
writing.

### Phase 2 -- Installation and configuration checks

**Entry criteria:** Phase 1 status recorded.

1. Confirm production environment settings match
   [compliance/policy/DC-DEP-001-deployment-configuration.md](../../../../compliance/policy/DC-DEP-001-deployment-configuration.md):
   Entra app registration correctly scoped, Cloudflare edge configuration
   checklist complete (section 7.2 of that document), required secrets
   populated in Key Vault, `cookieSecure=true`, no wildcard CORS origins.
2. Run the New Environment Deployment Checklist in
   `compliance/policy/DC-DEP-001-deployment-configuration.md` section 7 in
   full for this customer's environment.
3. Confirm platform install steps from
   [compliance/policy/DC-INST-001-installation-procedure.md](../../../../compliance/policy/DC-INST-001-installation-procedure.md)
   are complete: Neo4j Aura provisioned per environment, Azure OpenAI
   deployed, terminology API keys recorded, Redis and widget CDN deployed
   ahead of the main stack (Tracks A-C).
4. Confirm the pilot go/no-go checklist items are all satisfied --
   [docs/operations/pilot-go-no-go-checklist.md](../../../../docs/operations/pilot-go-no-go-checklist.md).
5. Complete Installation Qualification (IQ) and Operational Qualification
   (OQ) checks and record evidence.

**Exit criteria:** DC-DEP-001 section 7 checklist fully ticked; IQ/OQ
evidence captured.

### Phase 3 -- Clinical configuration and onboarding evidence

**Entry criteria:** Phase 2 complete; Modules E3 and E4 have delivered
evidence for the pilot pathway.

1. Confirm minimum dataset configuration is complete and approved (PB-E4
   Phases 5-8 evidence).
2. Confirm guideline rules are reviewed, tested, compiled, and published
   (PB-E4 Phases 3-4 evidence).
3. Confirm surface-form aliases for the customer pathway are reviewed,
   approved, and duplicate-checked (PB-E4 Phase 2 evidence).
4. Where e-RS is in scope, confirm `LEO-UM-ERS-001` per-customer onboarding
   evidence -- flag as "external QMS / TBD" if that manual is still
   missing (see [../GAPS-AND-BLOCKERS.md](../GAPS-AND-BLOCKERS.md)).
5. Confirm user access model, roles, and initial authorised users are
   approved (`SVP-LEO-CDS-001` section 6.1).

**Exit criteria:** all PB-E4 and PB-E3 evidence bundles referenced and
attached to this customer's Installation Record.

### Phase 4 -- Role-based training using the Validation Lab

**Entry criteria:** Phase 3 complete; named users identified.

1. Use the Validation Lab as a rehearsal space rather than production data.
   The Lab supports synthetic SPoA referral (`ras_referral`) and Advice and
   Guidance (`spo_ag`) scenarios
   ([docs/VALIDATION-LAB.md](../../../../docs/VALIDATION-LAB.md)).
2. For each trainee role, run at least one rehearsal scenario relevant to
   their day-to-day task: triage clinicians and referral supervisors review
   an SBAR end to end; platform administrators rehearse the E4 guideline
   and domain workflows; admin/registration staff rehearse referral intake.
3. Issue the widget IFU
   ([compliance/policy/leo-widget-ifu.md](../../../../compliance/policy/leo-widget-ifu.md))
   to every end user before go-live, and confirm training on how to review
   and confirm AI outputs, and how to report issues
   (`SVP-LEO-CDS-001` section 10.2, End-user level).
4. Record training completion per named user against the Installation
   Record.

**Exit criteria:** every named user in scope has completed at least one
Validation Lab rehearsal for their role, and has acknowledged the relevant
IFU.

### Phase 5 -- Customer acceptance and Installation Record

**Entry criteria:** Phases 1-4 all complete.

1. Assemble the Installation Record with all required fields: product
   version, customer/ODS code, environment, service class, SBOM reference,
   IQ/OQ evidence, clinical configuration references, onboarding evidence,
   customer instructions issue, customer acceptance, placed-into-service
   date, outcome, and deviations
   (`SVP-LEO-CDS-001` section 6.2).
2. Confirm customer identity, ODS code, contacts, and notice routes;
   clinical and information-governance contacts; DPA/DPIA/DTAC/DCB0129/
   DCB0160 responsibilities; and IFU issue and training are all recorded
   before the record is closed (`SVP-LEO-CDS-001` section 13.1).
3. Record customer acceptance (name, role, date, status).
4. Create the Installation Record within 2 business days of go-live.

**Exit criteria:** Installation Record complete and closed, with customer
acceptance recorded.

### Phase 6 -- Go/no-go decision

**Entry criteria:** Phase 5 Installation Record drafted (may be finalised
immediately after go-live, but the go/no-go decision itself precedes
production traffic).

1. Build the go/no-go pack from the evidence bundles in Phases 1-5: safety
   case status, DPA/DPIA/DTAC status, IQ/OQ evidence, clinical
   configuration sign-offs, training completion, and any open deviations.
2. Present the pack to the customer's Clinical Safety Officer and IT Lead,
   and to Mizaic's QA Lead and Clinical Safety Officer, for a joint go/no-go
   decision.
3. Agree rollback and support contacts before go-live: P1 response target
   30 minutes, P2 4 business hours, P3 2 business days
   (`SVP-LEO-CDS-001` section 11.1); rollback triggers and procedure per
   section 12.
4. Record the decision (go / conditional go / no-go) with any conditions on
   the Installation Record.

**Exit criteria:** recorded go/no-go decision with named sign-offs from
both Mizaic and customer clinical safety roles.

### Phase 7 -- Post go-live monitoring handover

**Entry criteria:** go decision recorded and production traffic live.

1. Hand over the monitoring plan for the first 30 days: availability
   (99.5% SLA / 99.9% SLO), P1 response time, failed service events,
   Critical CVE patching, CAPA on-time completion
   (`SVP-LEO-CDS-001` section 9.2 quality indicators table).
2. Confirm the customer knows the communication cadence they will receive
   by stakeholder level (executive, clinical safety, operational/IT,
   end-user -- `SVP-LEO-CDS-001` section 10.2).
3. Schedule the annual (or major-release) service performance summary for
   the customer's executive and clinical safety contacts.

**Exit criteria:** monitoring and communication plan confirmed with the
customer; contacts on file.

## 5. Tools and UI paths

| Task | Reference |
|---|---|
| Deployment checklist | `compliance/policy/DC-DEP-001-deployment-configuration.md` section 7 |
| Installation tracks (A-G) | `compliance/policy/DC-INST-001-installation-procedure.md` |
| Pilot go/no-go checklist | `docs/operations/pilot-go-no-go-checklist.md` |
| Validation Lab rehearsal | `/admin/validation-lab` |
| Monitoring dashboards | Azure Monitor / Application Insights (per `SVP-LEO-CDS-001` section 11.3) |
| Incident runbook | `docs/operations/incident-runbook-pipeline-jobs.md` |

## 6. Evidence to capture

- DTAC compliance summary snapshot and open-item list (Phase 1).
- DC-DEP-001 section 7 checklist, completed and dated (Phase 2).
- IQ/OQ evidence (Phase 2).
- Cross-references to PB-E3 and PB-E4 evidence bundles (Phase 3).
- Validation Lab rehearsal run IDs per trainee role, and IFU acknowledgement
  records (Phase 4).
- Completed Installation Record (Phase 5), including SBOM reference (Aikido
  export or project evidence).
- Signed go/no-go decision with named sign-offs (Phase 6).
- Monitoring and communication handover confirmation (Phase 7).

## 7. Risks and rollback

| Risk | Mitigation |
|---|---|
| Go-live proceeds without recorded DCB0160 confirmation from the customer | Hard stop -- Phase 1 exit criteria requires this in writing before Phase 2 starts. |
| Training skipped or rushed for a role | Phase 4 requires at least one Validation Lab rehearsal per role before Phase 5 can close; do not accept "will train after go-live" as a substitute. |
| Deployment causes a P1/P2 outage, patient-data separation failure, or incorrect pathway/guideline/write-back behaviour with safety impact | Follow the rollback procedure in `SVP-LEO-CDS-001` section 12.2: declare in the incident channel, confirm scope, revert to the previous approved image/config/snapshot, run post-rollback smoke and data-integrity checks, notify affected customers, open CAPA within 2 business days for failed events. |
| Customer treats this playbook as their complete DCB0160 safety case | Explicitly correct this in Phase 1 -- Mizaic's evidence supports, but does not replace, the customer's own DCB0160 process. |

## 8. Source index

- [compliance/policy/SVP-LEO-CDS-001-service-plan.md](../../../../compliance/policy/SVP-LEO-CDS-001-service-plan.md)
- [compliance/policy/DC-INST-001-installation-procedure.md](../../../../compliance/policy/DC-INST-001-installation-procedure.md)
- [compliance/policy/DC-DEP-001-deployment-configuration.md](../../../../compliance/policy/DC-DEP-001-deployment-configuration.md)
- [compliance/policy/DC-DTAC-001-dtac-compliance-statement.md](../../../../compliance/policy/DC-DTAC-001-dtac-compliance-statement.md)
- [compliance/policy/DC-SMP-001-maintenance-plan.md](../../../../compliance/policy/DC-SMP-001-maintenance-plan.md)
- [compliance/policy/DC-PR-001-problem-resolution.md](../../../../compliance/policy/DC-PR-001-problem-resolution.md)
- [docs/operations/pilot-go-no-go-checklist.md](../../../../docs/operations/pilot-go-no-go-checklist.md)
- [docs/operations/pilot-slos.md](../../../../docs/operations/pilot-slos.md)
- [docs/VALIDATION-LAB.md](../../../../docs/VALIDATION-LAB.md)
- [compliance/policy/leo-widget-ifu.md](../../../../compliance/policy/leo-widget-ifu.md)
- [compliance/GATE6-RELEASE-CHECKLIST.md](../../../../compliance/GATE6-RELEASE-CHECKLIST.md) (internal engineering release gate -- useful background on how Mizaic itself gates a release before it reaches this playbook, not a customer-facing artefact)

## 9. Open gaps

- **`IFU-LEO-CDS-001` (full-product Instructions For Use) and the DCB0160
  deployer support pack are both marked "pending" in current QMS
  documents.** Interim: use the widget IFU plus `SVP-LEO-CDS-001`'s own
  training section as the training basis, and flag explicitly to the
  customer that the full-product IFU and DCB0160 pack are in progress, not
  complete. See [../GAPS-AND-BLOCKERS.md](../GAPS-AND-BLOCKERS.md).
- DCB0129 declaration, NHS DSPT "Standards Met", Cyber Essentials Plus, and
  WCAG 2.1 AA audit are all still open per `DC-DTAC-001` as of 2026-03-04 --
  check current status before presenting DTAC compliance as complete in any
  customer conversation.
- Local CSO ownership of DCB0160 is the customer's responsibility, not
  something this playbook can complete on their behalf -- keep this
  boundary explicit in every go/no-go pack.
