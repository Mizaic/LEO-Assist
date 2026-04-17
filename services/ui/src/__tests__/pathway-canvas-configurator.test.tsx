// VT-LEO-AI-157 - Pathway editor configurator wiring (Phase 6b-iv)
// Static-source verification that page.tsx wires ConditionRuleBuilder under
// the wizard's Settings step for condition nodes, installs useDirtyGuard
// with beforeunload, derives PathwaySaveBar's state from the orchestrator's
// save lifecycle, and replaces the silent .catch(() => {}) with a visible
// PathwayLoadError surface.

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const EDITOR = path.join(
  ROOT,
  "services/ui/src/app/admin/pathways/[id]/editor",
);
const PAGE = path.join(
  ROOT,
  "services/ui/src/app/admin/pathways/[id]/page.tsx",
);

function readPage(): string {
  return fs.readFileSync(PAGE, "utf-8");
}

function readEditor(rel: string): string {
  return fs.readFileSync(path.join(EDITOR, rel), "utf-8");
}

describe("VT-LEO-AI-157 - Pathway editor configurator wiring", () => {
  it("VT-157-TC-001: useDirtyGuard hook file exists", () => {
    expect(fs.existsSync(path.join(EDITOR, "hooks/useDirtyGuard.ts"))).toBe(
      true,
    );
  });

  it("VT-157-TC-002: PathwayLoadError component file exists", () => {
    expect(fs.existsSync(path.join(EDITOR, "PathwayLoadError.tsx"))).toBe(true);
  });

  it("VT-157-TC-003: useDirtyGuard exports the canonical surface", () => {
    const src = readEditor("hooks/useDirtyGuard.ts");
    expect(src).toMatch(/export\s+function\s+useDirtyGuard/);
    expect(src).toMatch(/export\s+function\s+computePathwaySignature/);
    expect(src).toMatch(/markSaved/);
  });

  it("VT-157-TC-004: useDirtyGuard installs beforeunload while dirty", () => {
    const src = readEditor("hooks/useDirtyGuard.ts");
    expect(src).toMatch(/addEventListener\(\s*["']beforeunload["']/);
    expect(src).toMatch(/removeEventListener\(\s*["']beforeunload["']/);
  });

  it("VT-157-TC-005: page.tsx imports the new wiring", () => {
    const src = readPage();
    expect(src).toMatch(/from\s+["']\.\/editor\/PathwaySaveBar["']/);
    expect(src).toMatch(/from\s+["']\.\/editor\/PathwayLoadError["']/);
    expect(src).toMatch(/from\s+["']\.\/editor\/hooks\/useDirtyGuard["']/);
    expect(src).toMatch(
      /ConditionRuleBuilder[\s\S]*?from\s+["']@\/components\/pathway\/panel\/ConditionRuleBuilder["']/,
    );
  });

  it("VT-157-TC-006: ConditionRuleBuilder is wired under nodeType === \"condition\"", () => {
    const src = readPage();
    expect(src).toContain("<ConditionRuleBuilder");
    // The guard for the JSX block must include the condition type check.
    const builderIdx = src.indexOf("<ConditionRuleBuilder");
    const window = src.slice(Math.max(0, builderIdx - 1200), builderIdx);
    expect(window).toMatch(/config\.nodeType\s*===\s*"condition"/);
  });

  it("VT-157-TC-007: catch-all SubgraphSettingsPanel branch excludes condition", () => {
    const src = readPage();
    expect(src).toMatch(/config\.nodeType\s*!==\s*"condition"/);
  });

  it("VT-157-TC-008: useDirtyGuard is consumed in page.tsx", () => {
    const src = readPage();
    expect(src).toMatch(/useDirtyGuard\s*\(/);
    expect(src).toMatch(/markSaved/);
    expect(src).toMatch(/planLoaded/);
  });

  it("VT-157-TC-009: markSaved fires after a successful PUT", () => {
    const src = readPage();
    const putIdx = src.indexOf("api.put(`/fhir/PlanDefinition/");
    expect(putIdx).toBeGreaterThan(-1);
    const window = src.slice(putIdx, Math.min(src.length, putIdx + 800));
    expect(window).toMatch(/markSaved\s*\(\s*\)/);
  });

  it("VT-157-TC-010: PathwaySaveBar is rendered with derived state", () => {
    const src = readPage();
    expect(src).toContain("<PathwaySaveBar");
    expect(src).toMatch(/"saving"\s+as\s+SaveBarState/);
    expect(src).toMatch(/"dirty"\s+as\s+SaveBarState/);
    expect(src).toMatch(/onSave=\{\s*\(\)\s*=>\s*handleSave\(\)\s*\}/);
  });

  it("VT-157-TC-011: silent catch on the plan loader is removed", () => {
    const src = readPage();
    // The orchestrator must surface plan-load failures via setLoadError
    // rather than swallowing them with `.catch(() => {})`.
    expect(src).toMatch(/setLoadError\s*\(/);
    // The .then(...).catch chain rooted at the plan loader must end in a
    // non-empty handler. We assert by spanning from the plan-loader call
    // to the end of file and checking the empty silent form is absent.
    const getIdx = src.indexOf("api.get<PlanData>(`/fhir/PlanDefinition/${planId}`)");
    expect(getIdx).toBeGreaterThan(-1);
    const window = src.slice(getIdx, Math.min(src.length, getIdx + 8000));
    expect(window).toMatch(/setLoadError\s*\(/);
    expect(window).not.toMatch(/\.catch\(\(\)\s*=>\s*\{\}\s*\)/);
  });

  it("VT-157-TC-012: PathwayLoadError is rendered when loadError is set", () => {
    const src = readPage();
    expect(src).toContain("<PathwayLoadError");
    expect(src).toMatch(/loadError/);
    expect(src).toMatch(/setLoadAttempt/);
  });
});
