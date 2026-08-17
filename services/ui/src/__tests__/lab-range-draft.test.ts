/**
 * Reference-range confirm copy.
 *
 * Design Controls: DI-3F771AFB.
 */
import {
  ageCopy,
  bandCopy,
  filterRangeOrgs,
  orgSearchLabel,
  ownerCopy,
  PLATFORM_OWNER,
  rangeConfirmRows,
  sexLabel,
} from "../app/admin/lab-results/rangeDraft";

describe("lab range draft copy", () => {
  it("describes age bands in plain English", () => {
    expect(ageCopy("", "")).toBe("Any age");
    expect(ageCopy("18", "")).toBe("18 years and over");
    expect(ageCopy("", "16")).toBe("Up to 16 years");
    expect(ageCopy("18", "65")).toBe("18 to 65 years");
  });

  it("describes normal and critical bands", () => {
    expect(bandCopy("", "", "Not set")).toBe("Not set");
    expect(bandCopy("0", "21", "Not set")).toBe("0 to 21");
    expect(bandCopy("", "100", "Not set")).toBe("none to 100");
  });

  it("builds the confirm rows for a draft range", () => {
    const rows = rangeConfirmRows({
      orgId: "",
      sex: "female",
      ageMin: "18",
      ageMax: "",
      low: "0",
      high: "21",
      critLow: "",
      critHigh: "100",
      source: "manual",
    });
    expect(sexLabel("female")).toBe("Female");
    expect(ownerCopy("")).toBe("Platform default");
    expect(ownerCopy("org-1", "Oak GP")).toBe("Oak GP");
    expect(rows).toEqual([
      { label: "Owner", value: "Platform default" },
      { label: "Sex", value: "Female" },
      { label: "Age", value: "18 years and over" },
      { label: "Normal", value: "0 to 21" },
      { label: "Critical", value: "none to 100" },
      { label: "Source", value: "manual" },
    ]);
  });

  it("hides organisation names until the author types two letters", () => {
    const orgs = [
      PLATFORM_OWNER,
      { id: "org-1", name: "Oak GP", type: "gp", odsCode: "A12345" },
      { id: "org-2", name: "Pine ICB", type: "icb", odsCode: "B99999" },
    ];
    expect(filterRangeOrgs(orgs, { inputValue: "" })).toEqual([PLATFORM_OWNER]);
    expect(filterRangeOrgs(orgs, { inputValue: "o" })).toEqual([PLATFORM_OWNER]);
    expect(filterRangeOrgs(orgs, { inputValue: "oa" }).map((row) => row.id)).toEqual([
      "",
      "org-1",
    ]);
    expect(orgSearchLabel(orgs[1])).toBe("Oak GP · gp · A12345");
  });
});
