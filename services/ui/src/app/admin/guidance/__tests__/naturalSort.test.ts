import { naturalSortCompare } from "../naturalSort";

describe("naturalSortCompare", () => {
  it("orders dotted NICE section numbers numerically, not lexicographically", () => {
    const ids = ["1.2.1", "1.11.1", "1.2.10", "1.2.2"];
    expect([...ids].sort(naturalSortCompare)).toEqual(["1.2.1", "1.2.2", "1.2.10", "1.11.1"]);
  });

  it("puts 1.2.1 before 1.11.1", () => {
    expect(naturalSortCompare("1.2.1", "1.11.1")).toBeLessThan(0);
    expect(naturalSortCompare("1.11.1", "1.2.1")).toBeGreaterThan(0);
  });

  it("puts 1.9 before 1.10 (numeric segment, not string, comparison)", () => {
    expect(naturalSortCompare("1.9", "1.10")).toBeLessThan(0);
  });

  it("treats equal ids as equal", () => {
    expect(naturalSortCompare("1.2.1", "1.2.1")).toBe(0);
  });

  it("falls back to plain string comparison for non-numeric ids", () => {
    expect(naturalSortCompare("a", "b")).toBeLessThan(0);
    expect(naturalSortCompare("b", "a")).toBeGreaterThan(0);
  });

  it("handles mixed numeric/non-numeric ids without throwing", () => {
    expect(() => naturalSortCompare("1.2.1", "not-a-number")).not.toThrow();
  });
});
