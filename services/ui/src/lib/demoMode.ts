/**
 * Atlas trace:
 *   DO: DO-ACCEEF0C
 *   DI: DI-6FD9D8D1
 *   VT: VT-FA40F4D3
 */

const EMPTY_PLACEHOLDER = "--";

function stableNumber(value: string, modulo: number): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return hash % modulo;
}

function stableOrdinal(value: string | null | undefined): string {
  const source = value && value.trim() ? value : "unknown";
  return String(stableNumber(source, 10000)).padStart(4, "0");
}

export function maskPatientId(value: string | null | undefined): string {
  if (!value) return EMPTY_PLACEHOLDER;
  return `Patient DEMO-${stableOrdinal(value)}`;
}

export function maskNhsNumber(value: string | null | undefined): string {
  if (!value) return "NHS number hidden";
  return "NHS number hidden";
}

export function maskBirthDate(value: string | null | undefined): string {
  if (!value) return "DOB hidden";
  return "DOB hidden";
}

export function maskAge(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "Age hidden";
  return "Age hidden";
}

export function maskPostcode(value: string | null | undefined): string {
  if (!value) return "Postcode hidden";
  return "Postcode hidden";
}

export function maskOrgName(value: string | null | undefined): string {
  if (!value) return "Demo organisation";
  return `Demo organisation ${stableNumber(value, 100) + 1}`;
}

export function maskGpName(value: string | null | undefined): string {
  if (!value) return "Demo GP practice";
  return `Demo GP practice ${stableNumber(value, 100) + 1}`;
}

export function maskEncounterText(value: string | null | undefined): string {
  if (!value || !value.trim()) return "(No text)";
  return "Encounter text hidden in demo mode.";
}

export function demoValue<T>(
  isDemoMode: boolean,
  value: T,
  masker: (value: T) => string,
): T | string {
  return isDemoMode ? masker(value) : value;
}
