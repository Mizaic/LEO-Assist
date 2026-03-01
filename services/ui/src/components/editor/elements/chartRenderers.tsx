'use client';

import React from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { ChartElement as ChartElementType } from '@/lib/types/layout';
import { chartTheme } from '@/lib/chartTheme';
import {
  truncateLabel,
  numberFromRow,
  clampNumber,
  parseRangesFromRow,
  applyPreferredSort,
} from './chartUtils';
import { buildBoxPlotPoints, BoxPlotPoint } from './chartBoxPlot';
import { SankeyData } from './chartSankeyFunnel';
import { AngledTick } from './chartTickComponents';
import {
  renderBarChart,
  renderHorizontalBar,
  renderPieChart,
  renderLineChart,
  renderAreaChart,
  renderRadarChart,
  renderRadialBar,
  renderScatterChart,
  renderComposedChart,
  renderFunnelChart,
  renderSankeyChart,
} from './chartRechartsTypes';

// ─── Style constants ─────────────────────────────────────────────────

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

// ─── Shared context passed from ChartElement ─────────────────────────

export interface ChartRenderContext {
  element: ChartElementType;
  colors: string[];
  containerSize: { width: number; height: number };
  boxPlotWidth: number;
  boxPlotHeight: number;
  derivedSankey: SankeyData | null;
  normalizedRows: Array<Record<string, unknown>>;
  resolvedData: any[];
}

// ─── Dataset helpers ─────────────────────────────────────────────────

function getDefaultKeys(
  dataset: Array<Record<string, unknown>>,
  element: ChartElementType,
): { xKey: string; yKey: string } {
  const sample = dataset[0] || {};
  const keys = Object.keys(sample);
  const xKey =
    element.xAxisKey || keys.find((k) => typeof sample[k] === 'string') || 'name';
  const yKey =
    element.yAxisKey || keys.find((k) => typeof sample[k] === 'number') || 'value';
  return { xKey, yKey };
}

function getNumericKeys(dataset: Array<Record<string, unknown>>): string[] {
  const sample = dataset[0] || {};
  return Object.keys(sample).filter((k) => typeof sample[k] === 'number');
}

function getMaxLabelLength(
  dataset: Array<Record<string, unknown>>,
  key: string,
): number {
  if (!dataset.length) return 0;
  return dataset.reduce((max, row) => {
    const label = row[key] == null ? '' : String(row[key]);
    return Math.max(max, label.length);
  }, 0);
}

function isAngledChartType(type?: string): boolean {
  return type === 'bar' || type === 'composed' || type === 'line' || type === 'area';
}

// ─── renderBoxPlot (custom SVG) ──────────────────────────────────────

export function renderBoxPlot(ctx: ChartRenderContext): React.ReactNode {
  const { element, colors, containerSize } = ctx;
  const svgW = (containerSize.width > 0 ? containerSize.width : ctx.boxPlotWidth) - 8;
  const svgH = (containerSize.height > 0 ? containerSize.height : ctx.boxPlotHeight) - 8;
  if (svgW <= 0 || svgH <= 0) return null;

  const points = buildBoxPlotPoints(
    ctx.resolvedData as Array<Record<string, unknown>>,
    element.xAxisKey,
    element.yAxisKey,
  );
  if (!points.length) {
    return (
      <Box sx={placeholderSx}>
        <Typography sx={placeholderTextSx}>
          Box plot requires numeric values (min/q1/median/q3/max) or a value
          field to derive quartiles.
        </Typography>
      </Box>
    );
  }

  return renderBoxPlotSvg(points, svgW, svgH, colors);
}

