/**
 * VT-LEO-AI-092 TC-001: pathwayLabels maps all episode status values to plain English.
 */

import {
  CANCER_TYPE_OPTIONS,
  EPISODE_STATUS_LABELS,
  getStatusLabel,
  getCancerTypeLabel,
  getDiagnosticIntervalColour,
  getStatusColour,
} from "@/lib/pathwayLabels";

const EXPECTED_STATUS_PAIRS: Array<[string, string]> = [
  ["active", "Still active"],
  ["review", "Needs review"],
  ["completed", "Confirmed cancer"],
  ["closed_benign", "No cancer found"],
  ["stale_no_diagnosis", "No diagnosis after wait"],
  ["stale_post_specialist", "Specialist seen, no diagnosis"],
  ["closed_related", "Duplicate pathway closed"],
  ["in_progress", "Still being investigated"],
];

describe("EPISODE_STATUS_LABELS", () => {
  test("all expected statuses have a non-empty label", () => {
    const expectedStatuses = EXPECTED_STATUS_PAIRS.map(([s]) => s);
    for (const status of expectedStatuses) {
      const label = EPISODE_STATUS_LABELS[status];
      expect(label).toBeTruthy();
      expect(typeof label).toBe("string");
    }
  });

  test("no returned label contains underscore characters", () => {
    for (const label of Object.values(EPISODE_STATUS_LABELS)) {
      expect(label).not.toMatch(/_/);
    }
  });

  test.each(EXPECTED_STATUS_PAIRS)(
    "getStatusLabel('%s') returns '%s'",
    (status, expected) => {
      expect(getStatusLabel(status)).toBe(expected);
    }
  );
});

describe("getStatusColour", () => {
  test("maps episode outcomes to benign active and cancer colours", () => {
    expect(getStatusColour("closed_benign")).toBe("success");
    expect(getStatusColour("stale_no_diagnosis")).toBe("success");
    expect(getStatusColour("active")).toBe("warning");
    expect(getStatusColour("review")).toBe("warning");
    expect(getStatusColour("completed")).toBe("error");
  });
});

describe("getCancerTypeLabel", () => {
  test("normalises legacy site keys to NCDA labels", () => {
    expect(getCancerTypeLabel("colorectal")).toBe("Colorectal");
    expect(getCancerTypeLabel("lung")).toBe("Lung");
    expect(getCancerTypeLabel("non_site_specific")).toBe("Other");
  });

  test("falls back to Other for unknown types", () => {
    expect(getCancerTypeLabel("some_new_type")).toBe("Other");
  });

  test("filter options match NCDA values", () => {
    expect(CANCER_TYPE_OPTIONS[0]).toEqual({ value: "Bladder", label: "Bladder" });
    expect(CANCER_TYPE_OPTIONS.at(-1)).toEqual({
      value: "No Information",
      label: "No Information",
    });
  });
});

describe("getDiagnosticIntervalColour", () => {
  test("returns success for <= 28 days", () => {
    expect(getDiagnosticIntervalColour(0)).toBe("success");
    expect(getDiagnosticIntervalColour(28)).toBe("success");
  });

  test("returns warning for > 28 and <= 62 days", () => {
    expect(getDiagnosticIntervalColour(29)).toBe("warning");
    expect(getDiagnosticIntervalColour(62)).toBe("warning");
  });

  test("returns error for > 62 days", () => {
    expect(getDiagnosticIntervalColour(63)).toBe("error");
    expect(getDiagnosticIntervalColour(200)).toBe("error");
  });

  test("returns success for null (no data, no alarm)", () => {
    expect(getDiagnosticIntervalColour(null)).toBe("success");
    expect(getDiagnosticIntervalColour(undefined)).toBe("success");
  });
});
