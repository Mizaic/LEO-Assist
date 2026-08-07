/**
 * Unit tests for age x lab band tree builder (PSA / CA125 tables).
 * Atlas: DI-E5B04297 / DO-C38E6184 / VT-409A9A74
 */
import {
  bandSummaryText,
  buildAgeLabBandTree,
  validateAgeLabBandSpec,
  type AgeLabBandSpec,
} from "../HighlightWizard/ageLabBands";

const PSA_SPEC: AgeLabBandSpec = {
  observableId: "102097009",
  observableTerm: "Serum PSA",
  unit: "ug/L",
  operator: ">",
  bands: [
    { ageFrom: "40", ageTo: "49", value: "2" },
    { ageFrom: "50", ageTo: "59", value: "3.5" },
    { ageFrom: "60", ageTo: "69", value: "4.5" },
    { ageFrom: "70", ageTo: "", value: "5" },
  ],
};

describe("validateAgeLabBandSpec", () => {
  it("accepts a complete PSA-style band table", () => {
    expect(validateAgeLabBandSpec(PSA_SPEC)).toBeNull();
  });

  it("rejects a missing observable", () => {
    expect(
      validateAgeLabBandSpec({ ...PSA_SPEC, observableId: "" }),
    ).toMatch(/lab reading/i);
  });

  it("rejects an empty unit", () => {
    expect(validateAgeLabBandSpec({ ...PSA_SPEC, unit: "  " })).toMatch(
      /unit/i,
    );
  });

  it("rejects a band with no lab value", () => {
    expect(
      validateAgeLabBandSpec({
        ...PSA_SPEC,
        bands: [{ ageFrom: "40", ageTo: "49", value: "" }],
      }),
    ).toMatch(/lab value/i);
  });

  it("rejects age to below age from", () => {
    expect(
      validateAgeLabBandSpec({
        ...PSA_SPEC,
        bands: [{ ageFrom: "50", ageTo: "40", value: "3" }],
      }),
    ).toMatch(/age to/i);
  });
});

describe("bandSummaryText", () => {
  it("describes a closed age range with a greater-than threshold", () => {
    expect(
      bandSummaryText(
        { ageFrom: "40", ageTo: "49", value: "2" },
        "Serum PSA",
        ">",
        "ug/L",
      ),
    ).toBe("is between 40 and 49 years, Serum PSA more than 2 ug/L");
  });

  it("describes an open-ended age band", () => {
    expect(
      bandSummaryText(
        { ageFrom: "70", ageTo: "", value: "5" },
        "Serum PSA",
        ">",
        "ug/L",
      ),
    ).toBe("is 70 years or older, Serum PSA more than 5 ug/L");
  });
});

describe("buildAgeLabBandTree", () => {
  it("builds OR of AND(age, observation) pathways", () => {
    const tree = buildAgeLabBandTree(PSA_SPEC);
    expect(tree.kind).toBe("OR");
    expect(tree.children).toHaveLength(4);

    const first = tree.children![0]!;
    expect(first.kind).toBe("AND");
    expect(first.pathway_key).toBeTruthy();
    expect(first.children).toHaveLength(2);
    expect(first.children![0]).toMatchObject({
      kind: "DEMOGRAPHIC",
      field: "age",
      operator: "between",
      value: "40",
      value2: "49",
    });
    expect(first.children![1]).toMatchObject({
      kind: "OBSERVATION",
      observation: {
        observable_id: "102097009",
        operator: ">",
        value: 2,
        unit: "ug/L",
      },
    });

    const openEnded = tree.children![3]!;
    expect(openEnded.children![0]).toMatchObject({
      kind: "DEMOGRAPHIC",
      field: "age",
      operator: ">=",
      value: "70",
    });
    expect(openEnded.children![1]?.observation?.value).toBe(5);
  });

  it("throws when the spec is invalid", () => {
    expect(() =>
      buildAgeLabBandTree({ ...PSA_SPEC, bands: [] }),
    ).toThrow(/age band/i);
  });
});
