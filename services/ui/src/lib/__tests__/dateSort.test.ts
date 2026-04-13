import {
  compareIsoDateTimeAsc,
  compareIsoDateTimeDesc,
  sortByIsoDateAsc,
  sortByIsoDateDesc,
} from "@/lib/dateSort";

describe("dateSort", () => {
  it("sorts ascending chronologically", () => {
    const rows = [{ t: "2024-01-02" }, { t: "2024-01-01" }, { t: "2024-01-03" }];
    expect(sortByIsoDateAsc(rows, (r) => r.t).map((r) => r.t)).toEqual([
      "2024-01-01",
      "2024-01-02",
      "2024-01-03",
    ]);
  });

  it("sorts descending with newest first", () => {
    const rows = [{ t: "2024-01-02" }, { t: "2024-01-01" }];
    expect(sortByIsoDateDesc(rows, (r) => r.t).map((r) => r.t)).toEqual(["2024-01-02", "2024-01-01"]);
  });

  it("places missing dates last in ascending order", () => {
    expect(compareIsoDateTimeAsc("2024-01-01", null)).toBeLessThan(0);
    expect(compareIsoDateTimeAsc(null, "2024-01-01")).toBeGreaterThan(0);
  });

  it("places missing dates last in descending order", () => {
    expect(compareIsoDateTimeDesc("2024-01-01", null)).toBeLessThan(0);
    expect(compareIsoDateTimeDesc(null, "2024-01-01")).toBeGreaterThan(0);
  });
});
