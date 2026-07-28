<!-- LEO-UM-CG-001 -->
# LEO by Mizaic -- User Manual
## Clinical Guidelines: Loading and Publishing Guideline Rules

| Field | Value |
|---|---|
| Document Reference | LEO-UM-CG-001 |
| Version | 2.1 |
| Date | July 2026 |
| Status | Draft |
| Classification | Internal |
| Atlas VAL | VAL-1963DA04 |
| Atlas UN | UN-49C83395 |
| Atlas coach chrome | DI-LEO-AI-121 (CoachMark / Guide me) |
| Replaces | LEO-UM-CG-001 v2.0 (June 2026) |

---

## 1. Introduction

### 1.1 Purpose

This manual describes how to use the Clinical Guidelines feature within the LEO
Knowledge module. It covers the complete lifecycle for loading NICE clinical
guidelines into LEO, reviewing and editing AI-generated rules, testing rules in a
sandbox environment, and compiling approved rules into a live published model.

The manual reflects the redesigned Clinical Guidelines page introduced in the
Wave E Phase 5 release. The new page uses a status header, a sticky navigation
strip, and four step cards instead of the previous horizontal tab layout.

### 1.2 Intended Audience

This manual is intended for IT Administrators, Knowledge Base Authors, and Quality
Engineers who are responsible for maintaining the clinical guideline rule base
within LEO.

### 1.3 Related User Need

User Need (UN-49C83395): Load, Review, and Publish Guideline Rules
Priority: MUST

Guideline rules must come from approved sources and pass human review before they
go live. Administrators need clear steps to load content, check rules, publish the
model, and keep an audit trail.

### 1.4 Workflow Overview

The Clinical Guidelines workflow is organised into three numbered steps, each
presented as a separate card on the page:

- Step 1 -- Find and load a guideline: Search the NICE catalogue by condition name
  or NICE code and load the guideline into the knowledge graph.
- Inspect -- What is in the knowledge graph: Review guidelines already loaded,
  check chapter and recommendation counts, and ask the AI to generate rules.
- Step 2 -- Check and approve AI-generated rules: Read each AI-suggested rule,
  then click "Looks right", "Edit", or "Reject" for each one.
- Step 3 -- Compile and go live: Bundle approved rules into a versioned compiled
  model and choose which version is active in production.

---

## 2. Navigating to Clinical Guidelines

From the left-hand Knowledge sidebar, select "Clinical Guidelines" under the
"Clinical Knowledge" section.

The page opens showing a summary header, a sticky navigation strip, and four step
cards below.

**Summary header (Status bar)**

Four tiles show the current state at a glance:
- Guidelines loaded -- total number of guidelines in the knowledge graph.
- Rules pending -- total rules waiting for human review across all loaded
  guidelines.
- Rules approved -- total approved rules across all guidelines.
- Active bitmap version -- the version string of the compiled rule model currently
  in production (for example "v20260419-094210", or "--" if none has been published
  yet).

**Navigation strip**

A sticky strip below the header shows four jump links: "1. Load", "Inspect",
"2. Review", and "3. Compile". Click any link to scroll directly to that step card.
The strip stays in view as you scroll down the page.

### 2.1 Guided tour (Guide me)

Use **Guide me** when you are new to this page, or when you want a short
refresher before you train someone else.

**When to use**

- First time on Clinical Guidelines after a release.
- Before you show a Knowledge Base Author how the page works.
- After you open **Edit** on a draft rule (a second tour walks the editor).

**How to run and replay**

1. On the Clinical Guidelines page, click **Guide me** (near Import local
   guideline).
2. Read each tip. The dimmed screen leaves a clear cut-out on the control
   the tip is about.
3. Click **Next** to move on, **Back** to go back, or **Skip tour** to stop.
4. When the tour ends, you can click **Guide me** again anytime to replay it.
5. Inside **Change this rule**, click **Guide me** in the dialog header for
   the editor tour (Who, situations, conditions, preview, save).

**Important: Save is not live**

Saving or approving a rule records the change. Patients do not see it until
someone compiles and makes a bitmap version live (Step 3). The page tour and
the editor tour both remind you of this.

**Screenshot pack (training)**

Step titles and bodies match the in-product tour
(`services/ui/src/app/admin/guidance/guidanceTourSteps.ts`). Approved
viewport screenshots live under
`compliance/policy/assets/leo-um-cg-001/`.

**Act A -- page tour**

