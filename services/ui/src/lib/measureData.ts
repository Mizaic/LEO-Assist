import type { MeasureReport } from '@/lib/types/fhir';

export interface MeasureSeriesPoint {
  name: string;
  value: number;
  /** IQR lower bound (25th percentile) for median aggregation */
  iqr_low?: number;
  /** IQR upper bound (75th percentile) for median aggregation */
  iqr_high?: number;
  /** True when value is a percentage (0–100) */
  isPercentage?: boolean;
}

export type MeasureReportRow = Record<string, string | number>;

const QUERY_RESULT_URL = 'http://example.org/fhir/StructureDefinition/query-result';
const BENCHMARK_URL = 'http://example.org/fhir/StructureDefinition/benchmark-comparison';

export interface BenchmarkPoint {
  metric_id: string;
  label: string;
  scope_type: string;
  scope_name: string;
  value: number | null;
  unit: string | null;
  source?: string | null;
  /** For composite metrics (e.g. sex: male/female), holds { male, female } percentages. */
  value_breakdown?: Record<string, number> | null;
}

function decodeBase64(value: string): string {
  if (typeof atob === 'function') return atob(value);
  if (typeof Buffer !== 'undefined') return Buffer.from(value, 'base64').toString('utf-8');
  return value;
}

function valueLabel(value?: { text?: string; coding?: Array<{ display?: string; code?: string }> }): string {
  if (!value) return 'Unknown';
  const raw = value.text || value.coding?.[0]?.display || value.coding?.[0]?.code || 'Unknown';
  return cleanSnomedLabel(raw);
}

