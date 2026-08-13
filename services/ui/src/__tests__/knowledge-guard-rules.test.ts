/**
 * Static-source VT for the Pipeline Guards knowledge tab.
 *
 * Guard rules tab replaces the old Guards Workbench page.
 * Rendered inside the Knowledge shell at ?tab=guard-rules.
 */
import * as fs from "fs";
import * as path from "path";

import { resolveWorkedExample } from "../app/admin/guard-rules/guardWorkedExamples";

const PAGE_PATH = path.join(__dirname, "../app/admin/guard-rules/page.tsx");
const CARD_PATH = path.join(__dirname, "../app/admin/guard-rules/GuardFamilyCard.tsx");
const DIALOG_PATH = path.join(__dirname, "../app/admin/guard-rules/GuardFamilyDialog.tsx");
const EDITOR_PATH = path.join(__dirname, "../app/admin/guard-rules/GuardEditorPanel.tsx");
const HOOK_PATH = path.join(__dirname, "../app/admin/guard-rules/useGuardRulesPage.ts");
const FAMILY_COPY_PATH = path.join(__dirname, "../app/admin/guard-rules/guardFamilyCopy.ts");
const EXAMPLE_PATH = path.join(__dirname, "../app/admin/guard-rules/guardWorkedExamples.ts");
const EXAMPLE_PANEL_PATH = path.join(__dirname, "../app/admin/guard-rules/GuardExamplePanel.tsx");
const KNOWLEDGE_PATH = path.join(__dirname, "../app/admin/knowledge/page.tsx");
const SIDEBAR_PATH = path.join(__dirname, "../components/ui/KnowledgeSidebar.tsx");
const COPY_PATH = path.join(__dirname, "../lib/knowledgeCopy.ts");

describe("GuardRulesPage", () => {
  let src: string;
  beforeAll(() => {
    src = fs.readFileSync(PAGE_PATH, "utf-8");
  });

  it("exports a default page component", () => {
    expect(src).toMatch(/export default function/);
  });

  it("has a searchable rule list", () => {
    expect(src).toMatch(/search.*pattern|pattern.*search/i);
  });

  it("has a guard family selector", () => {
    expect(src).toMatch(/GUARD_FAMILIES/);
    const familyCopy = fs.readFileSync(FAMILY_COPY_PATH, "utf-8");
    expect(familyCopy).toMatch(/scope_guard/);
    expect(familyCopy).toMatch(/lab_value_guard/);
  });

  it("uses RuleEditor for editing", () => {
    const editor = fs.readFileSync(EDITOR_PATH, "utf-8");
    expect(editor).toMatch(/RuleEditor/);
  });

  it("does not include a live test preview in the rule dialog", () => {
    const editor = fs.readFileSync(EDITOR_PATH, "utf-8");
    expect(editor).not.toMatch(/StageOutputViewer/);
    expect(editor).not.toMatch(/Run test/);
  });

  it("reads fired_rule_id from URL params for guided discovery", () => {
    const hook = fs.readFileSync(HOOK_PATH, "utf-8");
    expect(hook).toMatch(/fired_rule_id/);
    expect(hook).toMatch(/source_sentence/);
  });

  it("calls the guard-rules API", () => {
    const hook = fs.readFileSync(HOOK_PATH, "utf-8");
    expect(hook).toMatch(/admin\/workbench\/guard-rules/);
  });

  it("has an Add rule button", () => {
    expect(src).toMatch(/Add rule/);
  });

  it("shows a Built-in badge for shipped rules", () => {
    const card = fs.readFileSync(CARD_PATH, "utf-8");
    expect(card).toMatch(/Built-in/);
    expect(card).toMatch(/source === "builtin"/);
  });

  it("opens built-in rules as read-only", () => {
    const editor = fs.readFileSync(EDITOR_PATH, "utf-8");
    expect(editor).toMatch(/source === "builtin"/);
    expect(editor).toMatch(/readOnly=\{readOnly\}/);
  });

  it("renders compact family cards that open a 16:9 detail dialog", () => {
    expect(src).toMatch(/GuardFamilyCard/);
    expect(src).toMatch(/GuardFamilyDialog/);
    const card = fs.readFileSync(CARD_PATH, "utf-8");
    expect(card).toMatch(/familyKind/);
    expect(card).toMatch(/onOpen/);
    expect(card).not.toMatch(/What it does/);
    const dialog = fs.readFileSync(DIALOG_PATH, "utf-8");
    expect(dialog).toMatch(/What it does/);
    expect(dialog).toMatch(/Why it is needed/);
    expect(dialog).toMatch(/If it is wrong/);
    expect(dialog).toMatch(/16 \/ 9/);
    expect(dialog).toMatch(/GuardExamplePanel/);
  });
});

