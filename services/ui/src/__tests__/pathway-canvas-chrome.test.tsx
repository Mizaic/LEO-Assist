// VT-LEO-AI-154 - Pathway editor chrome (Phase 6b-ii)
// Static-source verification that the pathway editor's top-level chrome has
// been decomposed into sibling modules, that the orchestrator no longer
// in-lines the toolbar / publish / delete / edge-confirm dialogs, and that
// the new files expose the canonical prop-based API.

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

function read(rel: string): string {
  return fs.readFileSync(path.join(EDITOR, rel), "utf-8");
}

describe("VT-LEO-AI-154 - Pathway editor chrome decomposition", () => {
  it("VT-154-TC-001: editor scaffold files exist", () => {
    expect(fs.existsSync(path.join(EDITOR, "PathwayToolbar.tsx"))).toBe(true);
    expect(fs.existsSync(path.join(EDITOR, "PathwaySaveBar.tsx"))).toBe(true);
    expect(fs.existsSync(path.join(EDITOR, "utils.ts"))).toBe(true);
    expect(
      fs.existsSync(path.join(EDITOR, "dialogs/EdgeDeleteConfirm.tsx")),
    ).toBe(true);
    expect(fs.existsSync(path.join(EDITOR, "dialogs/PublishDialog.tsx"))).toBe(
      true,
    );
    expect(
      fs.existsSync(path.join(EDITOR, "dialogs/DeletePathwayDialog.tsx")),
    ).toBe(true);
  });

  it("VT-154-TC-002: page.tsx imports the new chrome modules", () => {
    const src = fs.readFileSync(PAGE, "utf-8");
    expect(src).toMatch(
      /from\s+["']\.\/editor\/PathwayToolbar["']/,
    );
    expect(src).toMatch(
      /from\s+["']\.\/editor\/dialogs\/PublishDialog["']/,
    );
    expect(src).toMatch(
      /from\s+["']\.\/editor\/dialogs\/DeletePathwayDialog["']/,
    );
    expect(src).toMatch(
      /from\s+["']\.\/editor\/dialogs\/EdgeDeleteConfirm["']/,
    );
    expect(src).toMatch(/from\s+["']\.\/editor\/TriggerContextPanel["']/);
    expect(src).toMatch(/from\s+["']\.\/editor\/WorkflowModeBar["']/);
    expect(src).toMatch(/from\s+["']\.\/editor\/ValidationPanel["']/);
  });

  it("VT-154-TC-003: page.tsx renders the new components, not inline JSX", () => {
    const src = fs.readFileSync(PAGE, "utf-8");
    expect(src).toMatch(/<PathwayToolbar[\s\S]*?\/>/);
    expect(src).toMatch(/<PublishDialog[\s\S]*?\/>/);
    expect(src).toMatch(/<DeletePathwayDialog[\s\S]*?\/>/);
    expect(src).toMatch(/<EdgeDeleteConfirm[\s\S]*?\/>/);
  });

  it("VT-154-TC-004: legacy inline toolbar markup has been removed", () => {
    const src = fs.readFileSync(PAGE, "utf-8");
    expect(src).not.toMatch(/Add a data source\.\.\./);
    expect(src).not.toMatch(/Add a data source\u2026/);
    expect(src).not.toMatch(/Add an output\.\.\./);
    expect(src).not.toMatch(/Add a step\.\.\./);
    expect(src).not.toMatch(/onClick=\{handlePublish\}/);
  });

  it("VT-154-TC-005: PathwayToolbar is prop-driven (no inline state)", () => {
    const src = read("PathwayToolbar.tsx");
    expect(src).not.toMatch(/\buseState\b/);
    expect(src).not.toMatch(/\buseEffect\b/);
    expect(src).toMatch(/export\s+function\s+PathwayToolbar/);
    expect(src).toMatch(/export\s+interface\s+PathwayToolbarProps/);
  });

  it("VT-154-TC-006: PathwayToolbar exposes the canonical handler set", () => {
    const src = read("PathwayToolbar.tsx");
    [
      "onSaveDraft",
      "onPublish",
      "onRetire",
      "onAddSourceNode",
      "onAddOutputNode",
      "onAddViewerNode",
      "onAddAction",
      "onAutoLayout",
      "onClearTestTrace",
      "onOpenTestRun",
      "onRunAllSteps",
      "onOpenBatchPanel",
      "onOpenHistory",
      "onOpenDelete",
      "onBack",
      "onClearSaveError",
    ].forEach((handler) => {
      expect(src).toMatch(new RegExp(`\\b${handler}\\b`));
    });
  });

  it("VT-154-TC-007: PathwayToolbar applies aria-labels to icon-only controls", () => {
    const src = read("PathwayToolbar.tsx");
    expect(src).toMatch(/aria-label="Back to pathway list"/);
    expect(src).toMatch(/aria-label="Auto-layout pathway"/);
    expect(src).toMatch(/aria-label="Open version history"/);
    expect(src).toMatch(/"aria-label":\s*"Pathway name"/);
  });

  it("VT-154-TC-008: PublishDialog is prop-driven", () => {
    const src = read("dialogs/PublishDialog.tsx");
    expect(src).toMatch(/export\s+function\s+PublishDialog/);
    expect(src).toMatch(/export\s+interface\s+PublishDialogProps/);
    expect(src).not.toMatch(/\buseState\b/);
    expect(src).toMatch(/aria-label="Publish to live"/);
  });

  it("VT-154-TC-009: DeletePathwayDialog uses type-the-name confirm gate", () => {
    const src = read("dialogs/DeletePathwayDialog.tsx");
    expect(src).toMatch(/confirmText\.trim\(\)\s*===\s*pathwayName/);
    expect(src).toMatch(/Type the pathway name exactly/);
    expect(src).toMatch(/aria-label="Delete pathway permanently"/);
    expect(src).not.toMatch(/\buseState\b/);
  });

  it("VT-154-TC-010: EdgeDeleteConfirm is a small, single-purpose dialog", () => {
    const src = read("dialogs/EdgeDeleteConfirm.tsx");
    expect(src).toMatch(/Remove connection\?/);
    expect(src).toMatch(/Keep connected/);
    expect(src).toMatch(/export\s+function\s+EdgeDeleteConfirm/);
  });

  it("VT-154-TC-011: PathwaySaveBar exposes the dirty/saving/saved/error states", () => {
    const src = read("PathwaySaveBar.tsx");
    expect(src).toMatch(/SaveBarState/);
    expect(src).toMatch(/"idle"/);
    expect(src).toMatch(/"dirty"/);
    expect(src).toMatch(/"saving"/);
    expect(src).toMatch(/"saved"/);
    expect(src).toMatch(/"error"/);
    expect(src).toMatch(/role="status"/);
    expect(src).toMatch(/aria-live="polite"/);
  });

  it("VT-154-TC-012: utils centralises lifecycle helpers", () => {
    const src = read("utils.ts");
    expect(src).toMatch(/export\s+function\s+formatSaveTime/);
    expect(src).toMatch(/export\s+type\s+PlanLifecycleStatus/);
    expect(src).toMatch(/lifecycleColor/);
    expect(src).toMatch(/lifecycleLabel/);
  });

  it("VT-154-TC-013: extracted modules respect file-size discipline", () => {
    const sizes: Record<string, number> = {};
    [
      "PathwayToolbar.tsx",
      "PathwaySaveBar.tsx",
      "utils.ts",
      "dialogs/EdgeDeleteConfirm.tsx",
      "dialogs/PublishDialog.tsx",
      "dialogs/DeletePathwayDialog.tsx",
    ].forEach((rel) => {
      sizes[rel] = read(rel).split("\n").length;
    });
    expect(sizes["utils.ts"]).toBeLessThan(60);
    expect(sizes["dialogs/EdgeDeleteConfirm.tsx"]).toBeLessThan(100);
    expect(sizes["dialogs/PublishDialog.tsx"]).toBeLessThan(220);
    expect(sizes["dialogs/DeletePathwayDialog.tsx"]).toBeLessThan(220);
    expect(sizes["PathwaySaveBar.tsx"]).toBeLessThan(220);
    expect(sizes["PathwayToolbar.tsx"]).toBeLessThan(500);
  });
});
