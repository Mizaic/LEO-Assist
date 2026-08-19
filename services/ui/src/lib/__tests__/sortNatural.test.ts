import { compareStringsNatural, orgSortLabel } from "@/lib/sortNatural";

describe("compareStringsNatural", () => {
  it("orders embedded numbers by numeric value", () => {
    const labels = ["Last 30 days", "Last 7 days", "Last 90 days"];
    const sorted = [...labels].sort(compareStringsNatural);
    expect(sorted).toEqual(["Last 7 days", "Last 30 days", "Last 90 days"]);
  });

  it("falls back to locale order for non-numeric segments", () => {
    expect(compareStringsNatural("apple", "Banana")).toBeLessThan(0);
  });
});

describe("orgSortLabel", () => {
  it("prefers shortName over name", () => {
    expect(orgSortLabel({ shortName: "WMC", name: "Woodbrook" })).toBe("WMC");
  });

  it("returns empty string when shortName and name are null", () => {
    expect(orgSortLabel({ shortName: null, name: null })).toBe("");
  });

  it("sorts organisations that have a null name without throwing", () => {
    const orgs = [
      { id: "b", shortName: null, name: null },
      { id: "a", shortName: null, name: "Alpha Practice" },
    ];
    expect(() =>
      [...orgs].sort((left, right) =>
        compareStringsNatural(orgSortLabel(left), orgSortLabel(right)),
      ),
    ).not.toThrow();
  });
});