describe("Knowledge shell includes guard-rules tab", () => {
  let src: string;
  beforeAll(() => {
    src = fs.readFileSync(KNOWLEDGE_PATH, "utf-8");
  });

  it("imports GuardRulesPage", () => {
    expect(src).toMatch(/GuardRulesPage/);
  });

  it("registers guard-rules in TAB_PANELS", () => {
    expect(src).toMatch(/"guard-rules":\s*GuardRulesPage/);
  });

  it("lists Pipeline Guards in TABS", () => {
    expect(src).toMatch(/key:\s*"guard-rules"/);
    expect(src).toMatch(/label:\s*"Pipeline Guards"/);
  });

  it("no longer references the workbench page", () => {
    expect(src).not.toMatch(/WorkbenchPage/);
    expect(src).not.toMatch(/workbench\/page/);
  });
});

describe("Knowledge sidebar includes Pipeline Guards under NLP & AI", () => {
  let src: string;
  beforeAll(() => {
    src = fs.readFileSync(SIDEBAR_PATH, "utf-8");
  });

  it("places guard-rules in the NLP & AI group", () => {
    const nlpGroup = src.match(/label:\s*"NLP & AI"[\s\S]*?label:\s*"Clinical Knowledge"/);
    expect(nlpGroup).not.toBeNull();
    expect(nlpGroup![0]).toMatch(/key:\s*"guard-rules"/);
    expect(nlpGroup![0]).toMatch(/label:\s*"Pipeline Guards"/);
  });

  it("lists every Knowledge tab key in SIDEBAR_GROUPS", () => {
    const knowledgeSrc = fs.readFileSync(KNOWLEDGE_PATH, "utf-8");
    const tabKeys = [...knowledgeSrc.matchAll(/\{\s*key:\s*"([^"]+)"/g)].map(
      (m) => m[1],
    );
    expect(tabKeys.length).toBeGreaterThan(0);
    for (const key of tabKeys) {
      expect(src).toMatch(new RegExp(`key:\\s*"${key}"`));
    }
  });
});

describe("KnowledgeCopy includes guard-rules", () => {
  let src: string;
  beforeAll(() => {
    src = fs.readFileSync(COPY_PATH, "utf-8");
  });

  it("has guard-rules in KnowledgeTabKey union", () => {
    expect(src).toMatch(/"guard-rules"/);
  });

  it("has no workbench key in union", () => {
    expect(src).not.toMatch(/"workbench"/);
  });

  it("has platform_admin copy for guard-rules", () => {
    expect(src).toMatch(/Pipeline guard configuration/);
  });
});

describe("Guard family copy documents every family", () => {
  it("has what, why, and ifWrong for each family", () => {
    const src = fs.readFileSync(FAMILY_COPY_PATH, "utf-8");
    for (const family of [
      "scope_guard",
      "lab_value_guard",
      "referral_routing_guard",
      "assertion_guard",
      "entity_type_norm",
      "checkbox_norm",
      "situation_lookup",
      "term_concept_blocklist",
    ]) {
      expect(src).toMatch(new RegExp(`${family}:`));
    }
    expect(src).toMatch(/what:/);
    expect(src).toMatch(/why:/);
    expect(src).toMatch(/ifWrong:/);
  });

  it("has a with and without worked example for each family", () => {
    const src = fs.readFileSync(EXAMPLE_PATH, "utf-8");
    expect(src).toMatch(/guard_worked_examples\.json/);
    expect(src).toMatch(/resolveWorkedExample/);
    const catalog = fs.readFileSync(
      path.join(__dirname, "../app/admin/guard-rules/guard_worked_examples.json"),
      "utf-8",
    );
    for (const family of [
      "scope_guard",
      "lab_value_guard",
      "referral_routing_guard",
      "assertion_guard",
      "entity_type_norm",
      "checkbox_norm",
      "situation_lookup",
      "term_concept_blocklist",
    ]) {
      expect(catalog).toMatch(new RegExp(`"${family}"`));
    }
    expect(catalog).toMatch(/without_guard/);
    expect(catalog).toMatch(/with_guard/);
    expect(catalog).toMatch(/data_change/);
    expect(catalog).toMatch(/source_test/);
    const panel = fs.readFileSync(EXAMPLE_PANEL_PATH, "utf-8");
    expect(panel).toMatch(/Without this guard/);
    expect(panel).toMatch(/With this guard/);
    expect(panel).toMatch(/What this does to the data/);
    expect(panel).toMatch(/automated test/);
  });

  it("uses the selected blocklist wording in the worked example", () => {
    const example = resolveWorkedExample(
      "term_concept_blocklist",
      "term_concept_blocklist",
      "fit",
      "FIT is a test (Faecal Immunochemical Test), not a seizure.",
      "tcb-004",
    );
    expect(example.note).toMatch(/fit/i);
    expect(example.withGuard).toMatch(/seizure/i);
    expect(example.dataChange).toMatch(/91175000/);
  });
});
