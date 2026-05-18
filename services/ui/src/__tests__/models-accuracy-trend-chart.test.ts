/**
 * VT-F1C75ADC - Static-source verification for the
 * "Accuracy over time" chart on the /admin/models page.
 *
 * Atlas trace:
 *   DI: DI-3F771AFB
 *   DO: DO-2C03CA0E
 *   VT: VT-F1C75ADC
 *   Look up via: get_design_control(dc_type="verification-test",
 *     dc_id="VT-F1C75ADC")
 *
 * Files under test:
 *   - services/ui/src/app/admin/models/AccuracyOverTime.tsx
 *   - services/ui/src/app/admin/models/page.tsx
 *
 * Acceptance criteria (1:1 with the Atlas VT):
 *   AC1 - Imports AreaChart, Area, XAxis, YAxis, Tooltip,
 *         ResponsiveContainer from "recharts".
 *   AC2 - A SectionCard titled "Accuracy over time" is rendered
 *         above the "Medical coder - versions & deployment" card.
 *   AC3 - The chart exposes a Precision / Recall / F1 toggle and
 *         defaults to F1.
 *   AC4 - Only offline metrics (offline_precision, offline_recall)
 *         are charted; trial-run (canary_*) metrics are not plotted.
 *   AC5 - Versions are sorted by registered_at ascending so the
 *         x-axis reads oldest-to-newest.
 *   AC6 - When fewer than two versions have offline metrics, an
 *         empty-state message is rendered instead of a blank chart.
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

const COMPONENT_PATH =
  "services/ui/src/app/admin/models/AccuracyOverTime.tsx";
const PAGE_PATH = "services/ui/src/app/admin/models/page.tsx";

describe("VT-F1C75ADC - Models page accuracy-over-time chart", () => {
  test("AC1: AccuracyOverTime imports the required recharts primitives", () => {
    const src = readFile(COMPONENT_PATH);
    expect(src).toMatch(/from\s+["']recharts["']/);
    expect(src).toMatch(/\bAreaChart\b/);
    expect(src).toMatch(/\bArea\b/);
    expect(src).toMatch(/\bXAxis\b/);
    expect(src).toMatch(/\bYAxis\b/);
    expect(src).toMatch(/\bTooltip\b/);
    expect(src).toMatch(/\bResponsiveContainer\b/);
  });

  test("AC2: SectionCard 'Accuracy over time' renders above the medical coder versions card", () => {
    const src = readFile(PAGE_PATH);
    expect(src).toMatch(/import\s+AccuracyOverTime\s+from\s+["']\.\/AccuracyOverTime["']/);
    expect(src).toMatch(/title=["']Accuracy over time["']/);
    expect(src).toMatch(/<AccuracyOverTime\s+versions=\{versions\}\s*\/>/);

    const idxNew = src.indexOf("Accuracy over time");
    const idxLifecycle = src.indexOf(
      "Medical coder \u2014 versions & deployment",
    );
    expect(idxNew).toBeGreaterThan(0);
    expect(idxLifecycle).toBeGreaterThan(0);
    expect(idxNew).toBeLessThan(idxLifecycle);
  });

  test("AC3: chart exposes Precision / Recall / F1 toggle and defaults to F1", () => {
    const src = readFile(COMPONENT_PATH);
    expect(src).toMatch(/useState<Metric>\(["']f1["']\)/);
    expect(src).toMatch(/<ToggleButton\s+value=["']precision["']>Precision</);
    expect(src).toMatch(/<ToggleButton\s+value=["']recall["']>Recall</);
    expect(src).toMatch(/<ToggleButton\s+value=["']f1["']>F1</);
    expect(src).toMatch(/aria-label=["']Metric["']/);
  });

  test("AC4: only offline metrics are charted, trial-run (canary_*) is not", () => {
    const src = readFile(COMPONENT_PATH);
    expect(src).toMatch(/offline_precision/);
    expect(src).toMatch(/offline_recall/);
    expect(src).not.toMatch(/canary_precision/);
    expect(src).not.toMatch(/canary_recall/);
  });

  test("AC5: versions are sorted by registered_at ascending", () => {
    const src = readFile(COMPONENT_PATH);
    expect(src).toMatch(/registered_at[\s\S]*?registered_at/);
    expect(src).toMatch(
      /\.sort\(\s*\([\s\S]*?\)\s*=>\s*[\s\S]*?new Date\(a\.registered_at\)\.getTime\(\)\s*-\s*new Date\(b\.registered_at\)\.getTime\(\)/,
    );
  });

  test("AC6: empty-state message renders when fewer than two versions have offline metrics", () => {
    const src = readFile(COMPONENT_PATH);
    expect(src).toMatch(/data-testid=["']accuracy-empty["']/);
    expect(src).toMatch(/at least two registered versions/i);
    expect(src).toMatch(/data\.length\s*<\s*2/);
  });
});
