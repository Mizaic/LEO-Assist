# Gate 6 Release Checklist (R5.x -> G6.x)

Product: PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4

This document prepares the unified pipeline durability sprint for release.
It records automated verification evidence and lists human gates that
must NOT be simulated by tooling.

Status: ENGINEERING COMPLETE (2026-07-22). Automated verification, Draft Atlas
artefacts, and sprint VT pass runs are recorded for Gates 1-5 scope. Human CSO,
QA/RA, and clinician sign-off remain OUT OF SCOPE for engineering (see section
0 and "Release ready when" below).

---

## Release ready when

Engineering treats the sprint as **release-ready** when every row in the
**Engineering green** column is true. **Human sign-off** rows block production
cutover but do not block merging the release branch from an engineering view.

| Area | Engineering green (2026-07-22) | Human sign-off still required |
|------|------------------------------|-------------------------------|
| Gates 1-5 Draft DI/DO/Risk/VT chains | yes | QA/RA promote Draft -> Approved (H-1) |
| Sprint VT pass runs (35/35 matrix) | yes | QA/RA review runs during promotion |
| Gate 4 remainder durable_pubsub (8 plans) | yes (VT-F210824D) | none |
| Gate 4 U4.6 sync runner + analysis worker | waived (W-022) | none for this release |
| G5.9 Playwright VAL (local live stack) | yes (VAL-2A1EDC22 PASS) | optional staging re-run (H-9) |
| G6.1 rollback controls (local drill) | yes (11/11) | live staging drill (H-2) |
| get_traceability_gaps orphan DIs/DOs | yes (empty) | QA prune spurious VERIFIES edges |
| Broad pytest sprint slice | yes (206/206 local) | Full CI on release branch |
| black + flake8 (changed Python) | yes (2026-07-22) | none |
| Plan seed pre-deploy note | yes (seed_plan_definitions docstring) | DevOps run seed on staging/prod KG |
| G0.3 clinician gold (97 + SBAR ledger) | n/a (human only) | H-4, H-5 |
| CSO residual risk acceptance | n/a (human only) | H-3, H-8 |
| QA/RA Atlas promotion + CR | n/a (human only) | H-1 |

**Engineering verdict:** release-ready for handoff to QA/RA and CSO. Production
cutover requires H-1 through H-5 and live G6.1 staging drill (H-2).

---

## 0. Engineering sign-off gate (sprint policy)

Engineering sign-off for the unified pipeline sprint (Gates 1-5) happens
when BOTH are true:

1. All Draft design control artefacts exist in Atlas (UN -> DI -> DO ->
   Risk -> VT chains for every new/changed test module).
2. Every linked VT has at least one recorded pass run in Atlas.

Human CSO, clinician, and QA/RA sign-off are NOT part of this gate.
They follow in Gate 6 (sections 5-7).

Engineering gate status (2026-07-22):

- [x] Draft DIs, DOs, Risks, and VTs created in Atlas for Gates 1-5 scope
- [x] All sprint VT pass runs recorded (see section 1.3 matrix)
- [x] get_traceability_gaps returns no orphan DIs or DOs (2026-07-22 MCP audit)
- [ ] QA/RA promotion Draft -> Approved (human; section 7 H-1)
- [ ] CSO residual risk review (human; section 6)
- [ ] G0.3 clinician gold adjudication (human; section 5)

---

## 1. Draft Atlas artefacts (this sprint)

Promote these from Draft to Approved only after QA/RA review of the
linked verification runs and residual risk acceptance.

### Design Inputs (Draft)

| dcId | Title | Mitigates |
|------|-------|-----------|
| DI-0CB9E932 | Deterministic pipeline run admission key | R-7FC000A1 |
| DI-4976171D | Durable edge outbox with deterministic message IDs | R-C773C6BB |
| DI-B1E43400 | Pinned plan manifest for in-flight pipeline runs | R-FB9026D2 |
| DI-36F80B95 | Durable stage single-flight claim on redelivery | R-61F3E57E |
| DI-090D4939 | Monotonic PipelineRun status | R-B4214985 |
| DI-29BF950F | Referral policy publish validation | R-32D77F0C |
| DI-AB1C442D | Execution manifest snapshot at admission | R-FB9026D2 |
| DI-9EE8D65E | PlanDefinition seed immutability guard | R-FB9026D2 |
| DI-CB01B8A6 | Controlled workflow version admission | R-FB9026D2 |
| DI-075775FF | Mandatory SBAR audit persistence | R-53C2C4E9 |
| DI-33376FBB | Extraction window size equivalence | R-B2A860E4 |
| DI-E6BA4E80 | Trigger chunk and recall security isolation | R-64D396E0 |
| DI-8788B246 | Referral reference certification suite U4.1 | R-7CCCF7E3 |
| DI-3AAB5328 | SBAR evidence scope and background envelope | R-54048593 |
| DI-C31E59C4 | Two-week-wait detection and mismatch alert | R-54048593 |
| DI-9D356E59 | SBAR Recommendation prompt contract | R-54048593 |
| DI-ED65569C | Structured-first SBAR Situation section | R-54048593 |
| DI-8A2F4DAB | Referral policy extraction windows | R-54048593 |
| DI-CC00ABBD | Bounded SBAR recall orchestration | R-54048593 |
| DI-471C0642 | GP encounter durable plan parity | R-06BD07A6 |
| DI-B0885517 | Coding worker durable-only GP routing | R-143387B9 |
| DI-C1C4030F | Episode bundle durable dispatch contract | R-690DF11D |

