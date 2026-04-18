/**
 * VT-LEO-AI-183 -- CandidatePruneDialog static-source verification.
 *
 * Pins the destructive-action gating and ToolbarAction registration
 * for the auto-prune flow (DI-LEO-AI-197 / DO-LEO-AI-196). This is a
 * static-source VT per ui-testing.mdc: it asserts on the source
 * string of the affected files rather than rendering the component
 * (the dialog hits the network on mount via fetch).
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function readUI(relative: string): string {
  return fs.readFileSync(path.join(ROOT, "services/ui/src", relative), "utf-8");
}

const PANEL_SRC = readUI("components/gold-dataset/GoldDatasetPanel.tsx");
const DIALOG_SRC = readUI("components/gold-dataset/CandidatePruneDialog.tsx");

describe("VT-183 -- CandidatePruneDialog wiring + safety gates", () => {
  // -- VT-183-TC-001 -------------------------------------------------------
  it("TC-001: GoldDatasetPanel registers id='auto-prune' on the candidates tab", () => {
    expect(PANEL_SRC).toContain("CandidatePruneDialog");
    expect(PANEL_SRC).toContain("setPruneDialogOpen");
    // The auto-prune action lives next to the deduplicate action in the
    // ToolbarActions builder for the candidates tab. Slice from the
    // toolbar entry point and verify both labels live in the same block.
    const toolbarIdx = PANEL_SRC.indexOf("<ToolbarActions");
    expect(toolbarIdx).toBeGreaterThan(-1);
    const toolbarBlock = PANEL_SRC.slice(toolbarIdx, toolbarIdx + 2500);
    expect(toolbarBlock).toContain("auto-prune");
    expect(toolbarBlock).toContain("Auto-prune low confidence");
    expect(toolbarBlock).toContain("setPruneDialogOpen(true)");
    expect(toolbarBlock).toContain("Deduplicate similar");
  });

  // -- VT-183-TC-002 -------------------------------------------------------
  it("TC-002: default confidence floors are 0.7 / 0.92 / 0.66", () => {
    expect(DIALOG_SRC).toMatch(/setMinSurfaceMatch\][^=]*=\s*useState<number>\(0\.7\)/);
    expect(DIALOG_SRC).toMatch(
      /setSemanticVectorFloor\][^=]*=\s*useState<number>\(0\.92\)/,
    );
    expect(DIALOG_SRC).toMatch(
      /setSemanticMinSurface\][^=]*=\s*useState<number>\(0\.66\)/,
    );
  });

  // -- VT-183-TC-003 -------------------------------------------------------
  it("TC-003: destructive Delete button disabled until preview-loaded AND confirm-acknowledged AND deleteCount > 0", () => {
    // Find the destructive Button block (variant="contained" color="error")
    const variantContainedIdx = DIALOG_SRC.indexOf('variant="contained"');
    expect(variantContainedIdx).toBeGreaterThan(-1);
    const destructiveBlock = DIALOG_SRC.slice(
      variantContainedIdx,
      variantContainedIdx + 600,
    );
    expect(destructiveBlock).toContain("color=\"error\"");
    expect(destructiveBlock).toContain("previewLoaded");
    expect(destructiveBlock).toContain("deleteCount === 0");
    expect(destructiveBlock).toContain("!confirmAcknowledged");
  });

  // -- VT-183-TC-004 -------------------------------------------------------
  it("TC-004: confirmation checkbox label includes 'permanently delete'", () => {
    expect(DIALOG_SRC).toContain("permanently delete");
    // Must live inside a FormControlLabel paired with a Checkbox bound to
    // confirmAcknowledged.
    expect(DIALOG_SRC).toMatch(
      /FormControlLabel[\s\S]{0,400}checked=\{confirmAcknowledged\}/,
    );
  });

  // -- VT-183-TC-005 -------------------------------------------------------
  it("TC-005: handleClose is a no-op while loading is true", () => {
    expect(DIALOG_SRC).toMatch(/function handleClose\(\)\s*\{[\s\S]*?if \(loading\) return;/);
  });

  // -- VT-183-TC-006 -------------------------------------------------------
  it("TC-006: CandidatePruneDialog.tsx is <= 500 LOC (code-quality.mdc hard limit)", () => {
    const lineCount = DIALOG_SRC.split("\n").length;
    expect(lineCount).toBeLessThanOrEqual(500);
  });
});
