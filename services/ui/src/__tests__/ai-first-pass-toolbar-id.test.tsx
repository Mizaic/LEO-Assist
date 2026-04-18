/**
 * VT-LEO-AI-201 TC-001 -- AI first-pass toolbar id registration.
 *
 * Static-source verification per ui-testing.mdc: asserts that
 * GoldDatasetPanel registers a ToolbarAction with id="ai-first-pass"
 * on the candidates tab and wires its onClick to the dialog opener,
 * so reviewers always have a one-click entry into the AI first-pass
 * flow (DI-LEO-AI-209 / R-LEO-AI-197).
 *
 * Static-source rather than live render because the panel triggers
 * network requests on mount.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function readUI(relative: string): string {
  return fs.readFileSync(path.join(ROOT, "services/ui/src", relative), "utf-8");
}

const PANEL_SRC = readUI("components/gold-dataset/GoldDatasetPanel.tsx");

describe("VT-201 TC-001 -- AI first-pass toolbar id", () => {
  it("registers id='ai-first-pass' under <ToolbarActions> with the dialog opener", () => {
    const toolbarIdx = PANEL_SRC.indexOf("<ToolbarActions");
    expect(toolbarIdx).toBeGreaterThan(-1);

    const toolbarBlock = PANEL_SRC.slice(toolbarIdx, toolbarIdx + 4000);
    expect(toolbarBlock).toContain('id: "ai-first-pass"');
    expect(toolbarBlock).toContain('label: "AI first-pass"');
    expect(toolbarBlock).toContain("setAiFirstPassDialogOpen(true)");
  });

  it("imports AIFirstPassDialog and mounts it with the dialog state", () => {
    expect(PANEL_SRC).toContain('from "@/components/gold-dataset/AIFirstPassDialog"');
    expect(PANEL_SRC).toMatch(
      /<AIFirstPassDialog[\s\S]{0,400}open=\{aiFirstPassDialogOpen\}/,
    );
    expect(PANEL_SRC).toMatch(
      /<AIFirstPassDialog[\s\S]{0,800}onClose=\{[^}]*setAiFirstPassDialogOpen\(false\)/,
    );
  });
});
