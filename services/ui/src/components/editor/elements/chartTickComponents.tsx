/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
'use client';

import { chartTheme } from '@/lib/chartTheme';
import { truncateLabel } from './chartUtils';

// ─── AngledTick ──────────────────────────────────────────────────────

interface TickProps {
  x?: number;
  y?: number;
  payload?: { value: string };
}

/**
 * Custom Recharts tick renderer: rotates text -45 degrees and
 * truncates long labels. Used on categorical X-axes.
 */
export function AngledTick(props: TickProps) {
  const { x = 0, y = 0, payload } = props;
  const label = truncateLabel(String(payload?.value ?? ''));
  return (
    <g transform={`translate(${x},${y})`}>
      <text
        x={0}
        y={0}
        dy={8}
        textAnchor="end"
        fill={chartTheme.axis.tick.fill}
        fontSize={10}
        transform="rotate(-45)"
      >
        {label}
      </text>
    </g>
  );
}

// ─── TruncatedYTick ──────────────────────────────────────────────────

/**
 * Custom Recharts tick renderer for horizontal bars:
 * truncates long Y-axis labels.
 */
export function TruncatedYTick(props: TickProps) {
  const { x = 0, y = 0, payload } = props;
  const label = truncateLabel(String(payload?.value ?? ''), 32);
  return (
    <g transform={`translate(${x},${y})`}>
      <text
        x={0}
        y={0}
        dy={4}
        textAnchor="end"
        fill={chartTheme.axis.tick.fill}
        fontSize={10}
      >
        {label}
      </text>
    </g>
  );
}