function humanizeKey(key: string): string {
  return key
    .replace(/[_\-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

const SNOMED_QUALIFIERS =
  /\s*\((situation|finding|disorder|disease|observable entity|procedure|morphologic abnormality|qualifier value|clinical finding|body structure|substance|regime\/therapy|event|occupation|person|organism|physical object|product|assessment scale|tumor staging|cell structure|attribute|social concept|ethnic group|racial group|geographic location|environment|context-dependent category)\)\s*$/i;

export function cleanSnomedLabel(label: string): string {
  return label.replace(SNOMED_QUALIFIERS, '').trim();
}

function parseQueryResult(report: MeasureReport): Array<Record<string, unknown>> {
  const extension = report.extension?.find((ext) => ext.url === QUERY_RESULT_URL);
  if (!extension) return [];

  const rawValue =
    extension.valueString ||
    (extension.valueAttachment?.data ? decodeBase64(extension.valueAttachment.data) : undefined);

  if (!rawValue) return [];

  try {
    const parsed = JSON.parse(rawValue);
    if (Array.isArray(parsed)) {
      return parsed.filter((row) => row && typeof row === 'object') as Array<Record<string, unknown>>;
    }
    if (parsed && typeof parsed === 'object') {
      return [parsed as Record<string, unknown>];
    }
  } catch (error) {
    console.warn('Failed to parse query result extension:', error);
  }

  return [];
}

function rowToSeries(row: Record<string, unknown>): MeasureSeriesPoint[] {
  const entries = Object.entries(row);
  const stringEntries = entries.filter(([, value]) => typeof value === 'string' && (value as string).trim().length > 0);
  const numericEntries = entries.filter(([, value]) => typeof value === 'number' && !Number.isNaN(value));

  if (numericEntries.length === 0) return [];

  const rawLabel = stringEntries[0]?.[1] as string | undefined;
  const labelValue = rawLabel ? cleanSnomedLabel(rawLabel) : undefined;
  const valueNum = (row.value as number) ?? (numericEntries[0]?.[1] as number);
  const iqrLow = typeof row.iqr_low === 'number' && Number.isFinite(row.iqr_low) ? row.iqr_low : undefined;
  const iqrHigh = typeof row.iqr_high === 'number' && Number.isFinite(row.iqr_high) ? row.iqr_high : undefined;
  const isPercentage = row.name === 'Yes' && typeof valueNum === 'number' && valueNum >= 0 && valueNum <= 100;

  if ('value' in row && typeof row.value === 'number' && Number.isFinite(row.value)) {
    return [{
      name: labelValue || 'Value',
      value: row.value,
      iqr_low: iqrLow,
      iqr_high: iqrHigh,
      isPercentage,
    }];
  }

  if (numericEntries.length === 1) {
    const [key, value] = numericEntries[0];
    return [{ name: labelValue || humanizeKey(key), value: value as number, isPercentage }];
  }

  return numericEntries.map(([key, value]) => ({
    name: labelValue ? `${labelValue} (${humanizeKey(key)})` : humanizeKey(key),
    value: value as number,
  }));
}

export function extractMeasureReportSeries(report: MeasureReport): MeasureSeriesPoint[] {
  const group = report.group?.[0];
  if (group?.stratifier && group.stratifier.length > 0) {
    const stratifier = group.stratifier[0];
    return (
      stratifier.stratum?.map((stratum) => {
        const score = stratum.measureScore?.value;
        const count = stratum.population?.[0]?.count;
        return { name: valueLabel(stratum.value), value: score ?? count ?? 0 };
      }) || []
    );
  }

  if (group?.population && group.population.length > 0) {
    return group.population.map((population) => ({
      name:
        population.code?.text ||
        population.code?.coding?.[0]?.display ||
        population.code?.coding?.[0]?.code ||
        'Population',
      value: population.count ?? 0,
    }));
  }

  if (group?.measureScore?.value != null) {
    return [{ name: 'Score', value: group.measureScore.value }];
  }

  const rows = parseQueryResult(report);
  if (rows.length === 0) return [];
  return rows.flatMap((row) => rowToSeries(row)).filter((point) => Number.isFinite(point.value));
}

export function extractMeasureReportRows(report: MeasureReport): MeasureReportRow[] {
  const rows = parseQueryResult(report) as MeasureReportRow[];
  if (rows.length > 0) {
    return rows.map((row) => {
      const cleaned: MeasureReportRow = {};
      for (const [key, value] of Object.entries(row)) {
        cleaned[key] = typeof value === 'string' ? cleanSnomedLabel(value) : value;
      }
      return cleaned;
    });
  }
  const series = extractMeasureReportSeries(report);
  return series.map((point) => ({ name: point.name, value: point.value }));
}

export function extractMeasureReportValue(report: MeasureReport): number | null {
  const group = report.group?.[0];
  if (group?.measureScore?.value != null) return group.measureScore.value;
  if (group?.population?.[0]?.count != null) return group.population[0].count;
  const rows = parseQueryResult(report);
  const series = rows.flatMap((row) => rowToSeries(row));
  const firstValue = series.find((point) => Number.isFinite(point.value));
  return firstValue ? firstValue.value : null;
}

/**
 * Format a measure value for display (median + IQR, percentage, or plain number).
 */
export function formatMeasureValue(point: MeasureSeriesPoint, numberFormatter?: Intl.NumberFormat): string {
  const fmt = numberFormatter ?? new Intl.NumberFormat('en-US');
  const v = fmt.format(point.value);
  if (point.isPercentage) return `${v}%`;
  if (point.iqr_low != null && point.iqr_high != null && Number.isFinite(point.iqr_low) && Number.isFinite(point.iqr_high)) {
    return `${v} (IQR ${fmt.format(Math.round(point.iqr_low))}\u2013${fmt.format(Math.round(point.iqr_high))})`;
  }
  return v;
}

/**
 * Format value from raw row (for score display when row has extended fields).
 */
export function formatMeasureValueFromRow(row: Record<string, unknown>, numberFormatter?: Intl.NumberFormat): string {
  const val = typeof row.value === 'number' && Number.isFinite(row.value) ? row.value : 0;
  const point: MeasureSeriesPoint = {
    name: String(row.name ?? ''),
    value: val,
    iqr_low: typeof row.iqr_low === 'number' ? row.iqr_low : undefined,
    iqr_high: typeof row.iqr_high === 'number' ? row.iqr_high : undefined,
    isPercentage: row.name === 'Yes' && val >= 0 && val <= 100,
  };
  return formatMeasureValue(point, numberFormatter);
}

export function extractBenchmarkComparison(report: MeasureReport): BenchmarkPoint[] | null {
  const extension = report.extension?.find((ext) => ext.url === BENCHMARK_URL);
  if (!extension?.valueString) return null;
  try {
    const parsed = JSON.parse(extension.valueString);
    if (!Array.isArray(parsed) || parsed.length === 0) return null;
    return parsed as BenchmarkPoint[];
  } catch {
    return null;
  }
}