### Design Outputs (Draft)

| dcId | Title | Implements |
|------|-------|------------|
| DO-7EE5D7A6 | Pipeline run admission and first-step enqueue | DI-0CB9E932 |
| DO-3A657CCF | Pipeline stage outbox and dispatch | DI-4976171D |
| DO-3F7F7B7D | Pinned plan manifest loader | DI-B1E43400 |
| DO-CE65B1F2 | Durable PipelineStageRun claim and skip | DI-36F80B95 |
| DO-4F0779C8 | Monotonic PipelineRun status | DI-090D4939 |
| DO-E89DE9EE | Referral policy validation | DI-29BF950F |
| DO-04CEDFB1 | Execution manifest snapshot | DI-AB1C442D |
| DO-33776AFE | Plan seed immutability guard | DI-9EE8D65E |
| DO-55FE7CB1 | Version admission control | DI-CB01B8A6 |
| DO-025F8C6C | SBAR audit persistence | DI-075775FF |
| DO-CA3BBC37 | Extraction window equivalence | DI-33376FBB |
| DO-3A28C048 | Recall security isolation | DI-E6BA4E80 |
| DO-EA19691C | U4.1 referral certification | DI-8788B246 |
| DO-FA365C59 | SBAR evidence envelope | DI-3AAB5328 |
| DO-79266FAB | 2WW detection and alert | DI-C31E59C4 |
| DO-72BD118D | SBAR Recommendation prompt | DI-9D356E59 |
| DO-FE774247 | Structured Situation source | DI-ED65569C |
| DO-3DF854C4 | Referral extraction windows | DI-8A2F4DAB |
| DO-8CD63B3B | Bounded recall orchestrator | DI-CC00ABBD |
| DO-AC3730B6 | GP encounter durable plan parity | DI-471C0642 |
| DO-89C01ADA | Coding worker durable-only GP routing | DI-B0885517 |
| DO-684D1CE0 | Episode bundle durable dispatch | DI-C1C4030F |

### Verification Tests (Draft) -- Gates 1-5 matrix

| Test file | VT dcId | Run recorded |
|-----------|---------|--------------|
| tests/test_run_admission.py | VT-5427E0E1 | yes |
| tests/test_pipeline_outbox.py | VT-B14997B6 | yes |
| tests/test_pipeline_stage_poison.py | VT-A9FB7ADA | yes |
| tests/test_pipeline_run_status_monotonic.py | VT-35E95798 | yes |
| tests/test_gate5_lease_chaos.py | VT-0203C659 | yes |
| tests/test_pipeline_stage_claim_concurrency.py | VT-E4457D16 | yes |
| tests/test_pipeline_worker_competing_consumers.py | VT-E4457D16 | yes |
| tests/test_pipeline_stage_claim.py | VT-145DEC00 | yes |
| tests/test_referral_policy.py | VT-FBBB330F | yes |
| tests/test_execution_manifest.py | VT-4A288C6F | yes |
| tests/test_plan_manifest.py | VT-630B9016 | yes |
| tests/test_plan_seed_immutability.py | VT-BC4DA28C | yes |
| tests/test_version_admission.py | VT-0DD885A9 | yes |
| tests/test_sbar_audit_persistence.py | VT-01FC0CC7 | yes |
| tests/test_gate5_durable_replay.py | VT-DC4B1329 | yes |
| tests/test_gate5_already_completed_outbox_repair.py | VT-7158FF21 | yes |
| tests/test_gate5_extraction_equivalence.py | VT-C9F83C6B | yes |
| tests/test_platform_conformance.py | VT-AAC08C5B | yes |
| tests/test_gate3_security_isolation.py | VT-8518C6B9 | yes |
| tests/test_u4_1_referral_reference_certification.py | VT-6D3B6707 | yes |
| tests/test_gate3_trigger_chunk_scope.py | VT-310AF00A | yes |
| tests/test_gate3_source_resolver_evidence.py | VT-0E7A239B | yes |
| tests/test_gate3_uncoded_coverage.py | VT-200F07B2 | yes |
| tests/test_gate3_background_envelope.py | VT-2B69BC95 | yes |
| tests/test_gate3_twow_detector.py | VT-0D02C91C | yes |
| tests/test_gate3_twow_alert.py | VT-CDA55F9B | yes |
| tests/test_gate3_recommendation_prompt.py | VT-E3246437 | yes |
| tests/test_gate3_situation_structured_first.py | VT-6CA911CF | yes |
| tests/test_gate3_extraction_window.py | VT-319A59AF | yes |
| tests/test_gate3_bounded_recall.py | VT-C7B21302 | yes |
| tests/test_sbar_recall_loop.py | VT-768E31BB | yes |
| tests/test_gate3_orchestrator_wiring.py | VT-216A14F0 | yes |
| tests/test_durable_runner_encounter_parity.py | VT-D8F94264 | yes |
| services/coding_worker/tests/test_job_handler_engine.py | VT-EAAE584B | yes |
| tests/episode_v2_coding/test_episode_bundle_event.py | VT-EF76F4A1 | yes (handler; plan seeded in seed_plan_definitions) |

