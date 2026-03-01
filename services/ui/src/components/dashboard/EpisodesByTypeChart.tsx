"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";

interface DataItem {
  condition_type: string;
  status: string;
  count: number;
}

const TERMINAL = new Set(["closed", "completed", "merged", "excluded"]);

// #0D7C6F passes WCAG 3:1 against white and light-grey backgrounds
const COLOUR_OPEN = "#0D7C6F";
const COLOUR_CLOSED = "#1E3A8A";

// Well-known long cancer type names get a shorter display label
const ABBREVIATIONS: Record<string, string> = {
  "Lower Gastrointestinal": "Lower GI",
  "Haematology Malignancy": "Haematology",
  "Haematology Malignancies": "Haematology",
  "Gynaecological": "Gynaecology",
};

function formatLabel(raw: string | null): string {
  if (!raw) return "Unknown";
  const title = raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return ABBREVIATIONS[title] ?? (title.length > 16 ? title.slice(0, 15) + "…" : title);
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
    const key = row.condition_type || "Unknown";
    const entry = grouped.get(key) ?? { condition_type: key, open: 0, closed: 0, total: 0 };
    if (TERMINAL.has(row.status)) {
      entry.closed += row.count;
    } else {
      entry.open += row.count;
    }
    entry.total += row.count;
    grouped.set(key, entry);
  }

  const chartData = Array.from(grouped.values())
    .sort((a, b) => b.total - a.total)
    .slice(0, 12)
    .map((d) => ({ ...d, condition_type: formatLabel(d.condition_type) }));

  const total = chartData.reduce((s, d) => s + d.total, 0);
  const summary = chartData
    .slice(0, 3)
    .map((d) => `${d.condition_type} (${d.total})`)
    .join(", ");

  return (
    <Box sx={{ position: "relative" }}>
      {/* Screen-reader summary — width/height must be explicit px strings; MUI treats numeric 1 as 100% */}
      <Box component="p" sx={{ position: "absolute", width: "1px", height: "1px", overflow: "hidden", clip: "rect(0,0,0,0)", whiteSpace: "nowrap" }}>
        Bar chart: Referrals by cancer type. Total {total} referrals. Top types: {summary}.
      </Box>
      <Box role="img" aria-hidden="true" sx={{ overflow: "hidden" }}>
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
              formatter={(v: number, name: string) => [v, name === "open" ? "Active referrals" : "Closed referrals"]}
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
    </Box>
  );
}
