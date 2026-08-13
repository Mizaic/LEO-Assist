/**
 * Static-source VT for the Context Rules knowledge tab.
 *
 * Category cards replace the old 67-row list. Rendered inside the
 * Knowledge shell at ?tab=context-rules.
 */
import * as fs from "fs";
import * as path from "path";

import {
  CATEGORY_COPY,
  CATEGORY_KEYS,
  resolveContextExample,
} from "../app/admin/context-rules/categoryCopy";
import type { ContextRule } from "../app/admin/context-rules/types";

const PAGE_PATH = path.join(__dirname, "../app/admin/context-rules/page.tsx");
const CARD_PATH = path.join(__dirname, "../app/admin/context-rules/ContextCategoryCard.tsx");
const DIALOG_PATH = path.join(__dirname, "../app/admin/context-rules/ContextCategoryDialog.tsx");
const ADD_PATH = path.join(__dirname, "../app/admin/context-rules/ContextAddDialog.tsx");
const HOOK_PATH = path.join(__dirname, "../app/admin/context-rules/useContextRulesPage.ts");
const COPY_PATH = path.join(__dirname, "../app/admin/context-rules/categoryCopy.ts");
const EXAMPLE_PANEL_PATH = path.join(
  __dirname,
  "../app/admin/context-rules/ContextExamplePanel.tsx",
);
const KNOWLEDGE_PATH = path.join(__dirname, "../app/admin/knowledge/page.tsx");
const SIDEBAR_PATH = path.join(__dirname, "../components/ui/KnowledgeSidebar.tsx");
const SETTINGS_PATH = path.join(__dirname, "../app/settings/context-rules/page.tsx");

function sampleRule(overrides: Partial<ContextRule> = {}): ContextRule {
  return {
    rule_id: "r1",
    literal: "nil",
    category: "NEGATED_EXISTENCE",
    direction: "FORWARD",
    max_scope: 6,
    description: "No evidence of",
    example: "nil chest pain -> no chest pain",
    created_by: "system",
    active: true,
    created_at: null,
    source: "builtin",
    org_id: null,
    ...overrides,
  };
}

