/**
 * Case card search/summary/tag helpers for Validation Lab rolodex.
 *
 * Atlas: DI-EB716E68
 */

import {
  caseSearchHaystack,
  caseSummary,
  caseTags,
  collectTagUniverse,
  naturalCompare,
  sortCasesNaturally,
} from "../app/admin/validation-lab/caseCardMeta";
import type { LabCase } from "../app/admin/validation-lab/labApi";

function makeCase(overrides: Partial<LabCase> = {}): LabCase {
  return {
    id: "c1",
    title: "Raised CA125 Core20",
    summary: "Woman aged 55 with CA125 90 and Core20 decile 2.",
    tags: ["CA125", "Core20"],
    referral_preview: "Dear colleague, please see...",
    ...overrides,
  };
}

describe("validation-lab case card meta", () => {
  test("summary prefers summary then referral preview", () => {
    expect(caseSummary(makeCase())).toMatch(/Woman aged 55/);
    expect(
      caseSummary(makeCase({ summary: "", referral_preview: "Preview only" })),
    ).toBe("Preview only");
  });

  test("search haystack includes summary and tags", () => {
    const hay = caseSearchHaystack(makeCase());
    expect(hay).toContain("ca125");
    expect(hay).toContain("core20");
    expect(hay).toContain("woman aged 55");
  });

  test("tag universe is sorted unique", () => {
    const tags = collectTagUniverse([
      makeCase({ tags: ["CA125", "2WW"] }),
      makeCase({ id: "c2", tags: ["2WW", "Core20"] }),
    ]);
    expect(tags).toEqual(["2WW", "CA125", "Core20"]);
    expect(caseTags(makeCase({ tags: ["", "CA125"] }))).toEqual(["CA125"]);
  });

  test("naturalCompare puts Variant 2 before Variant 11", () => {
    const titles = ["Variant 11", "Variant 2", "Variant 1", "Variant 22"];
    expect([...titles].sort(naturalCompare)).toEqual([
      "Variant 1",
      "Variant 2",
      "Variant 11",
      "Variant 22",
    ]);
  });

  test("sortCasesNaturally orders by title numerically", () => {
    const sorted = sortCasesNaturally([
      makeCase({ id: "c11", title: "Variant 11" }),
      makeCase({ id: "c2", title: "Variant 2" }),
      makeCase({ id: "c1", title: "Variant 1" }),
    ]);
    expect(sorted.map((c) => c.title)).toEqual([
      "Variant 1",
      "Variant 2",
      "Variant 11",
    ]);
  });
});
