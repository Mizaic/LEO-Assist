/** Infer a human-readable encounter label from the encounter id suffix. */
export function encounterTypeLabel(
  encounterId: string,
  fallback: string
): string {
  const low = encounterId.toLowerCase();
  if (low.includes("referral")) return "GP referral";
  if (low.includes("diagnosis")) return "Diagnosis";
  if (low.includes("symptom")) return "Symptoms";
  if (low.includes("appointment")) return "Appointment";
  if (low.includes("triage")) return "Triage";
  if (low.includes("assessment")) return "Assessment";
  if (low.includes("treatment")) return "Treatment";
  if (low.includes("discharge")) return "Discharge";
  if (fallback && fallback !== "Encounter" && fallback !== "encounter") {
    return fallback;
  }
  return "Clinical note";
}
