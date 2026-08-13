/**
 * VT-10011926 -- recently and frequently used clinical patients.
 */
import {
  frequentlyUsed,
  mergeUsedPatient,
  parseUsedPatients,
  recentPickerRows,
  recentlyUsed,
  type UsedPatient,
} from "../app/admin/validation-lab/clinicalUsedPatients";
import type { ClinicalPipelineRun } from "../app/admin/validation-lab/labFindingsApi";

function used(
  id: string,
  opened: string,
  count: number,
): UsedPatient {
  return {
    patient_id: id,
    patient_name: id,
    nhs_number: id,
    ubrn: "",
    run_id: `run-${id}`,
    last_opened_at: opened,
    open_count: count,
  };
}

function patient(id: string, runCount: number): ClinicalPipelineRun {
  return {
    run_id: `run-${id}`,
    status: "completed",
    created_at: "2026-08-13",
    plan_id: "",
    patient_id: id,
    patient_name: id,
    nhs_number: id,
    ubrn: "",
    run_count: runCount,
  };
}

describe("clinical used patients", () => {
  test("mergeUsedPatient bumps open count and moves to front", () => {
    const first = mergeUsedPatient([], patient("p1", 1), "2026-08-13T10:00:00Z");
    const second = mergeUsedPatient(first, patient("p1", 1), "2026-08-13T11:00:00Z");
    expect(second[0].open_count).toBe(2);
    expect(second[0].last_opened_at).toBe("2026-08-13T11:00:00Z");
    expect(second).toHaveLength(1);
  });

  test("recentlyUsed sorts by last opened", () => {
    const rows = [
      used("old", "2026-08-01T00:00:00Z", 9),
      used("new", "2026-08-13T00:00:00Z", 1),
    ];
    expect(recentlyUsed(rows).map((row) => row.patient_id)).toEqual([
      "new",
      "old",
    ]);
  });

  test("frequentlyUsed needs two opens and sorts by count", () => {
    const rows = [
      used("hot", "2026-08-13T00:00:00Z", 5),
      used("repeat", "2026-08-01T00:00:00Z", 4),
      used("once", "2026-08-02T00:00:00Z", 1),
    ];
    expect(frequentlyUsed(rows).map((row) => row.patient_id)).toEqual([
      "hot",
      "repeat",
    ]);
  });

  test("recentPickerRows falls back to patients with a pipeline run", () => {
    const rows = recentPickerRows([], [patient("p9", 1)]);
    expect(rows[0].patient_id).toBe("p9");
  });

  test("parseUsedPatients ignores bad json", () => {
    expect(parseUsedPatients("not-json")).toEqual([]);
    expect(parseUsedPatients("[]")).toEqual([]);
  });
});
