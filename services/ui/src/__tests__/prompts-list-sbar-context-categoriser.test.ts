/**
 * VT-LEO-AI-509 -- AI Instructions categoriser routes
 * sbar_situation_context_* PromptConfig rows by the [<Group>] prefix
 * in their description.
 *
 * Static-source assertion: the categoriser change in
 * services/ui/src/app/admin/prompts/page.tsx must
 *   1. detect the sbar_situation_context_ name prefix; and
 *   2. parse the [<Group>] description prefix and use that as the
 *      category label, so the AI Instructions list shows these rows
 *      under Primary care / Secondary care / Statutory and social /
 *      Quality assurance instead of dumping them under General.
 *
 * We assert on source because the categoriser is a leaf helper
 * (returning JSX icons) that is awkward to evaluate in jsdom without
 * a full React renderer; the contract we care about is the mapping
 * from name + description -> label, and that mapping lives entirely
 * in the source string.
 */

import fs from "fs";
import path from "path";

const PAGE = path.resolve(
  __dirname,
  "..",
  "app",
  "admin",
  "prompts",
  "page.tsx",
);

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

describe("VT-LEO-AI-509 prompts/page categorise() routes SBAR contexts", () => {
  const src = read(PAGE);

  it("recognises the sbar_situation_context_ name prefix", () => {
    expect(src).toContain("sbar_situation_context_");
    expect(src).toMatch(/name\.startsWith\("sbar_situation_context_"\)/);
  });

  it("parses the [<Group>] prefix from the description", () => {
    expect(src).toContain("description?.match(/^\\[([^\\]]+)\\]/)");
  });

  it("ships a style entry for each of the four allowed groups", () => {
    expect(src).toMatch(/SBAR_CONTEXT_GROUP_STYLE/);
    for (const group of [
      "Primary care",
      "Secondary care",
      "Statutory and social",
      "Quality assurance",
    ]) {
      expect(src).toContain(`"${group}":`);
    }
  });

  it("falls back to a Summarisation context label when no [<Group>] prefix matches", () => {
    expect(src).toContain('"Summarisation context"');
  });

  it("routes computeStats / filtering / grouping through categoriseFromPrompt", () => {
    // Every internal call site (stats, filter, grouped, segmented tabs)
    // must use categoriseFromPrompt so the description is read; bare
    // `categorise(p.name)` calls would leak SBAR-context rows into
    // the General bucket.
    expect(src).toContain("categoriseFromPrompt");
    const bareNameOnly = src.match(/categorise\(p\.name\)/g) ?? [];
    expect(bareNameOnly.length).toBe(0);
  });
});
