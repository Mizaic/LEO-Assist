import { findKeyByCandidates, numberFromRow } from './chartUtils';

// ─── Types ───────────────────────────────────────────────────────────

export type BoxPlotPoint = {
  label: string;
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
  mean?: number;
};

type BoxPlotStatKey = 'min' | 'q1' | 'median' | 'q3' | 'max' | 'mean';

// ─── Stat label resolution ───────────────────────────────────────────

function normalizeStatLabel(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, '');
}

const STAT_MAP: ReadonlyArray<{ key: BoxPlotStatKey; tokens: string[] }> = [
  { key: 'min', tokens: ['min', 'mindays', 'minimum', 'minday'] },
  { key: 'q1', tokens: ['q1', 'quartile1', 'firstquartile', 'p25'] },
  { key: 'median', tokens: ['median', 'mediandays', 'p50'] },
  { key: 'q3', tokens: ['q3', 'quartile3', 'thirdquartile', 'p75'] },
  { key: 'max', tokens: ['max', 'maxdays', 'maximum', 'maxday'] },
  { key: 'mean', tokens: ['mean', 'meandays', 'avg', 'average'] },
];

function resolveBoxPlotStat(label: string): BoxPlotStatKey | null {
  const normalized = normalizeStatLabel(label);
  if (!normalized) return null;
  for (const entry of STAT_MAP) {
    if (entry.tokens.includes(normalized)) return entry.key;
  }
  return null;
}

// ─── Percentile helper ───────────────────────────────────────────────

export function percentile(sorted: number[], ratio: number): number {
  if (sorted.length === 0) return 0;
  if (sorted.length === 1) return sorted[0];
  const pos = (sorted.length - 1) * ratio;
  const lower = Math.floor(pos);
  const upper = Math.ceil(pos);
  if (lower === upper) return sorted[lower];
  const weight = pos - lower;
  return sorted[lower] + (sorted[upper] - sorted[lower]) * weight;
}

// ─── Row key candidates ─────────────────────────────────────────────

const MIN_CANDIDATES = ['min', 'min_days', 'min_day', 'minimum'];
const Q1_CANDIDATES = ['q1', 'quartile1', 'first_quartile', 'p25'];
const MEDIAN_CANDIDATES = ['median', 'median_days', 'p50'];
const Q3_CANDIDATES = ['q3', 'quartile3', 'third_quartile', 'p75'];
const MAX_CANDIDATES = ['max', 'max_days', 'maximum'];
const MEAN_CANDIDATES = ['mean', 'mean_days', 'avg', 'average'];

// ─── buildBoxPlotPoints ──────────────────────────────────────────────

/**
 * Main entry: try three strategies in order:
 *   1. Rows already contain min/q1/median/q3/max columns
 *   2. Field/value rows where labels map to stat names
 *   3. Group raw values by label and compute quartiles
 */
export function buildBoxPlotPoints(
  rows: Array<Record<string, unknown>>,
  labelKey?: string,
  valueKey?: string,
): BoxPlotPoint[] {
  const safeLabelKey = labelKey === '__field' ? undefined : labelKey;
  const safeValueKey = valueKey === '__value' ? undefined : valueKey;

  const direct = buildDirectPoints(rows, safeLabelKey);
  if (direct.length > 0) return direct;

  const fromFieldValue = buildBoxPlotFromFieldValueRows(rows, safeLabelKey, safeValueKey);
  if (fromFieldValue.length > 0) return fromFieldValue;

  return buildBoxPlotFromSeries(rows, safeLabelKey, safeValueKey);
}

// ─── Strategy 1: direct stat columns ─────────────────────────────────

function buildDirectPoints(
  rows: Array<Record<string, unknown>>,
  labelKey?: string,
): BoxPlotPoint[] {
  const points: BoxPlotPoint[] = [];

  rows.forEach((row, index) => {
    const stats = resolveDirectStats(row);
    if (!stats) return;
    const label = resolveLabel(row, labelKey, index);
    points.push({ label, ...stats });
  });

  return points;
}

