/**
 * VT-FA40F4D3 -- Demo mode masking helpers.
 *
 * Design Controls: DI-6FD9D8D1, DO-ACCEEF0C, VT-FA40F4D3.
 */

import {
  maskAge,
  maskBirthDate,
  maskEncounterText,
  maskGpName,
  maskNhsNumber,
  maskOrgName,
  maskPatientId,
  maskPostcode,
} from "@/lib/demoMode";

describe("VT-FA40F4D3 demo mode masking helpers", () => {
  test("TC-001: patient aliases are deterministic and hide raw IDs", () => {
    const first = maskPatientId("NHS-PATIENT-123");
    const second = maskPatientId("NHS-PATIENT-123");

    expect(first).toBe(second);
    expect(first).toMatch(/^Patient DEMO-\d{4}$/);
    expect(first).not.toContain("NHS-PATIENT-123");
  });

  test("TC-002: structured identifiers are replaced by safe labels", () => {
    expect(maskNhsNumber("9434765919")).toBe("NHS number hidden");
    expect(maskBirthDate("1950-01-02")).toBe("DOB hidden");
    expect(maskAge(74)).toBe("Age hidden");
    expect(maskPostcode("SW1A 1AA")).toBe("Postcode hidden");
  });

  test("TC-003: organisation labels are deterministic and hide source names", () => {
    const gp = maskGpName("Real GP Practice");
    const org = maskOrgName("Real NHS Trust");

    expect(gp).toMatch(/^Demo GP practice \d+$/);
    expect(org).toMatch(/^Demo organisation \d+$/);
    expect(gp).not.toContain("Real GP Practice");
    expect(org).not.toContain("Real NHS Trust");
  });

  test("TC-004: encounter text is replaced without retaining narrative", () => {
    const masked = maskEncounterText("Patient says their chest pain is worse.");

    expect(masked).toBe("Encounter text hidden in demo mode.");
    expect(masked).not.toContain("chest pain");
  });
});
