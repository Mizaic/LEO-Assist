/**
 * Workflow list chrome -- SegmentedTabs wiring.
 *
 * Static-source verification:
 *   - SegmentedTabs tab objects use `id` (not `value`) so React keys
 *     are unique and the selected pill matches.
 */

import * as fs from "fs";
import * as path from "path";

const PAGE = path.resolve(
  __dirname,
  "../app/admin/workflows/page.tsx",
);

function read(): string {
  return fs.readFileSync(PAGE, "utf8");
}

describe("Workflow list chrome", () => {
  test("delete dialog confirms against the displayed title", () => {
    const src = fs.readFileSync(
      path.resolve(__dirname, "../app/admin/workflows/dialogs.tsx"),
      "utf8",
    );
    expect(src).toMatch(/workflowTitle/);
    expect(src).toMatch(/Type <strong>\{title\}<\/strong> to confirm/);
  });

  test("SegmentedTabs tab objects use id, not value", () => {
    const src = read();
    const seg = src.match(/<SegmentedTabs[\s\S]*?\/>/);
    expect(seg).not.toBeNull();
    expect(seg![0]).toMatch(/id:\s*"all"/);
    expect(seg![0]).not.toMatch(/value:\s*"all"/);
  });
});