function renderBoxPlotSvg(
  points: BoxPlotPoint[],
  svgW: number,
  svgH: number,
  colors: string[],
): React.ReactNode {
  const minVal = Math.min(...points.map((p) => p.min));
  const maxVal = Math.max(...points.map((p) => p.max));
  const domainMin = minVal === maxVal ? minVal - 1 : minVal;
  const domainMax = minVal === maxVal ? maxVal + 1 : maxVal;

  const labelWidth = 70;
  const paddingRight = 10;
  const plotWidth = Math.max(0, svgW - labelWidth - paddingRight);
  const rowHeight = Math.min(50, Math.max(28, svgH * 0.4));
  const whiskerH = rowHeight * 0.6;
  const dataHeight = points.length * rowHeight;
  const contentHeight = dataHeight + 22;
  const yOffset = Math.max(0, (svgH - contentHeight) / 2);
  const scale = (v: number) =>
    labelWidth + ((v - domainMin) / (domainMax - domainMin || 1)) * plotWidth;
  const axisY = yOffset + dataHeight + 4;
  const ticks = buildTicks(domainMin, domainMax, 5);

  return (
    <svg width={svgW} height={svgH} style={{ display: 'block' }}>
      <g fontFamily={chartTheme.fonts.family} fontSize={10} fill={chartTheme.axis.tick.fill}>
        {points.map((pt, idx) =>
          renderSingleBox(pt, idx, yOffset, rowHeight, whiskerH, scale, colors),
        )}
        <line
          x1={labelWidth}
          x2={labelWidth + plotWidth}
          y1={axisY}
          y2={axisY}
          stroke={chartTheme.axis.stroke}
          strokeWidth={chartTheme.axis.strokeWidth}
        />
        {ticks.map((tick, i) => (
          <g key={`tick-${i}`}>
            <line
              x1={scale(tick)}
              x2={scale(tick)}
              y1={axisY}
              y2={axisY + 4}
              stroke={chartTheme.axis.stroke}
              strokeWidth={chartTheme.axis.strokeWidth}
            />
            <text x={scale(tick)} y={axisY + 15} textAnchor="middle" fill={chartTheme.axis.tick.fill} fontSize={9}>
              {Math.round(tick)}
            </text>
          </g>
        ))}
      </g>
    </svg>
  );
}

function buildTicks(min: number, max: number, count: number): number[] {
  return Array.from({ length: count }, (_, i) => {
    if (count === 1) return min;
    return min + (i / (count - 1)) * (max - min);
  });
}

function renderSingleBox(
  pt: BoxPlotPoint,
  idx: number,
  yOffset: number,
  rowHeight: number,
  whiskerH: number,
  scale: (v: number) => number,
  colors: string[],
): React.ReactNode {
  const centerY = yOffset + rowHeight * idx + rowHeight / 2;
  const yTop = centerY - whiskerH / 2;
  const yBottom = centerY + whiskerH / 2;
  const meanX = pt.mean != null ? scale(pt.mean) : null;

  return (
    <g key={`${pt.label}-${idx}`}>
      <text x={64} y={centerY + 4} textAnchor="end">
        {truncateLabel(pt.label, 20)}
      </text>
      <line x1={scale(pt.min)} x2={scale(pt.max)} y1={centerY} y2={centerY} stroke="#94A3B8" />
      <line x1={scale(pt.min)} x2={scale(pt.min)} y1={yTop} y2={yBottom} stroke="#94A3B8" />
      <line x1={scale(pt.max)} x2={scale(pt.max)} y1={yTop} y2={yBottom} stroke="#94A3B8" />
      <rect
        x={scale(pt.q1)}
        y={yTop}
        width={Math.max(1, scale(pt.q3) - scale(pt.q1))}
        height={whiskerH}
        fill={colors[0]}
        opacity={0.35}
        stroke={colors[0]}
      />
      <line x1={scale(pt.median)} x2={scale(pt.median)} y1={yTop} y2={yBottom} stroke={colors[0]} strokeWidth={2} />
      {meanX != null && <circle cx={meanX} cy={centerY} r={3} fill={colors[1] || colors[0]} />}
    </g>
  );
}

// ─── renderHeatmap (custom SVG) ──────────────────────────────────────