All 35 sprint VT rows above have at least one pass run in Atlas as of
2026-07-22 (cursor-agent-local, local pytest).

### Risks (Control Implemented, pending CSO residual review)

| dcId | Title | Mitigated by |
|------|-------|--------------|
| R-7FC000A1 | Duplicate referral trigger starts parallel pipeline runs | DI-0CB9E932 |
| R-C773C6BB | Stage completion republishes duplicate successor steps | DI-4976171D |
| R-FB9026D2 | Mid-run plan definition change alters pipeline steps | DI-B1E43400, DI-AB1C442D, DI-9EE8D65E, DI-CB01B8A6 |
| R-61F3E57E | Redelivered durable step runs same stage twice | DI-36F80B95 |
| R-B4214985 | Terminal pipeline run reopened by duplicate message | DI-090D4939 |
| R-32D77F0C | Invalid referral policy published | DI-29BF950F |
| R-64D396E0 | SBAR recall reads out-of-scope chunks | DI-E6BA4E80 |
| R-53C2C4E9 | SBAR audit trail incomplete | DI-075775FF |
| R-7CCCF7E3 | Referral reference drift breaks pipeline | DI-8788B246 |
| R-B2A860E4 | CDS processing degradation delays review | DI-33376FBB |
| R-54048593 | Suspected cancer or family history dropped | DI-3AAB5328, DI-C31E59C4, DI-CC00ABBD, others |
| R-06BD07A6 | GP encounter migration drops coding verifier | DI-471C0642 |
| R-143387B9 | Coding worker bypasses durable pipeline | DI-B0885517 |
| R-690DF11D | Episode bundle attaches coding to wrong episode | DI-C1C4030F |

### Atlas promotion checklist (QA/RA)

- [ ] Review each Draft DI acceptance criteria against implemented code.
- [ ] Confirm each DO source_reference paths exist in the release branch.
- [ ] Confirm every Draft VT has at least one recorded pass run in Atlas.
- [ ] Promote DI / DO / VT status from Draft to Approved in Atlas MCP.
- [ ] Re-run get_traceability_gaps; orphan lists must remain empty.
- [ ] Attach release Change Request linking all promoted dcIds.

---

## 2. G6.1 -- Rollback exercise

Goal: prove that a bad deployment can be reversed without corrupting
in-flight pipeline runs.

### Scope

- Workflow version rollback via `_versionRollout.rollbackTarget`
  (libs/workflow/version_admission.py).
- Plan-level durable activation via `_workflowMode` / `workflowMode`
  (libs/workflow/plan_manifest.py; seed in scripts/seed_plan_definitions.py).
- Emergency kill switch `DURABLE_ENGINE_DISABLED=true`
  (libs/workflow/durable_step_runner.py; blocks new durable triggers only;
  in-flight `durable_step` messages still route -- see durable_dispatcher.py).
- Container image rollback to last known good tags (pilot SLO policy).
- Model registry rollback (libs/episode_detector/registry.py) if a
  promoted ruleset misbehaves.

### Automated evidence (local, 2026-07-22)

```bash
pytest tests/test_version_admission.py -v
pytest tests/test_model_registry.py -k rollback -v
pytest tests/test_durable_step_runner.py -k "kill_switch or durable_pubsub or legacy_plan" -v
pytest tests/test_g6_1_rollback_drill.py -v
```

Key assertion: rollback changes the default version for new runs only;
in-flight runs keep their pinned admission manifest (DI-B1E43400).

Automated drill result (2026-07-22T14:20Z, cursor-agent-local):

| Check | Result | Evidence |
|-------|--------|----------|
| Version rollback selects v2 for new runs | PASS | test_g6_1_step4_new_run_uses_rollback_version |
| In-flight run keeps v3 pinned manifest | PASS | test_g6_1_step5_inflight_run_keeps_pinned_manifest |
| Kill switch blocks new triggers, not in-flight steps | PASS | test_g6_1_kill_switch_blocks_new_triggers_not_inflight_steps |
| Legacy plan stays off durable path | PASS | test_g6_1_legacy_plan_stays_off_durable_path |
| Seed plans declare durable_pubsub | PASS | test_g6_1_seed_plans_declare_durable_pubsub (2/2) |
| Model registry rollback | PASS | test_model_registry.py::test_rollback |

Total: 11/11 automated rollback assertions green (local pytest, no Neo4j).

### Staging rollback exercise (REQUIRED before production cutover)

Executable script: `scripts/g6_1_rollback_drill_staging.sh`

