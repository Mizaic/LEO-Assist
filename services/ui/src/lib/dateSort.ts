/**
 * Compare ISO date/time strings for sorting. Unknown or invalid dates sort last in ascending order.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
function parseIsoMs(s: string | null | undefined): number | null {
  if (s == null) return null;
  const t = new Date(String(s).trim()).getTime();
  return Number.isNaN(t) ? null : t;
}

export function compareIsoDateTimeAsc(
  a: string | null | undefined,
  b: string | null | undefined,
): number {
  const ta = parseIsoMs(a);
  const tb = parseIsoMs(b);
  if (ta === null && tb === null) return 0;
  if (ta === null) return 1;
  if (tb === null) return -1;
  return ta - tb;
}

export function compareIsoDateTimeDesc(
  a: string | null | undefined,
  b: string | null | undefined,
): number {
  const ta = parseIsoMs(a);
  const tb = parseIsoMs(b);
  if (ta === null && tb === null) return 0;
  if (ta === null) return 1;
  if (tb === null) return -1;
  return tb - ta;
}

export function sortByIsoDateAsc<T>(
  items: readonly T[],
  getIso: (item: T) => string | null | undefined,
): T[] {
  return [...items].sort((x, y) => compareIsoDateTimeAsc(getIso(x), getIso(y)));
}

export function sortByIsoDateDesc<T>(
  items: readonly T[],
  getIso: (item: T) => string | null | undefined,
): T[] {
  return [...items].sort((x, y) => compareIsoDateTimeDesc(getIso(x), getIso(y)));
}
