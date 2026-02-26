'use client';

import { chartTheme, getSeriesColor } from '@/lib/chartTheme';
import {
  truncateLabel,
  formatValue,
  findKeyByCandidates,
  numberFromRow,
} from './chartUtils';

// ─── buildSankeyFromRows ─────────────────────────────────────────────

const SOURCE_CANDIDATES = ['source', 'from', 'comorbidity', 'comorbidity_name'];
const TARGET_CANDIDATES = ['target', 'to', 'cancer_type', 'cancerType'];
const VALUE_CANDIDATES = ['value', 'count', 'patient_count', 'patients', 'total'];

export interface SankeyData {
  nodes: Array<{ name: string }>;
  links: Array<{ source: number; target: number; value: number }>;
}

export function buildSankeyFromRows(
  rows: Array<Record<string, unknown>>,
): SankeyData {
  if (!rows.length) return { nodes: [], links: [] };

  const sample = rows[0] || {};
  const sourceKey = findKeyByCandidates(sample, SOURCE_CANDIDATES);
  const targetKey = findKeyByCandidates(sample, TARGET_CANDIDATES);
  const valueKey = findKeyByCandidates(sample, VALUE_CANDIDATES);
  if (!sourceKey || !targetKey || !valueKey) return { nodes: [], links: [] };

  const nodeIndex = new Map<string, number>();
  const nodes: Array<{ name: string }> = [];
  const links: Array<{ source: number; target: number; value: number }> = [];

  rows.forEach((row) => {
    const sourceLabel = row[sourceKey] != null ? String(row[sourceKey]) : '';
    const targetLabel = row[targetKey] != null ? String(row[targetKey]) : '';
    const value = numberFromRow(row, valueKey);
    if (!sourceLabel || !targetLabel || value == null) return;

    const source = resolveNodeIndex(nodeIndex, nodes, sourceLabel);
    const target = resolveNodeIndex(nodeIndex, nodes, targetLabel);
    links.push({ source, target, value });
  });

  return { nodes, links };
}

function resolveNodeIndex(
  index: Map<string, number>,
  nodes: Array<{ name: string }>,
  label: string,
): number {
  let idx = index.get(label);
  if (idx != null) return idx;
  idx = nodes.length;
  index.set(label, idx);
  nodes.push({ name: label });
  return idx;
}

// ─── SankeyNode SVG component ────────────────────────────────────────

interface SankeyNodeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  index?: number;
  payload?: { name?: string; depth?: number; index?: number };
}

export function SankeyNode(props: SankeyNodeProps) {
  const { x = 0, y = 0, width = 0, height = 0, index = 0, payload } = props;
  const depth = payload?.depth ?? 0;
  const label = truncateLabel(String(payload?.name ?? ''), 28);
  const fill = getSeriesColor(payload?.index ?? index);
  const isLeft = depth === 0;
  const textX = isLeft ? x + width + 6 : x - 6;
  const textAnchor = isLeft ? 'start' : 'end';

  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={fill} />
      <text
        x={textX}
        y={y + height / 2}
        dy={4}
        textAnchor={textAnchor}
        fill={chartTheme.axis.tick.fill}
        fontSize={10}
      >
        {label}
      </text>
    </g>
  );
}

// ─── FunnelLabel SVG component ───────────────────────────────────────

interface FunnelLabelProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  value?: string;
  payload?: Record<string, unknown>;
  valueKey?: string;
}

export function FunnelLabel(props: FunnelLabelProps) {
  const { x = 0, y = 0, width = 0, height = 0, value, payload, valueKey } = props;
  const labelText = truncateLabel(String(value ?? ''), 28);
  if (!labelText) return null;

  const rawValue = valueKey ? payload?.[valueKey] : undefined;
  const formattedValue = formatValue(rawValue);
  const label = formattedValue ? `${labelText} - ${formattedValue}` : labelText;

  const fontSize = 12;
  const paddingX = 6;
  const paddingY = 4;
  const labelX = x + width + 14;
  const labelY = y + height / 2;
  const estimatedWidth = Math.min(240, Math.max(60, label.length * 6.5));

  return (
    <g>
      <line
        x1={x + width + 2}
        x2={labelX - 6}
        y1={labelY}
        y2={labelY}
        stroke="#E0E0E0"
        strokeWidth={1}
      />
      <rect
        x={labelX - paddingX}
        y={labelY - fontSize / 2 - paddingY}
        width={estimatedWidth + paddingX * 2}
        height={fontSize + paddingY * 2}
        fill="#FFFFFF"
        opacity={0.95}
        rx={3}
      />
      <text
        x={labelX}
        y={labelY}
        dy={fontSize / 3}
        fontSize={fontSize}
        fontFamily={chartTheme.fonts.family}
        fill={chartTheme.axis.tick.fill}
      >
        {label}
      </text>
    </g>
  );
}
