/**
 * VT-LEO-AI-511 -- TC-001 static-source check.
 *
 * The widescreen step-rail editor (DI-LEO-AI-512 / DO-LEO-AI-512) is
 * implemented across an orchestrator + a StepRail + a LivePreviewPane +
 * four step modules. This test reads the orchestrator file as a string
 * and asserts that all the wiring is present so a future refactor
 * cannot silently regress the file structure.
 */

import { promises as fs } from "fs";
import * as path from "path";

const DIALOG_ROOT = path.resolve(
  __dirname,
  "..",
  "app",
  "admin",
  "guidance",
  "EditRuleDialog",
);

async function readDialog(): Promise<string> {
  return fs.readFile(path.join(DIALOG_ROOT, "index.tsx"), "utf8");
}

describe("EditRuleDialog stepped shell -- VT-511-TC-001", () => {
  it("orchestrator imports the StepRail, LivePreviewPane and all four steps", async () => {
    const src = await readDialog();
    expect(src).toMatch(/import\s+StepRail[\s\S]*?from\s+["']\.\/StepRail["']/);
    expect(src).toMatch(
      /import\s+LivePreviewPane\s+from\s+["']\.\/LivePreviewPane["']/,
    );
    expect(src).toMatch(/import\s+Step1Who\s+from\s+["']\.\/steps\/Step1Who["']/);
    expect(src).toMatch(
      /import\s+Step2Suggest\s+from\s+["']\.\/steps\/Step2Suggest["']/,
    );
    expect(src).toMatch(/import\s+Step3Try\s+from\s+["']\.\/steps\/Step3Try["']/);
    expect(src).toMatch(/import\s+Step4Save\s+from\s+["']\.\/steps\/Step4Save["']/);
  });

  it("orchestrator declares a three-column gridTemplateColumns at the md breakpoint", async () => {
    const src = await readDialog();
    expect(src).toMatch(/gridTemplateColumns/);
    // The md column declaration has three minmax columns separated by spaces.
    const mdMatch = src.match(/md:\s*"([^"]+)"/);
    expect(mdMatch).not.toBeNull();
    const minmaxCount = (mdMatch?.[1] ?? "").match(/minmax\(/g)?.length ?? 0;
    expect(minmaxCount).toBe(3);
  });

  it("each step module exists on disk at the path listed in DO-LEO-AI-512", async () => {
    const expected = [
      "StepRail.tsx",
      "LivePreviewPane.tsx",
      "steps/Step1Who.tsx",
      "steps/Step2Suggest.tsx",
      "steps/Step3Try.tsx",
      "steps/Step4Save.tsx",
      "copy.ts",
    ];
    for (const rel of expected) {
      const full = path.join(DIALOG_ROOT, rel);
      await expect(fs.access(full)).resolves.toBeUndefined();
    }
  });

  it("save handler omits criterion when actionDirty is false and includes it when true", async () => {
    const src = await readDialog();
    // Spread guards the criterion field: ...(actionDirty && action ? { action } : {})
    expect(src).toMatch(/actionDirty\s*&&\s*action\s*\?\s*\{\s*action\s*\}\s*:\s*\{\s*\}/);
    // node ids are stripped from the saved logic_tree.
    expect(src).toMatch(/stripNodeIds\(tree\)/);
  });
});