| Step id | Title | Asset |
|---|---|---|
| cg-01-jump | Four steps on this page | [cg-01-jump.png](assets/leo-um-cg-001/cg-01-jump.png) |
| cg-02-load | Bring a guideline in | [cg-02-load.png](assets/leo-um-cg-001/cg-02-load.png) |
| cg-03-inspect | Check what loaded | [cg-03-inspect.png](assets/leo-um-cg-001/cg-03-inspect.png) |
| cg-04-review-pool | Rules waiting for you | [cg-04-review-pool.png](assets/leo-um-cg-001/cg-04-review-pool.png) |
| cg-05-card | Check the wording | [cg-05-card.png](assets/leo-um-cg-001/cg-05-card.png) |
| cg-06-compile | Save is not live yet | [cg-06-compile.png](assets/leo-um-cg-001/cg-06-compile.png) |

**Act B -- edit rule tour**

| Step id | Title | Asset |
|---|---|---|
| er-01-stepper | Who, Suggest, Save | [er-01-stepper.png](assets/leo-um-cg-001/er-01-stepper.png) |
| er-02-quote | Keep the guideline in view | [er-02-quote.png](assets/leo-um-cg-001/er-02-quote.png) |
| er-03-always | Always-true checks | [er-03-always.png](assets/leo-um-cg-001/er-03-always.png) |
| er-04-situations | Confirm the split | [er-04-situations.png](assets/leo-um-cg-001/er-04-situations.png) |
| er-05-conditions | Match every line | [er-05-conditions.png](assets/leo-um-cg-001/er-05-conditions.png) |
| er-06-review | Check the meaning | [er-06-review.png](assets/leo-um-cg-001/er-06-review.png) |
| er-07-save | Say why, then approve | [er-07-save.png](assets/leo-um-cg-001/er-07-save.png) |

**Engineering photo review (chromium pack, 2026-07-28)**

Pass means: target visible in the cut-out; copy matches the visible UI; tip
does not cover the target title; Act B step matches the wizard phase.

| Asset | Result |
|---|---|
| cg-01-jump through cg-06-compile | Pass |
| er-01-stepper through er-07-save | Pass |

Regenerate the working pack with:

```bash
cd services/ui && npx playwright test guideline-tab-ifu-screenshots --project=chromium
```

Copy approved PNGs into `compliance/policy/assets/leo-um-cg-001/` only after
a fresh photo review. Do not let CI overwrite signed assets silently.

**Trainer sign-off (required before Status = Approved)**

A Knowledge Base Author or Clinical Lead must run Guide me once on staging
with a real loaded guideline, then complete the form below. Customer-facing
IFU-LEO-CDS-001 training communication stays with CSM after this UM is
Approved (see SVP-LEO-CDS-001).

| Check | Pass / Fail | Notes |
|---|---|---|
| Every page-tour step spotlighted the correct control | | |
| Every editor-tour step matched the wizard phase on screen | | |
| No step described UI that was not on screen | | |
| Save is not live message was clear | | |
| Replay worked after completion (Guide me again) | | |

| Field | Value |
|---|---|
| Signer name | |
| Role | Knowledge Base Author / Clinical Lead |
| Staging environment / build | |
| Date | |
| Signature / approval | |

Until this form is complete, keep Status = Draft.

---

## 3. Step 1: Find and Load a Guideline

### 3.1 Refresh the Guideline Catalogue

Before searching, refresh the NICE guideline catalogue to make sure the latest
published guidelines are available.

