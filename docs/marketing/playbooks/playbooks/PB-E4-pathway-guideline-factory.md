# PB-E4 -- Pathway and guideline factory

Catalogue reference: Module E4, "Pathway and guideline factory" -- rules,
minimum data sets, shadow checks
(`docs/marketing/build_coo_service_catalogue.py`, `module_menu()`). Bundled
into Package A (Elective SPoA Accelerate).

Tier: 1 (full playbook). Audience: internal delivery / solutions
consultants configuring clinical knowledge for a new pathway.

## 1. Purpose and buyer outcome

**For the COO / CSO / Digital lead:** by the end of this playbook, a named
clinical pathway (for example, suspected lower GI cancer) has an approved,
compiled, live rule set and a clinically signed-off minimum dataset, so
every referral or A&G request on that pathway gets consistent guideline
matching and completeness checking -- not ad hoc, unreviewed AI judgement.

**What "done" looks like:**

- The target NICE guideline is loaded, its AI-generated rules are reviewed
  and approved by a human, and a compiled version is live in production.
- A minimum dataset (domain/subdomain) exists for the pathway, has passed
  clinical review, and is active.
- Test evidence exists for both the rules and the minimum dataset before
  go-live.
- Production referral traffic carries the approved
  `completeness_domain`/`completeness_subdomain`.

## 2. Preconditions and non-negotiable safety gate

- Platform readiness (Phase 1 of LEO-OP-001) is complete: terminology
  synced, admin UI accessible.
- **No minimum dataset or compiled rule set may reach production without
  recorded Clinical Reviewer and Approver sign-off.** This is enforced by
  procedure, not by the UI -- the Platform Administrator must not activate a
  schema or publish a compiled version without that sign-off on the change
  record
  ([compliance/policy/LEO-OP-001-customer-pathway-onboarding-procedure.md](../../../../compliance/policy/LEO-OP-001-customer-pathway-onboarding-procedure.md)
  section 8, "mandatory clinical review and approval gates").
- Uncompiled or unapproved rules mean an **empty Assessment section** in
  every SBAR for that pathway -- rule compilation and approval are both
  mandatory, not just one or the other
  ([compliance/policy/LEO-UM-CG-001-clinical-guidelines-user-manual.md](../../../../compliance/policy/LEO-UM-CG-001-clinical-guidelines-user-manual.md)
  section 7.2).

## 3. Roles

| Playbook role | Canonical app role / QMS role | Responsibility here |
|---|---|---|
| Requester (customer clinical lead) | -- (customer-side) | Describes the pathway, proposes required information groups, supplies sample referrals |
| Platform Administrator | `platform_admin` | Loads guidelines, generates and compiles rules, drafts minimum dataset schema |
| Clinical Reviewer | `pathway_supervisor` or named clinician (customer or CSO delegate) | Reviews AI-generated rules and minimum dataset groups for clinical correctness |
| Approver | Quality Manager or Clinical Safety Officer | Approves activation/publish to production |
| Release Coordinator | `pipeline_operator` | Confirms production queue messages carry the approved domain/subdomain |

The person who drafts the schema must not be the only clinical reviewer --
keep drafting and review independent where possible
(`compliance/policy/SVP-LEO-CDS-001-service-plan.md` section 13.1).

## 4. Step-by-step phases

### Phase 1 -- Readiness

**Entry criteria:** platform readiness confirmed.

1. Open **Knowledge** in the admin UI (`/admin/knowledge`).
2. Under Data Setup, select **Terminology** and confirm packages show as
   loaded.
3. Under Clinical Knowledge, select **Clinical Guidelines** and confirm the
   summary header shows guideline and rule counts without error banners.
4. Record readiness confirmation on the customer's change record.

**Exit criteria:** terminology and guideline pages both load without error.

### Phase 2 -- Surface forms and guideline loading

**Entry criteria:** Phase 1 complete.

1. **Surface forms:** open **Knowledge > Surface Forms**, search for key
   terms the pathway uses, add and approve missing aliases, and run the
   duplicate audit function
   (`compliance/policy/LEO-OP-001-customer-pathway-onboarding-procedure.md`
   section 7.1). See rehearsal evidence:
   `services/ui/e2e/val-surface-forms-d681ea88.spec.ts` (VAL-D681EA88).
2. **Guideline load:** open **Knowledge > Clinical Guidelines**. Click
   "Refresh guideline list", then search by NICE code (for example `NG12`)
   or condition name and click "Load this guideline". Confirm the "Done.
   Loaded N recommendations." banner and the Recent Loads table entry
   (`compliance/policy/LEO-UM-CG-001-clinical-guidelines-user-manual.md`
   section 3).
3. **Rule generation:** in the Inspect card, click "Generate rules" for the
   loaded guideline (takes 1-2 minutes; runs in the background).

**Exit criteria:** surface forms approved for the pathway's key terms; the
target guideline shows a "Pending (N)" rule badge.

### Phase 3 -- Rule review (mandatory human gate)

**Entry criteria:** Phase 2 complete; rules generated.

