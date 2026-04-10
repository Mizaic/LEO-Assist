/**
 * VT-LEO-AI-092 TC-001: pathwayLabels maps all episode status values to plain English.
 */

import {
  EPISODE_STATUS_LABELS,
  getStatusLabel,
  getCancerTypeLabel,
  getDiagnosticIntervalColour,
} from "@/lib/pathwayLabels";

const EXPECTED_STATUS_PAIRS: Array<[string, string]> = [
  ["completed", "Confirmed cancer"],
  ["closed_benign", "No cancer found"],
  ["stale_no_diagnosis", "No diagnosis after wait"],
  ["stale_post_specialist", "Specialist seen, no diagnosis"],
  ["closed_related", "Duplicate pathway closed"],
  ["in_progress", "Still being investigated"],
];

describe("EPISODE_STATUS_LABELS", () => {
  test("all 6 expected statuses have a non-empty label", () => {
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

describe("getCancerTypeLabel", () => {
  test("returns plain English for known cancer types", () => {
    expect(getCancerTypeLabel("colorectal")).toBe("Bowel (colorectal)");
    expect(getCancerTypeLabel("lung")).toBe("Lung");
    expect(getCancerTypeLabel("non_site_specific")).toBe("Type not yet confirmed");
  });

  test("returns the raw value for unknown types (graceful fallback)", () => {
    expect(getCancerTypeLabel("some_new_type")).toBe("some_new_type");
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
