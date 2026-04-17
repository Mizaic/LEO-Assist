/**
 * VT-LEO-AI-135 TC-001..TC-003 - centralised role-aware area intro copy.
 *
 * Pins: shape completeness, role coverage for areas where a role is a
 * primary user, and Flesch-Kincaid <= 9 for every default block.
 */

import { fleschKincaidGrade } from "@leo/design-system";

import { AREA_INTRO_COPY, type AreaKey } from "@/lib/areaCopy";

const EXPECTED_AREAS: AreaKey[] = [
  "care-overview",
  "operations",
  "pathway-explorer",
  "platform",
  "users",
  "portal",
  "support",
  "settings",
  "work",
];

describe("AREA_INTRO_COPY (VT-LEO-AI-135)", () => {
  test("TC-001 covers every required area", () => {
    const keys = Object.keys(AREA_INTRO_COPY).sort();
    expect(keys).toEqual([...EXPECTED_AREAS].sort());
  });

  test("TC-001 every default block has title, lede, how, what", () => {
    for (const key of EXPECTED_AREAS) {
      const block = AREA_INTRO_COPY[key].default;
      expect(block.title.length).toBeGreaterThan(0);
      expect(block.lede.length).toBeGreaterThan(0);
      expect(block.how).toBeDefined();
      expect(block.what).toBeDefined();
    }
  });

  test("TC-002 clinical areas include a clinician block", () => {
    for (const key of ["care-overview", "pathway-explorer", "portal"] as AreaKey[]) {
      expect(AREA_INTRO_COPY[key].clinician).toBeDefined();
    }
  });

  test("TC-002 admin areas include a platform_admin or staff block", () => {
    for (const key of ["operations", "platform", "users", "portal"] as AreaKey[]) {
      const entry = AREA_INTRO_COPY[key];
      expect(
        entry.platform_admin !== undefined || entry.staff !== undefined,
      ).toBe(true);
    }
  });

  test("TC-003 every default block grades <=9 on Flesch-Kincaid", () => {
    for (const key of EXPECTED_AREAS) {
      const block = AREA_INTRO_COPY[key].default;
      const text = [block.title, block.lede, block.how, block.what]
        .filter(Boolean)
        .join(" ");
      const { grade } = fleschKincaidGrade(text);
      expect(grade).toBeLessThanOrEqual(9);
    }
  });
});