1. Open the "Check and approve AI-generated rules" card (Step 2). Default
   view is the Pending review tab.
2. Click each rule row to expand it. Read the original NICE recommendation
   text against the AI-generated rule logic (patient criteria + recommended
   action).
3. For each rule: click **Looks right** to approve, **Edit** to correct via
   the four-step guided editor (patient criteria -> recommended action ->
   sandbox test -> save with reason), or **Reject**.
4. Do **not** use "Approve all" without having individually read every rule
   first -- the confirmation dialog exists precisely to stop that shortcut.
5. For any edited rule, run the sandbox test (Step 3 of the rule editor)
   against a synthetic or library test patient before saving
   (`LEO-UM-CG-001` section 5.4).

**Exit criteria:** every generated rule for the pathway is in the Active or
Superseded state -- none left in Pending review.

### Phase 4 -- Compile and publish

**Entry criteria:** Phase 3 complete; all rules for the pathway approved.

1. Open the "Compile and go live" card (Step 3). Confirm the scope type
   (Global or a narrower scope) and policy (Advisory or Strict) chips.
2. Click "Compile rules". Wait for the progress strip to complete.
3. In "All compiled versions", locate the new version and click "Make this
   live". Confirm the "Active version" tile updates.
4. If a compile fails, the previous active version stays live automatically
   -- use "Rollback scope" if you need to revert deliberately
   (`LEO-UM-CG-001` section 6.3).

**Exit criteria:** the new compiled version is the active production
version for this pathway's scope.

### Phase 5 -- Minimum dataset (domain/subdomain) configuration

**Entry criteria:** Requester has supplied the clinical source for required
information and sample anonymised referrals
(`compliance/policy/DC-GOV-001-service-minimum-dataset-onboarding-procedure.md`
section 5.1).

1. Open **Knowledge > Domains**. Create a new domain (for example "Cancer
   referrals") or open an existing one, then "Add subdomain" (for example
   `lower_gi`).
2. On the subdomain's Configure panel: use the **Overview** tab for
   milestone type, time window, and semantic tags; the **Concepts** tab to
   add SNOMED concepts; the **Rules** tab to build completeness criteria
   groups (name, required flag, concepts, semantic categories).
3. Do **not** activate the schema yet. Rehearsal evidence:
   `services/ui/e2e/val-completeness-domains-4d70e63c.spec.ts`
   (VAL-4D70E63C).
4. Send the draft schema and clinical rationale to the Clinical Reviewer.

**Exit criteria:** draft schema exists, unactivated, with a rationale
document ready for clinical review.

### Phase 6 -- Clinical review (mandatory)

**Entry criteria:** Phase 5 complete.

1. Clinical Reviewer checks each required group reflects clinically
   necessary information for triage -- not too broad (false completeness)
   and not too narrow (missed required items).
2. Clinical Reviewer records **Approved**, **Approved with conditions**, or
   **Rejected** on the change record.
3. If rejected or conditional, return to Phase 5. Do not proceed.

**Exit criteria:** recorded Clinical Reviewer sign-off on the change record.

### Phase 7 -- Preview and test evidence (mandatory)

**Entry criteria:** Phase 6 sign-off recorded.

1. Run schema preview:
   `POST /analytics/domains/{id}/subdomains/{name}/schema/preview` against
   sample patient facts. Save the output (present/missing groups).
2. Run at least one of: an AI Summarisation scenario batch for the target
   domain/subdomain, a sample referral batch through the pipeline, or a
   documented review of the widget completeness panel on representative
   cases.
3. Record test evidence on the change record (`DC-GOV-001` section 8 sets
   the minimum content per evidence type -- schema preview output, run IDs,
   case IDs, or screenshots, depending on the evidence type chosen).

**Exit criteria:** preview evidence and at least one test evidence type
recorded and linked to the change record.

### Phase 8 -- Approval and activation

**Entry criteria:** Phase 7 evidence complete.

1. Approver reviews Clinical Reviewer sign-off, preview output, and test
   evidence, then records approval on the change record.
2. Platform Administrator activates the schema:
   `PUT /analytics/domains/{domain_id}/subdomains/{name}/schema`.
3. Confirm `completeness_schema_active` is true and the
   `save_completeness_schema` audit entry was written
   (`services/analytics_api/app/routers/domains.py`,
   `_record_domain_config_audit`).
4. Release Coordinator confirms production `referral-received` messages
   carry the approved `completeness_domain` and `completeness_subdomain`
   (see PB-E3 Phase 1 for the trigger-side confirmation).

**Exit criteria:** schema active in production; audit entry confirmed;
Release Coordinator has verified production message shape.

### Phase 9 -- Integration smoke test and go-live

**Entry criteria:** Phases 4 and 8 both complete for this pathway.

1. Run an AI Summarisation scenario batch using the target
   domain/subdomain and confirm completeness findings appear in the run
   results (`LEO-OP-001` section 9.1). Cross-reference PB-E3 Phase 3 for
   the same evidence from the integration side.
