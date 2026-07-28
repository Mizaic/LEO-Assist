/**
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import { detectDemographicPhrase } from "../demographicPhraseMatch";

describe("detectDemographicPhrase: age", () => {
  it("parses 'aged 40 and over' as >= 40 years", () => {
    expect(detectDemographicPhrase("aged 40 and over")).toEqual({
      field: "age",
      operator: ">=",
      value: "40",
      unit: "years",
    });
  });

  it("parses 'aged 55 or over'", () => {
    expect(detectDemographicPhrase("aged 55 or over")).toEqual({
      field: "age",
      operator: ">=",
      value: "55",
      unit: "years",
    });
  });

  it("parses '60 years or older'", () => {
    expect(detectDemographicPhrase("60 years or older")).toEqual({
      field: "age",
      operator: ">=",
      value: "60",
      unit: "years",
    });
  });

  it("parses 'aged over 18' as > 18 years", () => {
    expect(detectDemographicPhrase("aged over 18")).toEqual({
      field: "age",
      operator: ">",
      value: "18",
      unit: "years",
    });
  });

  it("parses 'aged under 16' as < 16 years", () => {
    expect(detectDemographicPhrase("aged under 16")).toEqual({
      field: "age",
      operator: "<",
      value: "16",
      unit: "years",
    });
  });

  it("parses 'aged 16 to 24' as a between range", () => {
    expect(detectDemographicPhrase("aged 16 to 24")).toEqual({
      field: "age",
      operator: "between",
      value: "16",
      value2: "24",
      unit: "years",
    });
  });

  it("parses a bare 'aged 40' as an exact match", () => {
    expect(detectDemographicPhrase("aged 40")).toEqual({
      field: "age",
      operator: "=",
      value: "40",
      unit: "years",
    });
  });

  it("parses NICE 'children and young people' as age <= 24 (NG12 glossary)", () => {
    expect(detectDemographicPhrase("children and young people")).toEqual({
      field: "age",
      operator: "<=",
      value: "24",
      unit: "years",
    });
  });

  it("parses NICE 'young people' as age 16 to 24", () => {
    expect(detectDemographicPhrase("young people")).toEqual({
      field: "age",
      operator: "between",
      value: "16",
      value2: "24",
      unit: "years",
    });
  });

  it("parses NICE 'children' as age <= 15", () => {
    expect(detectDemographicPhrase("children")).toEqual({
      field: "age",
      operator: "<=",
      value: "15",
      unit: "years",
    });
  });

  it("parses NICE 'adults' as age >= 18", () => {
    expect(detectDemographicPhrase("adults")).toEqual({
      field: "age",
      operator: ">=",
      value: "18",
      unit: "years",
    });
  });
});

describe("detectDemographicPhrase: sex", () => {
  it("parses 'women' as sex = female", () => {
    expect(detectDemographicPhrase("women")).toEqual({
      field: "sex",
      operator: "=",
      value: "female",
      unit: null,
    });
  });

  it("parses 'men' as sex = male", () => {
    expect(detectDemographicPhrase("men")).toEqual({
      field: "sex",
      operator: "=",
      value: "male",
      unit: null,
    });
  });
});

describe("detectDemographicPhrase: conservative guard rails", () => {
  it("returns null for an ordinary finding with no age/sex wording", () => {
    expect(detectDemographicPhrase("cough and unexplained weight loss")).toBeNull();
  });

  it("returns null when a number is present but not an age phrase", () => {
    expect(detectDemographicPhrase("2 or more of the following symptoms")).toBeNull();
  });

  it("does not fire on a longer selection that merely contains an age phrase alongside another finding", () => {
    expect(
      detectDemographicPhrase(
        "unexplained symptoms in people aged 40 and over with a persistent cough",
      ),
    ).toBeNull();
  });

  it("does not treat a longer CYP-containing selection as an age band alone", () => {
    expect(
      detectDemographicPhrase(
        "Refer children and young people for immediate specialist assessment",
      ),
    ).toBeNull();
  });

  it("returns null for an empty selection", () => {
    expect(detectDemographicPhrase("   ")).toBeNull();
  });
});
