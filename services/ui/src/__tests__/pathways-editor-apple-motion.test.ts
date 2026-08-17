/**
 * Pathway editor -- Apple fluid-interface + Mizaic brand chrome.
 *
 * Cosmetic motion/material polish on the canvas editor. No new
 * clinical or graph behaviour.
 *
 * Design Controls: DI-693FFEEA, DI-C5A523A7, DI-613A48DA.
 */
import fs from "fs";
import path from "path";

const EDITOR = path.resolve(
  __dirname,
  "..",
  "app",
  "admin",
  "pathways",
  "[id]",
  "editor",
);
const NODES = path.resolve(
  __dirname,
  "..",
  "components",
  "pathway",
  "nodes",
  "_base",
);
const PAGE = path.resolve(
  __dirname,
  "..",
  "app",
  "admin",
  "pathways",
  "[id]",
  "page.tsx",
);

function read(dir: string, name: string): string {
  return fs.readFileSync(path.join(dir, name), "utf8");
}

describe("Pathway editor Apple motion and brand kit", () => {
  const page = fs.readFileSync(PAGE, "utf8");
  const strip = read(EDITOR, "EditorStrip.tsx");
  const base = read(NODES, "BaseNode.tsx");

  it("keeps trigger, mode, and validation in frost strips", () => {
    expect(page).toMatch(/<TriggerContextPanel\b/);
    expect(page).toMatch(/<WorkflowModeBar\b/);
    expect(page).toMatch(/<ValidationPanel\b/);
    expect(page).toMatch(/testId="pathway-editor-chrome"|data-testid="pathway-editor-chrome"/);
    expect(strip).toMatch(/frostStyle\(/);
    expect(strip).toMatch(/Show/);
  });

  it("canvas sits on the brand canvas token", () => {
    expect(page).toMatch(/color\.surface\.canvas/);
    expect(page).toMatch(/<Background\s+color=\{color\.text\.disabled\}/);
  });

  it("nodes use brand tokens and card elevation, not Material hex", () => {
    expect(base).toMatch(/color\.brand\.primary/);
    expect(base).toMatch(/elevation\.card/);
    expect(base).toMatch(/borderRadius:\s*"12px"/);
    expect(base).not.toMatch(/#1976D2/);
    expect(base).not.toMatch(/#1D4ED8/i);
    expect(base).not.toMatch(/ease-out/);
  });
});
