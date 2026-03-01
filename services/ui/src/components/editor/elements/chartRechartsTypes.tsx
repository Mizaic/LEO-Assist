'use client';

import React from 'react';
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ScatterChart,
  Scatter,
  ComposedChart,
  RadialBarChart,
  RadialBar,
  ReferenceArea,
  ReferenceDot,
  Sankey,
  FunnelChart,
  Funnel,
  LabelList,
} from 'recharts';
import { ChartElement as ChartElementType } from '@/lib/types/layout';
import { chartTheme, getSeriesColor } from '@/lib/chartTheme';
import { SankeyNode, FunnelLabel, SankeyData } from './chartSankeyFunnel';
import { AngledTick, TruncatedYTick } from './chartTickComponents';

// ─── Shared legend props ─────────────────────────────────────────────

export const LEGEND_PROPS = {
  height: 14,
  iconSize: 6,
  wrapperStyle: {
    fontSize: 10,
    lineHeight: '10px',
    marginTop: 8,
    paddingTop: 6,
    paddingBottom: 2,
  },
} as const;

// ─── Bar chart ───────────────────────────────────────────────────────

export function renderBarChart(
  commonProps: any,
  element: ChartElementType,
  resolvedData: any[],
  xKey: string,
  yKey: string,
  colors: string[],
  tickEl: any,
  xAxisHeight: number,
): React.ReactNode {
  return (
    <BarChart {...commonProps}>
      {element.showGrid && <CartesianGrid strokeDasharray={chartTheme.grid.strokeDasharray} stroke={chartTheme.grid.stroke} />}
      <XAxis dataKey={xKey} tick={tickEl} interval={0} height={xAxisHeight} />
      <YAxis tick={{ fontSize: 10 }} />
      <Tooltip />
      {element.showLegend && <Legend {...LEGEND_PROPS} />}
      {element.multiSeries?.length ? (
        element.multiSeries.map((s, i) => (
          <Bar key={s.dataKey} dataKey={s.dataKey} name={s.name || s.dataKey} fill={s.color || getSeriesColor(i)} radius={chartTheme.bar.radius} maxBarSize={chartTheme.bar.maxBarSize} />
        ))
      ) : (
        <Bar dataKey={yKey} fill={colors[0]}>
          {resolvedData.map((_, i) => <Cell key={`cell-${i}`} fill={colors[i % colors.length]} />)}
        </Bar>
      )}
    </BarChart>
  );
}

// ─── Horizontal bar chart ────────────────────────────────────────────

export function renderHorizontalBar(
  commonProps: any,
  element: ChartElementType,
  resolvedData: any[],
  xKey: string,
  yKey: string,
  colors: string[],
  yAxisWidth: number,
): React.ReactNode {
  return (
    <BarChart {...commonProps} layout="vertical">
      {element.showGrid && <CartesianGrid strokeDasharray={chartTheme.grid.strokeDasharray} stroke={chartTheme.grid.stroke} />}
      <XAxis type="number" tick={{ fontSize: 10 }} />
      <YAxis dataKey={xKey} type="category" tick={<TruncatedYTick />} width={yAxisWidth} interval={0} />
      <Tooltip />
      {element.showLegend && <Legend {...LEGEND_PROPS} />}
      {element.multiSeries?.length ? (
        element.multiSeries.map((s, i) => (
          <Bar key={s.dataKey} dataKey={s.dataKey} name={s.name || s.dataKey} fill={s.color || getSeriesColor(i)} radius={chartTheme.bar.radius} maxBarSize={chartTheme.bar.maxBarSize} />
        ))
      ) : (
        <Bar dataKey={yKey} fill={colors[0]}>
          {resolvedData.map((_, i) => <Cell key={`cell-${i}`} fill={colors[i % colors.length]} />)}
        </Bar>
      )}
    </BarChart>
  );
}

// ─── Pie chart ───────────────────────────────────────────────────────

export function renderPieChart(
  element: ChartElementType,
  resolvedData: any[],
  xKey: string,
  yKey: string,
  colors: string[],
): React.ReactNode {
  return (
    <PieChart>
      <Pie data={resolvedData} cx="50%" cy="50%" innerRadius={0} outerRadius="80%" fill={colors[0]} dataKey={yKey} nameKey={xKey} label={{ fontSize: 10 }}>
        {resolvedData.map((_, i) => <Cell key={`cell-${i}`} fill={colors[i % colors.length]} />)}
      </Pie>
      <Tooltip />
      {element.showLegend && <Legend {...LEGEND_PROPS} />}
    </PieChart>
  );
}

// ─── Line chart ──────────────────────────────────────────────────────

