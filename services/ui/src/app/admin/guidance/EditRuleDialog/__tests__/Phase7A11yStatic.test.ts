/**
 * Phase 7d -- a11y static-source guard rails for the rule-edit wizard.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *
 * Static-source checks that encode a11y intent at unit-test time so a
 * regression cannot land between e2e refreshes.
 */

import fs from "fs";
import path from "path";

const WIZARD = path.resolve(__dirname, "..");

function read(name: string): string {
  return fs.readFileSync(path.join(WIZARD, name), "utf-8");
}

describe("Phase 7d -- wizard a11y static guard rails", () => {
  it("every Popover in ChipSearchPopover carries an aria-label", () => {
    const src = read("ChipSearchPopover.tsx");
    expect(src).toMatch(/aria-label["']?\s*:\s*heading/);
  });

  it("LogicTreeEditor root has role=tree and aria-label", () => {
    const src = read("LogicTreeEditor/index.tsx");
    expect(src).toContain('role="tree"');
    expect(src).toContain("aria-label");
  });

  it("PathwayCard exposes data-testid for each pathway letter", () => {
    const src = read("LogicTreeEditor/PathwayCard.tsx");
    expect(src).toMatch(/data-testid=.*pathway-card/);
  });

  it("ConceptPill carries aria-label on the chip", () => {
    const src = read("LogicTreeEditor/ConceptPill.tsx");
    expect(src).toMatch(/aria-label/);
  });

  it("AddBar buttons each have aria-label", () => {
    const src = read("LogicTreeEditor/AddBar.tsx");
    const matches = src.match(/aria-label/g) ?? [];
    expect(matches.length).toBeGreaterThanOrEqual(2);
  });

  it("ConfirmKindChangeDialog has an aria-label", () => {
    const src = read("ConfirmDialogs.tsx");
    expect(src).toMatch(/CONFIRM_KIND_CHANGE\.ariaLabel/);
  });

  it("ConfirmObservationFlipDialog has an aria-label", () => {
    const src = read("ConfirmDialogs.tsx");
    expect(src).toMatch(/CONFIRM_OBSERVATION_FLIP\.ariaLabel/);
  });

  it("ConceptSearchPanel hits centralised aria strings", () => {
    const src = read("ConceptSearchPanel.tsx");
    expect(src).toMatch(/SEARCH_PANEL\.searchAriaLabel/);
    expect(src).toMatch(/SEARCH_PANEL\.resultsAriaLabel/);
    expect(src).toMatch(/SEARCH_PANEL\.searchingAriaLabel/);
  });

  it("Step1Who renders the duplicate-set alert with the centralised aria-label", () => {
    const src = read("steps/Step1Who.tsx");
    expect(src).toMatch(/DUPLICATE_SETS_ALERT\.ariaLabel/);
  });

  it("DialogTitle copy is centralised in copy.ts (no inline duplicate)", () => {
    const indexSrc = read("index.tsx");
    expect(indexSrc).toMatch(/DIALOG_CHROME\.title/);
    const inlineHits = indexSrc.match(/"Change this rule"/g) ?? [];
    expect(inlineHits.length).toBe(0);
  });
});
