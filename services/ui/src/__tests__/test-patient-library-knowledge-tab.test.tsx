/**
 * VT-5BDFE5F7 -- Knowledge tab Test Patients surface, Phase A.
 *
 * Static-source verification of:
 *   - The Knowledge page registers the Test Patients tab (tab key,
 *     label, panel binding).
 *   - The Knowledge tab copy carries plain-English "default" /
 *     "clinician" / "staff" intro blocks (UK reading age 11 audience
 *     standard from .cursor/rules/health-literacy.mdc).
 *   - The new /admin/knowledge/test-patients page renders the four
 *     count tiles, the aspect filter, and the table column headers
 *     called out in the DI acceptance criterion.
 *   - The legacy /admin/guidance/test-patients route file is deleted.
 *
 * Static-source rather than live-render: the page hits the network
 * on mount, and the design-controls rule mandates static-source VTs
 * for any page that fetches on mount.
 *
 * Atlas IDs: UN-50102672, DI-7625C251, R-8C0CC94B, VT-5BDFE5F7.
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, rel), "utf8");
}

function exists(rel: string): boolean {
  return fs.existsSync(path.join(REPO_ROOT, rel));
}

describe("VT-5BDFE5F7 - Knowledge > Test Patients tab (Phase A)", () => {
  test("TC-001: Knowledge page registers the test-patients tab", () => {
    const src = read("services/ui/src/app/admin/knowledge/page.tsx");
    expect(src).toMatch(
      /\{\s*key:\s*"test-patients"\s*,\s*label:\s*"Test Patients"\s*\}/,
    );
    expect(src).toMatch(/"test-patients":\s*TestPatientsPage/);
    expect(src).toMatch(/"test-patients":\s*"wide"/);
    expect(src).toMatch(
      /import\("@\/app\/admin\/knowledge\/test-patients\/page"\)/,
    );
  });

  test("TC-002: Knowledge tab copy carries plain-English intro blocks", () => {
    const src = read("services/ui/src/lib/knowledgeCopy.ts");
    // The KnowledgeTabKey union includes the new key.
    expect(src).toMatch(/\|\s*"test-patients"/);
    // The copy block is present and uses sentence-case labels.
    expect(src).toMatch(/"test-patients":\s*\{/);
    expect(src).toMatch(/title:\s*"Test Patients"/);
    // Extract the block by slicing from the test-patients key to the
    // next sibling key (terminology) -- avoids brittle nested regexes.
    const startIdx = src.indexOf('"test-patients":');
    const endIdx = src.indexOf("terminology:", startIdx);
    expect(startIdx).toBeGreaterThan(0);
    expect(endIdx).toBeGreaterThan(startIdx);
    const text = src.slice(startIdx, endIdx);
    // Audience-grade blocks present (default + clinician + staff).
    expect(text).toMatch(/default:\s*\{/);
    expect(text).toMatch(/clinician:\s*\{/);
    expect(text).toMatch(/staff:\s*\{/);
    expect(text).toMatch(/qa_ra_lead:\s*\{/);
    // Plain-English markers: no IT jargon in the default block.
    const defaultStart = text.indexOf("default: {");
    const defaultEnd = text.indexOf("clinician:", defaultStart);
    expect(defaultStart).toBeGreaterThan(-1);
    expect(defaultEnd).toBeGreaterThan(defaultStart);
    const defaultText = text.slice(defaultStart, defaultEnd);
    expect(defaultText).not.toMatch(/regression/i);
    expect(defaultText).not.toMatch(/fixture/i);
    expect(defaultText).not.toMatch(/aspect/i);
  });

  test("TC-003: Test Patients page uses canonical design-system primitives", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/page.tsx",
    );
    // The page is a sibling of /admin/pathways and must use the same
    // Knowledge tab primitives so the visual rhythm of the tabs is
    // consistent. See DI-LEO-AI-150 for the canonical pattern.
    expect(src).toMatch(/from\s+"@leo\/design-system"/);
    expect(src).toMatch(/StatHero/);
    expect(src).toMatch(/SegmentedTabs/);
    expect(src).toMatch(/ToolbarActions/);
    expect(src).toMatch(/DataGridCard/);
    // Filter exposes one tab per aspect, driven by ASPECT_VALUES so
    // the source of truth stays in types.ts.
    expect(src).toMatch(/ASPECT_VALUES\.map/);
    expect(src).toMatch(
      /aria-label="Filter test patients by AI aspect"/,
    );
    // Copy-from-real and Build actions surface in the toolbar.
    expect(src).toMatch(/id:\s*"copy-from-real"/);
    expect(src).toMatch(/id:\s*"build-patient"/);
    expect(src).toMatch(/Copy from a real patient/);
    // The duplicate page-level title is gone -- KnowledgePageLayout
    // already renders the intro from KNOWLEDGE_TAB_COPY.
    expect(src).not.toMatch(/<Typography[^>]*variant="h6"[^>]*>\s*Test patients/);
  });

  test("TC-004: aspect type defines all four AI aspects + 'all'", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/types.ts",
    );
    expect(src).toMatch(
      /ASPECT_VALUES\s*=\s*\[\s*"all",\s*"nlp",\s*"episodes",\s*"guidelines",\s*"summarisation",?\s*\]/,
    );
    // Plain-English labels for the audience standard.
    expect(src).toMatch(/nlp:\s*"Reading notes"/);
    expect(src).toMatch(/episodes:\s*"Patient story"/);
    expect(src).toMatch(/guidelines:\s*"Rule checks"/);
    // Renamed in the NG12 / referral-triage pass: the SBAR aspect IS
    // the referral-triage aspect (the SBAR transcript is the deliverable
    // and the action priority is the triage outcome). The label says so.
    expect(src).toMatch(/summarisation:\s*"SBAR \/ referral triage"/);
  });

  test("TC-005: api client points at the centralised endpoints", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/api.ts",
    );
    expect(src).toMatch(/\/api\/guidance\/test-patients/);
    expect(src).toMatch(/\/aspect-counts/);
    expect(src).toMatch(/\/source-patients/);
    expect(src).toMatch(/\/clone/);
    // Bulk replay is batched so the proxy does not time out on large cohorts.
    expect(src).toMatch(/REPLAY_BATCH_SIZE/);
    expect(src).toMatch(/replayInBatches/);
    expect(src).toMatch(/mergeReplayReports/);
    // The list endpoint passes the aspect query param when set.
    expect(src).toMatch(/qs\.set\("aspect"/);
  });

  test("TC-007: page mounts both Build and Copy dialogs and wires the toolbar", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/page.tsx",
    );
    expect(src).toMatch(/from\s+"\.\/BuildPatientDialog"/);
    expect(src).toMatch(/from\s+"\.\/CopyFromRealDialog"/);
    expect(src).toMatch(/onClick:\s*\(\)\s*=>\s*setBuildOpen\(true\)/);
    expect(src).toMatch(/onClick:\s*\(\)\s*=>\s*setCopyOpen\(true\)/);
    expect(src).toMatch(/onCreated=\{[^}]*setRefreshKey/);
    expect(src).toMatch(/onCloned=\{[^}]*setRefreshKey/);
  });

  test("TC-008: BuildPatientDialog covers the three non-Guideline aspects", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/BuildPatientDialog.tsx",
    );
    expect(src).toMatch(
      /BUILDABLE_ASPECTS:\s*BuildableAspect\[\]\s*=\s*\[\s*"nlp",\s*"episodes",\s*"summarisation",?\s*\]/,
    );
    expect(src).toMatch(/initialAspect === "guidelines"/);
    expect(src).toMatch(/buildBlankTestPatient\(/);
    expect(src).toMatch(/test_/);
  });

  test("TC-009: CopyFromRealDialog runs the cross-graph clone path", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/CopyFromRealDialog.tsx",
    );
    expect(src).toMatch(/listSourcePatients\(/);
    expect(src).toMatch(/cloneFromReal\(/);
    expect(src).toMatch(/source_patient_id:/);
    expect(src).toMatch(/remove\s+anything that could identify them/);
    expect(src).toMatch(/encounters_cloned/);
    expect(src).toMatch(/documents_cloned/);
    expect(src).toMatch(/concept_rels_cloned/);
  });

  test("TC-010: api.ts exposes a typed buildBlankTestPatient helper", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/api.ts",
    );
    expect(src).toMatch(/export function buildBlankTestPatient\(/);
    expect(src).toMatch(/"\/build"/);
    expect(src).toMatch(
      /aspect:\s*"nlp"\s*\|\s*"episodes"\s*\|\s*"summarisation"/,
    );
  });

  test("TC-011: Knowledge page wires the Edit drawer per row", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/page.tsx",
    );
    expect(src).toMatch(
      /from\s+"\.\/editor\/EditTestPatientDrawer"/,
    );
    // The state machine that opens the drawer.
    expect(src).toMatch(/setEditingId\(/);
    expect(src).toMatch(/patientId=\{editingId\}/);
    // Edit button is keyboard-accessible and aria-labelled.
    expect(src).toMatch(/Edit test patient/);
    // Guidelines aspect is intentionally disabled at the row icon
    // (the drawer routes that user back to the guideline editor).
    expect(src).toMatch(/disabled=\{row\.aspect === "guidelines"\}/);
    // The Save handler refreshes the table.
    expect(src).toMatch(/onSaved=\{[^}]*setRefreshKey/);
  });

  test("TC-012: api.ts exposes typed full-patient editor helpers", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/api.ts",
    );
    expect(src).toMatch(/export function getTestPatientFull\(/);
    expect(src).toMatch(/export function updateTestPatientFull\(/);
    expect(src).toMatch(/\/full/);
    expect(src).toMatch(/method:\s*"PATCH"/);
  });

  test("TC-013: editor types model encounters + expected SBAR", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/types.ts",
    );
    expect(src).toMatch(/EditorCode/);
    expect(src).toMatch(/EditorEncounter/);
    expect(src).toMatch(/EditorExpectedSbar/);
    expect(src).toMatch(/FullTestPatient/);
    expect(src).toMatch(/UpdateFullBody/);
    // Plain-English assertion vocabulary, capped to the same five
    // values the API enforces.
    expect(src).toMatch(
      /ASSERTION_VALUES.*"present".*"absent".*"history_of".*"suspected".*"uncertain"/s,
    );
  });

  test("TC-014: EncounterListEditor delegates the SNOMED + term inputs to SnomedConceptPicker", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/editor/EncounterListEditor.tsx",
    );
    // The standalone SNOMED ID + Term TextFields are gone; the editor
    // now delegates to the terminology-backed picker so a code typed
    // here is guaranteed to exist in the knowledge graph.
    expect(src).toMatch(
      /import SnomedConceptPicker from "\.\/SnomedConceptPicker"/,
    );
    expect(src).toMatch(/<SnomedConceptPicker/);
    expect(src).toMatch(/conceptId=\{code\.concept_id\}/);
    expect(src).toMatch(/term=\{code\.term \?\? null\}/);
    expect(src).toMatch(/testIdSuffix=\{`\$\{index\}-\$\{codeIndex\}`\}/);
    // The label "SNOMED ID" and the standalone "Term (optional)"
    // textfield are no longer rendered from the encounter editor --
    // the picker owns that copy now.
    expect(src).not.toMatch(/label="SNOMED ID"/);
    expect(src).not.toMatch(/label="Term \(optional\)"/);
    // Assertion select + add buttons + date / source field controls
    // are still owned by the encounter editor.
    expect(src).toMatch(/label="Assertion"/);
    expect(src).toMatch(/Add code/);
    expect(src).toMatch(/Add note/);
    expect(src).toMatch(/showDate/);
    expect(src).toMatch(/showSource/);
    expect(src).not.toMatch(/encounter_id/);
  });

  test("TC-028: SnomedConceptPicker calls /api/terminology/search and is debounced + free-solo", () => {
    const picker = read(
      "services/ui/src/app/admin/knowledge/test-patients/editor/SnomedConceptPicker.tsx",
    );
    // Uses the shared terminology helper from the test-patients api module
    // so the endpoint is the SAME one the rule editor and the operations
    // console use -- no parallel codepath that could drift.
    expect(picker).toMatch(
      /import \{ searchTerminology, type TerminologyHit \} from "\.\.\/api"/,
    );
    expect(picker).toMatch(/searchTerminology\(trimmed\)/);
    // Debounce matches ConceptSearchPanel (250ms) so we do not hammer
    // the terminology service while the reviewer is still typing, and
    // a stale request guard prevents an old response overwriting a new
    // selection.
    expect(picker).toMatch(/DEBOUNCE_MS = 250/);
    expect(picker).toMatch(/window\.setTimeout/);
    expect(picker).toMatch(/reqRef\.current/);
    // freeSolo lets a reviewer paste a known SNOMED id directly so we
    // do not trap them behind a forced lookup when they already know
    // the code.
    expect(picker).toMatch(/freeSolo/);
    // Audience standard: plain-English label + placeholder, and the
    // helper text explains that picking a result keeps the id and the
    // term in sync.
    expect(picker).toMatch(/label="Clinical term"/);
    expect(picker).toMatch(
      /placeholder="Search a clinical term, like cough or weight loss"/,
    );
    expect(picker).toMatch(/SNOMED \{hit\.snomed_concept_id\}/);
    expect(picker).toMatch(/"data-testid":\s*dataTestId/);
    // Regression guard: MUI v5.13+ injects `key` into renderOption's
    // props bag. React drops keys passed via spread, so the key MUST
    // be destructured out of props and passed explicitly on the <li>
    // root. Without the destructure, the dropdown logs "each child in
    // a list should have a unique key" every time the user types a
    // letter into the picker.
    expect(picker).toContain("const { key: muiKey, ...liProps } = props");
    expect(picker).toContain("key={muiKey ?? hit.snomed_concept_id}");
    expect(picker).toContain("{...liProps}");
    // The legacy "spread props then set our own key after" pattern
    // must NOT come back -- it silenced the warning briefly but lost
    // MUI's own key resolution and re-introduced the bug.
    expect(picker).not.toMatch(/\{\.\.\.props\}\s*\n?\s*key=\{hit\.snomed_concept_id\}/);
  });

  test("TC-029: searchTerminology helper hits /api/terminology/search and rejects empty queries", () => {
    const api = read(
      "services/ui/src/app/admin/knowledge/test-patients/api.ts",
    );
    expect(api).toMatch(
      /export async function searchTerminology\(\s*q: string,\s*limit\s*=\s*15,?\s*\)/,
    );
    expect(api).toMatch(/\/api\/terminology\/search\?\$\{params\}/);
    // Short queries are short-circuited client-side so we do not waste
    // a round-trip while the reviewer is still typing the first letter.
    expect(api).toMatch(/if \(trimmed\.length < 2\) return \[\]/);
    // The hit shape matches the existing legacy.searchTerms response so
    // the same backend contract is exercised by both surfaces.
    expect(api).toMatch(/snomed_concept_id: string/);
    expect(api).toMatch(/term: string/);
    expect(api).toMatch(/semantic_tag\?: string/);
  });

  test("TC-015: ExpectedSbarEditor surfaces S/B/A/R + must-include / must-not-say lists", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/editor/ExpectedSbarEditor.tsx",
    );
    expect(src).toMatch(/label="Situation"/);
    expect(src).toMatch(/label="Background"/);
    expect(src).toMatch(/label="Recommendation"/);
    expect(src).toMatch(/Must-include phrases/);
    expect(src).toMatch(/Must-not-say phrases/);
    expect(src).toMatch(/Action priority/);
    expect(src).toMatch(/Rules that should fire/);
    expect(src).toMatch(/Reviewer notes/);
  });

  test("TC-017: Matched rule IDs uses the tree-dialog picker, not free text or a flat dropdown", () => {
    const editor = read(
      "services/ui/src/app/admin/knowledge/test-patients/editor/ExpectedSbarEditor.tsx",
    );
    // The editor delegates to the tree dialog and never imports the
    // flat MUI Autocomplete for this field.
    expect(editor).toMatch(/import RulePickerDialog from "\.\/RulePickerDialog"/);
    expect(editor).not.toMatch(/from "@mui\/material\/Autocomplete"/);
    expect(editor).toMatch(/listGuidanceRules\(/);
    // The visible trigger is a "Browse rules" button + a chip strip,
    // and the field name is nurse-friendly.
    expect(editor).toMatch(/Rules that should fire/);
    expect(editor).toMatch(/Browse rules/);
    expect(editor).toMatch(/setPickerOpen\(true\)/);
    expect(editor).toMatch(/data-testid="matched-rule-ids-picker"/);
    // The dialog is wired with the live rule list, the current
    // selection, and an Apply callback that dedupes the chosen ids.
    expect(editor).toMatch(/<RulePickerDialog/);
    expect(editor).toMatch(/applyPickerSelection/);
    expect(editor).toMatch(/selectedRuleIds=\{value\.matched_rule_ids/);
    // Selected chips show plain-English labels, not raw rule IDs, and
    // each chip is removable.
    expect(editor).toMatch(/rule\.display_label \|\| rule\.rule_id/);
    expect(editor).toMatch(/onDelete=\{[\s\S]*?removeRule\(rule\.rule_id\)/);
    // The legacy textarea wiring is gone for this field.
    expect(editor).not.toMatch(
      /update\(\{\s*matched_rule_ids:\s*textToList/,
    );

    const api = read(
      "services/ui/src/app/admin/knowledge/test-patients/api.ts",
    );
    expect(api).toMatch(/export function listGuidanceRules\(/);
    expect(api).toMatch(/`\/rules\$\{tail/);

    const types = read(
      "services/ui/src/app/admin/knowledge/test-patients/types.ts",
    );
    expect(types).toMatch(/GuidanceRulePickerEntry/);
    expect(types).toMatch(/display_label:\s*string/);
    expect(types).toMatch(/recommendation_text:\s*string \| null/);
    expect(types).toMatch(/chapter_title:\s*string \| null/);
    expect(types).toMatch(/action_priority:\s*string \| null/);
    expect(types).toMatch(/trigger_terms:\s*string\[\]/);
  });

  test("TC-018: RulePickerDialog renders a 3-level tree with bulk select + search", () => {
    const dlg = read(
      "services/ui/src/app/admin/knowledge/test-patients/editor/RulePickerDialog.tsx",
    );
    // Three-level tree: Guideline -> Chapter -> Rule. The build
    // function groups by guideline first then chapter, with a
    // rule_count visible on each branch.
    expect(dlg).toMatch(/buildTree/);
    expect(dlg).toMatch(/guideline_title/);
    expect(dlg).toMatch(/chapter_title/);
    // Bulk select via tri-state checkboxes (parent ticks all children;
    // partial selections show as indeterminate).
    expect(dlg).toMatch(/indeterminate=/);
    expect(dlg).toMatch(/setBulk\(/);
    // Expand / collapse plumbing -- search auto-expands matched
    // branches so the reviewer sees hits without clicking.
    expect(dlg).toMatch(/Collapse/);
    expect(dlg).toMatch(/expandAll/);
    expect(dlg).toMatch(/collapseAll/);
    expect(dlg).toMatch(/effectiveExpanded/);
    // Plain-English search across guideline / section / symptom / rule.
    expect(dlg).toMatch(
      /Search by guideline, section, symptom or rule/,
    );
    // Each rule row shows the priority chip and the SNOMED triggers.
    expect(dlg).toMatch(/rule\.action_priority/);
    expect(dlg).toMatch(/rule\.trigger_terms/);
    expect(dlg).toMatch(/Triggers:/);
    // Apply / Cancel: Cancel discards, Apply fires the callback with
    // the new id set.
    expect(dlg).toMatch(/onApply\(Array\.from\(draft\)\)/);
    expect(dlg).toMatch(/data-testid="rule-picker-tree"/);
  });

  test("TC-016: EditTestPatientDrawer dispatches by aspect and blocks guidelines", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/editor/EditTestPatientDrawer.tsx",
    );
    expect(src).toMatch(/getTestPatientFull\(/);
    expect(src).toMatch(/updateTestPatientFull\(/);
    // Aspect dispatch: SBAR section only when aspect=summarisation;
    // encounter editor only when aspect != guidelines.
    expect(src).toMatch(/loaded\.aspect === "summarisation"/);
    expect(src).toMatch(/!guidelinesAspect/);
    // The drawer talks to the user about why guidelines is read-only
    // here -- the snapshot lives in the guideline editor.
    expect(src).toMatch(/guideline editor/);
  });

  test("TC-019: api.ts exposes scaffoldFromRule helper for the AI scaffold flow", () => {
    const api = read(
      "services/ui/src/app/admin/knowledge/test-patients/api.ts",
    );
    // The new helper hits POST /scaffold-from-rule and is typed against
    // the scaffolder's response shape so callers cannot drift from the
    // backend contract.
    expect(api).toMatch(
      /export function scaffoldFromRule\(\s*body:\s*ScaffoldFromRuleBody/,
    );
    expect(api).toMatch(/return request\("\/scaffold-from-rule"/);
    expect(api).toMatch(/method:\s*"POST"/);
    // Body shape: rule_id + aspect (one of the three non-Guidelines
    // aspects -- the scaffolder rejects guidelines with a 422).
    expect(api).toMatch(/rule_id:\s*string/);
    expect(api).toMatch(/draft_rule\?:\s*Record<string, unknown> \| null/);
    expect(api).toMatch(/aspect:\s*"nlp"\s*\|\s*"episodes"\s*\|\s*"summarisation"/);
    // Result shape: patient_id (drives the editor open) + provenance
    // counts the dialog can show on success.
    expect(api).toMatch(/patient_id:\s*string/);
    expect(api).toMatch(/encounters_written:\s*number/);
    expect(api).toMatch(/expected_sbar_written:\s*boolean/);
  });

  test("TC-020: ScaffoldFromRuleDialog wires the rule picker, the aspect select and the scaffold call", () => {
    const dlg = read(
      "services/ui/src/app/admin/knowledge/test-patients/ScaffoldFromRuleDialog.tsx",
    );
    // Reuses the shared rule tree (no second picker UI).
    expect(dlg).toMatch(
      /import RulePickerDialog from "\.\/editor\/RulePickerDialog"/,
    );
    expect(dlg).toMatch(/<RulePickerDialog/);
    // Fetches the rule library once on open via the existing endpoint.
    expect(dlg).toMatch(/listGuidanceRules\(\{ limit: 500 \}\)/);
    // Aspect select restricted to the three scaffoldable aspects;
    // SBAR handover is the default because the scaffolder is most
    // useful for the SBAR handover regression set.
    expect(dlg).toMatch(
      /SCAFFOLDABLE_ASPECTS:\s*ScaffoldAspect\[\]\s*=\s*\[\s*"summarisation"/,
    );
    // Calls the new endpoint and returns the new patient id to the
    // page so the editor drawer opens with the AI draft loaded.
    expect(dlg).toMatch(/scaffoldFromRule\(\{/);
    expect(dlg).toMatch(/draft_rule:\s*lockedRuleId \? draftRule \?\? null : null/);
    expect(dlg).toMatch(/onScaffolded:\s*\(newPatientId:\s*string\)\s*=>\s*void/);
    // The honest-test guarantee is shown to the reviewer in plain
    // English so they understand the AI does NOT write its own ground
    // truth (that comes from the rule).
    expect(dlg).toMatch(/expected SBAR/);
    expect(dlg).toMatch(/AI never\s+writes its own ground truth/);
  });

  test("TC-021: Knowledge page mounts the Scaffold dialog and opens the editor on success", () => {
    const page = read(
      "services/ui/src/app/admin/knowledge/test-patients/page.tsx",
    );
    expect(page).toMatch(
      /import ScaffoldFromRuleDialog from "\.\/ScaffoldFromRuleDialog"/,
    );
    // Scaffold is offered alongside Build and Copy in the toolbar.
    expect(page).toMatch(/id:\s*"scaffold-from-rule"/);
    expect(page).toMatch(/label:\s*"Scaffold from a rule \(AI\)"/);
    expect(page).toMatch(/setScaffoldOpen\(true\)/);
    // Mount + state.
    expect(page).toMatch(/<ScaffoldFromRuleDialog/);
    expect(page).toMatch(/scaffoldOpen,\s*setScaffoldOpen/);
    // On success: refresh the table AND open the editor on the new
    // patient so the reviewer can review the AI draft immediately.
    expect(page).toMatch(/onScaffolded=\{\(newPatientId\)\s*=>/);
    expect(page).toMatch(/setEditingId\(newPatientId\)/);
  });

  test("TC-022: api.ts exposes scaffoldFromScenario helper for the AI scenario flow", () => {
    const api = read(
      "services/ui/src/app/admin/knowledge/test-patients/api.ts",
    );
    // The helper hits POST /scaffold-from-scenario and is typed
    // against the scaffolder's response shape so callers cannot
    // drift from the backend contract.
    expect(api).toMatch(
      /export function scaffoldFromScenario\(\s*body:\s*ScaffoldFromScenarioBody/,
    );
    expect(api).toMatch(/return request\("\/scaffold-from-scenario"/);
    // Body shape: scenario text + the same three scaffoldable aspects.
    expect(api).toMatch(/scenario:\s*string/);
    expect(api).toMatch(
      /aspect:\s*"nlp"\s*\|\s*"episodes"\s*\|\s*"summarisation"/,
    );
    // Result shape: patient_id (drives the editor open) + a rich
    // resolution summary so the dialog can show what resolved, what
    // needs review, and which rules fired.
    expect(api).toMatch(/patient_id:\s*string/);
    expect(api).toMatch(/scenario:\s*string/);
    expect(api).toMatch(/resolved_terms:\s*ScaffoldResolvedTerm\[\]/);
    expect(api).toMatch(/unresolved_terms:\s*ScaffoldUnresolvedTerm\[\]/);
    expect(api).toMatch(/matched_rules:\s*ScaffoldMatchedRule\[\]/);
    // Resolved-term row carries the SNOMED concept_id (nullable when
    // the candidate scored below the floor) and the assertion.
    expect(api).toMatch(/concept_id:\s*string\s*\|\s*null/);
    expect(api).toMatch(/assertion:\s*string/);
  });

  test("TC-023: ScaffoldFromScenarioDialog wires the text area, the aspect select and the scaffold call", () => {
    const dlg = read(
      "services/ui/src/app/admin/knowledge/test-patients/ScaffoldFromScenarioDialog.tsx",
    );
    // Scenario textarea is the focus of the dialog -- it must be
    // multiline, have a min/max length validation, and be data-test
    // discoverable.
    expect(dlg).toMatch(/<TextField[\s\S]*?multiline/);
    expect(dlg).toMatch(/MIN_SCENARIO_CHARS/);
    expect(dlg).toMatch(/MAX_SCENARIO_CHARS/);
    expect(dlg).toMatch(/data-testid":\s*"scenario-input"/);
    // Aspect select restricted to the three scaffoldable aspects;
    // SBAR handover is the default because the rule engine pass is
    // most useful when checking SBAR rule fires.
    expect(dlg).toMatch(
      /SCAFFOLDABLE_ASPECTS:\s*ScaffoldAspect\[\]\s*=\s*\[\s*"summarisation"/,
    );
    // Calls the new endpoint and returns the new patient id to the
    // page so the editor drawer opens with the AI draft loaded.
    expect(dlg).toMatch(/scaffoldFromScenario\(\{/);
    expect(dlg).toMatch(
      /onScaffolded:\s*\(newPatientId:\s*string\)\s*=>\s*void/,
    );
    // The honest-test guarantee is shown to the reviewer in plain
    // English: AI writes the prose, codes come from the terminology
    // service, expected SBAR comes from the rule engine.
    expect(dlg).toMatch(/AI\s+never\s+writes\s+its\s+own\s+ground\s+truth/);
    expect(dlg).toMatch(/terminology service/);
    expect(dlg).toMatch(/rule engine/);
  });

  test("TC-024: Knowledge page mounts the Scenario dialog and opens the editor on success", () => {
    const page = read(
      "services/ui/src/app/admin/knowledge/test-patients/page.tsx",
    );
    expect(page).toMatch(
      /import ScaffoldFromScenarioDialog from "\.\/ScaffoldFromScenarioDialog"/,
    );
    // The new toolbar action sits alongside the existing flows.
    expect(page).toMatch(/id:\s*"scaffold-from-scenario"/);
    expect(page).toMatch(/label:\s*"Author from a scenario \(AI\)"/);
    expect(page).toMatch(/setScenarioOpen\(true\)/);
    // Mount + state for the dialog itself.
    expect(page).toMatch(/<ScaffoldFromScenarioDialog/);
    expect(page).toMatch(/scenarioOpen,\s*setScenarioOpen/);
    // On success: refresh the table AND open the editor on the new
    // patient so the reviewer can review the AI draft immediately.
    expect(page).toMatch(
      /<ScaffoldFromScenarioDialog[\s\S]*?onScaffolded=\{\(newPatientId\)\s*=>[\s\S]*?setEditingId\(newPatientId\)/,
    );
  });

  test("TC-025: api client + types expose the triage outcome filter", () => {
    const api = read(
      "services/ui/src/app/admin/knowledge/test-patients/api.ts",
    );
    expect(api).toMatch(/TriageOutcome,/);
    expect(api).toMatch(/TriageOutcomeCounts,/);
    expect(api).toMatch(/triage_outcome\?:\s*TriageOutcome/);
    expect(api).toMatch(
      /params\.triage_outcome[\s\S]*?qs\.set\("triage_outcome",\s*params\.triage_outcome\)/,
    );
    expect(api).toMatch(/getTriageOutcomeCounts\(\):\s*Promise<TriageOutcomeCounts>/);
    expect(api).toMatch(/\/triage-outcome-counts/);
  });

  test("TC-026: triage outcome vocabulary is plain English and matches the backend", () => {
    const types = read(
      "services/ui/src/app/admin/knowledge/test-patients/types.ts",
    );
    expect(types).toMatch(
      /TRIAGE_OUTCOME_VALUES\s*=\s*\[\s*"all",\s*"2ww",\s*"urgent",\s*"routine",\s*"no_rule_fired",\s*"evaluator_outage",\s*"unset",?\s*\]/,
    );
    expect(types).toMatch(/"2ww":\s*"2 week wait \(suspected cancer\)"/);
    expect(types).toMatch(/no_rule_fired:\s*"No rule fired"/);
    expect(types).toMatch(/evaluator_outage:\s*"Evaluator outage"/);
    expect(types).toMatch(/NICE NG12 suspected-cancer referrals/);
    expect(types).toMatch(
      /triage_outcome:\s*Exclude<TriageOutcome,\s*"all">\s*\|\s*null/,
    );
  });

  test("TC-027: page wires the triage chip group, fetches counts, and resets on aspect switch", () => {
    const page = read(
      "services/ui/src/app/admin/knowledge/test-patients/page.tsx",
    );
    expect(page).toMatch(/triageOutcome,\s*setTriageOutcome/);
    expect(page).toMatch(/showsTriageFilter\(aspect\)/);
    expect(page).toMatch(/if \(!showsTriageFilter\(next\)\)\s*setTriageOutcome\("all"\)/);
    expect(page).toMatch(/data-testid=\{`triage-chip-\$\{value\}`\}/);
    expect(page).toMatch(/TRIAGE_OUTCOME_HINT\[value\]/);
    expect(page).toMatch(/TRIAGE_OUTCOME_LABEL\[value\]/);
    // The list call now also forwards the rule_id URL param so the
    // central library can be deep-linked from the rule editor.
    expect(page).toMatch(
      /listTestPatients\(\{\s*aspect,\s*triage_outcome:\s*outcomeForList,\s*rule_id:\s*ruleIdFilter\s*\?\?\s*undefined,?\s*\}\)/,
    );
    expect(page).toMatch(/getTriageOutcomeCounts\(\)/);
    expect(page).toMatch(/id:\s*"triage_outcome"/);
    expect(page).toMatch(/header:\s*"Triage outcome"/);
    expect(page).toMatch(/row\.triage_outcome === "2ww"[\s\S]*?\?\s*"error"/);
  });

  test("TC-030: library page exposes per-row Test, Test selected and Test all buttons wired to /replay", () => {
    const page = read(
      "services/ui/src/app/admin/knowledge/test-patients/page.tsx",
    );
    // Calls the same /replay endpoint and renders the same dialog as
    // the rule editor's "Try it on real patients" panel, so reviewers
    // never have to learn two flows.
    expect(page).toMatch(/from\s+"\.\/api"[\s\S]*?replayInBatches/);
    expect(page).toMatch(
      /import ReplayResultsDialog from "\.\/replay\/ReplayResultsDialog"/,
    );
    expect(page).toMatch(
      /import RulesetNotCompiledBanner from "\.\/replay\/RulesetNotCompiledBanner"/,
    );
    // Per-row Test button
    expect(page).toMatch(/data-testid=\{`test-now-\$\{row\.id\}`\}/);
    expect(page).toMatch(/aspectSupportsReplay\(row\.aspect\)/);
    // Action strip + bulk buttons
    expect(page).toMatch(/data-testid="test-action-strip"/);
    expect(page).toMatch(/data-testid="test-selected-button"/);
    expect(page).toMatch(/data-testid="test-all-button"/);
    expect(page).toMatch(/`Test selected \(\$\{selectedCount\}\)`/);
    expect(page).toMatch(/Test all visible \(\$\{visibleEligibleCount\}\)/);
    expect(page).toMatch(/replayProgress/);
    // Selection scaffolding -- testids are passed through inputProps
    // because MUI Checkbox spreads them onto the underlying <input>.
    expect(page).toMatch(/"data-testid":\s*"select-all-checkbox"/);
    expect(page).toMatch(/"data-testid":\s*`select-row-\$\{row\.id\}`/);
    // Replay payload uses the shared scope and never persists a report
    // (the library is a manual triage surface, not a regression
    // baseline; the nightly scheduler still owns persisted reports).
    expect(page).toMatch(/scope_type:\s*"global"/);
    expect(page).toMatch(/scope_id:\s*"default"/);
    expect(page).toMatch(/persist_report:\s*false/);
  });

  test("TC-031: NLP and Episodes patients cannot be replayed and the UI says why", () => {
    const page = read(
      "services/ui/src/app/admin/knowledge/test-patients/page.tsx",
    );
    // The helper short-list is the single source of truth -- guidelines
    // and SBAR / referral triage carry rule-firing expectations the
    // bitmap evaluator can score, the others do not.
    expect(page).toMatch(
      /aspectSupportsReplay[\s\S]*?aspect === "guidelines"[\s\S]*?aspect === "summarisation"/,
    );
    // The disabled tooltip explains the gap in plain English.
    expect(page).toMatch(/REPLAY_UNSUPPORTED_HINT\s*=/);
    expect(page).toMatch(/NLP and Episodes patients do not yet have/);
    // Disabled state on the per-row button is wired to the helper.
    expect(page).toMatch(/disabled=\{!supportsReplay \|\| replaying\}/);
    // The bulk callback drops ineligible patients and surfaces the skip
    // count instead of silently calling /replay with mixed input.
    expect(page).toMatch(
      /const eligible = patientsToTest\.filter\(\(p\) => aspectSupportsReplay\(p\.aspect\)\)/,
    );
    expect(page).toMatch(/Skipped \$\{skipped\} patient/);
  });

  test("TC-032: selection clears when the visible cohort changes", () => {
    // A reviewer who selects 3 SBAR rows then switches to NLP would
    // otherwise be carrying around invisible selections that "Test
    // selected" would silently include. The page resets the set on
    // every filter change.
    const page = read(
      "services/ui/src/app/admin/knowledge/test-patients/page.tsx",
    );
    expect(page).toMatch(
      /useEffect\(\(\) => \{\s*setSelectedIds\(new Set\(\)\);\s*\},\s*\[aspect, triageOutcome, ruleIdFilter, refreshKey\]\)/,
    );
  });

  test("TC-033: ReplayResultsDialog is mounted on the library page in live mode", () => {
    const page = read(
      "services/ui/src/app/admin/knowledge/test-patients/page.tsx",
    );
    // The dialog is mounted unconditionally so its open state is the
    // single source of truth -- the page never renders two dialogs.
    // It also receives the rules lookup so patient descriptions show
    // friendly rule names (e.g. "1.1.5 Offer an urgent chest X-ray
    // ...") instead of the raw rule_id.
    expect(page).toMatch(
      /<ReplayResultsDialog\s*\n\s*open=\{replayOpen\}\s*\n\s*onClose=\{\(\) => setReplayOpen\(false\)\}\s*\n\s*report=\{replayReport\}\s*\n\s*patients=\{replayPatients\}\s*\n\s*rules=\{rulesLookup\}\s*\n\s*mode="live"\s*\n\s*\/>/,
    );
  });

  test("TC-034: page lazy-loads the rule lookup so dialog has friendly names", () => {
    const page = read(
      "services/ui/src/app/admin/knowledge/test-patients/page.tsx",
    );
    // We import listGuidanceRules, store the lookup in state, and
    // build each entry with display_label as the canonical "name"
    // -- that's the same string the rule picker shows the user.
    expect(page).toMatch(/listGuidanceRules,\s*\n/);
    expect(page).toMatch(/setRulesLookup\(/);
    expect(page).toMatch(/listGuidanceRules\(\{ limit: 500 \}\)/);
    expect(page).toMatch(
      /name:\s*r\.display_label\s*\|\|\s*r\.name\s*\|\|\s*undefined/,
    );
    expect(page).toMatch(/recommendation_text:\s*r\.recommendation_text/);
    // The replay codepath kicks the lookup off in parallel with the
    // network call so the dialog opens with friendly labels in hand.
    expect(page).toMatch(/ensureRulesLookup\(\)/);
  });

  test("TC-006: legacy /admin/guidance/test-patients folder is removed end-to-end", () => {
    // Phase A removed the route page; this PR removes the supporting
    // modules too. The rule editor now imports api/types/dialogs from
    // the centralised /admin/knowledge/test-patients folder, and the
    // moved replay components live in the /replay subfolder.
    expect(
      exists("services/ui/src/app/admin/guidance/test-patients/page.tsx"),
    ).toBe(false);
    expect(
      exists("services/ui/src/app/admin/guidance/test-patients/api.ts"),
    ).toBe(false);
    expect(
      exists("services/ui/src/app/admin/guidance/test-patients/types.ts"),
    ).toBe(false);
    expect(
      exists(
        "services/ui/src/app/admin/guidance/test-patients/" +
          "ReplayResultsDialog.tsx",
      ),
    ).toBe(false);
    expect(
      exists(
        "services/ui/src/app/admin/guidance/test-patients/" +
          "RulesetNotCompiledBanner.tsx",
      ),
    ).toBe(false);
    expect(
      exists(
        "services/ui/src/app/admin/knowledge/test-patients/replay/" +
          "ReplayResultsDialog.tsx",
      ),
    ).toBe(true);
    expect(
      exists(
        "services/ui/src/app/admin/knowledge/test-patients/replay/" +
          "RulesetNotCompiledBanner.tsx",
      ),
    ).toBe(true);

    expect(
      exists(
        "services/ui/src/app/admin/guidance/BitmapLifecycleSection.tsx",
      ),
    ).toBe(true);
    const lifecycle = read(
      "services/ui/src/app/admin/guidance/BitmapLifecycleSection.tsx",
    );
    // The "Open library" button now points at the Knowledge tab.
    expect(lifecycle).toMatch(
      /href="\/admin\/knowledge\?tab=test-patients"/,
    );
    expect(lifecycle).not.toMatch(/href="\/admin\/guidance\/test-patients"/);
  });

  test("TC-007: rule editor panel is wired to the central library", () => {
    // The "Try it on real patients" panel (rule editor) MUST import
    // its data layer from the centralised library so SBAR-aspect
    // patients show up alongside guideline ones, and MUST replace the
    // legacy "Build new" / "Generate" pair with the new "Author with
    // AI from this rule" + "Open in Test Patient Library" buttons.
    const panel = read(
      "services/ui/src/app/admin/guidance/EditRuleDialog/" +
        "TestPatientsPanel.tsx",
    );
    expect(panel).toContain('from "../../knowledge/test-patients/api"');
    expect(panel).toContain('from "../../knowledge/test-patients/types"');
    expect(panel).toContain(
      'from "../../knowledge/test-patients/ScaffoldFromRuleDialog"',
    );
    expect(panel).toContain(
      'from "../../knowledge/test-patients/replay/ReplayResultsDialog"',
    );
    // Phase 1 retired the in-panel live-replay flow that depended on
    // RulesetNotCompiledBanner. The sandbox-only panel surfaces a
    // local "draft sandbox could not be compiled" Alert instead.
    expect(panel).toMatch(/draft sandbox could not be compiled/i);
    expect(panel).toMatch(/Author with AI from this rule/);
    expect(panel).toMatch(/Open in Test Patient Library/);
    expect(panel).toMatch(/lockedRuleId=\{ruleId\}/);
    // Open-in-library deep link uses URLSearchParams. The literal
    // "test-patients" tab key and the rule_id field must both appear
    // so the central library lands on the right tab + filter.
    expect(panel).toMatch(/tab:\s*"test-patients"/);
    expect(panel).toMatch(/rule_id:\s*ruleId/);
    // Legacy entry points must be gone.
    expect(panel).not.toMatch(/BuildPatientDialog/);
    expect(panel).not.toMatch(/GeneratePatientsDialog/);
    expect(panel).not.toMatch(/listPatients\(/);
  });

  test("TC-007b: rule editor AI scaffolding uses the current draft rule", () => {
    const panel = read(
      "services/ui/src/app/admin/guidance/EditRuleDialog/" +
        "TestPatientsPanel.tsx",
    );
    expect(panel).toMatch(/draftRule=\{draftRule\}/);
  });

  test("TC-008: knowledge page reads ?rule_id and shows a clear banner", () => {
    const page = read(
      "services/ui/src/app/admin/knowledge/test-patients/page.tsx",
    );
    expect(page).toMatch(
      /searchParams\.get\(\s*"rule_id"\s*\)/,
    );
    expect(page).toMatch(/rule_id:\s*ruleIdFilter\s*\?\?\s*undefined/);
    expect(page).toMatch(/data-testid="rule-filter-banner"/);
    expect(page).toMatch(/data-testid="clear-rule-filter"/);
    expect(page).toMatch(/Show all/);
  });
});
