"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";

interface DataItem {
  cancer_type: string;
  count: number;
}

// All colours checked against white: minimum 3:1 for UI components (WCAG 1.4.11)
const COLOURS = [
  "#0D7C6F", "#0F6B60", "#105A52",  // teal family
  "#1D4ED8", "#1E3A8A", "#1E2D6B",  // blue family
  "#7C3AED", "#6D28D9", "#5B21B6",  // purple family
  "#B45309", "#92400E", "#78350F",  // amber family
];

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

export default function DiagnosedByTypeChart({ data }: { data: DataItem[] }) {
  if (!data.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No confirmed diagnoses to show for this period.
      </Typography>
    );
  }

  const chartData = data
    .slice(0, 12)
    .map((d) => ({ ...d, label: formatLabel(d.cancer_type) }));

  const total = chartData.reduce((s, d) => s + d.count, 0);
  const summary = chartData
    .slice(0, 3)
    .map((d) => `${d.label} (${d.count})`)
    .join(", ");

  return (
    <Box sx={{ position: "relative" }}>
      <Box
        role="img"
        aria-label={`Bar chart: Confirmed cancers by type. Total ${total} confirmed diagnoses. Top types: ${summary}.`}
        sx={{ overflow: "hidden" }}
      >
        <ResponsiveContainer width="99%" height={280}>
          <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
        <XAxis
          dataKey="label"
          tick={<AxisTick />}
          interval={0}
          height={80}
        />
            <YAxis tick={{ fontSize: 11, fill: "#374151" }} allowDecimals={false} />
            <Tooltip
              formatter={(value) => [value ?? 0, "Confirmed diagnoses"]}
            />
            <Bar dataKey="count" name="Confirmed diagnoses" radius={[3, 3, 0, 0]}>
              {chartData.map((_, i) => (
                <Cell key={i} fill={COLOURS[i % COLOURS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Box>
    </Box>
  );
}