function resolveDirectStats(
  row: Record<string, unknown>,
): Omit<BoxPlotPoint, 'label'> | null {
  const min = numberFromRow(row, findKeyByCandidates(row, MIN_CANDIDATES));
  const q1 = numberFromRow(row, findKeyByCandidates(row, Q1_CANDIDATES));
  const median = numberFromRow(row, findKeyByCandidates(row, MEDIAN_CANDIDATES));
  const q3 = numberFromRow(row, findKeyByCandidates(row, Q3_CANDIDATES));
  const max = numberFromRow(row, findKeyByCandidates(row, MAX_CANDIDATES));
  if ([min, q1, median, q3, max].some((v) => v == null)) return null;
  const mean = numberFromRow(row, findKeyByCandidates(row, MEAN_CANDIDATES)) ?? undefined;
  return {
    min: min as number,
    q1: q1 as number,
    median: median as number,
    q3: q3 as number,
    max: max as number,
    mean,
  };
}

function resolveLabel(
  row: Record<string, unknown>,
  labelKey: string | undefined,
  index: number,
): string {
  if (labelKey && row[labelKey] != null) return String(row[labelKey]);
  const firstString = Object.values(row).find((v) => typeof v === 'string');
  return firstString != null ? String(firstString) : `Series ${index + 1}`;
}

// ─── Strategy 2: field/value stat rows ───────────────────────────────

export function buildBoxPlotFromFieldValueRows(
  rows: Array<Record<string, unknown>>,
  labelKey?: string,
  valueKey?: string,
): BoxPlotPoint[] {
  if (!rows.length) return [];
  const sample = rows[0] || {};
  const resolvedLabelKey =
    labelKey ||
    Object.keys(sample).find((k) => typeof sample[k] === 'string') ||
    '__field';
  const resolvedValueKey =
    valueKey ||
    Object.keys(sample).find((k) => typeof sample[k] === 'number') ||
    '__value';

  const stats = collectStatValues(rows, resolvedLabelKey, resolvedValueKey);
  if (
    stats.min == null ||
    stats.q1 == null ||
    stats.median == null ||
    stats.q3 == null ||
    stats.max == null
  ) {
    return [];
  }
  return [
    {
      label: 'Summary',
      min: stats.min,
      q1: stats.q1,
      median: stats.median,
      q3: stats.q3,
      max: stats.max,
      mean: stats.mean,
    },
  ];
}

function collectStatValues(
  rows: Array<Record<string, unknown>>,
  labelKey: string,
  valueKey: string,
): Partial<Record<BoxPlotStatKey, number>> {
  const stats: Partial<Record<BoxPlotStatKey, number>> = {};
  rows.forEach((row) => {
    const rawLabel = row[labelKey];
    if (rawLabel == null) return;
    const statKey = resolveBoxPlotStat(String(rawLabel));
    if (!statKey) return;
    const numeric = numberFromRow(row, valueKey);
    if (numeric == null) return;
    stats[statKey] = numeric;
  });
  return stats;
}

// ─── Strategy 3: group raw values ────────────────────────────────────

export function buildBoxPlotFromSeries(
  rows: Array<Record<string, unknown>>,
  labelKey?: string,
  valueKey?: string,
): BoxPlotPoint[] {
  if (!rows.length) return [];
  const sample = rows[0] || {};
  const resolvedLabelKey =
    labelKey ||
    Object.keys(sample).find((k) => typeof sample[k] === 'string') ||
    'name';
  const resolvedValueKey =
    valueKey ||
    Object.keys(sample).find((k) => typeof sample[k] === 'number') ||
    'value';

  const groups = groupValuesByLabel(rows, resolvedLabelKey, resolvedValueKey);
  return computeQuartilePoints(groups);
}

function groupValuesByLabel(
  rows: Array<Record<string, unknown>>,
  labelKey: string,
  valueKey: string,
): Map<string, number[]> {
  const groups = new Map<string, number[]>();
  rows.forEach((row, index) => {
    const rawLabel = row[labelKey];
    const label = rawLabel != null ? String(rawLabel) : `Series ${index + 1}`;
    const value = numberFromRow(row, valueKey);
    if (value == null) return;
    const bucket = groups.get(label) || [];
    bucket.push(value);
    groups.set(label, bucket);
  });
  return groups;
}

function computeQuartilePoints(
  groups: Map<string, number[]>,
): BoxPlotPoint[] {
  const points: BoxPlotPoint[] = [];
  groups.forEach((values, label) => {
    if (values.length === 0) return;
    const sorted = [...values].sort((a, b) => a - b);
    points.push({
      label,
      min: sorted[0],
      q1: percentile(sorted, 0.25),
      median: percentile(sorted, 0.5),
      q3: percentile(sorted, 0.75),
      max: sorted[sorted.length - 1],
      mean: sorted.reduce((s, v) => s + v, 0) / sorted.length,
    });
  });
  return points;
}
