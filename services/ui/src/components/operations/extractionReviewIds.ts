/**
 * Display helpers for NHS number and UBRN chips on paused extraction review.
 *
 * Atlas trace: DI-4A012A59
 */

export function compactDigits(raw: string): string {
  return (raw || "").replace(/\D/g, "");
}

export function formatNhsNumber(raw: string): string {
  const digits = compactDigits(raw);
  if (digits.length !== 10) return "";
  return `${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6)}`;
}

export function formatUbrn(raw: string): string {
  const digits = compactDigits(raw);
  if (digits.length !== 12) return "";
  return `${digits.slice(0, 4)} ${digits.slice(4, 8)} ${digits.slice(8)}`;
}
