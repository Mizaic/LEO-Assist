/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Static-source a11y guard rails for the Simple sentence canvas
 * (SentenceEditor/), mirroring Phase7A11yStatic.test.ts's pattern for
 * the Advanced tree canvas -- encodes a11y intent at unit-test time so
 * a regression cannot land between e2e refreshes.
 */

import fs from "fs";
import path from "path";

const EDIT_RULE_DIALOG = path.resolve(__dirname, "..");

function read(name: string): string {
  return fs.readFileSync(path.join(EDIT_RULE_DIALOG, name), "utf-8");
}

describe("SentenceEditor -- static a11y guard rails", () => {
  it("SentenceEditor/index.tsx root has role=group (not tree) and aria-label", () => {
    // role="group", not "tree": the canvas is a labelled container of
    // ordinary interactive controls, not an ARIA tree widget with
    // treeitem children. "tree" trips axe's aria-required-children
    // check as soon as real content is a direct child (verified live in
    // e2e/sentence-editor-guided-journey.spec.ts).
    const src = read("SentenceEditor/index.tsx");
    expect(src).toContain('role="group"');
    expect(src).not.toContain('role="tree"');
    expect(src).toContain("aria-label");
  });

  it("PathwaySentenceCard exposes data-testid for each pathway letter, matching PathwayCard", () => {
    const src = read("SentenceEditor/PathwaySentenceCard.tsx");
    expect(src).toMatch(/data-testid=.*pathway-card/);
  });

  it("GroupSentence's kind selector and min-count field carry aria-labels", () => {
    const src = read("SentenceEditor/GroupSentence.tsx");
    expect(src).toMatch(/aria-label.*How to match conditions in this group/);
    expect(src).toMatch(/aria-label.*How many conditions must match/);
  });

  it("GroupSentence's collapse chevron has a distinct aria-label per state", () => {
    const src = read("SentenceEditor/GroupSentence.tsx");
    expect(src).toMatch(/aria-label=\{collapsed \? "Expand group" : "Collapse group"\}/);
  });

  it("AddInlineLinks buttons each have an aria-label", () => {
    const src = read("SentenceEditor/AddInlineLinks.tsx");
    const matches = src.match(/aria-label/g) ?? [];
    expect(matches.length).toBeGreaterThanOrEqual(2);
  });

  it("AddInlineLinks renders semantic <button> elements, not bare clickable <span>/<div>", () => {
    const src = read("SentenceEditor/AddInlineLinks.tsx");
    expect(src).toMatch(/component="button"/);
    expect(src).toMatch(/type="button"/);
  });

  it("EmptySentenceState has role=status and an aria-label describing the empty rule", () => {
    const src = read("SentenceEditor/EmptySentenceState.tsx");
    expect(src).toContain('role="status"');
    expect(src).toContain("aria-label");
  });

  it("PathwaySentenceList's 'Add pathway' button has an aria-label", () => {
    const src = read("SentenceEditor/PathwaySentenceList.tsx");
    expect(src).toMatch(/aria-label="Add another pathway"/);
  });

  it("SentenceEditor/index.tsx's prerequisite lead-in reuses the same aria-label as LogicTreeEditor's, so switching views keeps the same landmark name", () => {
    const sentenceSrc = read("SentenceEditor/index.tsx");
    const treeSrc = read("LogicTreeEditor/index.tsx");
    const label = "Applies to every pathway below";
    expect(sentenceSrc).toContain(label);
    expect(treeSrc).toContain(label);
  });

});