2. Approver confirms Phases 1-8 evidence is complete on the change record.
3. Customer clinical lead confirms the go-live date; Release Coordinator
   enables production traffic for the pathway.

**Exit criteria:** production traffic enabled; go-live approval recorded.

### Phase 10 -- Post-activation monitoring (first 30 days)

Monitor: completeness panel results on live referrals, support tickets
about missing or incorrect completeness flags, clinical safety escalations
linked to configuration, and failed message counts in the operations queue.
Escalate to the Clinical Safety Officer if a schema or guideline
configuration issue may have affected live clinical review
(`LEO-OP-001` section 10).

## 5. Tools and UI paths

| Task | UI path / endpoint |
|---|---|
| Surface forms | `/admin/knowledge` > Surface Forms |
| Clinical guidelines (load, review, compile) | `/admin/knowledge` > Clinical Guidelines |
| Domains and subdomains | `/admin/knowledge` > Domains (`/settings/domains`) |
| Schema preview | `POST /analytics/domains/{id}/subdomains/{name}/schema/preview` |
| Schema activation | `PUT /analytics/domains/{domain_id}/subdomains/{name}/schema` |
| Domain/subdomain create | `POST /analytics/domains`, `POST /analytics/domains/{domain_id}/subdomains` |
| AI Summarisation scenario runs | `/admin/knowledge` > AI Summarisation > Scenario runs |
| Command palette (jump to any tab) | Cmd+K / Ctrl+K |

## 6. Evidence to capture

- Surface form approval log (Phase 2), with rehearsal reference
  VAL-D681EA88 if the customer's own manual is not yet ready.
- Guideline load record and rule review decisions (Phases 2-3): every rule's
  approve/edit/reject decision is already captured in the audit trail
  automatically (`LEO-UM-CG-001` section 7).
- Compiled version string and "Make this live" confirmation (Phase 4).
- Draft schema JSON, Clinical Reviewer sign-off, preview output, and test
  evidence (Phases 5-7), with rehearsal reference VAL-4D70E63C.
- Approver sign-off and `save_completeness_schema` audit entry (Phase 8).
- Integration smoke test run IDs (Phase 9), shared with PB-E3's evidence
  set for the same pathway.

## 7. Risks and rollback

| Risk | Mitigation |
|---|---|
| Rules approved without individual read (rubber-stamped via "Approve all") | Procedure text explicitly warns against this; the confirmation dialog is a control point, not a shortcut. |
| Compiled version breaks a rule that worked before | "Rollback scope" reverts to the last known-good published version; a failed compile does not overwrite the active model automatically. |
| Minimum dataset activated without clinical review | Hard procedural gate in `LEO-OP-001` and `DC-GOV-001` -- Platform Administrator must not activate without a recorded Clinical Reviewer sign-off. |
| Schema change breaks existing coded referrals | Existing `:Assessment` nodes are not retroactively updated; only new referrals use a revised schema (`DC-GOV-001` section 6.4). |
| Emergency clinical safety change needed outside normal review timeline | CSO or delegate can approve an expedited change in writing; full retrospective review must complete within 5 working days (`DC-GOV-001` section 6.5). |

## 8. Source index

- [compliance/policy/LEO-OP-001-customer-pathway-onboarding-procedure.md](../../../../compliance/policy/LEO-OP-001-customer-pathway-onboarding-procedure.md)
- [compliance/policy/LEO-UM-CG-001-clinical-guidelines-user-manual.md](../../../../compliance/policy/LEO-UM-CG-001-clinical-guidelines-user-manual.md)
- [compliance/policy/DC-GOV-001-service-minimum-dataset-onboarding-procedure.md](../../../../compliance/policy/DC-GOV-001-service-minimum-dataset-onboarding-procedure.md)
- `services/ui/e2e/val-surface-forms-d681ea88.spec.ts` (VAL-D681EA88)
- `services/ui/e2e/val-completeness-domains-4d70e63c.spec.ts` (VAL-4D70E63C)
- `services/ui/e2e/val-guideline-workflow-1963da04.spec.ts` (VAL-1963DA04)
- [services/design-system/src/roles/types.ts](../../../../services/design-system/src/roles/types.ts)

## 9. Open gaps

- **`LEO-UM-SF-001` and `LEO-UM-DO-001` are missing.** This playbook's
  Phase 2 (surface forms) and Phase 5 (domains) steps are drawn from
  `LEO-OP-001` and `DC-GOV-001`, which already contain enough procedural
  detail to run the steps, plus the Validation Lab rehearsal specs listed
  above. There is no separate illustrated user manual for either area yet
  -- see [../GAPS-AND-BLOCKERS.md](../GAPS-AND-BLOCKERS.md).
- No written guidance exists yet for choosing *which* pathway to configure
  first beyond the Elective SPoA priority-10 specialty list (see
  [../NHS-POLICY-EXTRACTS.md](../NHS-POLICY-EXTRACTS.md)) -- this is
  currently a consulting judgement call, informed by Module E0's readiness
  diagnostic.
