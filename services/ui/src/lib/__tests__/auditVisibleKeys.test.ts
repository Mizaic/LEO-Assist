import { buildAuditBarVisibleKeys } from "../auditVisibleKeys";

describe("buildAuditBarVisibleKeys", () => {
  it("returns practice and national only when no org", () => {
    expect(buildAuditBarVisibleKeys(false, false, false)).toEqual(["practice", "national"]);
    expect(buildAuditBarVisibleKeys(false, true, true)).toEqual(["practice", "national"]);
  });

  it("defaults org view to practice and benchmark national slot only", () => {
    expect(buildAuditBarVisibleKeys(true, false, false)).toEqual(["practice", "national"]);
  });

  it("adds optional comparators when toggled", () => {
    expect(buildAuditBarVisibleKeys(true, true, false)).toEqual(["practice", "national", "similar"]);
    expect(buildAuditBarVisibleKeys(true, false, true)).toEqual(["practice", "national", "alliance"]);
    expect(buildAuditBarVisibleKeys(true, true, true)).toEqual([
      "practice",
      "national",
      "similar",
      "alliance",
    ]);
  });
});
