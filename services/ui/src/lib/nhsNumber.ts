/**
 * NHS number parsing and validation utilities.
 *
 * NHS numbers are 10 digits.  Users enter them in various formats:
 *   - 10 raw digits:        "9990000001"
 *   - Standard spaced:      "999 000 0001"
 *   - Hyphenated:           "999-000-0001"
 *   - Mixed spacing:        "999 0000001"
 *   - Multiple IDs:         "999 000 0001, 999-000-0002\n9990000003"
 *
 * The NHS Modulus 11 check digit algorithm is implemented in `isValidNhsNumber`
 * to catch obvious typos, but validation is advisory — internal IDs that don't
 * follow the check-digit rule (e.g. synthetic test IDs) are still accepted.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
/**
 * Strip whitespace and hyphens from a candidate string and return the raw
 * digits, or null if the result is not exactly 10 digits.
 */
export function normaliseNhsNumber(raw: string): string | null {
  const digits = raw.replace(/[\s\-]/g, "");
  return /^\d{10}$/.test(digits) ? digits : null;
}

/**
 * Parse a free-text input field that may contain one or more NHS numbers
 * separated by commas, newlines, or semicolons.  Each segment is normalised
 * (spaces/hyphens removed).  Invalid segments are silently skipped.
 *
 * Returns deduplicated list of 10-digit strings in input order.
 */
export function parseNhsNumberInput(input: string): string[] {
  // Split on comma, semicolon, or newline — NOT on spaces (which appear
  // within a single spaced NHS number like "999 000 0001").
  const segments = input.split(/[,;\n]+/);
  const seen = new Set<string>();
  const result: string[] = [];
  for (const seg of segments) {
    const normalised = normaliseNhsNumber(seg.trim());
    if (normalised && !seen.has(normalised)) {
      seen.add(normalised);
      result.push(normalised);
    }
  }
  return result;
}

/**
 * NHS Modulus 11 check-digit validation.
 *
 * Returns true if the 10-digit number passes the check.
 * Note: synthetic test IDs (999-prefix) intentionally may not pass — callers
 * should treat a failing check as a warning, not a hard error.
 */
export function isValidNhsNumber(digits: string): boolean {
  if (!/^\d{10}$/.test(digits)) return false;
  const weights = [10, 9, 8, 7, 6, 5, 4, 3, 2];
  const sum = weights.reduce((acc, w, i) => acc + w * parseInt(digits[i], 10), 0);
  const remainder = sum % 11;
  const checkDigit = 11 - remainder;
  if (checkDigit === 11) return parseInt(digits[9], 10) === 0;
  if (checkDigit === 10) return false; // invalid number
  return parseInt(digits[9], 10) === checkDigit;
}

/**
 * Format a 10-digit NHS number as the standard "3 3 4" display format.
 * e.g. "9990000001" → "999 000 0001"
 */
export function formatNhsNumber(digits: string): string {
  if (!/^\d{10}$/.test(digits)) return digits;
  return `${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6)}`;
}