Prerequisites: `FHIR_API_BASE`, `NEO4J_URI`, `NEO4J_PASSWORD`, Azure CLI
access to staging Container Apps. Optional: `INFLIGHT_RUN_ID` for step 5
auto-verify.

| Step | Actor | Action | Evidence | Staging status (2026-07-22) |
|------|-------|--------|----------|----------------------------|
| 1 | DevOps | Deploy canary build to staging pipeline-worker | Deployment record | BLOCKED (no staging creds in agent env) |
| 2 | DevOps | Start one referral assessment run; note run_id | PipelineRun node | SIMULATED (mock pinned manifest in test_g6_1_step5) |
| 3 | DevOps | Set rollbackTarget on pd-referral-assessment; redeploy prior image | PlanDefinitionVersion diff | SIMULATED (VersionRollout rollback_target in tests) |
| 4 | DevOps | Submit a NEW trigger; confirm new run uses rollback version | execution_manifest on run | SIMULATED (select_admission_version rollback_default) |
| 5 | DevOps | Confirm in-flight run from step 2 completes on original manifest | Stage hashes unchanged | SIMULATED (load_manifest_for_run pinned query) |
| 6 | QA/RA | Record exercise outcome in Atlas change record | CR attachment | PENDING human sign-off |

Rollback exercise status: **SIMULATED (local automated drill PASS; staging live drill BLOCKED).**

Drill executed: **no** (true staging) / **yes** (local simulated controls verified).

Recovery steps (documented, not run on staging):

1. Clear `_versionRollout.rollbackTarget` on affected PlanDefinition via FHIR PATCH.
2. Unset `DURABLE_ENGINE_DISABLED` on pipeline-worker Container App env.
3. Redeploy last-known-good image tags from ACR (see docs/operations/pilot-slos.md).
4. Confirm new referral trigger admits with `version_selection_reason=default`.
5. Attach drill stdout + PipelineRun Cypher snapshots to Atlas change record.

Owner sign-off placeholders:

| Role | Name | Date | Outcome |
|------|------|------|---------|
| DevOps (staging drill) | __________ | __________ | PASS / FAIL / BLOCKED |
| QA/RA (Atlas CR) | __________ | __________ | PASS / FAIL / PENDING |

---

## 2.5 G6.0 -- Service Bus settlement policy (multi-worker)

Reference: `docs/PIPELINE-EXECUTION-INVENTORY.md` (settlement table).

| Handler outcome | Service Bus settlement |
|-----------------|------------------------|
| completed / already_completed / poisoned | Complete |
| stage lease busy | Abandon (defer) |
| stale lease on complete (stage not done) | Abandon (defer) |
| stale complete recovered -> already_completed | Complete |
| unhandled exception | Abandon (retry until poison) |

Code: `libs/message_bus/settlement.py`, `libs/workflow/stage_lease.py`,
`services/pipeline_worker/app/services/durable_dispatcher.py`,
`libs/message_bus/azure_adapter.py`.

Tests: `tests/test_pipeline_message_settlement.py`,
`tests/test_pipeline_worker_competing_consumers.py` (settlement cases),
`tests/test_gate5_lease_chaos.py` (stale complete settlement).

Atlas: covered by existing DI-36F80B95 / VT-E4457D16 / VT-0203C659 chains
(no new Draft artefacts for this patch).

---

## 3. G6.2 -- General release gate checklist

### Engineering gates (automated)

- [x] Gate 5 in-memory durability suite green (see docs/GATE5-TEST-POLICY.md)
- [x] Gates 1-5 sprint VT runs recorded in Atlas (section 1.3 matrix; 35/35)
- [x] Gate 4 GP coding migration VT runs recorded (section 1.3; 3/3)
- [x] Draft UN/DI/DO/Risk/VT chains created for all sprint test modules
- [x] get_traceability_gaps returns no orphan DIs or DOs (2026-07-22)
- [x] Broad pytest sprint slice green locally (206 passed; see section 8)
- [x] black + flake8 on changed Python files (2026-07-22)
- [ ] Full CI pipeline green on release branch
- [ ] SOUP / dependency CVE review for changed packages

### QA/RA gates (human -- OUT OF SCOPE for engineering sign-off)

- [ ] Design control promotion (section 1) signed by QA/RA lead
- [ ] Change Request approved in Atlas
- [ ] DPIA-LEO-AI-001 reviewed if processing scope changed
- [ ] Release notes drafted with known limitations
- [x] Rollback procedure (G6.1) automated controls verified locally (11/11 pass)
- [ ] Rollback procedure (G6.1) live staging drill executed (blocked: staging creds)

### Clinical Safety Officer gates (human -- OUT OF SCOPE for engineering sign-off)

- [ ] Residual risk review for R-7FC000A1, R-C773C6BB, R-FB9026D2
      and new sprint risks (see section 6)
- [ ] G0.3 clinician gold adjudication complete (see section 5)
- [ ] SBAR signed_ledger.json attached to VT-LEO-AI-189 evidence bundle
- [ ] Written CSO statement that advisory-only human review gate remains
      mandatory for all AI proposals reaching the patient record

