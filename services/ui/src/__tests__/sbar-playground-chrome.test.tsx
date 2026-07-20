/**
 * VT-LEO-AI-184 -- SBAR Playground retired into Validation Lab.
 *
 * The clinical harness now lives at /admin/validation-lab.
 * Legacy component files may remain for reference until deleted;
 * Knowledge registry must not re-mount the playground tab.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app");

const FILES = {
  knowledgePage: path.join(ROOT, "admin", "knowledge", "page.tsx"),
  playgroundPage: path.join(ROOT, "admin", "ai-summarisation", "page.tsx"),
  validationLab: path.join(ROOT, "admin", "validation-lab", "page.tsx"),
  copy: path.resolve(__dirname, "..", "lib", "knowledgeCopy.ts"),
  hook: path.resolve(__dirname, "..", "hooks", "useSbarStream.ts"),
};

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

describe("VT-LEO-AI-184 SBAR playground retired to Validation Lab", () => {
  it("registers Validation Lab instead of ai-summarisation", () => {
    const src = read(FILES.knowledgePage);
    expect(src).toMatch(/key:\s*"validation-lab"/);
    expect(src).toMatch(/ValidationLabPage/);
    expect(src).not.toMatch(/AiSummarisationPage/);
  });

  it("declares validation-lab copy", () => {
    const src = read(FILES.copy);
    expect(src).toMatch(/"validation-lab":\s*\{/);
    expect(src).toMatch(/Validation Lab/);
    expect(src).not.toMatch(/"ai-summarisation":\s*\{/);
  });

  it("legacy ai-summarisation page redirects to Validation Lab", () => {
    const src = read(FILES.playgroundPage);
    expect(src).toMatch(/\/admin\/validation-lab/);
    expect(src).toMatch(/router\.replace/);
  });

  it("Validation Lab mounts the single patient wizard flow with LeoSbarHost", () => {
    const src = read(FILES.validationLab);
    const cases = read(
      path.join(ROOT, "admin", "validation-lab", "LabCasesPanel.tsx"),
    );
    expect(src).toMatch(/validation-lab-page/);
    expect(src).toMatch(/LabCasesPanel/);
    expect(cases).toMatch(/LeoSbarHost/);
  });

  it("hook still posts to /api/sbar/jobs for non-Lab consumers", () => {
    const src = read(FILES.hook);
    expect(src).toContain('"/api/sbar/jobs"');
    expect(src).toMatch(/sbar_completed/);
  });
});
