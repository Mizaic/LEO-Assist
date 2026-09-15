/**
 * Display helpers for the EPR identity bar.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

export function formatNhsNumber(nhs: string): string {
  const digits = nhs.replace(/\D/g, "");
  if (digits.length === 10) {
    return `${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6)}`;
  }
  return nhs;
}

export function ageFromBirthDate(iso: string | null): string {
  if (!iso) return "";
  const birth = new Date(iso);
  if (Number.isNaN(birth.getTime())) return "";
  const now = new Date();
  let age = now.getUTCFullYear() - birth.getUTCFullYear();
  const monthDelta = now.getUTCMonth() - birth.getUTCMonth();
  if (
    monthDelta < 0 ||
    (monthDelta === 0 && now.getUTCDate() < birth.getUTCDate())
  ) {
    age -= 1;
  }
  if (age < 0) return "";
  return age === 1 ? "1 year" : `${age} years`;
}

export function formatBornDate(iso: string | null): string {
  if (!iso) return "Date of birth unknown";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return `Born ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function genderLabel(raw: string | null): string {
  if (!raw) return "";
  return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase();
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}
