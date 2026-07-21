/**
 * VT-C6B93AF0 -- createCasesFromVariants helper.
 *
 * Atlas: DI-EB716E68 / DO-A0ADDB38
 */

import {
  createCasesFromVariants,
  normaliseVariantFromApi,
  variantToCreatePayload,
  type ScenarioVariant,
} from "../app/admin/validation-lab/scenarioVariants";

function makeVariant(overrides: Partial<ScenarioVariant> = {}): ScenarioVariant {
  return {
    variantId: "v1",
    label: "Age 68 female",
    rationale: "fires age branch",
    recommended: true,
    isControl: false,
    title: "Haematuria age branch",
    patientName: "Pat Example",
    patientAge: "68",
    patientSex: "female",
    referralText: "Dear colleague...",
    pmh: [{ category: "condition", conceptId: "123", term: "Haematuria" }],
    observations: [{ observableId: "100", value: 50, unit: "U/mL" }],
    equity: {
      ethnicityConceptId: "976631000000101",
      ethnicityTerm: "White British",
      performanceStatusGrade: 1,
      comorbidityBand: "low",
      core20Decile: 2,
      plusGroup: "none",
    },
    ...overrides,
  };
}

describe("createCasesFromVariants", () => {
  test("maps equity and observations into createCase payload", () => {
    const payload = variantToCreatePayload(
      makeVariant({
        summary: "Age 68 female with visible haematuria.",
        tags: ["haematuria", "2WW", "age-68"],
      }),
    );
    expect(payload.title).toBe("Haematuria age branch");
    expect(payload.summary).toBe("Age 68 female with visible haematuria.");
    expect(payload.tags).toEqual(["haematuria", "2WW", "age-68"]);
    expect(payload.patient_age).toBe(68);
    expect(payload.gp_practice_name).toBe("Validation Lab GP Practice");
    expect(payload.ethnicity_concept_id).toBe("976631000000101");
    expect(payload.observations?.[0]).toEqual({
      observable_id: "100",
      value: 50,
      unit: "U/mL",
      term: "",
    });
    expect(payload.pmh[0].concept_id).toBe("123");
  });

  test("creates sequentially and reports per-variant results", async () => {
    const createCase = jest
      .fn()
      .mockResolvedValueOnce({ id: "c1" })
      .mockRejectedValueOnce(new Error("boom"));
    const results = await createCasesFromVariants(
      [makeVariant({ variantId: "a" }), makeVariant({ variantId: "b" })],
      createCase,
    );
    expect(createCase).toHaveBeenCalledTimes(2);
    expect(results[0]).toEqual({
      variantId: "a",
      ok: true,
      caseId: "c1",
    });
    expect(results[1]).toEqual({
      variantId: "b",
      ok: false,
      error: "boom",
    });
  });

  test("empty selection returns empty results without calling createCase", async () => {
    const createCase = jest.fn();
    const results = await createCasesFromVariants([], createCase);
    expect(results).toEqual([]);
    expect(createCase).not.toHaveBeenCalled();
  });

  test("normaliseVariantFromApi fills blank snake_case payloads", () => {
    const v = normaliseVariantFromApi(
      {
        patient_age: 68,
        patient_sex: "female",
        referral_text: "Dear colleague",
        is_control: false,
      },
      0,
    );
    expect(v.variantId).toBe("variant-1");
    expect(v.label).toBe("Variant 1");
    expect(v.rationale.length).toBeGreaterThan(0);
    expect(v.patientAge).toBe("68");
    expect(v.patientSex).toBe("female");
  });
});
