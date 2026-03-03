'use client';

import { useMemo } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';
import Tooltip from '@mui/material/Tooltip';
import BarChartOutlined from '@mui/icons-material/BarChartOutlined';
import HourglassEmptyOutlined from '@mui/icons-material/HourglassEmptyOutlined';
import { MeasureElement as MeasureElementType, PopulationPyramidDatum, ChartType, ComparisonMetric } from '@/lib/types/layout';
import {
  BenchmarkPoint,
  extractMeasureReportRows,
  extractMeasureReportSeries,
  extractMeasureReportValue,
  formatMeasureValue,
  formatMeasureValueFromRow,
  type MeasureSeriesPoint,
} from '@/lib/measureData';
import { useMeasureData } from './useMeasureData';
import { ChartElement as ChartRenderer } from './ChartElement';
import { ComparisonBarsElement as ComparisonBarsRenderer } from './ComparisonBarsElement';
import { PopulationPyramidElement } from './PopulationPyramidElement';

const containerSx = {
  width: '100%',
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
  bgcolor: 'background.paper',
  border: 1,
  borderColor: 'divider',
  borderRadius: 0.5,
  overflow: 'hidden',
} as const;

const placeholderSx = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  color: 'text.disabled',
  gap: '8px',
  padding: '16px',
  textAlign: 'center',
} as const;

interface MeasureElementProps {
  element: MeasureElementType;
}

const CHART_DISPLAY_MODES = new Set([
  'bar', 'horizontalBar', 'boxPlot', 'pie', 'line', 'area',
  'radar', 'radialBar', 'scatter', 'composed', 'funnel',
  'heatmap', 'bullet', 'sankey',
]);

const RAW_DATA_MODES = new Set(['boxPlot', 'heatmap', 'bullet', 'sankey']);

const DRAFT_MEASURE_GAPS: Record<string, string> = {
  'cancer-stage-distribution':
    'Cancer staging requires PHE COSD (Cancer Outcomes & Services Dataset) — ' +
    'not available from GP records alone.',
  'referral-routes':
    'Referral route (TWW / urgent / routine) — ' +
    'pipeline enhancement in progress to extract from coded GP data.',
  'emergency-referral-routes':
    'Emergency sub-classification (categories 0–7) — ' +
    'requires retrospective NCDA audit form completion by GP.',
  'safety-netting-recorded':
    'Safety-netting recorded flag — ' +
    'pipeline enhancement in progress to extract from coded GP data.',
  'avoidable-delays-summary':
    'Avoidable delay assessment — ' +
    'requires retrospective GP audit judgment; cannot be automated.',
  'place-of-presentation':
    'Place of first presentation — ' +
    'pipeline enhancement in progress to extract from coded GP data.',
  'multiple-consultation-reasons':
    'Multiple consultation reason — ' +
    'requires GP NCDA audit form data; cannot be automated.',
};

function deriveBenchmarkSource(points: BenchmarkPoint[]): string | undefined {
  const src = points.find((p) => p.source)?.source;
  return src ?? undefined;
}

function isPHEMeasure(measureId: string | undefined): boolean {
  if (!measureId) return false;
  const id = measureId.replace('Measure/', '');
  return id.startsWith('phe-');
}