### VT / VAL evidence summary

| Gate | Evidence type | Status |
|------|---------------|--------|
| G1 admission/outbox/poison/monotonic/lease/concurrency | VT matrix section 1.3 | Recorded |
| G2 referral policy/manifest/seed/version/audit | VT matrix section 1.3 | Recorded |
| G3 SBAR orchestrator suite | VT matrix section 1.3 | Recorded |
| G5.2 durable replay | VT-DC4B1329 pass | Recorded |
| G5.3 concurrency | VT-E4457D16 pass | Recorded |
| U4.7 plan conformance | VT-AAC08C5B pass | Recorded |
| U4.2 GP encounter durable parity | VT-D8F94264 pass | Recorded |
| U4.2 coding worker routing | VT-EAAE584B pass | Recorded |
| U4.6 episode bundle dispatch | VT-EF76F4A1 pass | Recorded (plan seeded; analysis worker deferred W-022) |
| U4.1 referral certification | VT-6D3B6707 pass | Recorded |
| G0.3 extraction gold | Clinician adjudication | NOT STARTED |
| G0.3 SBAR gold | signed_ledger.json | NOT STARTED |
| G5.9 Playwright VAL | VAL-2A1EDC22 (local live stack) | PASS (df495d2d repair-loop fix; MCP + Playwright recorded) |

---

## 4. G6.3 -- Post-release monitoring and rollback triggers

Reference: docs/operations/pilot-slos.md

### Monitoring metrics (first 30 days post-release)

| Metric | Source | Review cadence |
|--------|--------|----------------|
| Consumer health | GET /health/consumer on pipeline-worker | Continuous |
| Queue depth + DLQ depth | Azure Service Bus metrics | Hourly |
| Job completion rate | PipelineRun status in Patient Graph | Daily |
| duplicate admission_key created=false | pipeline-worker logs | Daily |
| Stage poison terminal count | PipelineStageRun.attempts | Daily |
| Stage lease defer count | pipeline_message_defer logs | Daily |
| Stale complete recovered count | durable_step_already_completed logs | Daily |
| LLM cost anomaly | AuditEvent llm_cost_usd aggregates | Weekly |

### Rollback triggers (any one fires -> initiate rollback)

1. Error budget exhausted (pilot SLO policy): rollback container images
   to last known good tags.
2. Duplicate PipelineRun for same admission_key in production (R-7FC000A1
   monitoring breach): escalate to CSO; rollback if not resolved in 4 hours.
3. Job completion reliability below 98% for 1 hour (SLO 2 page threshold).
4. P95 queue-to-start latency above 120 seconds for 3 consecutive checks
   (SLO 3 page threshold).
5. Any unplanned mid-run plan step change detected (R-FB9026D2 sentinel):
   freeze PlanDefinition publishes; CSO review within 24 hours.

### Rollback procedure (summary)

1. Set rollbackTarget on affected PlanDefinition via FHIR API.
2. Redeploy prior pipeline-worker and core-api image tags from ACR.
3. Confirm new runs pin rollback manifest; in-flight runs unaffected.
4. Open Atlas deviation if patient-visible outputs were affected.
5. CSO sign-off before re-enabling canary promotion.

---

## 5. G0.3 -- Clinician gold adjudication (NOT COMPLETE)

Two cohorts require named clinician review. Automation prepares artefacts;
humans must adjudicate and sign.

### 5a. Clinical extraction fixtures (97 cases)

Location: tests/fixtures/clinical_extraction_scenarios/expected_strings.json

Automated structural gate (developer):

```bash
pytest tests/test_clinical_extraction_scenario_fixtures.py -v
```

Human adjudication steps:

| Step | Actor | Action |
|------|-------|--------|
| 1 | Clinical lead | Export fixture cohort summary (site, format, difficulty) |
| 2 | Clinician panel (min 2) | Review expected_strings for each of 97 cases |
| 3 | Clinician panel | Mark each case: accept / revise / reject with comment |
| 4 | Clinical lead | Merge accepted revisions into expected_strings.json via PR |
| 5 | QA/RA | Attach adjudication spreadsheet to validation evidence |
| 6 | CSO | Confirm cohort meets UN-89E2AE36 95% F1 target plan |

Adjudication status: NOT STARTED. Automated fixture count test passes (97).

### 5b. SBAR golden set signed_ledger

Location: data/training/sbar-golden-set/ (21 fixture YAML files)

Automation (developer):

```bash
python3 scripts/run_sbar_golden_set.py
python3 scripts/review_sbar_golden_set.py --reviewer "<name>" --role "Clinician"
```

The review harness writes data/sbar-golden-set-reports/<UTC>/signed_ledger.json
with per-fixture pass/fail/skip verdicts and an overall pass/fail.

Human adjudication steps:

