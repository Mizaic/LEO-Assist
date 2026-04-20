/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import { CLOSED_STATUSES } from "@/lib/episodeStatus";
import {
  cancerTypeOrderIndex,
  getCancerTypeLabel,
  normaliseCancerType,
} from "@/lib/cancerTypes";

interface DataItem {
  condition_type: string;
  status: string;
  count: number;
}

// Source of truth: libs/episodes/status.py mirrored at lib/episodeStatus.ts.
const TERMINAL = CLOSED_STATUSES;

// #0D7C6F passes WCAG 3:1 against white and light-grey backgrounds
const COLOUR_OPEN = "#0D7C6F";
const COLOUR_CLOSED = "#1E3A8A";

// All cancer-type values are coerced to the canonical NCDA list, so
// the chart never renders raw strings like "gastric/oesophageal".
function formatLabel(raw: string | null): string {
  const canonical = normaliseCancerType(raw);
  const label = getCancerTypeLabel(canonical);
  return label.length > 16 ? label.slice(0, 15) + "..." : label;
}

/** Custom XAxis tick rendered at -45° so labels never overlap or overflow. */
function AxisTick({ x, y, payload }: any) {
  return (
    <g transform={`translate(${x},${y})`}>
      <text
        x={0}
        y={0}
        dy={4}
        textAnchor="end"
        fill="#374151"
        fontSize={11}
        transform="rotate(-45)"
      >
        {payload.value}
      </text>
    </g>
  );
}

export default function EpisodesByTypeChart({ data }: { data: DataItem[] }) {
  if (!data.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No referral data to show for this period.
      </Typography>
    );
  }

  const grouped = new Map<string, { condition_type: string; open: number; closed: number; total: number }>();
  for (const row of data) {
    const key = normaliseCancerType(row.condition_type);
    const entry = grouped.get(key) ?? { condition_type: key, open: 0, closed: 0, total: 0 };
    if (TERMINAL.has(row.status)) {
      entry.closed += row.count;
    } else {
      entry.open += row.count;
    }
    entry.total += row.count;
    grouped.set(key, entry);
  }

  // Order bars by the canonical NCDA display order so the chart axis
  // matches the data-entry form clinicians see (Bladder, Brain, Breast,
  // ...). Empty buckets are dropped before sorting so the chart stays
  // dense.
  const sorted = Array.from(grouped.values())
    .filter((d) => d.total > 0)
    .sort(
      (a, b) =>
        cancerTypeOrderIndex(a.condition_type) -
        cancerTypeOrderIndex(b.condition_type),
    );
  const MAX_BARS = 15;
  const hidden = sorted.slice(MAX_BARS);
  const chartData = sorted
    .slice(0, MAX_BARS)
    .map((d) => ({ ...d, condition_type: formatLabel(d.condition_type) }));

  const grandTotal = sorted.reduce((s, d) => s + d.total, 0);
  const hiddenTotal = hidden.reduce((s, d) => s + d.total, 0);
  const summary = chartData
    .slice(0, 3)
    .map((d) => `${d.condition_type} (${d.total})`)
    .join(", ");

  return (
    <Box sx={{ position: "relative" }}>
      <Box
        role="img"
        aria-label={`Bar chart: Referrals by cancer type. Total ${grandTotal} referrals. Top types: ${summary}.`}
        sx={{ overflow: "hidden" }}
      >
        <ResponsiveContainer width="99%" height={280}>
          <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
        <XAxis
          dataKey="condition_type"
          tick={<AxisTick />}
          interval={0}
          height={80}
        />
            <YAxis tick={{ fontSize: 11, fill: "#374151" }} allowDecimals={false} />
            <Tooltip
              formatter={(value, name) => [
                value ?? 0,
                name === "open" ? "Active referrals" : "Closed referrals",
              ]}
            />
            <Legend
              wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
              formatter={(v) => (v === "open" ? "Active referrals" : "Closed referrals")}
            />
            <Bar dataKey="open" fill={COLOUR_OPEN} name="open" stackId="a" />
            <Bar dataKey="closed" fill={COLOUR_CLOSED} name="closed" stackId="a" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
        </Box>
      {hidden.length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "right", mt: 0.5 }}>
          {`+${hiddenTotal} referral${hiddenTotal !== 1 ? "s" : ""} across ${hidden.length} more type${hidden.length !== 1 ? "s" : ""} not shown`}
        </Typography>
      )}
    </Box>
  );
}
