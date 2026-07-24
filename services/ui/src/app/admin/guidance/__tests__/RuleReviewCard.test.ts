/**
 * Static-source verification for RuleReviewCard action-button branching,
 * the 'discuss' strength label, and the is_default fallback badge.
 *
 * Verifies:
 *   - no_rule_expected: shows "Confirm no rule needed" wired to onReject
 *     (exclude list), not onApprove
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

  test("TC-003: Confirm no rule needed uses onReject (exclude), not onApprove", () => {
    const fnStart = CARD_SRC.indexOf("function RuleCardActions");
    const fnEnd = CARD_SRC.indexOf("function RuleCardBody", fnStart);
    const actionsFn = CARD_SRC.slice(fnStart, fnEnd);
    // First branch ends before the standard "Looks right" return.
    const branchEnd = actionsFn.indexOf("return (", actionsFn.indexOf("Confirm no rule needed"));
    const noRuleBranch = actionsFn.slice(0, branchEnd);
    expect(noRuleBranch).toMatch(/Confirm no rule needed/);
    expect(noRuleBranch).toMatch(/callbacks\.onReject/);
    expect(noRuleBranch).not.toMatch(/callbacks\.onApprove/);
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

describe("RuleReviewCard - priority chip on header", () => {
  test("TC-014: header renders a Priority chip from action_priority", () => {
    expect(CARD_SRC).toMatch(/priorityChipLabel/);
    expect(CARD_SRC).toMatch(/rule\.action_priority/);
    expect(CARD_SRC).toMatch(/action_due_days/);
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

describe("RuleReviewCard - stale AI-generation warnings hidden once reviewed", () => {
  test("TC-016: generation_outcome chip is gated on rule.status === pending_review", () => {
    const headerStart = CARD_SRC.indexOf("function RuleCardHeader");
    const headerEnd = CARD_SRC.indexOf("function RuleGenerationAlert");
    const headerFn = CARD_SRC.slice(headerStart, headerEnd);
    expect(headerFn).toMatch(
      /rule\.status\s*===\s*["']pending_review["']\s*&&\s*rule\.generation_outcome\s*&&\s*rule\.generation_outcome\s*!==\s*["']success["']/,
    );
  });

  test("TC-017: needs_human_review chip is gated on rule.status === pending_review", () => {
    const headerStart = CARD_SRC.indexOf("function RuleCardHeader");
    const headerEnd = CARD_SRC.indexOf("function RuleGenerationAlert");
    const headerFn = CARD_SRC.slice(headerStart, headerEnd);
    expect(headerFn).toMatch(
      /rule\.status\s*===\s*["']pending_review["']\s*&&\s*rule\.needs_human_review\s*&&\s*!rule\.generation_outcome/,
    );
  });

  test("TC-018: RuleGenerationAlert returns null before rendering the banner when rule is no longer pending_review", () => {
    const fnStart = CARD_SRC.indexOf("function RuleGenerationAlert");
    const fnEnd = CARD_SRC.indexOf("function RuleCardActions");
    const alertFn = CARD_SRC.slice(fnStart, fnEnd);
    const guardIdx = alertFn.search(
      /if\s*\(\s*rule\.status\s*!==\s*["']pending_review["']\s*\)\s*return\s*null;/,
    );
    const existingGuardIdx = alertFn.indexOf("if (!rule.generation_errors?.length) return null;");
    expect(guardIdx).toBeGreaterThan(-1);
    expect(existingGuardIdx).toBeGreaterThan(-1);
    expect(guardIdx).toBeLessThan(existingGuardIdx);
  });
});