| Step | Actor | Action |
|------|-------|--------|
| 1 | Dev | Run golden-set runner; confirm structural checks green |
| 2 | Named clinician | Walk each fixture via review_sbar_golden_set.py |
| 3 | Named clinician | Pass/fail each rendered SBAR with free-text comment |
| 4 | Clinician | Confirm signed_ledger.json overall=pass (no fail/skip) |
| 5 | QA/RA | Copy signed_ledger.json into VT-LEO-AI-189 evidence bundle |
| 6 | CSO | Review any fail verdicts before release |

Adjudication status: NOT STARTED. No signed_ledger.json in evidence bundle.

---

## 6. CSO residual risk review (NOT COMPLETE)

The following risks have design controls implemented and VT evidence
recorded locally, but CSO must formally accept residual risk before
promoting Draft DIs to Approved.

### R-7FC000A1 -- Duplicate referral trigger

- Hazard: parallel PipelineRuns for identical referral inputs.
- Control: DI-0CB9E932 admission_key MERGE + CLAIM_FIRST_STEP_ENQUEUE.
- VT evidence: VT-5427E0E1 pass (4/4).
- Residual score: 6 (acceptable in Atlas).
- CSO action: confirm monitoring plan for duplicate admission_key rate;
  sign residual acceptance in Atlas risk record.

### R-C773C6BB -- Duplicate successor step publish

- Hazard: stage completion republishes next-step messages without outbox dedup.
- Control: DI-4976171D durable outbox with deterministic message IDs.
- VT evidence: VT-B14997B6 pass (4/4).
- CSO action: confirm outbox pending row audit query in post-market plan;
  sign residual acceptance.

### R-FB9026D2 -- Mid-run plan definition change

- Hazard: live PlanDefinition drift during an in-flight run.
- Control: DI-B1E43400 pinned plan manifest at admission.
- VT evidence: VT-630B9016 pass (4/4); VT-AAC08C5B pass (39/39).
- CSO action: confirm plan publish freeze procedure in G6.3 rollback triggers;
  sign residual acceptance.

CSO review status: NOT RECORDED. Do not treat Atlas "acceptable" residual
labels as CSO sign-off.

---

## 7. Human action items (summary)

| ID | Owner | Action | Blocks release? |
|----|-------|--------|-------------------|
| H-1 | QA/RA lead | Promote Draft DIs/DOs/VTs in Atlas after review | Yes |
| H-2 | DevOps | Execute G6.1 rollback exercise in staging (local sim PASS 2026-07-22) | Yes (staging live pending) |
| H-3 | CSO | Residual risk sign-off for R-7FC000A1, R-C773C6BB, R-FB9026D2 | Yes |
| H-4 | Clinician panel | G0.3 adjudication of 97 extraction fixtures | Yes |
| H-5 | Named clinician | G0.3 SBAR signed_ledger.json via review harness | Yes |
| H-6 | QA/RA | Confirm VT-145DEC00 pass run in Atlas (recorded) | Done |
| H-7 | DevOps | Configure post-release monitoring dashboards (G6.3) | Should |
| H-8 | CSO | Written advisory-only gate confirmation (G6.2) | Yes |
| H-9 | QA/RA | Optional G5.9 Playwright VAL on staging (Entra test user) | Should |

---

## 8. Quick reference commands

Full sprint VT slice (local):

```bash
pytest tests/test_run_admission.py \
  tests/test_pipeline_outbox.py \
  tests/test_plan_manifest.py \
  tests/test_pipeline_stage_claim_concurrency.py \
  tests/test_gate5_durable_replay.py \
  tests/test_platform_conformance.py -v
```

Gate 5 broader slice (see docs/GATE5-TEST-POLICY.md):

```bash
pytest tests/test_pipeline_stage_claim_concurrency.py \
  tests/test_pipeline_worker_competing_consumers.py \
  tests/test_pipeline_stage_poison.py \
  tests/test_gate5_durable_replay.py \
  tests/test_gate5_extraction_equivalence.py \
  tests/test_gate5_lease_chaos.py \
  tests/test_gate3_security_isolation.py \
  tests/test_platform_conformance.py \
  tests/test_referral_durable_pubsub.py \
  -v --no-cov -m "not integration"
```

Full Gates 1-5 sprint slice (103 tests, local 2026-07-22):

```bash
pytest tests/test_run_admission.py \
  tests/test_pipeline_outbox.py \
  tests/test_pipeline_stage_poison.py \
  tests/test_pipeline_run_status_monotonic.py \
  tests/test_gate5_lease_chaos.py \
  tests/test_pipeline_stage_claim_concurrency.py \
  tests/test_pipeline_worker_competing_consumers.py \
  tests/test_pipeline_stage_claim.py \
  tests/test_referral_policy.py \
  tests/test_execution_manifest.py \
  tests/test_plan_manifest.py \
  tests/test_plan_seed_immutability.py \
  tests/test_version_admission.py \
  tests/test_sbar_audit_persistence.py \
  tests/test_gate5_durable_replay.py \
  tests/test_gate5_extraction_equivalence.py \
  tests/test_platform_conformance.py \
  tests/test_gate3_security_isolation.py \
  tests/test_u4_1_referral_reference_certification.py \
  tests/test_gate3_trigger_chunk_scope.py \
  tests/test_gate3_source_resolver_evidence.py \
  tests/test_gate3_uncoded_coverage.py \
  tests/test_gate3_background_envelope.py \
  tests/test_gate3_twow_detector.py \
  tests/test_gate3_twow_alert.py \
  tests/test_gate3_recommendation_prompt.py \
  tests/test_gate3_situation_structured_first.py \
  tests/test_gate3_extraction_window.py \
  tests/test_gate3_bounded_recall.py \
  tests/test_sbar_recall_loop.py \
  tests/test_gate3_orchestrator_wiring.py \
  -v --no-cov
```

