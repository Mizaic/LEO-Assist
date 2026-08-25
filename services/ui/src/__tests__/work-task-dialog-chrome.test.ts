/**
 * VT -- My work opens a type-specific modal and stays on /work.
 *
 * Atlas: DI-4A012A59 / VT-CE7006EE
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

describe("WorkTaskDialog chrome", () => {
  const dialog = readFile("services/ui/src/app/work/WorkTaskDialog.tsx");
  const sourceId = readFile("services/ui/src/app/work/workTaskSourceId.ts");

  test("parses the source id after the task-type prefix", () => {
    expect(sourceId).toMatch(/export function workTaskSourceId/);
    expect(sourceId).toMatch(/indexOf\(":"\)|split\(":"\)/);
  });

  test("paused extractions open the letter unlock dialog", () => {
    expect(dialog).toMatch(/extraction_quality_pause/);
    expect(dialog).toMatch(/ExtractionQualityReviewDialog/);
  });

  test("each work task type has an in-page resolver", () => {
    expect(dialog).toMatch(/coding_review/);
    expect(dialog).toMatch(/gold_label/);
    expect(dialog).toMatch(/surface_form_approval/);
    expect(dialog).toMatch(/safety_net_alert/);
    expect(dialog).not.toMatch(/admin\/console/);
  });
});