describe("ContextRulesPage", () => {
  let src: string;
  beforeAll(() => {
    src = fs.readFileSync(PAGE_PATH, "utf-8");
  });

  it("exports a default page component", () => {
    expect(src).toMatch(/export default function/);
  });

  it("has a searchable rule list", () => {
    expect(src).toMatch(/searchPlaceholder="Search phrases/);
    expect(src).toMatch(/FilterBar/);
  });

  it("reads term from URL params for guided discovery", () => {
    const hook = fs.readFileSync(HOOK_PATH, "utf-8");
    expect(hook).toMatch(/searchParams\.get\("term"\)/);
  });

  it("filters built-in and added rules", () => {
    expect(src).toMatch(/Built-in/);
    expect(src).toMatch(/Added/);
    expect(src).toMatch(/sourceChips/);
  });

  it("exports a PDF of the visible rules", () => {
    const hook = fs.readFileSync(HOOK_PATH, "utf-8");
    expect(hook).toMatch(/exportContextRulesPdf/);
    expect(src).toMatch(/Export PDF/);
  });

  it("has an Add rule button", () => {
    expect(src).toMatch(/Add rule/);
    const add = fs.readFileSync(ADD_PATH, "utf-8");
    expect(add).toMatch(/data-testid="context-rules-add-form"/);
  });

  it("does not use ReviewListCard on the Knowledge page", () => {
    expect(src).not.toMatch(/ReviewListCard/);
    expect(src).not.toMatch(/StatHero/);
    expect(src).not.toMatch(/SegmentedTabs/);
  });

  it("renders compact category cards that open a 16:9 detail dialog", () => {
    expect(src).toMatch(/ContextCategoryCard/);
    expect(src).toMatch(/ContextCategoryDialog/);
    const card = fs.readFileSync(CARD_PATH, "utf-8");
    expect(card).toMatch(/onOpen/);
    expect(card).toMatch(/Built-in/);
    expect(card).not.toMatch(/What it does/);
    const dialog = fs.readFileSync(DIALOG_PATH, "utf-8");
    expect(dialog).toMatch(/What it does/);
    expect(dialog).toMatch(/Why it is needed/);
    expect(dialog).toMatch(/If it is wrong/);
    expect(dialog).toMatch(/16 \/ 9/);
    expect(dialog).toMatch(/ContextExamplePanel/);
  });

  it("lets custom rules be deactivated", () => {
    const dialog = fs.readFileSync(DIALOG_PATH, "utf-8");
    expect(dialog).toMatch(/Deactivate/);
    expect(src).toMatch(/Deactivate context rule/);
    const hook = fs.readFileSync(HOOK_PATH, "utf-8");
    expect(hook).toMatch(/deactivate/);
  });

  it("does not use the deprecated standalone admin URL as a nav target", () => {
    expect(src).not.toMatch(/"\/admin\/context-rules"/);
  });
});

describe("Knowledge shell includes context-rules tab", () => {
  let src: string;
  beforeAll(() => {
    src = fs.readFileSync(KNOWLEDGE_PATH, "utf-8");
  });

  it("imports ContextRulesPage", () => {
    expect(src).toMatch(/ContextRulesPage/);
  });

  it("registers context-rules in TAB_PANELS", () => {
    expect(src).toMatch(/"context-rules":\s*ContextRulesPage/);
  });

  it("lists Context Rules in TABS", () => {
    expect(src).toMatch(/key:\s*"context-rules"/);
    expect(src).toMatch(/label:\s*"Context Rules"/);
  });
});

describe("Knowledge sidebar includes Context Rules under NLP & AI", () => {
  it("places context-rules in the NLP & AI group", () => {
    const src = fs.readFileSync(SIDEBAR_PATH, "utf-8");
    const nlpGroup = src.match(/label:\s*"NLP & AI"[\s\S]*?label:\s*"Clinical Knowledge"/);
    expect(nlpGroup).not.toBeNull();
    expect(nlpGroup![0]).toMatch(/key:\s*"context-rules"/);
    expect(nlpGroup![0]).toMatch(/label:\s*"Context Rules"/);
  });
});

describe("Settings Context Rules page stays intact for VT-LEO-AI-145", () => {
  it("still uses ReviewListCard on the settings route", () => {
    const src = fs.readFileSync(SETTINGS_PATH, "utf-8");
    expect(src).toMatch(/ReviewListCard/);
    expect(src).toMatch(/StatHero/);
    expect(src).toMatch(/SegmentedTabs/);
  });
});

describe("Category copy documents every category", () => {
  it("has what, why, and ifWrong for each category", () => {
    const src = fs.readFileSync(COPY_PATH, "utf-8");
    for (const key of [
      "NEGATED_EXISTENCE",
      "POSSIBLE_EXISTENCE",
      "HISTORICAL",
      "PLANNED",
      "HYPOTHETICAL",
      "FAMILY",
      "DECLINED",
      "CANCELLED",
    ]) {
      expect(src).toMatch(new RegExp(`${key}:`));
      expect(CATEGORY_KEYS).toContain(key);
      expect(CATEGORY_COPY[key].what.length).toBeGreaterThan(0);
      expect(CATEGORY_COPY[key].why.length).toBeGreaterThan(0);
      expect(CATEGORY_COPY[key].ifWrong.length).toBeGreaterThan(0);
    }
    expect(src).toMatch(/what:/);
    expect(src).toMatch(/why:/);
    expect(src).toMatch(/ifWrong:/);
  });

  it("has a with and without worked example for each category", () => {
    const panel = fs.readFileSync(EXAMPLE_PANEL_PATH, "utf-8");
    expect(panel).toMatch(/Without this rule/);
    expect(panel).toMatch(/With this rule/);
    expect(panel).toMatch(/What this does to the data/);
    expect(panel).toMatch(/Sample note/);
    for (const key of CATEGORY_KEYS) {
      expect(CATEGORY_COPY[key].withoutGuard.length).toBeGreaterThan(0);
      expect(CATEGORY_COPY[key].withGuard.length).toBeGreaterThan(0);
    }
  });

  it("keeps the category story and swaps the sample note with the phrase", () => {
    const copy = CATEGORY_COPY.NEGATED_EXISTENCE;
    const first = resolveContextExample(copy, sampleRule({
      literal: "nil",
      example: "nil chest pain -> no chest pain",
    }));
    const second = resolveContextExample(copy, sampleRule({
      literal: "no evidence of",
      example: "no evidence of infection -> infection is not present",
    }));
    expect(first.note).toBe("nil chest pain");
    expect(second.note).toBe("no evidence of infection");
    expect(first.withGuard).toBe(second.withGuard);
    expect(first.withoutGuard).toBe(copy.withoutGuard);
    expect(first.dataChange).toBe(copy.dataChange);
  });
});