1. Click "Refresh guideline list" in the top-right toolbar of the Load card.
2. The button shows a loading state while the catalogue is updated.
3. A green confirmation banner appears showing how many guidelines are now
   available (for example "Catalogue updated. 3,690 guidelines now available to
   search."). Dismiss the banner by clicking the close icon.

### 3.2 Browse by Clinical Area

If you prefer to explore guidelines by condition area rather than searching by
name or code, click "Browse by area". A side panel opens showing a hierarchy of
clinical domains. Click a domain to expand it, then select a guideline to
auto-fill the search field.

### 3.3 Search and Load a Guideline

1. Type a condition name or NICE code into the search field (for example "ng12" or
   "bowel cancer"). The field accepts partial names and full NICE codes such as
   NG12, CG89, and TA123.
2. Click "Load this guideline". The button is only active when a valid NICE code is
   in the field. If you have typed a condition name, the system validates it against
   the catalogue before enabling the button.
3. A progress strip appears below the search field, showing the current step (for
   example "Fetching recommendations..."). Click "Show progress details" to see the
   full log.
4. When loading completes, a green "Done. Loaded N recommendations." banner
   replaces the progress strip.
5. The "Recent loads" table below updates to show the completed job, including the
   guideline code, current step, status, recommendation count, and date.

**Important:** Loading a guideline does not generate rules. Rules are generated
separately in the Inspect section below.

### 3.4 Recent Loads Table

The Recent loads section shows a compact table of load jobs. Each row shows:
- Code -- the NICE code as a blue chip (for example NG12).
- Step -- the last step completed during the load job.
- Status -- "done" (green), "error" (red), or in-progress (grey).
- Recommendations -- the number of recommendations loaded.
- Date -- when the job completed.

If no jobs have been run yet, an empty state message reads "No recent loads.
Loaded guidelines appear here."

---

## 4. Inspect -- What Is in the Knowledge Graph

The Inspect card shows all guidelines currently loaded in LEO's knowledge graph.
It sits between the Load card and the Review card.

Each guideline is shown as a row in a list. The row shows:
- A blue code chip (for example NG12).
- The guideline title.
- Chapter count and recommendation count.
- Guidance type (for example "evidence-based recommendations").
- A rule status badge showing "No rules yet", "Pending (N)", "Approved (N)", or
  a combined count where rules exist in multiple states.

### 4.1 Generate Rules

To ask the AI to write decision criteria for each recommendation:

1. Locate the guideline row and click "Generate rules". If the guideline already
   has rules, the button shows "Re-generate" in amber.
2. If you click "Re-generate", a confirmation dialog appears: "This will delete all
   draft rules for [code] and ask the AI to write new ones. Rules you have already
   approved will also be deleted. Are you sure?" Click "Yes, re-generate" to
   confirm, or "Cancel" to go back.
3. The button shows "Generating..." with a spinner while the AI processes each
   recommendation. The rule status badge updates when generation completes.

Generating rules can take one to two minutes for guidelines with many
recommendations. You do not need to stay on the page -- the job runs in the
background.

### 4.2 Inspect the Knowledge Graph for a Guideline

Click the graph icon button on any guideline row to open the Inspect side panel.
The panel shows the full Neo4j subgraph for that guideline: chapters,
recommendations, and any linked rule nodes. This view helps you verify that the
correct data was loaded before moving to review.

Close the panel by clicking the X or clicking outside it.

---

## 5. Step 2: Check and Approve AI-Generated Rules

### 5.1 The Rule Review Queue

After generating rules, scroll to the "Check and approve AI-generated rules" card
(Step 2) or click "2. Review" in the navigation strip.

Three filter tabs appear at the top of the review card:
- Pending review -- rules waiting for a decision. This is the default view.
- Active -- rules that have been approved and are ready for the next compile.
- Superseded -- rules replaced by a newer version following an edit. Read-only
  history.

A count line below the filter shows how many rules are in the current view (for
example "4 rules to check -- click a row to read in full").

### 5.2 Reading a Rule

Click any rule row to expand it. The expanded row shows:
- The original NICE recommendation text.
- The AI-generated rule logic in plain English, including patient criteria and the
  recommended action (for example "offer urgent chest X-ray").
- The chapter the recommendation belongs to.
- When the rule was last updated.

Click the row again to collapse it.

### 5.3 Approving, Editing, or Rejecting a Rule

Three action buttons appear in each unexpanded rule row:

**Looks right** -- Approves the rule as generated. The rule moves to the Active
tab and is included in the next compile.

**Edit** -- Opens the four-step rule editor (see Section 5.4 below).

**Reject** -- Rejects the rule. It will not be included in any compiled model.
Rejected rules do not appear in the Pending or Active tabs.

**Approve all** -- When rules are in the Pending review tab, an "Approve all"
button appears in the top-right of the review area. Clicking it shows a
confirmation dialog: "This will approve all N rules and make them ready to
compile. Only approve rules you have read and checked." Click "Yes, approve all"
to confirm. Use this only after individually reading each rule.

### 5.4 Editing a Rule

Clicking "Edit" opens a guided four-step dialog. A live preview panel on the right
updates in plain English as you make changes.

**Step 1: Who is this rule about?**

This step defines the patient criteria -- the symptoms, signs, or findings a
patient must have for the rule to fire.

Click "+ Add the first symptom" to start. A search field appears. Type a term
(for example "chest x") to search the clinical terminology. A dropdown shows
matching SNOMED concepts with their clinical codes and semantic types. Click
"Use this" next to the appropriate concept.

For complex NICE recommendations, the editor supports multi-pathway logic:
- The "Patient must have" section defines criteria that apply to all pathways
  (for example age >= 40 years).
- The "Patient must match one of these pathways" section lets you define
  alternative clinical scenarios, each as a named pathway (A, B, C, etc.).
- Within each pathway, symptom groups can be set with threshold logic (for
  example "Any 2 or more of these").
- Individual symptoms appear as green pills. Click the X on a pill to remove it.
- Click "+ Add pathway" to add another pathway.
- Click the bin icon on a pathway to delete it.

The live preview updates in real time so reviewers can confirm the rule matches
the NICE recommendation text without reading the structured editor directly.

**Step 2: What should the system suggest?**

This step defines what the system should recommend when the rule matches.

The recommended action appears as a green pill (for example "Fast track referral
for suspected lung cancer"). Hover over the pill to see the SNOMED code. Click the
pill to swap it for a different procedure.

**Step 3: Test your change safely**

Before saving, test the rule change against test patients in a sandbox
environment. Production data is never touched.

Two options are available:
- "Author with AI from this rule" -- the AI drafts a synthetic test patient note
  designed to trigger the rule. Review the note and save it as a test patient.
- "Open in Test Patient Library" -- select from existing test patients in the
  central library.

After running the sandbox test, a test report shows whether the rule matched as
expected. A failed test shows exactly which criteria did not match (red cross). A
passed test confirms all saved checks matched (green tick).

**Step 4: Save your change**

Enter a reason for the change (minimum 3 characters). A "Before and After" panel
shows the previous and new rule definitions side by side.

Click "Save" to save the change. The rule returns to pending-review state and
must be approved before it affects any compiled model.

---

## 6. Step 3: Compile and Go Live

Once rules have been approved, scroll to the "Compile and go live" card (Step 3)
or click "3. Compile" in the navigation strip.

### 6.1 Compile Settings

The compile settings are shown as filter chips at the top of the compile card:

- Scope type -- "Global" (applies to all tenants) or another scope type such as
  "Guideline", "Domain", "Subdomain", or "Custom".
- Policy -- "Advisory" or "Strict".

Click a chip to change the value before compiling.

### 6.2 Compiling Rules

1. Check the four summary tiles at the top of the compile card:
   - Active version -- the version string currently in production.
   - Active rules -- how many rules are included in the active model.
   - Pending -- how many approved rules are waiting to be compiled.
   - Last test replay -- regression test results for the current version.
2. Click "Compile rules" to create a new compiled version.
3. A progress strip appears showing the compile steps ("Rules approved",
   "Compile rules", "Go live"). The strip shows the active step and a step count.
4. When the compile completes, the new version appears in the "All compiled
   versions" list below.

### 6.3 Publishing a Version

1. In the "All compiled versions" list, locate the version you want to make live.
2. Click "Make this live" to promote that version to production.
3. The "Active version" tile in the header updates to show the new version string.

Only one version can be live at a time. If a compile fails, the system keeps the
last active published model. The "Rollback scope" button allows reverting to a
previous version if needed.

---

## 7. Audit Trail

All actions within the Clinical Guidelines workflow are recorded in an audit log.
This includes:
- Guideline catalogue refreshes.
- Guideline loads (success and failure).
- Rule generation events.
- Individual rule decisions (approve, edit, reject).
- Rule compilations.
- Publish and rollback actions.

Each entry records the user, the timestamp, the action performed, and the
outcome. This provides full traceability for regulatory compliance and quality
management.

---

## 8. Key Concepts

**NICE Guideline** -- A clinical guideline published by the National Institute for
Health and Care Excellence, containing evidence-based recommendations for patient
care.

**Recommendation** -- An individual clinical recommendation within a NICE guideline
chapter.

**Rule** -- A machine-readable decision criterion linking patient facts (symptoms,
signs, findings) to a recommended clinical action. Rules are generated by AI and
reviewed by humans.

**Pending Review** -- A rule that has been AI-generated but not yet approved,
edited, or rejected by a human reviewer.

**Active** -- An approved rule included in the current compiled model.

**Superseded** -- A rule that has been replaced by a newer version following an
edit.

**Compiled Model** -- A versioned, immutable snapshot of all approved rules, ready
to be published.

**Sandbox** -- An isolated test environment where rule changes can be validated
against test patients without affecting production.

**Bitmap** -- The compiled rule lookup index used at runtime to evaluate whether a
patient episode triggers a guideline recommendation.

---

## 9. Troubleshooting

| Issue | Cause | Action |
|---|---|---|
| "Load this guideline" button is greyed out | The field does not contain a valid NICE code | Make sure the code follows the pattern NG12, CG89, TA123, etc. |
| Catalogue sync shows "Sync failed. Check the API key and try again." | The NICE API key is missing or expired | Contact your IT administrator to check the NICE API configuration. |
| Rule generation finishes but no rules appear | The guideline has no structured recommendations that the AI can parse | Review the guideline on the NICE website. Some guidelines (for example quality standards) do not contain rule-ready recommendations. |
| "Could not load rules to review. Please try again." | A temporary network error | Refresh the page. If the error persists, contact support. |
| "Compile rules" button produces an error | There are no approved rules to compile, or a previous compile job is still running | Check that at least one rule has been approved and that no compile is already in progress. |
| "Make this live" does not update the active version | The request failed | Refresh the page and try again. Check the Recent Activity panel for errors. |
