/**
 * VT-LEO-AI-134 TC-005 -- source-level integration check.
 *
 * Verifies that services/ui/src/app/work/page.tsx wires the
 * TaskQueue primitive to /api/work/tasks and surfaces the
 * counts-by-source strip.
 */

import fs from "fs";
import path from "path";

const WORK_PAGE = path.resolve(
  __dirname,
  "..",
  "app",
  "work",
  "page.tsx",
);

describe("WorkPage integration (VT-LEO-AI-134 TC-005)", () => {
  const source = fs.readFileSync(WORK_PAGE, "utf8");

  test("imports TaskQueue from the design system and AreaIntro wrapper", () => {
    expect(source).toMatch(/TaskQueue/);
    expect(source).toMatch(/AreaIntro/);
    expect(source).toMatch(/@leo\/design-system/);
  });

  test("fetches the unified /api/work/tasks endpoint", () => {
    expect(source).toMatch(/\/api\/work\/tasks/);
  });

  test("passes counts_by_source through to the queue", () => {
    expect(source).toMatch(/counts_by_source/);
    expect(source).toMatch(/countsBySource/);
  });

  test("surfaces an error state when the fetch fails", () => {
    expect(source).toMatch(/setError/);
    expect(source).toMatch(/data-testid="work-error"/);
  });

  test("mounts AreaIntro with area='work' so intro copy adapts to staff", () => {
    expect(source).toMatch(/AreaIntro area="work"/);
  });

  test("selecting a row opens an in-page modal instead of leaving /work", () => {
    expect(source).toMatch(/onSelectTask/);
    expect(source).toMatch(/WorkTaskDialog/);
    expect(source).not.toMatch(/window\.location/);
    expect(source).not.toMatch(/router\.(push|replace)/);
  });

  test("paused extractions can be removed from the list without leaving /work", () => {
    expect(source).toMatch(/onCancelTask/);
    expect(source).toMatch(/WorkCancelDialog/);
    expect(source).toMatch(/extraction_quality_pause/);
    expect(source).not.toMatch(/extraction-reviews\/complete/);
  });
});