export function renderLineChart(
  commonProps: any,
  element: ChartElementType,
  resolvedData: any[],
  xKey: string,
  yKey: string,
  colors: string[],
  tickEl: any,
  xAxisHeight: number,
): React.ReactNode {
  return (
    <LineChart {...commonProps}>
      {element.showGrid && <CartesianGrid strokeDasharray={chartTheme.grid.strokeDasharray} stroke={chartTheme.grid.stroke} />}
      <XAxis dataKey={xKey} tick={tickEl} interval={0} height={xAxisHeight} />
      <YAxis tick={{ fontSize: 10 }} />
      <Tooltip />
      {element.showLegend && <Legend {...LEGEND_PROPS} />}
      {element.shadedAreas?.map((a, i) => <ReferenceArea key={`area-${i}`} x1={a.start} x2={a.end} fill={a.color || colors[0]} fillOpacity={0.15} />)}
      {element.multiSeries?.length ? (
        element.multiSeries.map((s, i) => (
          <Line key={s.dataKey} type="monotone" dataKey={s.dataKey} name={s.name || s.dataKey} stroke={s.color || getSeriesColor(i)} strokeWidth={chartTheme.line.strokeWidth} dot={{ r: chartTheme.line.dot.r }} activeDot={{ r: chartTheme.line.activeDot.r }} />
        ))
      ) : (
        <Line type="monotone" dataKey={yKey} stroke={colors[0]} strokeWidth={chartTheme.line.strokeWidth} dot={{ r: chartTheme.line.dot.r }} activeDot={{ r: chartTheme.line.activeDot.r }} />
      )}
      {element.highlightedPoints?.map((pt, i) => {
        const match = resolvedData.find((r) => r[xKey] === pt.key) as Record<string, unknown> | undefined;
        const yVal = match ? Number(match[yKey]) : undefined;
        if (yVal == null || Number.isNaN(yVal)) return null;
        return <ReferenceDot key={`hl-${i}`} x={pt.key} y={yVal} r={6} fill={pt.color || colors[0]} stroke="#fff" label={pt.label ? { value: pt.label, position: 'top' } : undefined} />;
      })}
    </LineChart>
  );
}

// ─── Area chart ──────────────────────────────────────────────────────

export function renderAreaChart(
  commonProps: any,
  element: ChartElementType,
  resolvedData: any[],
  xKey: string,
  yKey: string,
  colors: string[],
  tickEl: any,
  xAxisHeight: number,
): React.ReactNode {
  return (
    <AreaChart {...commonProps}>
      {element.showGrid && <CartesianGrid strokeDasharray={chartTheme.grid.strokeDasharray} stroke={chartTheme.grid.stroke} />}
      <XAxis dataKey={xKey} tick={tickEl} interval={0} height={xAxisHeight} />
      <YAxis tick={{ fontSize: 10 }} />
      <Tooltip />
      {element.showLegend && <Legend {...LEGEND_PROPS} />}
      {element.shadedAreas?.map((a, i) => <ReferenceArea key={`area-${i}`} x1={a.start} x2={a.end} fill={a.color || colors[0]} fillOpacity={0.15} />)}
      {element.multiSeries?.length ? (
        element.multiSeries.map((s, i) => (
          <Area key={s.dataKey} type="monotone" dataKey={s.dataKey} name={s.name || s.dataKey} stroke={s.color || getSeriesColor(i)} fill={s.color || getSeriesColor(i)} fillOpacity={chartTheme.area.fillOpacity} />
        ))
      ) : (
        <Area type="monotone" dataKey={yKey} stroke={colors[0]} fill={colors[0]} fillOpacity={chartTheme.area.fillOpacity} />
      )}
    </AreaChart>
  );
}

// ─── Radar chart ─────────────────────────────────────────────────────

export function renderRadarChart(
  element: ChartElementType,
  resolvedData: any[],
  xKey: string,
  allNumericKeys: string[],
): React.ReactNode {
  const radarSeries =
    element.multiSeries?.length
      ? element.multiSeries
      : element.composedSeries?.length
        ? element.composedSeries
        : undefined;
  const numericKeys = radarSeries?.length
    ? radarSeries.map((s) => s.dataKey)
    : allNumericKeys.slice(0, 2);
  return (
    <RadarChart data={resolvedData}>
      <PolarGrid />
      <PolarAngleAxis dataKey={xKey} />
      <PolarRadiusAxis />
      {numericKeys.map((k, i) => (
        <Radar key={k} dataKey={k} stroke={getSeriesColor(i)} fill={getSeriesColor(i)} fillOpacity={0.2} name={radarSeries?.[i]?.name || k} />
      ))}
      {element.showLegend && <Legend {...LEGEND_PROPS} />}
      <Tooltip />
    </RadarChart>
  );
}

// ─── Radial bar chart ────────────────────────────────────────────────

export function renderRadialBar(
  element: ChartElementType,
  resolvedData: any[],
  yKey: string,
  colors: string[],
): React.ReactNode {
  return (
    <RadialBarChart data={resolvedData} innerRadius="50%" outerRadius="100%" barSize={12}>
      <RadialBar dataKey={yKey} background cornerRadius={6} fill={colors[0]} />
      {element.showLegend && <Legend {...LEGEND_PROPS} />}
      <Tooltip />
    </RadialBarChart>
  );
}

// ─── Scatter chart ───────────────────────────────────────────────────

