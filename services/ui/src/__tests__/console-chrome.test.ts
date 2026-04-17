/**
 * VT-LEO-AI-162 -- Intelligence Console Wave E Phase 8a chrome.
 *
 * Static-source verification that /admin/console has been moved onto
 * the @leo/design-system spine: KnowledgePageLayout (width="wide",
 * screenId="admin-console") + StatHero + PipelineRail + NudgeStrip
 * + ConsoleStagePanel, with the legacy HealthBar / NudgeBanner imports
 * removed. Also pins the API contract of the new primitives and the
 * additive computeConsoleStats helper.
 *
 * Design Controls: DI-LEO-AI-164, DO-LEO-AI-163, R-LEO-AI-165, VT-LEO-AI-162.
 */

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const PAGE = path.join(ROOT, "services/ui/src/app/admin/console/page.tsx");
const STATE = path.join(
  ROOT,
  "services/ui/src/components/console/useConsoleState.ts",
);
const PANEL = path.join(
  ROOT,
  "services/ui/src/components/console/ConsoleStagePanel.tsx",
);
const RAIL = path.join(
  ROOT,
  "services/design-system/src/primitives/PipelineRail.tsx",
);
const NUDGE = path.join(
  ROOT,
  "services/design-system/src/primitives/NudgeStrip.tsx",
);
const PRIM_INDEX = path.join(
  ROOT,
  "services/design-system/src/primitives/index.ts",
);

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

describe("VT-LEO-AI-162 - Intelligence Console chrome (Phase 8a)", () => {
  test("TC-001: page imports the design-system spine", () => {
    const src = read(PAGE);
    const importBlock = src.match(
      /import\s*\{[\s\S]*?\}\s*from\s+["']@leo\/design-system["']/,
    );
    expect(importBlock).not.toBeNull();
    expect(importBlock![0]).toMatch(/KnowledgePageLayout/);
    expect(importBlock![0]).toMatch(/StatHero/);
    expect(importBlock![0]).toMatch(/PipelineRail/);
    expect(importBlock![0]).toMatch(/NudgeStrip/);
  });

  test("TC-002: legacy HealthBar / NudgeBanner imports are removed", () => {
    const src = read(PAGE);
    const importLines = src
      .split("\n")
      .filter((line) => /^\s*import/.test(line))
      .join("\n");
    expect(importLines).not.toMatch(/\bHealthBar\b/);
    expect(importLines).not.toMatch(/\bNudgeBanner\b/);
  });

  test("TC-003: KnowledgePageLayout is invoked with admin-console + wide", () => {
    const src = read(PAGE);
    const layout = src.match(/<KnowledgePageLayout[\s\S]*?>/);
    expect(layout).not.toBeNull();
    expect(layout![0]).toMatch(/screenId="admin-console"/);
    expect(layout![0]).toMatch(/width="wide"/);
    expect(src).toMatch(/<\/KnowledgePageLayout>/);
  });

  test("TC-004: computeConsoleStats helper is exported with >= 3 tiles", () => {
    const src = read(STATE);
    expect(src).toMatch(/export function computeConsoleStats/);
    const fn = src.match(
      /export function computeConsoleStats[\s\S]*?\n\}/,
    );
    expect(fn).not.toBeNull();
    const body = fn![0];
    expect(body).toMatch(/goldTile/);
    expect(body).toMatch(/queueTile/);
    expect(body).toMatch(/modelTile/);
    expect(body).toMatch(/return\s*\[[\s\S]+?\]/);
  });

  test("TC-005: PipelineRail primitive exposes the agreed contract", () => {
    const src = read(RAIL);
    expect(src).toMatch(/export function PipelineRail/);
    expect(src).toMatch(/role="tablist"/);
    expect(src).toMatch(/useMotion/);
    expect(src).toMatch(/event\.key === "Enter" \|\| event\.key === " "/);
  });

  test("TC-006: NudgeStrip primitive exposes the agreed contract", () => {
    const src = read(NUDGE);
    expect(src).toMatch(/export function NudgeStrip/);
    expect(src).toMatch(/role="status"/);
    expect(src).toMatch(/aria-live="polite"/);
    expect(src).toMatch(/color\.status\./);
    expect(src).toMatch(/severity[\s\S]*?["']info["']/);
    expect(src).toMatch(/["']warning["']/);
    expect(src).toMatch(/["']danger["']/);
  });

  test("TC-007: ConsoleStagePanel preserves accent + action surface", () => {
    const src = read(PANEL);
    expect(src).toMatch(/export function ConsoleStagePanel/);
    expect(src).toMatch(/accentColor/);
    expect(src).toMatch(/actionLabel/);
    expect(src).toMatch(/onAction/);
    expect(src).toMatch(/defaultExpanded/);
    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
  });

  test("TC-008: design-system index re-exports PipelineRail + NudgeStrip", () => {
    const src = read(PRIM_INDEX);
    expect(src).toMatch(/PipelineRail/);
    expect(src).toMatch(/NudgeStrip/);
    expect(src).toMatch(/from\s+["']\.\/PipelineRail["']/);
    expect(src).toMatch(/from\s+["']\.\/NudgeStrip["']/);
  });

  test("TC-009: page preserves stage handlers + 10s polling contract", () => {
    const src = read(PAGE);
    expect(src).toMatch(/handleTrain/);
    expect(src).toMatch(/handleCancelJob/);
    expect(src).toMatch(/api\/training-worker\/jobs/);
    expect(src).toMatch(/api\/training\/jobs\//);
    expect(src).toMatch(/<DiscoverStage/);
    expect(src).toMatch(/<CurateStage/);
    expect(src).toMatch(/<TrainStage/);
    expect(src).toMatch(/<EvaluateStage/);
    expect(src).toMatch(/<DeployStage/);
    expect(src).toMatch(/<MonitorStage/);
  });

  test("TC-010: page still renders AreaIntro for the operations area", () => {
    // Cross-check with VT-LEO-AI-135 TC-004 (area-intro-wiring): every
    // top-level admin landing page must still mount the role-aware
    // AreaIntro IntroCard.
    const src = read(PAGE);
    expect(src).toMatch(/import\s+AreaIntro/);
    expect(src).toMatch(/<AreaIntro\s+area="operations"\s*\/>/);
  });
});
