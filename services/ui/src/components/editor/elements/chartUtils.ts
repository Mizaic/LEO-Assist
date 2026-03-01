/** Max characters before a tick label is truncated with "\u2026" */
export const LABEL_MAX_CHARS = 28;

/** Truncate a string to maxLen characters, appending "\u2026" if needed. */
export function truncateLabel(text: string, maxLen = LABEL_MAX_CHARS): string {
  if (!text || text.length <= maxLen) return text;
  return text.slice(0, maxLen - 1).trimEnd() + '\u2026';
}

export function formatValue(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value.toLocaleString();
  }
  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed.toLocaleString() : value;
  }
  return '';
}

export function humanizeKey(key: string): string {
  return key
    .replace(/[_\-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/**
 * Normalize a string for fuzzy key matching:
 * lowercase + strip non-alphanumeric characters.
 */
function normalize(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '');
}

/**
 * Given a row object and an ordered list of candidate key names,
 * return the first matching real key (fuzzy match).
 */
export function findKeyByCandidates(
  row: Record<string, unknown>,
  candidates: string[],
): string | undefined {
  const normalized = new Map<string, string>();
  Object.keys(row).forEach((key) => normalized.set(normalize(key), key));
  for (const candidate of candidates) {
    const match = normalized.get(normalize(candidate));
    if (match) return match;
  }
  return undefined;
}

/** Safely extract a finite number from a row property. */
export function numberFromRow(
  row: Record<string, unknown>,
  key?: string,
): number | null {
  if (!key) return null;
  const raw = row[key];
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw;
  if (typeof raw === 'string') {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function clampNumber(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

/** Try to extract numeric range boundaries from a row. */
export function parseRangesFromRow(
  row: Record<string, unknown>,
  rangeKeys?: string[],
): number[] {
  if (Array.isArray(row.ranges)) {
    return (row.ranges as unknown[])
      .map((v) => (typeof v === 'number' ? v : Number(v)))
      .filter((v) => Number.isFinite(v)) as number[];
  }
  if (rangeKeys && rangeKeys.length > 0) {
    return rangeKeys
      .map((key) => numberFromRow(row, key))
      .filter((v): v is number => v != null);
  }
  const autoKeys = [
    'range_low',
    'range_mid',
    'range_high',
    'range1',
    'range2',
    'range3',
  ];
  return autoKeys
    .map((key) => numberFromRow(row, findKeyByCandidates(row, [key])))
    .filter((v): v is number => v != null);
}

/**
 * For rows whose only numeric columns represent aggregate values
 * (e.g. pct, count), expand them into `{ __field, __value }` records.
 */
export function expandNumericColumns(
  rows: Array<Record<string, unknown>>,
  fieldGroup?: 'all' | 'pct' | 'count',
): Array<Record<string, unknown>> {
  if (!rows.length) return rows;
  const row = rows[0];
  const entries = Object.entries(row).filter(
    ([, value]) => typeof value === 'number' && Number.isFinite(value),
  );

  const pctPatterns = [/pct/i, /percent/i];
  const countExcludePatterns = [
    /pct/i,
    /percent/i,
    /avg/i,
    /average/i,
    /mean/i,
    /score/i,
    /total/i,
  ];

  const filtered = selectFieldGroup(entries, fieldGroup, pctPatterns, countExcludePatterns);
  const active = filtered.length > 0 ? filtered : entries;

  return active.map(([key, value]) => ({
    __field: humanizeKey(key),
    __value: value as number,
  }));
}

function selectFieldGroup(
  entries: Array<[string, unknown]>,
  fieldGroup: 'all' | 'pct' | 'count' | undefined,
  pctPatterns: RegExp[],
  countExcludePatterns: RegExp[],
): Array<[string, unknown]> {
  if (fieldGroup === 'pct') {
    return entries.filter(([key]) => pctPatterns.some((p) => p.test(key)));
  }
  if (fieldGroup === 'count') {
    return entries.filter(([key]) => !countExcludePatterns.some((p) => p.test(key)));
  }
  return entries;
}

export const CCI_RISK_ORDER = new Map<string, number>([
  ['None Risk', 0],
  ['Low Risk', 1],
  ['Moderate Risk', 2],
  ['High Risk', 3],
]);

/**
 * Sort rows by CCI risk label order when applicable,
 * otherwise return as-is.
 */
export function applyPreferredSort(
  dataset: Array<Record<string, unknown>>,
  labelKey?: string,
): Array<Record<string, unknown>> {
  if (!labelKey || dataset.length === 0) return dataset;

  const hasCciLabels = dataset.some((row) => {
    const raw = row[labelKey];
    return raw != null && CCI_RISK_ORDER.has(String(raw));
  });
  if (!hasCciLabels) return dataset;

  return [...dataset].sort((a, b) => {
    const aRank = CCI_RISK_ORDER.get(String(a[labelKey] ?? ''));
    const bRank = CCI_RISK_ORDER.get(String(b[labelKey] ?? ''));
    if (aRank == null && bRank == null) return 0;
    if (aRank == null) return 1;
    if (bRank == null) return -1;
    return aRank - bRank;
  });
}
