/**
 * Phase 7d -- a11y static-source guard rails for the rule-edit wizard.
 *
 * Atlas trace:
 *   UN: UN-26E57FA1
 *   DI: DI-061AD3D1
 *   DO: DO-1EE0BFAE
 *   VT: VT-EEF2D497
 *
 * The full axe-core/playwright sweep over the wizard runs in
 * ``services/ui/e2e/a11y-baseline.spec.ts`` once the test backend can
 * spawn an editor with a sample rule. These static-source checks
 * encode the same intent at unit-test time so a regression cannot
 * land between two e2e refreshes:
 *
 *   - Every Popover that the wizard opens carries an explicit
 *     ``aria-label`` so screen readers announce it on focus.
 *   - The sentence canvas exposes a ``role="region"`` with an
 *     ``aria-label`` so it shows up as a landmark.
 *   - Pathway cards expose a region with a name (positional letter
 *     plus optional pathway name).
 *   - Observation rows expose a row-level ``aria-label`` summarising
 *     the leaf in plain English.
 *   - Both confirm dialogs expose a top-level ``aria-label``.
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

  it("SentenceCanvas exposes the canvas as a labelled region", () => {
    const src = read("SentenceCanvas.tsx");
    expect(src).toMatch(/role="region"\s+aria-label="Sentence canvas"/);
  });

  it("Pathway cards expose a labelled region (positional + optional name)", () => {
    const src = read("SentenceCanvas.tsx");
    expect(src).toMatch(/role="region"\s+aria-label=\{cardAriaLabel\}/);
    expect(src).toContain("cardAriaLabel");
  });

  it("Observation rows expose a row-level aria-label", () => {
    const src = read("SentenceRow.tsx");
    expect(src).toMatch(/observationAriaLabel/);
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
    // The literal "Change this rule" must not appear inline anywhere
    // else under the editor; the guard prevents two reviewers updating
    // the same string in different places.
    const inlineHits = indexSrc.match(/"Change this rule"/g) ?? [];
    expect(inlineHits.length).toBe(0);
  });
});
