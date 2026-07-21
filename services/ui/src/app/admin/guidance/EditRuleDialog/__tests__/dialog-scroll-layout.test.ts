/**
 * Static-source guard rails for the EditRuleDialog's scrollable layout.
 *
 * Reviewers reported "I can't scroll through the rules": long pathways
 * (many symptom chips, several pathways) overflowed the Dialog without
 * ever triggering an internal scrollbar. Root cause was that the Dialog
 * `Paper` only declared a `minHeight: "80vh"` floor -- with no real
 * ceiling, Paper simply grew to fit its full content (well past the
 * viewport), so the descendant `flex: 1, minHeight: 0` chain had nothing
 * definite to shrink against and never actually bounded the canvas /
 * preview columns. The page scrolled as a whole instead of the dialog
 * scrolling internally.
 *
 * These checks encode the fix at unit-test time (no real browser
 * layout engine is available in jsdom, so this locks in the CSS
 * properties rather than the resulting pixels):
 *   - The (non-fullscreen) Dialog Paper has an explicit `height` (not
 *     just a `minHeight` floor) so it is a bounded box the rest of the
 *     flex chain can shrink against.
 *   - DialogContent and every intermediate flex layer down to the
 *     canvas / preview columns declare an explicit `minHeight: 0`
 *     (never a bare percentage height) so they can shrink to fit the
 *     Dialog's bounded height instead of growing with their content.
 *   - The canvas (60%) and preview (40%) columns each own their
 *     `overflowY: "auto"` on desktop so they scroll independently.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */

import fs from "fs";
import path from "path";

const SRC = fs.readFileSync(
  path.join(__dirname, "../index.tsx"),
  "utf-8",
);

describe("EditRuleDialog -- scrollable layout guard rails", () => {
  it("does not rely on a percentage minHeight to size the scroll region (the nested-flexbox trap)", () => {
    expect(SRC).not.toMatch(/minHeight:\s*["']100%["']/);
  });

  it("the non-fullscreen Dialog Paper has an explicit height, not just a minHeight floor, so the flex chain has a real box to shrink against", () => {
    const start = SRC.indexOf("PaperProps={{");
    expect(start).toBeGreaterThan(-1);
    const paperPropsBlock = SRC.slice(start, start + 900);
    expect(paperPropsBlock).toMatch(/height:\s*["']80vh["']/);
  });

  it("DialogContent is an explicit flex column with minHeight: 0 so it can shrink within the Paper", () => {
    const dialogContentBlock = SRC.match(
      /<DialogContent[\s\S]*?>/,
    )?.[0];
    expect(dialogContentBlock).toBeTruthy();
    expect(dialogContentBlock).toMatch(/display:\s*["']flex["']/);
    expect(dialogContentBlock).toMatch(/minHeight:\s*0/);
  });

  it("the step-canvas row and both columns declare minHeight: 0 to stay within the bounded dialog height", () => {
    const minHeightZeroCount = (SRC.match(/minHeight:\s*0\b/g) ?? []).length;
    // DialogContent, the stepper+row wrapper, the row itself, and the
    // 60% canvas column all need this -- four distinct occurrences.
    expect(minHeightZeroCount).toBeGreaterThanOrEqual(4);
  });

  it("the 60% canvas column and 40% preview column each scroll independently on desktop", () => {
    const overflowYMatches = SRC.match(/overflowY:\s*\{[^}]*md:\s*["']auto["'][^}]*\}/g) ?? [];
    expect(overflowYMatches.length).toBeGreaterThanOrEqual(2);
  });

  it("the Dialog Paper clips overflow so a broken inner flex chain fails loudly instead of silently overflowing the screen", () => {
    const start = SRC.indexOf("PaperProps={{");
    expect(start).toBeGreaterThan(-1);
    const paperPropsBlock = SRC.slice(start, start + 400);
    expect(paperPropsBlock).toMatch(/overflow:\s*["']hidden["']/);
  });
});
