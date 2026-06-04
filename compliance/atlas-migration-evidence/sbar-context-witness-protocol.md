# SBAR context witness protocol

| Field        | Value                                              |
| ------------ | -------------------------------------------------- |
| Document ID  | SBAR-CONTEXT-WITNESS-001                           |
| Version      | 0.4.0-draft                                        |
| Status       | Draft -- host integration witness only             |
| Date         | 2026-06-02                                         |
| Product      | PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4 |
| Related UN   | UN-F8819A42                                        |
| Related VAL  | VAL-7207DFBE                                       |
| Related risk | R-0E8A90ED                                         |

This protocol validates **host / consuming-system integration** only:

1. The host publishes the **correct pub/sub message** (patient and record context).
2. The host **consumes completion output** for that same context.
3. The host **renders the widget** (or review surface) for that same patient and assessment.

---

## Scope boundary

| In witness scope | Out of witness scope (already verified internally) |
| ---------------- | -------------------------------------------------- |
| Host pub/sub publish (`referral-received` or agreed job message) | DI-957B8352 Graph data model |
| Host subscribes and loads the right run / assessment | DI-F71A6A69 Clinical facts storage |
| Widget render for the same `patient_id` and assessment id | DI-FA2E369F Pipeline initiation inside LEO |
| Host correlation metadata in the message where required | VT-61E749AA / VT-75F1B23D / DO-3CAFDCC3 |
| | VAL-C8B14655 Lower GI internal E2E |
| | DI-44D0E115 / DO-88F13322 Onboarding procedure |
| | LEO admin playground, NG12 scenario runner, referral review UI as LEO-owned paths |

Witness pass/fail is **host wiring only**. LEO `run_id` and `assessment_id` may
appear in the pack as correlation evidence. They are not a second functional test
of LEO.

---

## Witness pack (minimum)

One pack per **host integration** per **release baseline**.

Store each pack as an Atlas **Record** linked to product
`PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4` and validation test
**VAL-7207DFBE**. Suggested record title:
`SBAR context witness pack - <host> - <release baseline>`.

The pack is the signed evidence bundle for the three steps below (logs,
redacted message metadata, screenshots). Attach files to the VAL run via Atlas
(`upload_validation_evidence`) and record the outcome with
`record_validation_run`. Reference the record in the run notes as
`atlas:records/documents/<uuid>`.

Redact clinical text in all captures.

### 1. Publish (pub/sub out)

Evidence that the host sent the agreed job message with the correct context:

- Message type (for example `referral-received` or host-documented equivalent).
- `patient_id` and record ids (encounter, referral, document reference, chunk as applicable).
- Routing fields the contract requires (`run_id`, tenant, domain/subdomain if used).
- `upstream_correlation_id` and `source_system` when the host supports them.

Capture: host publish log, Service Bus message metadata, or redacted message body.

### 2. Consume (pub/sub in)

Evidence that the host received and acted on the **same** context:

- Completion or status event for the same `run_id` (or host correlation id).
- Host retrieval or hand-off uses the same `patient_id` as step 1.
- Host does not attach the result to a different patient or case shell.

Capture: host subscription handler log, event payload metadata, or host API read
for that run.

### 3. Render (widget / review surface)

Evidence that the embedded widget or host review UI shows output for step 1 context:

- Same `patient_id` visible in host session or widget props.
- Same assessment or run id as steps 1-2.
- Widget loads without cross-patient bleed (wrong banner, wrong citations, or
  wrong case header).

Capture: screenshot or structured UI state with ids; widget `assessment-id` /
token attributes where used.

**Sign-off:** witness executed by, date, environment (validation/staging), pass/fail.

---

## Systems in scope

| Integration | Publish | Consume | Render | Priority |
| ----------- | ------- | ------- | ------ | -------- |
| External Healthcare Co host | Host EPR / scheduler -> pub/sub | Host event handler -> case load | Embedded LEO widget or host SBAR panel | Must at go-live |

LEO supplies this protocol and the message field checklist. The **Controller**
runs the witness in validation and returns completed packs before production
cutover.

---

## Scheduled jobs

If the host triggers via scheduler rather than a clinician action, the pack must
still show the same three steps with:

- Scheduler identity and job name.
- Patient and record ids resolved the same way as the interactive path.
- Widget or review surface for that patient after completion.

---

## Negative case (optional)

Host deliberately publishes mismatched patient and record ids. Pass criteria:

- Host consume/render path does **not** present a complete SBAR as ready for the
  wrong patient.
- Host consume/render path does not treat a rejected or wrong-context run as
  ready for clinical use.

---

## Atlas traceability (host integration only)

| Role | Artefact | Notes |
| ---- | -------- | ----- |
| Validation | VAL-7207DFBE | Executes this protocol |
| Risk | R-0E8A90ED | Wrong context from upstream assembly |
| Widget embed | DI-85C95E53, DI-A1206416 | Render step; token and origin guard |
| Widget safety | R-4965BCD2 | Source disclosure in embedded surface |

Do not link this document to LEO-internal DIs, DOs, VTs, or VAL-C8B14655.

---

## Monitoring (R-0E8A90ED)

After release, review per release:

- Wrong-patient incidents traced to **host publish, consume, or widget render**
- Witness pack outcomes at host go-live or major host release

Escalate to the Clinical Safety Officer if any wrong-patient summary is confirmed
in production.