export function MeasureElement({ element }: MeasureElementProps) {
  const { measure, measureReport, benchmarks, loading, dataLoading, errorMessage } = useMeasureData(element);
  const numberFormatter = useMemo(() => new Intl.NumberFormat('en-US'), []);

  const formatValue = (rawValue: unknown): string => {
    if (rawValue === null || rawValue === undefined) return '--';
    if (typeof rawValue === 'number' && Number.isFinite(rawValue)) {
      return numberFormatter.format(rawValue);
    }
    if (typeof rawValue === 'string') {
      const numericValue = Number(rawValue);
      if (Number.isFinite(numericValue) && rawValue.trim() !== '') {
        return numberFormatter.format(numericValue);
      }
    }
    return String(rawValue);
  };

  if (!element.measureId) {
    return (
      <Box sx={containerSx}>
        <Box sx={placeholderSx}>
          <BarChartOutlined sx={{ fontSize: '32px' }} />
          <Typography sx={{ fontSize: '0.625rem' }}>
            No measure selected.
            <br />
            Select one in properties.
          </Typography>
        </Box>
      </Box>
    );
  }

  if (loading || dataLoading) {
    return (
      <Box sx={containerSx}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: '100%' }}>
          <CircularProgress aria-label="Loading" size={24} />
        </Box>
      </Box>
    );
  }

  if (errorMessage) {
    return (
      <Box sx={containerSx}>
        <Box sx={placeholderSx}>
          <BarChartOutlined sx={{ fontSize: '32px' }} />
          <Typography sx={{ fontSize: '0.625rem' }}>{errorMessage}</Typography>
        </Box>
      </Box>
    );
  }

  if (measure?.status === 'draft') {
    const measureKey = element.measureId?.replace('Measure/', '') ?? '';
    const gapText = DRAFT_MEASURE_GAPS[measureKey] ?? 'Data for this measure is not yet available.';
    return (
      <Box sx={containerSx}>
        <Box sx={{ ...placeholderSx, gap: '6px' }}>
          <Tooltip title={gapText} placement="top">
            <HourglassEmptyOutlined sx={{ fontSize: '28px', color: 'warning.main', opacity: 0.7 }} />
          </Tooltip>
          <Typography sx={{ fontSize: '0.625rem', fontWeight: 600, color: 'warning.dark' }}>
            {measure.title ?? measureKey}
          </Typography>
          <Typography sx={{ fontSize: '0.5625rem', color: 'text.disabled', maxWidth: '90%' }}>
            {gapText}
          </Typography>
        </Box>
      </Box>
    );
  }

  const series = measureReport ? extractMeasureReportSeries(measureReport) : [];
  const rows = measureReport ? extractMeasureReportRows(measureReport) : [];
  const value = computeDisplayValue(element, rows, measureReport);
  const title = element.title?.trim() || measure?.title || measure?.name || 'Measure';
  const scoreDisplayValue =
    rows.length > 0 && (rows[0].iqr_low != null || rows[0].iqr_high != null || rows[0].name === 'Yes')
      ? formatMeasureValueFromRow(rows[0] as Record<string, unknown>, numberFormatter)
      : formatValue(value);

  return (
    <Box sx={containerSx}>
      {element.showTitle && (
        <Box sx={{ padding: '8px', bgcolor: 'grey.200', borderBottom: 1, borderColor: 'divider' }}>
          <Typography sx={{ fontSize: '0.75rem', fontWeight: 600, color: 'text.primary', overflow: 'hidden', whiteSpace: 'normal', wordBreak: 'break-word' }}>
            {title}
          </Typography>
        </Box>
      )}
      <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '8px' }}>
        {element.displayMode === 'table' ? (
          renderTable(series, (v, point) => (point ? formatMeasureValue(point, numberFormatter) : formatValue(v)))
        ) : element.displayMode === 'populationPyramid' ? (
          <PopulationPyramidElement
            element={{
              id: element.id, type: 'populationPyramid',
              x: element.x, y: element.y, w: element.w, h: element.h,
              title, data: buildPopulationData(element, rows),
            }}
          />
        ) : CHART_DISPLAY_MODES.has(element.displayMode ?? '') ? (
          <ChartRenderer
            element={{
              id: element.id, type: 'chart',
              x: element.x, y: element.y, w: element.w, h: element.h,
              chartType: element.displayMode as ChartType,
              xAxisKey: element.dataBindings?.xAxisKey,
              yAxisKey: element.dataBindings?.yAxisKey,
              seriesKey: element.dataBindings?.seriesKey,
              fieldGroup: element.dataBindings?.fieldGroup,
              targetKey: element.dataBindings?.seriesKey,
              showLegend: true, showGrid: true,
            }}
            dataOverride={
              RAW_DATA_MODES.has(element.displayMode ?? '') ||
              element.dataBindings?.xAxisKey ||
              element.dataBindings?.yAxisKey
                ? (rows as any)
                : series
            }
          />
        ) : element.showScore ? (
          <Typography sx={{ fontSize: '2rem', fontWeight: 700, color: 'primary.main' }}>
            {scoreDisplayValue}
          </Typography>
        ) : (
          <Typography sx={{ fontSize: '0.625rem' }}>
            {measure?.description || 'Measure data will appear here'}
          </Typography>
        )}
        {isPHEMeasure(element.measureId) && (
          <Typography sx={{ fontSize: '0.5rem', color: 'text.disabled', fontStyle: 'italic', mt: '4px' }}>
            Source: PHE Fingertips
          </Typography>
        )}
      </Box>
      {benchmarks && benchmarks.length > 0 && (
        <Box sx={{ padding: '8px', borderTop: 1, borderColor: 'divider' }}>
          <ComparisonBarsRenderer
            element={{
              id: `${element.id}-bench`, type: 'comparisonBars',
              x: 0, y: 0, w: 0, h: 0,
              title: 'Benchmark Comparison',
              source: deriveBenchmarkSource(benchmarks),
              metrics: benchmarksToMetrics(
                benchmarks,
                measureReport ? extractMeasureReportValue(measureReport) : null,
              ),
            }}
          />
        </Box>
      )}
    </Box>
  );
}

function formatBreakdown(breakdown: Record<string, number>, unit: string): string {
  const parts = Object.entries(breakdown)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, v]) => (unit === 'pct' ? `${v}%` : `${v} ${unit}`));
  return parts.join(' / ');
}

