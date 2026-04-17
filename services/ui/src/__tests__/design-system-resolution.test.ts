/**
 * VT-LEO-AI-126: @leo/design-system package resolves from services/ui.
 * Covers TC-001 (tokens barrel) and TC-002 (role navMap barrel).
 */

import { tokens, roleNavMap } from "@leo/design-system";

describe("VT-126 - @leo/design-system resolution", () => {
  test("TC-001 tokens barrel", () => {
    expect(tokens.spacing.md).toBe(16);
    expect(tokens.radius.md).toBe(12);
    expect(tokens.motion.default.duration).toBe(180);
    expect(tokens.color.text.primary).toBe("#0F172A");
    expect(tokens.typography.fontFamily.body).toContain("DM Sans");
    expect(tokens.density.touchTargetMin).toBe(44);
  });

  test("TC-002 roleNavMap barrel", () => {
    const keys = Object.keys(roleNavMap).sort();
    expect(keys).toEqual([
      "clinician",
      "platform_admin",
      "qa_ra_lead",
      "staff",
    ]);
    for (const role of keys) {
      const config = (roleNavMap as Record<string, unknown>)[role] as {
        landing: string;
        primary: unknown[];
        advanced: unknown[];
      };
      expect(typeof config.landing).toBe("string");
      expect(Array.isArray(config.primary)).toBe(true);
      expect(Array.isArray(config.advanced)).toBe(true);
      expect(config.primary.length).toBeGreaterThan(0);
    }
  });
});
