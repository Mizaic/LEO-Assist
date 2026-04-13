import { compareStringsNatural } from "@/lib/sortNatural";

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