export function renderHeatmap(ctx: ChartRenderContext): React.ReactNode {
  const { element, colors, containerSize } = ctx;
  const { width, height } = containerSize;
  if (width <= 0 || height <= 0) return null;

  const dataset = ctx.resolvedData as Array<Record<string, unknown>>;
  const xKey = element.xAxisKey || 'x';
  const yKey = element.seriesKey || 'y';
  const valueKey = element.yAxisKey || 'value';

  const xVals = [...new Set(dataset.map((r) => String(r[xKey] ?? '')))].filter(Boolean);
  const yVals = [...new Set(dataset.map((r) => String(r[yKey] ?? '')))].filter(Boolean);
  if (!xVals.length || !yVals.length) return null;

  const values = dataset.map((r) => numberFromRow(r, valueKey)).filter((v): v is number => v != null);
  const minV = values.length ? Math.min(...values) : 0;
  const maxV = values.length ? Math.max(...values) : 1;

  const left = 140;
  const top = 18;
  const gw = Math.max(0, width - left - 16);
  const gh = Math.max(0, height - top - 40);
  const cw = gw / xVals.length;
  const ch = gh / yVals.length;

  const opacityFor = (v: number) => {
    if (maxV === minV) return 0.6;
    return clampNumber(0.15 + ((v - minV) / (maxV - minV)) * 0.75, 0.15, 0.9);
  };

  return (
    <svg width={width} height={height}>
      <g fontFamily={chartTheme.fonts.family} fontSize={10} fill={chartTheme.axis.tick.fill}>
        {yVals.map((label, ri) => (
          <text key={`y-${label}`} x={left - 8} y={top + ri * ch + ch / 2 + 4} textAnchor="end">
            {truncateLabel(label, 24)}
          </text>
        ))}
        {xVals.map((label, ci) => (
          <text key={`x-${label}`} x={left + ci * cw + cw / 2} y={height - 12} textAnchor="middle">
            {truncateLabel(label, 18)}
          </text>
        ))}
      </g>
      {dataset.map((row, i) => {
        const ci = xVals.indexOf(String(row[xKey] ?? ''));
        const ri = yVals.indexOf(String(row[yKey] ?? ''));
        if (ci < 0 || ri < 0) return null;
        return (
          <rect
            key={`cell-${i}`}
            x={left + ci * cw}
            y={top + ri * ch}
            width={cw}
            height={ch}
            fill={colors[0]}
            opacity={opacityFor(numberFromRow(row, valueKey) ?? 0)}
            stroke="#E2E8F0"
          />
        );
      })}
    </svg>
  );
}

// ─── renderBullet (custom SVG) ───────────────────────────────────────

const BAND_COLORS = [
  'rgba(148, 163, 184, 0.35)',
  'rgba(59, 130, 246, 0.25)',
  'rgba(16, 185, 129, 0.25)',
];

export function renderBullet(ctx: ChartRenderContext): React.ReactNode {
  const { element, colors, containerSize } = ctx;
  const { width, height } = containerSize;
  if (width <= 0 || height <= 0) return null;

  const dataset = ctx.resolvedData as Array<Record<string, unknown>>;
  if (!dataset.length) return null;

  const labelKey = element.xAxisKey || 'label';
  const valueKey = element.yAxisKey || 'value';
  const targetKey = element.targetKey || 'target';
  const left = 140;
  const topPad = 12;
  const bottomPad = 12;
  const rowH = Math.max(36, Math.min(56, (height - topPad - bottomPad) / dataset.length));
  const plotW = Math.max(0, width - left - 20);

  return (
    <svg width={width} height={height}>
      <g fontFamily={chartTheme.fonts.family} fontSize={10} fill={chartTheme.axis.tick.fill}>
        {dataset.map((row, i) =>
          renderBulletRow(row, i, { labelKey, valueKey, targetKey, left, topPad, rowH, plotW, colors, element }),
        )}
      </g>
    </svg>
  );
}

interface BulletRowOpts {
  labelKey: string;
  valueKey: string;
  targetKey: string;
  left: number;
  topPad: number;
  rowH: number;
  plotW: number;
  colors: string[];
  element: ChartElementType;
}