function benchmarksToMetrics(
  points: BenchmarkPoint[],
  liveValue: number | null,
): ComparisonMetric[] {
  const grouped = new Map<string, Map<string, number | null>>();
  const breakdownGrouped = new Map<string, Map<string, Record<string, number>>>();
  const labels = new Map<string, string>();
  const units = new Map<string, string>();
  for (const pt of points) {
    labels.set(pt.metric_id, pt.label);
    units.set(pt.metric_id, pt.unit ?? '%');
    if (pt.value_breakdown) {
      if (!breakdownGrouped.has(pt.metric_id)) breakdownGrouped.set(pt.metric_id, new Map());
      breakdownGrouped.get(pt.metric_id)!.set(pt.scope_type, pt.value_breakdown);
    } else {
      if (!grouped.has(pt.metric_id)) grouped.set(pt.metric_id, new Map());
      grouped.get(pt.metric_id)!.set(pt.scope_type, pt.value);
    }
  }
  const metrics: ComparisonMetric[] = [];
  for (const [metricId, scopes] of breakdownGrouped) {
    const unit = units.get(metricId) ?? '%';
    const scopeDisplayValues: Record<string, string> = {};
    for (const [scopeType, breakdown] of scopes) {
      scopeDisplayValues[scopeType] = formatBreakdown(breakdown, unit);
    }
    metrics.push({
      metric: labels.get(metricId) ?? metricId,
      current: 0,
      target: 0,
      unit,
      scopeDisplayValues,
    });
  }
  for (const [metricId, scopes] of grouped) {
    metrics.push({
      metric: labels.get(metricId) ?? metricId,
      current: liveValue ?? 0,
      target: scopes.get('national') ?? 0,
      benchmark: scopes.get('cancer_alliance') ?? undefined,
      unit: units.get(metricId) ?? '%',
    });
  }
  return metrics;
}

function parseNumericValue(rawValue: unknown): number | null {
  if (typeof rawValue === 'number' && Number.isFinite(rawValue)) return rawValue;
  if (typeof rawValue === 'string') {
    const parsed = Number(rawValue);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function computeDisplayValue(
  element: MeasureElementType,
  rows: Record<string, unknown>[],
  measureReport: import('@/lib/types/fhir').MeasureReport | null,
): unknown {
  const preferredKeys = [
    element.dataBindings?.yAxisKey, 'median_days', 'mean_days',
    'avg', 'average', 'days', 'value',
  ].filter(Boolean) as string[];

  const valueFromRows = rows.reduce<number | null>((acc, row) => {
    if (acc != null) return acc;
    for (const key of preferredKeys) {
      if (key in row) {
        const numeric = parseNumericValue((row as any)[key]);
        if (numeric != null) return numeric;
      }
    }
    return acc;
  }, null);

  if (element.displayMode === 'value') {
    return valueFromRows ?? (measureReport ? extractMeasureReportValue(measureReport) : null);
  }
  return measureReport ? extractMeasureReportValue(measureReport) : null;
}

function buildPopulationData(
  element: MeasureElementType,
  rows: Record<string, unknown>[],
): PopulationPyramidDatum[] {
  if (rows.length === 0) return [];

  const hasMaleFemale = rows.some((row) => 'male' in row || 'female' in row);
  if (hasMaleFemale) {
    return rows.map((row) => ({
      ageBand: (row as any).ageBand || (row as any).age_group || (row as any).age || '',
      male: typeof (row as any).male === 'number' ? (row as any).male : 0,
      female: typeof (row as any).female === 'number' ? (row as any).female : 0,
    }));
  }

  const ageKey = element.dataBindings?.xAxisKey || 'ageBand';
  const genderKey = element.dataBindings?.seriesKey || 'gender';
  const valueKey = element.dataBindings?.yAxisKey || 'count';

  return rows
    .map((row) => ({
      ageBand: (row as any)[ageKey],
      gender: (row as any)[genderKey],
      count: typeof (row as any)[valueKey] === 'number' ? (row as any)[valueKey] : undefined,
    }))
    .filter((row) => row.ageBand && row.gender && typeof row.count === 'number');
}

function renderTable(
  series: MeasureSeriesPoint[],
  formatCell: (v: unknown, point?: MeasureSeriesPoint) => string,
): React.ReactNode {
  if (series.length === 0) {
    return <Typography sx={{ fontSize: '0.625rem' }}>No data available.</Typography>;
  }
  return (
    <table style={{ width: '100%', fontSize: '0.75rem' }}>
      <thead>
        <tr>
          <th style={{ textAlign: 'left', padding: '4px 6px' }}>Label</th>
          <th style={{ textAlign: 'right', padding: '4px 6px' }}>Value</th>
        </tr>
      </thead>
      <tbody>
        {series.map((row) => (
          <tr key={row.name}>
            <td style={{ padding: '4px 6px' }}>{row.name}</td>
            <td style={{ textAlign: 'right', padding: '4px 6px' }}>{formatCell(row.value, row)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