export function renderScatterChart(
  commonProps: any,
  element: ChartElementType,
  resolvedData: any[],
  xKey: string,
  yKey: string,
  colors: string[],
  numericKeys: string[],
): React.ReactNode {
  const scatterX = element.xAxisKey || numericKeys[0] || xKey;
  const scatterY = element.yAxisKey || numericKeys[1] || yKey;
  return (
    <ScatterChart {...commonProps}>
      {element.showGrid && <CartesianGrid strokeDasharray={chartTheme.grid.strokeDasharray} stroke={chartTheme.grid.stroke} />}
      <XAxis dataKey={scatterX} type="number" />
      <YAxis dataKey={scatterY} type="number" />
      <Tooltip />
      {element.showLegend && <Legend {...LEGEND_PROPS} />}
      {element.multiSeries?.length ? (
        element.multiSeries.map((s, i) => <Scatter key={s.dataKey} name={s.name || s.dataKey} data={resolvedData} fill={s.color || getSeriesColor(i)} dataKey={s.dataKey} />)
      ) : (
        <Scatter data={resolvedData} fill={colors[0]} />
      )}
    </ScatterChart>
  );
}

// ─── Composed chart ──────────────────────────────────────────────────

export function renderComposedChart(
  commonProps: any,
  element: ChartElementType,
  resolvedData: any[],
  xKey: string,
  yKey: string,
  colors: string[],
  tickEl: any,
  xAxisHeight: number,
): React.ReactNode {
  const composedSeries =
    element.composedSeries?.length
      ? element.composedSeries
      : element.multiSeries?.length
        ? element.multiSeries
        : [{ dataKey: yKey, type: 'bar' as const }];
  return (
    <ComposedChart {...commonProps}>
      {element.showGrid && <CartesianGrid strokeDasharray={chartTheme.grid.strokeDasharray} stroke={chartTheme.grid.stroke} />}
      <XAxis dataKey={xKey} tick={tickEl} interval={0} height={xAxisHeight} />
      <YAxis tick={{ fontSize: 10 }} />
      <Tooltip />
      {element.showLegend && <Legend {...LEGEND_PROPS} />}
      {element.shadedAreas?.map((a, i) => <ReferenceArea key={`area-${i}`} x1={a.start} x2={a.end} fill={a.color || colors[0]} fillOpacity={0.15} />)}
      {composedSeries.map((s, i) => renderComposedSeries(s, i))}
    </ComposedChart>
  );
}

function renderComposedSeries(
  series: { dataKey: string; name?: string; color?: string; type?: string },
  index: number,
): React.ReactNode {
  const color = series.color || getSeriesColor(index);
  const type = series.type || (index === 0 ? 'bar' : 'line');
  if (type === 'area') {
    return <Area key={series.dataKey} type="monotone" dataKey={series.dataKey} name={series.name || series.dataKey} stroke={color} fill={color} fillOpacity={chartTheme.area.fillOpacity} />;
  }
  if (type === 'line') {
    return <Line key={series.dataKey} type="monotone" dataKey={series.dataKey} name={series.name || series.dataKey} stroke={color} strokeWidth={chartTheme.line.strokeWidth} />;
  }
  return <Bar key={series.dataKey} dataKey={series.dataKey} name={series.name || series.dataKey} fill={color} radius={chartTheme.bar.radius} maxBarSize={chartTheme.bar.maxBarSize} />;
}

// ─── Funnel chart ────────────────────────────────────────────────────

export function renderFunnelChart(
  resolvedData: any[],
  xKey: string,
  yKey: string,
): React.ReactNode {
  return (
    <FunnelChart margin={{ top: 8, right: 160, left: 20, bottom: 8 }}>
      <Tooltip />
      <Funnel dataKey={yKey} data={resolvedData} isAnimationActive={false} stroke="#fff">
        <LabelList
          dataKey={xKey}
          content={(props) => {
            const p = props as Record<string, unknown>;
            return <FunnelLabel x={Number(p.x) || 0} y={Number(p.y) || 0} width={Number(p.width) || 0} height={Number(p.height) || 0} value={String(p.value ?? '')} payload={p.payload as Record<string, unknown>} valueKey={yKey} />;
          }}
        />
      </Funnel>
    </FunnelChart>
  );
}

// ─── Sankey chart ────────────────────────────────────────────────────

export function renderSankeyChart(
  element: ChartElementType,
  derivedSankey: SankeyData | null,
): React.ReactNode {
  const sankeyData = element.sankey || derivedSankey || { nodes: [], links: [] };
  // Cast to recharts SankeyData — our SankeyLink allows string | number for source/target
  // but the buildSankeyFromRows helper resolves them to numeric indices at runtime.
  const rechartsData = sankeyData as { nodes: { name: string }[]; links: { source: number; target: number; value: number }[] };
  return (
    <Sankey
      data={rechartsData}
      nodePadding={chartTheme.sankey.nodePadding}
      nodeWidth={chartTheme.sankey.nodeThickness}
      linkCurvature={0.5}
      node={<SankeyNode />}
    >
      <Tooltip />
    </Sankey>
  );
}
