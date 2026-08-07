/**
 * Unit options for observation threshold dropdowns.
 * Atlas: DI-C21AE387 / DO-AA74E9A6 / VT-5632FA0D
 */
import {
  FALLBACK_OBSERVABLE_UNITS,
  preferredUnit,
  unitOptionsForObservable,
  unitsFromLabConfig,
} from "../observableUnits";

describe("unitsFromLabConfig", () => {
  it("returns canonical unit plus conversion aliases", () => {
    expect(
      unitsFromLabConfig({
        canonical_unit: "ug/L",
        conversions: [{ unit: "ng/mL" }, { unit: "mcg/L" }, { unit: "ug/L" }],
      }),
    ).toEqual(["ug/L", "ng/mL", "mcg/L"]);
  });

  it("returns empty when config is missing", () => {
    expect(unitsFromLabConfig(null)).toEqual([]);
  });
});

describe("unitOptionsForObservable", () => {
  it("prefers lab config units over the fallback list", () => {
    expect(
      unitOptionsForObservable({
        canonical_unit: "ug/L",
        conversions: [{ unit: "ng/mL" }],
      }),
    ).toEqual(["ug/L", "ng/mL"]);
  });

  it("falls back to the seeded converter units", () => {
    const options = unitOptionsForObservable(null);
    expect(options).toContain("ug/L");
    expect(options).toContain("10*9/L");
    expect(options.length).toBe(FALLBACK_OBSERVABLE_UNITS.length);
  });

  it("keeps a current free-text unit in the list so Select stays valid", () => {
    expect(
      unitOptionsForObservable(
        { canonical_unit: "ug/L", conversions: [] },
        "micrograms",
      ),
    ).toEqual(["micrograms", "ug/L"]);
  });
});

describe("preferredUnit", () => {
  it("returns the canonical unit", () => {
    expect(preferredUnit({ canonical_unit: "g/L", conversions: [] })).toBe(
      "g/L",
    );
  });
});
