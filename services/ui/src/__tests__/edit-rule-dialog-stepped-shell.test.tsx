/**
 * VT-LEO-AI-511 -- TC-001 static-source check.
 *
 * The widescreen step editor (DI-LEO-AI-512 / DO-LEO-AI-512) is
 * implemented across an orchestrator + a HorizontalStepper + a LivePreviewPane +
 * three step modules (the former sandbox-test "Step3Try" step was
 * removed as awkward/redundant with the Bitmap Lifecycle compile-time
 * check). This test reads the orchestrator file as a string and
 * asserts that all the wiring is present so a future refactor cannot
 * silently regress the file structure.
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
  it("orchestrator imports the HorizontalStepper, LivePreviewPane and all three steps", async () => {
    const src = await readDialog();
    expect(src).toMatch(
      /import\s+HorizontalStepper[\s\S]*?from\s+["']\.\/HorizontalStepper["']/,
    );
    expect(src).toMatch(
      /import\s+LivePreviewPane\s+from\s+["']\.\/LivePreviewPane["']/,
    );
    expect(src).toMatch(/import\s+Step1Who\s+from\s+["']\.\/steps\/Step1Who["']/);
    expect(src).toMatch(
      /import\s+Step2Suggest\s+from\s+["']\.\/steps\/Step2Suggest["']/,
    );
    expect(src).toMatch(/import\s+Step4Save\s+from\s+["']\.\/steps\/Step4Save["']/);
    expect(src).not.toMatch(/Step3Try/);
  });

  it("orchestrator declares the md two-pane flex layout", async () => {
    const src = await readDialog();
    expect(src).toMatch(/flexDirection:\s*\{\s*xs:\s*"column",\s*md:\s*"row"\s*\}/);
    expect(src).toMatch(/md:\s*"0 0 60%"/);
    expect(src).toMatch(/md:\s*"0 0 40%"/);
  });

  it("each step module exists on disk at the path listed in DO-LEO-AI-512", async () => {
    const expected = [
      "HorizontalStepper.tsx",
      "LivePreviewPane.tsx",
      "steps/Step1Who.tsx",
      "steps/Step2Suggest.tsx",
      "steps/Step4Save.tsx",
      "copy.ts",
    ];
    for (const rel of expected) {
      const full = path.join(DIALOG_ROOT, rel);
      await expect(fs.access(full)).resolves.toBeUndefined();
    }
  });

  it("the sandbox test-patients step module no longer exists on disk", async () => {
    await expect(
      fs.access(path.join(DIALOG_ROOT, "steps/Step3Try.tsx")),
    ).rejects.toBeDefined();
    await expect(
      fs.access(path.join(DIALOG_ROOT, "TestPatientsPanel.tsx")),
    ).rejects.toBeDefined();
  });

  it("save handler omits actions when actionsDirty is false and includes it when true", async () => {
    const src = await readDialog();
    // Spread guards the actions field: ...(actionsDirty ? { actions: ... } : {})
    expect(src).toMatch(
      /actionsDirty\s*\?\s*\{\s*actions:\s*sanitiseActionsForSave\(actions\)\s*\}\s*:\s*\{\s*\}/,
    );
    // node ids are stripped from the saved logic_tree.
    expect(src).toMatch(/stripNodeIds\(tree\)/);
  });
});
