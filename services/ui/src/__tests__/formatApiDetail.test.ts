/**
 * VT -- readable API error messages (no "[object Object]").
 *
 * Regression for Platform Management and other admin surfaces that use
 * apiFetch when FastAPI returns Pydantic validation detail arrays.
 */

import { formatApiDetail } from "@/lib/api/formatApiDetail";

describe("formatApiDetail", () => {
  it("renders an array of validation errors as a readable, joined string", () => {
    const detail = [
      {
        type: "extra_forbidden",
        loc: ["body", "group_ids", 0],
        msg: "Extra inputs are not permitted",
      },
      {
        type: "string_type",
        loc: ["body", "name"],
        msg: "Input should be a valid string",
      },
    ];

    const out = formatApiDetail(detail);

    expect(out).not.toMatch(/\[object Object\]/);
    expect(out).toMatch(/group_ids/);
    expect(out).toMatch(/name/);
    expect(out).toMatch(/Extra inputs are not permitted/);
    expect(out).not.toMatch(/^body\./);
  });

  it("passes a plain-string detail through unchanged", () => {
    expect(formatApiDetail("Platform admin access required")).toBe(
      "Platform admin access required",
    );
  });

  it("never returns the literal string '[object Object]' for unexpected shapes", () => {
    const out = formatApiDetail({ unexpected: { nested: "shape" } });
    expect(out).not.toMatch(/\[object Object\]/);
    expect(out.length).toBeGreaterThan(0);
  });

  it("returns an empty string for null / undefined so callers fall back", () => {
    expect(formatApiDetail(null)).toBe("");
    expect(formatApiDetail(undefined)).toBe("");
  });
});
