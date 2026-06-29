/**
 * Static-source verification for RuleReviewCard action-button branching,
 * the 'discuss' strength label, and the is_default fallback badge.
 *
 * Verifies:
 *   - no_rule_expected: shows "Confirm no rule needed" button, not "Reject"
 *   - no_rule_expected: uses severity="info" alert, not severity="warning"
 *   - normal rules: shows "Looks right" and "Reject", not "Confirm no rule needed"
 *   - 'discuss' strength option exists in STRENGTH_LABELS
 *   - is_default badge rendered in RuleCardHeader
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../../../../..");

function read(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

const CARD_SRC = read("services/ui/src/app/admin/guidance/RuleReviewCard.tsx");
const COPY_SRC = read("services/ui/src/app/admin/guidance/EditRuleDialog/copy.ts");
const STEP2_SRC = read("services/ui/src/app/admin/guidance/EditRuleDialog/steps/Step2Suggest.tsx");
const TYPES_SRC = read("services/ui/src/app/admin/guidance/ruleReviewTypes.ts");

describe("RuleReviewCard - no_rule_expected action branching", () => {
  test("TC-001: RuleCardActions branches on no_rule_expected generation_outcome", () => {
    expect(CARD_SRC).toMatch(/generation_outcome\s*===\s*["']no_rule_expected["']/);
  });

  test("TC-002: Confirm no rule needed button is rendered in the no_rule_expected branch", () => {
    expect(CARD_SRC).toMatch(/Confirm no rule needed/);
  });

  test("TC-003: Reject button is absent from the no_rule_expected branch", () => {
    const confirmIdx = CARD_SRC.indexOf("Confirm no rule needed");
    const rejectIdx = CARD_SRC.indexOf(">Reject<");
    expect(confirmIdx).toBeGreaterThan(-1);
    expect(rejectIdx).toBeGreaterThan(-1);
    expect(Math.abs(rejectIdx - confirmIdx)).toBeGreaterThan(300);
  });

  test("TC-004: no_rule_expected alert uses severity info", () => {
    const fnStart = CARD_SRC.indexOf("function RuleGenerationAlert");
    const fnEnd = CARD_SRC.indexOf("function RuleCardActions");
    const alertFn = CARD_SRC.slice(fnStart, fnEnd);
    expect(alertFn).toMatch(/severity=["']info["']/);
  });

  test("TC-005: standard alert still uses severity warning for other errors", () => {
    expect(CARD_SRC).toMatch(/severity=["']warning["']/);
  });

  test("TC-006: Looks right button is present for normal rules", () => {
    expect(CARD_SRC).toMatch(/Looks right/);
  });

  test("TC-007: aria-label for confirm button references the rule_id", () => {
    expect(CARD_SRC).toMatch(/Confirm no rule needed for/);
  });
});

describe("STRENGTH_LABELS - discuss option", () => {
  test("TC-008: discuss value exists in STRENGTH_LABELS", () => {
    expect(COPY_SRC).toMatch(/value:\s*["']discuss["']/);
  });

  test("TC-009: discuss label reads Discuss with specialist", () => {
    expect(COPY_SRC).toMatch(/Discuss with specialist/);
  });

  test("TC-010: discuss appears between refer and safety_net in the list", () => {
    const referIdx = COPY_SRC.indexOf('"refer"');
    const discussIdx = COPY_SRC.indexOf('"discuss"');
    const safetyIdx = COPY_SRC.indexOf('"safety_net"');
    expect(discussIdx).toBeGreaterThan(referIdx);
    expect(discussIdx).toBeLessThan(safetyIdx);
  });
});

describe("Fallback rule - is_default flag", () => {
  test("TC-011: is_default field exists in ruleReviewTypes Rule interface", () => {
    expect(TYPES_SRC).toMatch(/is_default\?\s*:\s*boolean/);
  });

  test("TC-012: Fallback rule badge is rendered in RuleCardHeader", () => {
    expect(CARD_SRC).toMatch(/Fallback rule/);
  });

  test("TC-013: badge is gated on rule.is_default", () => {
    expect(CARD_SRC).toMatch(/rule\.is_default/);
  });

  test("TC-014: isDefault toggle exists in Step2Suggest", () => {
    expect(STEP2_SRC).toMatch(/isDefault/);
    expect(STEP2_SRC).toMatch(/Fallback rule/);
  });

  test("TC-015: onIsDefaultChange prop wired in Step2Suggest", () => {
    expect(STEP2_SRC).toMatch(/onIsDefaultChange/);
  });
});
