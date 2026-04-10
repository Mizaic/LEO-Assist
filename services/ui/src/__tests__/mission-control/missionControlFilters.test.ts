/**
 * VT-LEO-AI-092 TC-002: missionControlFilters round-trips all filter fields via URL params.
 */

import {
  serialiseFilters,
  deserialiseFilters,
  toApiParams,
  DEFAULT_FILTERS,
  type MissionControlFilters,
} from "@/lib/missionControlFilters";

const FULL_FILTERS: MissionControlFilters = {
  dateFrom: "2024-04-06",
  dateTo: "2025-04-05",
  orgId: "org-123",
  patientId: "4181221113",
  pathwayFilter: "closures",
  cancerTypes: ["colorectal", "lung"],
  closureReasons: ["closed_benign", "stale_no_diagnosis"],
  reviewStatus: "unreviewed",
  sortBy: "diagnostic_interval",
  sortDir: "ASC",
  page: 2,
  pageSize: 50,
};

describe("serialiseFilters / deserialiseFilters round-trip", () => {
  test("round-trips the complete filter object without data loss", () => {
    const params = serialiseFilters(FULL_FILTERS);
    const restored = deserialiseFilters(params);
    expect(restored).toEqual(FULL_FILTERS);
  });

  test("round-trips default filters (all empty/default values)", () => {
    const params = serialiseFilters(DEFAULT_FILTERS);
    const restored = deserialiseFilters(params);
    expect(restored).toEqual(DEFAULT_FILTERS);
  });

  test("array fields (cancerTypes, closureReasons) serialise and deserialise correctly", () => {
    const filters: MissionControlFilters = {
      ...DEFAULT_FILTERS,
      cancerTypes: ["breast", "prostate", "lung"],
      closureReasons: ["closed_benign"],
    };
    const params = serialiseFilters(filters);
    const restored = deserialiseFilters(params);
    expect(restored.cancerTypes).toEqual(["breast", "prostate", "lung"]);
    expect(restored.closureReasons).toEqual(["closed_benign"]);
  });

  test("pathwayFilter defaults to 'all' for unknown values", () => {
    const params = new URLSearchParams("pathway_filter=invalid_value");
    const restored = deserialiseFilters(params);
    expect(restored.pathwayFilter).toBe("all");
  });

  test("reviewStatus defaults to 'all' for unknown values", () => {
    const params = new URLSearchParams("review_status=unknown");
    const restored = deserialiseFilters(params);
    expect(restored.reviewStatus).toBe("all");
  });

  test("page and pageSize default to 1 and 25 when absent", () => {
    const params = new URLSearchParams();
    const restored = deserialiseFilters(params);
    expect(restored.page).toBe(1);
    expect(restored.pageSize).toBe(25);
  });
});

describe("toApiParams", () => {
  test("includes pathway_filter and review_status in all cases", () => {
    const params = toApiParams(DEFAULT_FILTERS);
    expect(params.get("pathway_filter")).toBe("all");
    expect(params.get("review_status")).toBe("all");
    expect(params.get("sort_by")).toBe("referral_date");
    expect(params.get("sort_dir")).toBe("DESC");
  });

  test("includes cancer_types when non-empty", () => {
    const params = toApiParams({ ...DEFAULT_FILTERS, cancerTypes: ["lung", "breast"] });
    expect(params.get("cancer_types")).toBe("lung,breast");
  });

  test("omits cancer_types when empty", () => {
    const params = toApiParams(DEFAULT_FILTERS);
    expect(params.get("cancer_types")).toBeNull();
  });

  test("includes patient_id when non-empty", () => {
    const params = toApiParams({ ...DEFAULT_FILTERS, patientId: "  4181221113  " });
    expect(params.get("patient_id")).toBe("4181221113");
  });

  test("omits patient_id when blank", () => {
    const params = toApiParams({ ...DEFAULT_FILTERS, patientId: "   " });
    expect(params.get("patient_id")).toBeNull();
  });
});
