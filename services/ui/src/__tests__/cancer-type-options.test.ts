/**
 * VT-LEO-AI-530: Canonical NCDA cancer-type vocabulary (TS surface).
 *
 * Pins the TS mirror at services/ui/src/lib/cancerTypes.ts so:
 *   - the chart axes always render canonical labels in NCDA order,
 *   - normaliseCancerType is idempotent and case-insensitive,
 *   - the legacy raw spellings still observed on the live graph
 *     (skin / haematology / upper gi / etc.) collapse onto the
 *     correct canonical bucket on read.
 *
 * The Python <-> TS parity is enforced separately by
 * tests/contracts/test_cancer_type_vocabulary.py.
 */
import {
  CANCER_TYPE_NO_INFORMATION,
  CANCER_TYPE_OPTIONS,
  CANCER_TYPE_OTHER,
  CANCER_TYPE_SET,
  cancerTypeOrderIndex,
  getCancerTypeLabel,
  isCanonicalCancerType,
  normaliseCancerType,
} from "../lib/cancerTypes";

describe("VT-530-TC-001 canonical list shape", () => {
  it("contains 30 unique canonical entries (27 NCDA + 3 sentinels)", () => {
    expect(CANCER_TYPE_OPTIONS).toHaveLength(30);
    expect(new Set(CANCER_TYPE_OPTIONS).size).toBe(30);
    expect(CANCER_TYPE_SET.has("Other")).toBe(true);
    expect(CANCER_TYPE_SET.has("Unknown Primary")).toBe(true);
    expect(CANCER_TYPE_SET.has("No Information")).toBe(true);
  });

  it("starts with Bladder and ends with No Information (NCDA order)", () => {
    expect(CANCER_TYPE_OPTIONS[0]).toBe("Bladder");
    expect(CANCER_TYPE_OPTIONS[CANCER_TYPE_OPTIONS.length - 1]).toBe(
      CANCER_TYPE_NO_INFORMATION,
    );
  });
});

describe("VT-530-TC-002 normaliseCancerType remap", () => {
  it.each([
    ["breast", "Breast"],
    ["BREAST", "Breast"],
    ["Breast", "Breast"],
    ["skin", "Melanoma"],
    ["head and neck", "Oropharyngeal"],
    ["head & neck", "Oropharyngeal"],
    ["urinary bladder / prostate", "Prostate"],
    ["anal", "Colorectal"],
    ["upper gi", "Other"],
    ["upper gastrointestinal", "Other"],
    ["urological", "Other"],
    ["gynaecological", "Other"],
    ["gynaecological (cervix)", "Cervical"],
    ["haematology", "Lymphoma"],
    ["lymphoid", "Lymphoma"],
    ["lung", "Lung"],
    ["unknown", "Unknown Primary"],
    ["unknown primary", "Unknown Primary"],
  ])("normalises %p -> %p", (raw, expected) => {
    expect(normaliseCancerType(raw)).toBe(expected);
  });

  it("returns 'No Information' for null, undefined, empty, whitespace", () => {
    expect(normaliseCancerType(null)).toBe(CANCER_TYPE_NO_INFORMATION);
    expect(normaliseCancerType(undefined)).toBe(
      CANCER_TYPE_NO_INFORMATION,
    );
    expect(normaliseCancerType("")).toBe(CANCER_TYPE_NO_INFORMATION);
    expect(normaliseCancerType("   ")).toBe(CANCER_TYPE_NO_INFORMATION);
  });

  it("falls back to 'Other' for unrecognised values", () => {
    expect(normaliseCancerType("zzz_made_up_site")).toBe(
      CANCER_TYPE_OTHER,
    );
  });

  it("is idempotent on every canonical value", () => {
    for (const canonical of CANCER_TYPE_OPTIONS) {
      expect(normaliseCancerType(canonical)).toBe(canonical);
    }
  });
});

describe("VT-530-TC-003 helpers", () => {
  it("isCanonicalCancerType is true for canonical values only", () => {
    expect(isCanonicalCancerType("Breast")).toBe(true);
    expect(isCanonicalCancerType("Melanoma")).toBe(true);
    expect(isCanonicalCancerType("breast")).toBe(false);
    expect(isCanonicalCancerType("skin")).toBe(false);
    expect(isCanonicalCancerType(null)).toBe(false);
    expect(isCanonicalCancerType(undefined)).toBe(false);
    expect(isCanonicalCancerType(42)).toBe(false);
  });

  it("getCancerTypeLabel passes through canonical values and routes everything else to 'Other'", () => {
    expect(getCancerTypeLabel("Breast")).toBe("Breast");
    expect(getCancerTypeLabel("Other")).toBe("Other");
    expect(getCancerTypeLabel("not-a-cancer")).toBe("Other");
    expect(getCancerTypeLabel("breast")).toBe("Other");
  });

  it("cancerTypeOrderIndex sorts the chart axes in NCDA order", () => {
    const shuffled = ["Lung", "Bladder", "Breast", "No Information"];
    const sorted = [...shuffled].sort(
      (a, b) => cancerTypeOrderIndex(a) - cancerTypeOrderIndex(b),
    );
    expect(sorted).toEqual(["Bladder", "Breast", "Lung", "No Information"]);
  });

  it("cancerTypeOrderIndex sends unknown values to the end of the chart", () => {
    expect(cancerTypeOrderIndex("not-a-cancer")).toBe(
      CANCER_TYPE_OPTIONS.length,
    );
    expect(cancerTypeOrderIndex("Bladder")).toBe(0);
  });
});
