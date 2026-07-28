# PB-E3 -- Integration and embed

Catalogue reference: Module E3, "Integration and embed" -- e-RS / EPR
triggers, widget, gated write-back
(`docs/marketing/build_coo_service_catalogue.py`, `module_menu()`). Bundled
into Package A (Elective SPoA Accelerate).

Tier: 1 (full playbook). Audience: internal delivery / solutions
consultants running an integration workstream for a COO-sponsored
programme. Not a substitute for the customer's own DCB0160 safety case or
for `LEO-UM-ERS-001` (missing -- see Open gaps).

## 1. Purpose and buyer outcome

**For the COO / CSO / Digital lead:** by the end of this playbook, referrals
or Advice and Guidance requests from the customer's source system reach a
clinician as a reviewed, completeness-checked clinical summary (SBAR)
inside their existing workflow -- with no unreviewed write-back to e-RS,
PAS, or the EPR.

**What "done" looks like:**

- A trigger contract is agreed and tested end to end for at least one
  referral or A&G pathway.
- The SBAR widget (or the SBAR REST API, for host products that render
  their own UI) is live inside the customer's clinical workflow.
- Host governance onboarding is complete, so production widget tokens can
  be issued.
- Write-back (where contracted) only fires after clinician confirmation.
- A smoke test and an incident runbook are in place before go-live.

## 2. Preconditions and non-negotiable safety gate

- LEO CDS platform readiness (Phase 1 of `LEO-OP-001`) is already complete
  for this environment -- this playbook does not re-run platform install.
- **Human review is mandatory and cannot be configured away.** Every SBAR
  the widget renders is a proposal. A clinician confirms or rejects it
  before any clinical action or write-back occurs
  ([compliance/policy/leo-widget-ifu.md](../../../../compliance/policy/leo-widget-ifu.md)
  section 2).
- If the engagement includes write-back to a source system, confirm the
  Data Processing Agreement addendum in scope permits it --
  [compliance/policy/DC-DPA-002-addendum-b-referral-assessment.md](../../../../compliance/policy/DC-DPA-002-addendum-b-referral-assessment.md)
  clause 5(e) currently states the Referral Assessment use case does
  **not** write back to source systems under that addendum. Do not promise
  write-back beyond what the signed addendum covers.

## 3. Roles

| Playbook role | Canonical app role (`services/design-system/src/roles/types.ts`) | Responsibility here |
|---|---|---|
| Integration lead (Mizaic) | -- (delivery role, not an app role) | Owns the trigger contract, Service Bus / REST integration, and smoke testing |
| Platform Administrator | `platform_admin` | Confirms platform readiness, configures production queue routing |
| Customer IT Lead | -- (customer-side, not an app role) | Provides source-system access, network readiness, CSP allowlist changes for the widget origin |
| Host product engineer | -- (customer-side or partner) | Implements the widget-token exchange call and mounts `<leo-sbar>` or the iframe variant |
| Clinical Safety Officer (Mizaic) | -- (QMS role) | Confirms the human review gate is intact in the finished integration; owns clinical safety advisories |
| Triage Clinician / Referral Supervisor (customer) | `triage_clinician`, `referral_supervisor` | Reviews and confirms SBAR proposals in the live workflow |

## 4. Step-by-step phases

### Phase 1 -- Graph and platform prerequisites

**Entry criteria:** platform readiness confirmed (LEO-OP-001 Phase 1).

1. Confirm the customer's `patient_id`, `referral_id`, and
   `document_reference_id` conventions can be mapped onto LEO's expected
   node shapes. For referral handoff:
   `(:Patient)<-[:FOR_PATIENT]-(:ReferralRequest)`,
   `(:DocumentReference)-[:HAS_CHUNK]->(:Chunk)`
   ([docs/REFERRAL-PIPELINE-INTEGRATION.md](../../../../docs/REFERRAL-PIPELINE-INTEGRATION.md)).
