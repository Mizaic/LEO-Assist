/**
 * Static-source verification for the LoadedGuidelinesPanel + RuleReviewPool
 * + RuleReviewSection motion pass (skeleton swap, filter-chip pop,
 * "approved in this session" spring entrance). Cosmetic-only change --
 * see atlas-vt-enforcement.mdc Step 0.
 */

import * as fs from "fs";
import * as path from "path";

const GUIDANCE_DIR = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance",
);

function read(file: string): string {
  return fs.readFileSync(path.join(GUIDANCE_DIR, file), "utf8");
}

describe("LoadedGuidelinesPanel.tsx motion pass", () => {
  const src = read("LoadedGuidelinesPanel.tsx");

  test("uses SkeletonList instead of a spinner for the loading state", () => {
    expect(src).toMatch(/from\s*["']@leo\/design-system["']/);
    expect(src).toMatch(/SkeletonList/);
    expect(src).toMatch(/if \(loading\) \{\s*\n\s*return <SkeletonList/);
  });

  test("status filter chips pop when selected", () => {
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/STATUS_FILTERS\.map/);
    expect(src).toMatch(/bounceInteraction\(reducedMotion\)/);
  });

  test("still renders the guideline empty states", () => {
    expect(src).toMatch(/data-testid="guidelines-empty"/);
    expect(src).toMatch(/data-testid="guidelines-no-match"/);
  });
});

describe("RuleReviewPool.tsx motion pass", () => {
  const src = read("RuleReviewPool.tsx");

  test("uses SkeletonList instead of a spinner for the loading state", () => {
    expect(src).toMatch(/SkeletonList/);
    expect(src).not.toMatch(/CircularProgress/);
  });

  test("preserves the pending/approved/superseded pool test ids", () => {
    expect(src).toMatch(/data-testid=\{`rule-pool-\$\{poolId\}`\}/);
  });
});

describe("RuleReviewSection.tsx motion pass", () => {
  const src = read("RuleReviewSection.tsx");

  test("imports framer-motion and the shared popVariants preset", () => {
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/popVariants\(reducedMotion\)/);
  });

  test("approved-in-session boxes animate in via AnimatePresence", () => {
    expect(src).toMatch(/sessionApproved\.map/);
    expect(src).toMatch(/AnimatePresence initial=\{false\}/);
  });

  test("approved-in-session boxes show a springy checkmark pop", () => {
    expect(src).toMatch(/CheckCircleRoundedIcon/);
    expect(src).toMatch(/type:\s*"spring"/);
  });

  test("preserves the edit-approved-rule workflow", () => {
    expect(src).toMatch(/Edit approved rule/);
  });
});
