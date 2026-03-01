'use client';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import InsertChartOutlined from '@mui/icons-material/InsertChartOutlined';
import { useEffect, useRef, useState } from 'react';
import { ResponsiveContainer } from 'recharts';
import { ChartElement as ChartElementType } from '@/lib/types/layout';
import { evaluateMeasure } from '@/lib/api';
import { ApiError } from '@/lib/api/client';
import { useEditorStore } from '@/stores/editorStore';
import { useOrgId } from '@/context/OrgContext';
import {
  extractMeasureReportSeries,
  extractMeasureReportRows,
  MeasureSeriesPoint,
  MeasureReportRow,
} from '@/lib/measureData';
import { chartColors } from '@/lib/chartTheme';
import { expandNumericColumns } from './chartUtils';
import { buildSankeyFromRows } from './chartSankeyFunnel';
import { renderChart, ChartRenderContext } from './chartRenderers';

// ─── Style constants ─────────────────────────────────────────────────

const containerSx = {
  width: '100%',
  height: '100%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
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

const placeholderTextSx = { fontSize: '0.625rem' } as const;

const chartContainerSx = {
  width: '100%',
  height: '100%',
  padding: '4px',
  minWidth: 0,
  minHeight: 0,
  overflow: 'hidden',
} as const;

const MM_TO_PX = 96 / 25.4;
const DEFAULT_COLORS = chartColors.series;

// ─── Props ───────────────────────────────────────────────────────────

interface ChartElementProps {
  element: ChartElementType;
  dataOverride?: Array<{ name: string; value: number }>;
}

// ─── Component ───────────────────────────────────────────────────────

export function ChartElement({ element, dataOverride }: ChartElementProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const colors = element.colors || DEFAULT_COLORS;
  const zoom = useEditorStore((s) => s.zoom);
  const report = useEditorStore((s) => s.report);
  const reportScope = useEditorStore((s) => s.layout.reportScope);
  const runtimeParams = useEditorStore((s) => s.layout.runtimeParams);
  const globalOrgId = useOrgId();
  const orgIdsKey = (runtimeParams?.organizationIds || []).join('|');
  const cohortFiltersKey = JSON.stringify(runtimeParams?.cohortFilters || {});

  const [boundData, setBoundData] = useState<MeasureSeriesPoint[] | null>(null);
  const [boundRows, setBoundRows] = useState<MeasureReportRow[] | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  // ─── Data fetching ─────────────────────────────────────────────────

  const fetchMeasureData = async () => {
    const measureId = element.dataSource!.replace('Measure/', '');
    const periodStart =
      report?.period?.start || new Date().toISOString().split('T')[0];
    const periodEnd =
      report?.period?.end || new Date().toISOString().split('T')[0];
    const subject =
      reportScope === 'patient' ? runtimeParams?.subjectRef : undefined;
    const orgId =
      reportScope === 'organization'
        ? (runtimeParams?.organizationId || globalOrgId)
        : undefined;
    const orgIds =
      reportScope === 'organization' ? runtimeParams?.organizationIds : undefined;
    return evaluateMeasure(measureId, {
      periodStart,
      periodEnd,
      subject,
      orgId,
      orgIds,
      cohortFilters: runtimeParams?.cohortFilters,
    });
  };

  const handleLoadError = (error: unknown) => {
    const msg = error instanceof ApiError ? error.message : (error instanceof Error ? error.message : 'Failed to evaluate chart data');
    setErrorMessage(msg);
    setBoundData([]);
    setBoundRows([]);
  };

  useEffect(() => {
    if (!element.dataSource) return;
    const orgId =
      reportScope === 'organization'
        ? (runtimeParams?.organizationId || globalOrgId)
        : undefined;
    if (reportScope === 'organization' && !orgId) {
      setBoundData([]);
      setBoundRows([]);
      setErrorMessage('Select an organization in the toolbar (or header) to evaluate this measure.');
      return;
    }
    fetchMeasureData().then(result => {
      setBoundData(extractMeasureReportSeries(result as any));
      setBoundRows(extractMeasureReportRows(result as any));
      setErrorMessage(null);
    }).catch(error => handleLoadError(error));
  }, [
    element.dataSource,
    report?.period?.start,
    report?.period?.end,
    reportScope,
    runtimeParams?.subjectRef,
    runtimeParams?.organizationId,
    globalOrgId,
    orgIdsKey,
    cohortFiltersKey,
    runtimeParams?.refreshToken,
  ]);

  // ─── Container sizing ──────────────────────────────────────────────

  const measureAndClamp = (node: HTMLDivElement) => {
    const rect = node.getBoundingClientRect();
    const expectedW = element.w > 0 ? element.w * MM_TO_PX * zoom : 0;
    const expectedH = element.h > 0 ? element.h * MM_TO_PX * zoom : 0;
    let width = rect.width;
    let height = rect.height;
    if (Number.isFinite(expectedW) && expectedW > 0) {
      width = Math.min(width, expectedW);
    }
    if (Number.isFinite(expectedH) && expectedH > 0) {
      height = Math.min(height, expectedH);
    }
    setContainerSize({ width, height });
  };

  useEffect(() => {
    const node = chartContainerRef.current;
    if (!node) return;
    const updateSize = () => measureAndClamp(node);
    updateSize();
    const observer = new ResizeObserver(() => updateSize());
    observer.observe(node);
    return () => observer.disconnect();
  }, [element.h, element.w, zoom]);

  // ─── Derived data ──────────────────────────────────────────────────

  const resolvedDataSource = element.dataSource ? boundData ?? [] : element.data ?? [];
  const resolvedRows = element.dataSource ? boundRows ?? [] : element.data ?? [];
  const data = dataOverride ?? resolvedDataSource;
  const rows = dataOverride ?? resolvedRows;

  const expectedW = element.w > 0 ? element.w * MM_TO_PX * zoom : 0;
  const expectedH = element.h > 0 ? element.h * MM_TO_PX * zoom : 0;
  const containerPadding = 8;
  const measuredW = containerSize.width || expectedW;
  const measuredH = containerSize.height || expectedH;
  const boxPlotWidth = Math.max(0, measuredW - containerPadding);
  const boxPlotHeight = Math.max(0, measuredH - containerPadding);

  const shouldExpandNumeric =
    element.chartType !== 'boxPlot' &&
    element.xAxisKey === '__field' &&
    element.yAxisKey === '__value';
  const normalizedRows = shouldExpandNumeric
    ? expandNumericColumns(rows, element.fieldGroup)
    : rows;

  const derivedSankey =
    element.chartType === 'sankey'
      ? buildSankeyFromRows(normalizedRows as Array<Record<string, unknown>>)
      : null;

  const prefersRowData =
    element.chartType === 'scatter' ||
    element.chartType === 'composed' ||
    element.chartType === 'radar' ||
    element.chartType === 'pie' ||
    element.chartType === 'boxPlot' ||
    element.chartType === 'heatmap' ||
    element.chartType === 'bullet' ||
    Boolean(element.xAxisKey || element.yAxisKey);

  const resolvedData =
    element.multiSeries?.length || prefersRowData
      ? (normalizedRows as any[])
      : (data as any[]);

  // ─── Build render context ──────────────────────────────────────────

  const ctx: ChartRenderContext = {
    element,
    colors,
    containerSize,
    boxPlotWidth,
    boxPlotHeight,
    derivedSankey,
    normalizedRows: normalizedRows as Array<Record<string, unknown>>,
    resolvedData,
  };

  // ─── Render ────────────────────────────────────────────────────────

  if (errorMessage) {
    return (
      <Box sx={containerSx}>
        <Box sx={placeholderSx}>
          <InsertChartOutlined sx={{ fontSize: '32px' }} />
          <Typography sx={placeholderTextSx}>{errorMessage}</Typography>
        </Box>
      </Box>
    );
  }

  if (!hasData(element, data, normalizedRows, derivedSankey)) {
    return (
      <Box sx={containerSx}>
        <Box sx={placeholderSx}>
          <InsertChartOutlined sx={{ fontSize: '32px' }} />
          <Typography sx={placeholderTextSx}>
            {element.dataSource ? 'No data available.' : 'Select a data source in properties.'}
          </Typography>
        </Box>
      </Box>
    );
  }

  if (!element.chartType) {
    return (
      <Box sx={containerSx}>
        <Box sx={placeholderSx}>
          <InsertChartOutlined sx={{ fontSize: '32px' }} />
          <Typography sx={placeholderTextSx}>
            No chart type selected.
            <br />
            Configure in properties.
          </Typography>
        </Box>
      </Box>
    );
  }

  const isCustomChart =
    element.chartType === 'boxPlot' ||
    element.chartType === 'heatmap' ||
    element.chartType === 'bullet';
  const canRender = containerSize.width > 1 && containerSize.height > 1;
  const canRenderBoxPlot = boxPlotWidth > 1 && boxPlotHeight > 1;
  const renderedChart =
    element.chartType === 'boxPlot'
      ? canRenderBoxPlot ? renderChart(ctx) : null
      : canRender ? renderChart(ctx) : null;

  return (
    <Box sx={containerSx}>
      <Box sx={chartContainerSx} ref={chartContainerRef}>
        {!canRender ? (
          <Box sx={placeholderSx}>
            <Typography sx={placeholderTextSx}>Chart area is too small.</Typography>
          </Box>
        ) : isCustomChart ? (
          renderedChart || <div>Invalid chart type</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
            {renderedChart || <div>Invalid chart type</div>}
          </ResponsiveContainer>
        )}
      </Box>
    </Box>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────

function hasData(
  element: ChartElementType,
  data: any[],
  normalizedRows: any[],
  derivedSankey: { nodes: any[]; links: any[] } | null,
): boolean {
  if (element.chartType === 'sankey') {
    const sankey = element.sankey;
    if (sankey && sankey.nodes.length > 0 && sankey.links.length > 0) return true;
    if (derivedSankey && derivedSankey.nodes.length > 0 && derivedSankey.links.length > 0) return true;
  }
  return (data?.length || 0) > 0 || (normalizedRows?.length || 0) > 0;
}