2. For Advice and Guidance, confirm the `communication_thread` shape
   instead:
   `(:CommunicationRequest)-[:HAS_CONVERSATION]->(:Communication)`, with
   optional `HAS_DOCUMENT` / `HAS_RESPONSE` edges (same source, "Advice and
   Guidance (communication_thread)" section).
3. Confirm which NICE guideline (`guideline_id`, e.g. `NG12`) and which
   `completeness_domain` / `completeness_subdomain` apply to this pathway.
   These come from Module E4 (Pathway and guideline factory) -- if E4 has
   not run yet for this pathway, stop and sequence E4 first.

**Exit criteria:** node-shape mapping agreed and written down; guideline
and completeness identifiers confirmed with the LEO clinical team.

### Phase 2 -- Trigger contract

**Entry criteria:** Phase 1 complete.

1. Choose the trigger path:
   - **REST API** (recommended for most hosts): `POST /api/sbar/scenario-runs`
     for pre-loaded scenarios, or the direct Service Bus path below for live
     referrals.
   - **Direct Service Bus**: send a `referral-received` message to the
     `pipeline-jobs` queue (env var `PIPELINE_QUEUE_NAME`, default
     `pipeline-jobs`). See the full field reference and worked Python
     example in
     [docs/REFERRAL-PIPELINE-INTEGRATION.md](../../../../docs/REFERRAL-PIPELINE-INTEGRATION.md)
     ("Message fields reference").
2. Confirm the host has network/credential access:
   `AZURE_SERVICEBUS_CONNECTION_STRING` with `Send` rights on
   `pipeline-jobs`, or a service account JWT for the REST path.
3. Send one test trigger per pathway and confirm a `run_started` event
   arrives on the progress stream (see Phase 5).

**Exit criteria:** at least one successful test trigger per in-scope
pathway, with a `run_id` that a human can trace end to end.

### Phase 3 -- SBAR consumption

**Entry criteria:** Phase 2 complete.

1. Decide how the host will consume the finished SBAR:
   - Subscribe to the `referral-assessments-output` Service Bus queue for a
     `referral_assessment_completed` event (push model), or
   - Poll `GET /api/pipeline/progress-status/{run_id}` (pull model), or
   - Connect to the Server-Sent Events stream at
     `GET /api/pipeline/progress/{run_id}` for real-time step-by-step
     progress (nine pipeline steps; event types `run_started`,
     `durable_step_started`, `durable_step_completed`,
     `durable_step_failed`, `run_completed`, `pipeline_error`, `heartbeat`).
2. Once the run completes, retrieve the SBAR via
   `GET /api/sbar/{assessment_id}`, or mount the widget directly (Phase 4) --
   the widget fetches its own data once it has an `assessment_id` and
   widget token.
3. Confirm the completeness panel and any red-flag / two-week-wait
   detection surfaces correctly for at least one positive and one negative
   test case (see Module E4's Validation Lab rehearsal for the shared test
   patient library).

**Exit criteria:** host can reliably retrieve a completed SBAR by
`assessment_id` for every trigger sent in Phase 2.

### Phase 4 -- Widget mount, IFU acknowledgement, and host governance

**Entry criteria:** Phase 3 complete; host has decided on the web-component
or hardened-iframe distribution variant.

1. Confirm host governance onboarding is complete **before** requesting
   production widget tokens. LEO holds four mandatory artefacts per host:
   (a) LEO SaaS Embedding Agreement, (b) Data Processing Agreement,
   (c) reference to the host's accepted DCB0129 supplier safety case, and
   (d) an acknowledgement of the widget IFU with version recorded
   ([services/widget-sdk/README.md](../../../../services/widget-sdk/README.md)
   "Slice 6 -- host governance acknowledgement";
   [compliance/policy/leo-widget-ifu.md](../../../../compliance/policy/leo-widget-ifu.md)
   section 5). The token-exchange endpoint
   (`services/api/app/routers/sdk_auth.py`) returns
   `403 host_not_onboarded` if any artefact is missing -- this is a hard
   system gate, not a paperwork nicety.
2. Confirm the host's Content Security Policy allowlists the LEO widget CDN
   origin and the LEO analytics endpoint. The widget cannot render behind a
   CSP that blocks either origin (widget IFU section 4.2).
3. Confirm the host will not proxy-strip `POST /sdk/telemetry` calls, and
   will surface (not hide or auto-dismiss) any degraded-state indicator or
   CSO advisory banner the widget renders (widget IFU section 4.3-4.4).
4. Implement the token exchange: host backend calls
   `POST /sdk/auth/exchange` with the shared `X-Mizaic-Host-Secret` header,
   naming the host user, tenant, assessment, and role. LEO returns a JWT
   scoped to that assessment, audience `leo-widget`, TTL 900 seconds
   (widget-sdk README "Slice 2 -- widget-token auth").
5. Mount `<leo-sbar assessment-id="..." widget-token="..."
   proxy-origin="...">` (web component) or the hardened iframe equivalent.
   Confirm the `leo:loaded` event fires and the SBAR renders inside the
   customer's clinical workflow, not on a standalone page.
6. Record the host's IFU acknowledgement version against the host record
   via `POST /sdk/governance/hosts/{host_id}/ifu`.

**Exit criteria:** a production widget token is successfully issued and the
widget renders a real SBAR inside the host's live workflow for at least one
pilot user.

### Phase 5 -- Gated write-back (where contracted)

**Entry criteria:** Phase 4 complete; the signed DPA addendum for this
customer explicitly permits write-back (see section 2 above -- the standard
Referral Assessment addendum currently does not).

1. Confirm the write-back trigger is the clinician's explicit confirmation
   action in the UI, not a background or scheduled process.
2. Confirm the audit trail records clinician identity, the AI output shown,
   and the clinician's decision for every write-back event
   ([compliance/policy/DC-DPA-002-addendum-b-referral-assessment.md](../../../../compliance/policy/DC-DPA-002-addendum-b-referral-assessment.md)
   clause 2(f)).
3. Run a rollback drill: confirm a rejected or incorrect write-back can be
   corrected without silently overwriting the clinician's audit trail.

**Exit criteria:** write-back only fires after a recorded clinician
confirmation, with a working correction path. If write-back is not in scope
for this customer, skip this phase and record that explicitly in the
customer plan.

### Phase 6 -- Smoke test and incident runbook

**Entry criteria:** Phases 1-4 (and 5, if in scope) complete.

1. Run one end-to-end smoke test per pathway: trigger -> SBAR generated ->
   widget renders -> clinician reviews -> (write-back, if in scope).
   Capture the `run_id` and screenshot evidence.
2. Hand the customer's operational contact the relevant runbook sections:
   consumer health check (`GET /health/consumer` on the pipeline worker),
   dead-letter queue growth, and rollback criteria
   ([docs/operations/incident-runbook-pipeline-jobs.md](../../../../docs/operations/incident-runbook-pipeline-jobs.md)).
3. Confirm the customer's IT Lead knows the P1/P2/P3 response targets they
   should expect (30 minutes / 4 business hours / 2 business days --
   `compliance/policy/SVP-LEO-CDS-001-service-plan.md` section 11.1) and how
   to raise an incident.

**Exit criteria:** smoke test evidence captured; customer IT Lead has the
runbook and knows how to escalate.

## 5. Tools and UI paths

| Task | UI path / endpoint |
|---|---|
| Trigger a referral or A&G run | `POST /api/sbar/scenario-runs` (REST) or `pipeline-jobs` Service Bus queue |
| Monitor a run | `GET /api/pipeline/progress/{run_id}` (SSE) or `GET /api/pipeline/progress-status/{run_id}` (poll) |
| Retrieve a finished SBAR | `GET /api/sbar/{assessment_id}` |
| Register a host / record governance artefacts | `POST /sdk/governance/hosts`, `POST /sdk/governance/hosts/{host_id}/artefacts`, `POST /sdk/governance/hosts/{host_id}/ifu` |
| View the host governance register | `GET /sdk/governance/register` |
| Exchange a widget token | `POST /sdk/auth/exchange` |
| Widget CDN demo (per environment) | `https://leoaiwidgetcdn{env}.z33.web.core.windows.net/demo/` |

## 6. Evidence to capture

- Trigger contract test evidence: `run_id`s and pathway coverage from
  Phase 2.
- SBAR retrieval evidence: `assessment_id`s and completeness panel
  screenshots from Phase 3.
- Host governance register entry (all four artefacts) from
  `GET /sdk/governance/register`.
- Widget IFU acknowledgement version recorded against the host.
- Smoke test evidence (Phase 6) for the Installation Record referenced in
  PB-E8.
- If write-back is in scope: audit trail export showing clinician
  confirmation for each write-back event.

## 7. Risks and rollback

| Risk | Mitigation |
|---|---|
| Host embeds the widget before governance onboarding is complete | System-enforced: `sdk_auth.py` refuses to mint tokens (`403 host_not_onboarded`). Do not attempt to bypass this. |
| Host CSP blocks the widget CDN or analytics origin | Confirm allowlisting in Phase 4 before attempting a live mount; the widget fails closed, not open. |
| Pipeline step fails mid-run | No auto-retry. Re-submit the original `referral-received` message with the same `run_id` to resume, or a new `run_id` to start fresh. Previous partial results for that `run_id` are overwritten on resubmission ([docs/REFERRAL-PIPELINE-INTEGRATION.md](../../../../docs/REFERRAL-PIPELINE-INTEGRATION.md) "Error handling"). |
| Consumer unhealthy for over 30 minutes, or error budget exhausted | Rollback to the previous known-good image tag per the incident runbook. |
| Write-back promised beyond the signed DPA addendum | Confirm addendum scope in Phase 5 before agreeing any write-back timeline with the customer. |

## 8. Source index

- [docs/REFERRAL-PIPELINE-INTEGRATION.md](../../../../docs/REFERRAL-PIPELINE-INTEGRATION.md)
- [services/widget-sdk/README.md](../../../../services/widget-sdk/README.md)
- [compliance/policy/leo-widget-ifu.md](../../../../compliance/policy/leo-widget-ifu.md)
- [compliance/policy/DC-INST-001-installation-procedure.md](../../../../compliance/policy/DC-INST-001-installation-procedure.md)
- [compliance/policy/DC-DEP-001-deployment-configuration.md](../../../../compliance/policy/DC-DEP-001-deployment-configuration.md)
- [compliance/policy/DC-DPA-002-addendum-b-referral-assessment.md](../../../../compliance/policy/DC-DPA-002-addendum-b-referral-assessment.md)
- [docs/operations/incident-runbook-pipeline-jobs.md](../../../../docs/operations/incident-runbook-pipeline-jobs.md)
- [docs/operations/monitoring-alerts.md](../../../../docs/operations/monitoring-alerts.md)
- [services/design-system/src/roles/types.ts](../../../../services/design-system/src/roles/types.ts)

## 9. Open gaps

- **`LEO-UM-ERS-001` is missing.** Any step involving NHS e-RS (Initial
  Connection Approval, CIS2 app registration, Key Vault secret setup for
  the customer's e-RS credentials) is marked "external QMS / TBD" in this
  playbook. Do not improvise these steps -- escalate to the platform team
  for a customer-specific e-RS onboarding plan. See
  [../GAPS-AND-BLOCKERS.md](../GAPS-AND-BLOCKERS.md).
- **LEO SaaS Embedding Agreement status is not confirmed per customer.**
  Check with Commercial/Legal before promising a widget go-live date for a
  new host.
- Write-back is currently **not permitted** under the standard Referral
  Assessment DPA addendum (clause 5(e)). If a customer wants write-back,
  this needs a contract variation before Phase 5 can start -- do not treat
  Phase 5 as available by default.