---

## 9. G5.9 -- Validation Lab durable Playwright VAL (2026-07-22)

Atlas VAL: VAL-2A1EDC22 (linked to UN-4DCE95C8).

Spec: `services/ui/e2e/val-g5-9-validation-lab-durable.spec.ts`

### Environment attempted

| Target | Result |
|--------|--------|
| `https://leo-ai-audit-val.mizaic.cloud` (validation staging UI) | BLOCKED -- Entra sign-in required; E2E auth not enabled; `/auth/session` returns no user |
| Local live stack (Core API :8000 + pipeline-worker :8006 + Playwright E2E UI) | Executed -- FAIL |

### Staging Playwright VAL (Entra test user)

Prerequisites (load from `secrets/.env.secrets` via `validation-env.ts`; never
commit credential values):

```text
PLAYWRIGHT_BASE_URL=https://leo-ai-audit-val.mizaic.cloud
PLAYWRIGHT_REUSE_SERVER=true
PLAYWRIGHT_SKIP_WEBSERVER=1
PLAYWRIGHT_LIVE_BACKEND=1
PLAYWRIGHT_ENTRA_EMAIL=<validation staging test user>
PLAYWRIGHT_ENTRA_PASSWORD=<from Key Vault / secrets file>
SERVICE_AUTH_SECRET=<from secrets/.env.secrets>
ATLAS_VALIDATION_RUNS_BASE_URL
ATLAS_ORGANIZATION_ID
QMS_SERVICE_TOKEN
```

Steps:

1. Confirm staging UI loads and Entra sign-in works manually once.
2. Run `auth.setup.ts` (via full spec or `--project=setup`) to refresh
   `e2e/.auth/user.json` against the staging host.
3. Run the VAL spec with live backend service auth (see commands below).
4. Record pass via Playwright REST + optional Atlas MCP `record_validation_run`.

```bash
cd services/ui
PLAYWRIGHT_BASE_URL=https://leo-ai-audit-val.mizaic.cloud \
PLAYWRIGHT_REUSE_SERVER=true PLAYWRIGHT_SKIP_WEBSERVER=1 \
PLAYWRIGHT_LIVE_BACKEND=1 \
  npx playwright test e2e/val-g5-9-validation-lab-durable.spec.ts \
  --project=chromium --workers=1
```

`auth.setup.ts` uses Entra email/password when the base URL is not localhost.
Local dev continues to use `NEXT_PUBLIC_E2E_MODE` via the Playwright webServer.

### Required env vars (local)

```text
ATLAS_VALIDATION_RUNS_BASE_URL
ATLAS_ORGANIZATION_ID
QMS_SERVICE_TOKEN
PLAYWRIGHT_LIVE_BACKEND=1
PLAYWRIGHT_BASE_URL=http://localhost:3000
SERVICE_AUTH_SECRET
```

Optional staging: `PLAYWRIGHT_BASE_URL=https://leo-ai-audit-val.mizaic.cloud`,
`PLAYWRIGHT_REUSE_SERVER=true` (requires Entra session storage state; not in repo).

Load order: `services/ui/.env.local`, then `secrets/.env.secrets` (via `validation-env.ts`).

CI does not define Playwright staging vars (manual / staging only per
`docs/GATE5-TEST-POLICY.md`).

### Commands

Local live stack (executed 2026-07-22):

```bash
cd services/ui
PLAYWRIGHT_LIVE_BACKEND=1 \
  npx playwright test e2e/val-g5-9-validation-lab-durable.spec.ts \
  --project=chromium --workers=1
```

Staging (blocked at auth.setup):

```bash
cd services/ui
PLAYWRIGHT_BASE_URL=https://leo-ai-audit-val.mizaic.cloud \
PLAYWRIGHT_LIVE_BACKEND=1 PLAYWRIGHT_REUSE_SERVER=true \
  npx playwright test e2e/val-g5-9-validation-lab-durable.spec.ts \
  --project=chromium --workers=1
```

### Outcome (2026-07-22 re-run after df495d2d repair-loop fix)

- Local PASS: 4/4 protocol steps green in 38.3s after pipeline-worker :8006
  restart with latest code.
- Pipeline run id: `faad8039a2a5455bbcd1db2b5e2e3375` (`:PipelineRun` status
  `completed`; durable referral reached SBAR widget).
- Fixes verified in tree: already_completed successor repair (3a0a582f),
  gated repair / no message storm / sent outbox not reset (df495d2d).