function renderBulletRow(
  row: Record<string, unknown>,
  index: number,
  opts: BulletRowOpts,
): React.ReactNode {
  const { labelKey, valueKey, targetKey, left, topPad, rowH, plotW, colors, element } = opts;
  const label = row[labelKey] != null ? String(row[labelKey]) : `Series ${index + 1}`;
  const value = numberFromRow(row, valueKey) ?? 0;
  const target = numberFromRow(row, targetKey);
  const ranges = parseRangesFromRow(row, element.rangeKeys);
  const sortedRanges = ranges.length ? [...ranges].sort((a, b) => a - b) : [28, 62];
  const maxVal = Math.max(value, target ?? 0, ...sortedRanges);
  const rowTop = topPad + index * rowH;
  const centerY = rowTop + rowH / 2;
  const barH = rowH * 0.35;
  const scale = (v: number) => left + (v / (maxVal || 1)) * plotW;
  const bandStops = [0, ...sortedRanges, maxVal];

  return (
    <g key={`bullet-${index}`}>
      <text x={left - 8} y={centerY + 4} textAnchor="end">
        {truncateLabel(label, 24)}
      </text>
      {bandStops.slice(0, -1).map((start, bi) => (
        <rect
          key={`band-${index}-${bi}`}
          x={scale(start)}
          y={centerY - barH / 2}
          width={Math.max(1, scale(bandStops[bi + 1]) - scale(start))}
          height={barH}
          fill={BAND_COLORS[bi] || BAND_COLORS[BAND_COLORS.length - 1]}
        />
      ))}
      <rect x={left} y={centerY - barH / 4} width={Math.max(1, scale(value) - left)} height={barH / 2} fill={colors[0]} />
      {target != null && (
        <line
          x1={scale(target)}
          x2={scale(target)}
          y1={centerY - barH / 2 - 4}
          y2={centerY + barH / 2 + 4}
          stroke={colors[1] || colors[0]}
          strokeWidth={2}
        />
      )}
    </g>
  );
}

// ─── renderChart (main switch) ───────────────────────────────────────

export function renderChart(ctx: ChartRenderContext): React.ReactNode {
  const { element, colors } = ctx;
  const resolvedData = ctx.resolvedData as any[];
  const { xKey, yKey } = getDefaultKeys(resolvedData, element);
  const sortedData = applyPreferredSort(resolvedData, xKey);

  const needsAngled = isAngledChartType(element.chartType);
  const maxLabelLen = getMaxLabelLength(resolvedData, xKey);
  const shouldAngle = needsAngled && maxLabelLen > 12;
  const xAxisHeight = shouldAngle ? 56 : 24;
  const bottomMargin = shouldAngle ? 56 : 20;
  const yAxisWidth = Math.min(160, Math.max(60, maxLabelLen * 6));
  const legendPad = element.showLegend ? 18 : 0;

  const commonProps = {
    data: sortedData,
    margin: {
      top: 10,
      right: 10,
      left: element.chartType === 'horizontalBar' ? 16 : 0,
      bottom: (needsAngled ? bottomMargin : 10) + legendPad,
    },
  };

  const tickEl = shouldAngle ? <AngledTick /> : { fontSize: 10 };
  const numericKeys = getNumericKeys(resolvedData);

  switch (element.chartType) {
    case 'boxPlot':
      return renderBoxPlot(ctx);
    case 'bar':
      return renderBarChart(commonProps, element, resolvedData, xKey, yKey, colors, tickEl, xAxisHeight);
    case 'horizontalBar':
      return renderHorizontalBar(commonProps, element, resolvedData, xKey, yKey, colors, yAxisWidth);
    case 'pie':
      return renderPieChart(element, resolvedData, xKey, yKey, colors);
    case 'line':
      return renderLineChart(commonProps, element, resolvedData, xKey, yKey, colors, tickEl, xAxisHeight);
    case 'area':
      return renderAreaChart(commonProps, element, resolvedData, xKey, yKey, colors, tickEl, xAxisHeight);
    case 'radar':
      return renderRadarChart(element, resolvedData, xKey, numericKeys);
    case 'radialBar':
      return renderRadialBar(element, resolvedData, yKey, colors);
    case 'scatter':
      return renderScatterChart(commonProps, element, resolvedData, xKey, yKey, colors, numericKeys);
    case 'composed':
      return renderComposedChart(commonProps, element, resolvedData, xKey, yKey, colors, tickEl, xAxisHeight);
    case 'funnel':
      return renderFunnelChart(resolvedData, xKey, yKey);
    case 'heatmap':
      return renderHeatmap(ctx);
    case 'bullet':
      return renderBullet(ctx);
    case 'sankey':
      return renderSankeyChart(element, ctx.derivedSankey);
    default:
      return null;
  }
}
