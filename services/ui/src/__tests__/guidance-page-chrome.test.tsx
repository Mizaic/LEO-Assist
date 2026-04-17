/**
 * VT-LEO-AI-150 -- Clinical Guidelines page Wave E Phase 5 chrome.
 *
 * Static-source verification:
 *   - Imports the design-system SegmentedTabs primitive.
 *   - Removes legacy SectionBox / Card chrome in favour of motion-enabled
 *     StepCard sections.
 *   - Preserves all four child sections (NiceLoaderSection,
 *     LoadedGuidelinesPanel, RuleReviewSection, BitmapLifecycleSection)
 *     and their state-bridging refresh keys.
 *   - Provides a sticky workflow jump strip (Load / Review / Compile)
 *     wired through SegmentedTabs.
 *
 * Design Controls: DI-LEO-AI-152, DO-LEO-AI-148, VT-LEO-AI-150.
 */

import * as fs from "fs";
import * as path from "path";

const SRC = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance/page.tsx",
);

function readFile(): string {
  return fs.readFileSync(SRC, "utf8");
}

describe("VT-LEO-AI-150 - Clinical Guidelines chrome", () => {
  test("TC-001: imports design-system SegmentedTabs primitive", () => {
    const src = readFile();
    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
    expect(src).toMatch(/SegmentedTabs/);
  });

  test("TC-002: imports motion from framer-motion for stagger entry", () => {
    const src = readFile();
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/fm\.section/);
  });

  test("TC-003: removes legacy heavy 4px-accent Card chrome", () => {
    const src = readFile();
    expect(src).not.toMatch(/borderLeft:\s*"4px solid"/);
    expect(src).not.toMatch(/import\s+Card\s+from\s+"@mui\/material\/Card"/);
    expect(src).not.toMatch(/import\s+CardContent\s+from\s+"@mui\/material\/CardContent"/);
  });

  test("TC-004: each StepCard uses 12px radius and 3px tone-coded accent strip", () => {
    const src = readFile();
    expect(src).toMatch(/borderRadius:\s*12,/);
    expect(src).toMatch(/width:\s*3,/);
    expect(src).toMatch(/background:\s*accent,/);
  });

  test("TC-005: preserves all four child sections", () => {
    const src = readFile();
    expect(src).toMatch(/<NiceLoaderSection[\s\S]*?onGuidelineLoaded=/);
    expect(src).toMatch(/<LoadedGuidelinesPanel[\s\S]*?refreshKey=/);
    expect(src).toMatch(/<RuleReviewSection[\s\S]*?refreshKey=/);
    expect(src).toMatch(/<BitmapLifecycleSection\s*\/>/);
  });

  test("TC-006: preserves both refresh-key state bridges between sections", () => {
    const src = readFile();
    expect(src).toMatch(/loadedRefreshKey/);
    expect(src).toMatch(/ruleRefreshKey/);
    expect(src).toMatch(/setLoadedRefreshKey\(\(n\)\s*=>\s*n\s*\+\s*1\)/);
    expect(src).toMatch(/setRuleRefreshKey\(\(n\)\s*=>\s*n\s*\+\s*1\)/);
  });

  test("TC-007: provides a sticky workflow jump strip with three steps", () => {
    const src = readFile();
    const stepTabs = src.match(/STEP_TABS[\s\S]*?\];/m);
    expect(stepTabs).not.toBeNull();
    expect(stepTabs![0]).toMatch(/id:\s*"load"/);
    expect(stepTabs![0]).toMatch(/id:\s*"review"/);
    expect(stepTabs![0]).toMatch(/id:\s*"compile"/);
    expect(src).toMatch(/position:\s*"sticky"/);
    expect(src).toMatch(/data-testid="guidance-jump-strip"/);
  });

  test("TC-008: SegmentedTabs uses the correct tabs/value/aria-label API", () => {
    const src = readFile();
    const seg = src.match(/<SegmentedTabs[\s\S]*?\/>/);
    expect(seg).not.toBeNull();
    expect(seg![0]).toMatch(/tabs=\{/);
    expect(seg![0]).toMatch(/value=\{activeStep\}/);
    expect(seg![0]).toMatch(/aria-label="Jump to guidance workflow step"/);
    expect(seg![0]).not.toMatch(/\bitems=/);
  });

  test("TC-009: ID and structure matches the three-step workflow", () => {
    const src = readFile();
    expect(src).toMatch(/id="nice-loader"/);
    expect(src).toMatch(/id="loaded-guidelines"/);
    expect(src).toMatch(/id="rule-review"/);
    expect(src).toMatch(/id="bitmap-lifecycle"/);
    const stepProps = src.match(/step=\{(\d)\}/g);
    expect(stepProps).not.toBeNull();
    expect(stepProps!.sort()).toEqual(["step={1}", "step={2}", "step={3}"]);
  });
});