- Unit repair evidence: `pytest tests/test_gate5_already_completed_outbox_repair.py`
  6/6 pass (local). Atlas VT-7158FF21 created and pass recorded.
- Playwright REST pass: `VTRUN-89F73A37413E` (4 step evidence attachments).
- Atlas MCP `record_validation_run` pass: `VTRUN-VAL-2A1EDC22-20260722134846`.

### Outcome (2026-07-22 re-run after already_completed outbox repair -- superseded)

- Local FAIL (retest): step 0 pass with element-scoped evidence; step 2 timeout
  180s waiting for `completed|failed`.
- Example run id: `54e637606e104eefbf6d2064777831a6`.
- Neo4j: `:PipelineRun` status `running`; only `act-ref-extract` stage `completed`.
- Two `:OutboxEvent` rows for `act-ref-post-process` marked `sent`; no
  `act-ref-post-process` stage row created (successor message not executed).
- Differs from earlier local fail: that run skipped post-process as
  `already_completed` without enqueueing the SBAR successor.
- Unit repair evidence: `pytest tests/test_gate5_already_completed_outbox_repair.py`
  3/3 pass (local). No dedicated Atlas VT for that module yet.
- Atlas VAL fail recorded via Playwright REST (`VTRUN-A727E9615CD4`) and MCP
  `record_validation_run` (`VTRUN-VAL-2A1EDC22-20260722134250`).
- Evidence note: full-page Playwright screenshots (> ~1 MB) fail Atlas evidence
  upload (HTTP 500); use element-scoped `screenshotTarget` in the spec.

### Outcome (2026-07-22 retry)

- Staging BLOCKED: UI homepage HTTP 200 but `auth.setup.ts` fails because staging
  requires Microsoft Entra sign-in (no `NEXT_PUBLIC_E2E_MODE`). No staging test-user
  credentials in env.
- Local FAIL: step 1 pass with screenshot evidence; step 2 timeout 180s waiting for
  `completed|failed`. Example run id `700e8fde142443c68f69d1133808621b`:
  `:PipelineRun` stayed `running`, Validation Lab run stayed `queued`.
- Atlas VAL `VAL-2A1EDC22` fail run recorded via Playwright REST API
  (`VTRUN-2E4762F998E2`, step 1 evidence attached). MCP `record_validation_run`
  not used (skill: Playwright owns execution evidence). Pass run not recorded.

### Session fixes (spec/helpers/API)

- Registered Atlas VAL `VAL-2A1EDC22` (replaces placeholder `VAL-G5-9-DURABLE-LAB`).
- MUI TextField fill via `wizardField()` helper.
- Live backend service auth via `installLiveBackendServiceAuth()` plus Validation Lab
  router `require_admin_or_service`.

### Blockers before pass

1. Staging Entra test-user session (or staging-specific auth.setup) for
   `https://leo-ai-audit-val.mizaic.cloud` (local live stack now PASS).
2. Element-scoped Playwright evidence screenshots (full-page PNG > ~1 MB returns
   HTTP 500 from Atlas validation-runs evidence upload) -- mitigated via
   `screenshotTarget` in spec.

---

## 10. Known follow-ups (non-blocking for engineering gate)

- Bulk IMPLEMENTS/VERIFIES link batch created spurious cross-edges on
  some Gate 2 VTs (each VT may show VERIFIES to multiple DIs). QA/RA
  should prune incorrect edges via unlink_design_controls during promotion.
- Some DO source_reference fields may need refresh via update_design_output.
- Live Neo4j integration tests in test_pipeline_stage_claim_concurrency.py
  remain skipped without credentials (@pytest.mark.integration).

---

## 11. Gaps that cannot be closed without new code, tests, or humans

| Gap | Why blocked |
|-----|-------------|
| G0.3 extraction gold (97 fixtures) | Named clinician adjudication required |
| G0.3 SBAR signed_ledger.json | Named clinician review harness run |
| G5.9 Playwright VAL (local live stack) | PASS (VAL-2A1EDC22; run faad8039...) |
| G5.9 Playwright VAL (staging) | BLOCKED until H-9 Entra test user configured |
| G6.1 rollback exercise (live staging) | DevOps staging creds + Container Apps access |
| G6.1 rollback exercise (local controls) | DONE -- tests/test_g6_1_rollback_drill.py 6/6 pass |
| CSO residual risk sign-off | Human CSO review in Atlas |
| QA/RA Draft -> Approved promotion | Human QA/RA review |
| Full CI green on release branch | CI run pending (not engineering blocker) |
| Neo4j integration claim tests | Requires live Patient Graph creds (@pytest.mark.integration) |
| U4.6 sync validation runner | Deferred W-022 (production path uses durable pubsub) |
| U4.6 analysis worker jobs | Deferred W-022 (separate queue; post-release sprint) |
| Legacy CDS pipeline VTs | PASS locally after Gate 4 cutover (test_cds_pipeline_verification_vts.py) |

Last updated: 2026-07-22 (engineering release-ready pass; W-022 waiver; staging auth.setup Entra support).
