"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  LabelList,
} from "recharts";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { BENCHMARK_COLOURS, getBenchmarkLabels } from "./BenchmarkLegend";

export interface ComparisonDataRow {
  category: string;
  practice?: number | null;
  similar?: number | null;
  alliance?: number | null;
  national?: number | null;
}

interface ComparisonBarChartProps {
  data: ComparisonDataRow[];
  unit?: "percent" | "days" | "count" | "median";
  layout?: "grouped" | "horizontal";
  height?: number;
  visibleKeys?: ReadonlyArray<keyof Omit<ComparisonDataRow, "category">>;
  ariaLabel?: string;
  orgSelected?: boolean;
}

const DEFAULT_KEYS: ReadonlyArray<keyof Omit<ComparisonDataRow, "category">> = [
  "practice",
  "national",
  "similar",
  "alliance",
];

function formatTick(val: number | string, unit: ComparisonBarChartProps["unit"]): string {
  if (typeof val !== "number") return String(val);
  if (unit === "percent") return `${val}%`;
  if (unit === "days") return `${val}d`;
  return String(val);
}

function AxisTick({ x, y, payload }: any) {
  return (
    <g transform={`translate(${x},${y})`}>
      <text x={0} y={0} dy={4} textAnchor="end" fill="#374151" fontSize={11} transform="rotate(-40)">
        {payload.value}
      </text>
    </g>
  );
}

export default function ComparisonBarChart({
  data,
  unit = "percent",
  layout = "grouped",
  height = 300,
  visibleKeys = DEFAULT_KEYS,
  ariaLabel,
  orgSelected = true,
}: ComparisonBarChartProps) {
  const BENCHMARK_LABELS = getBenchmarkLabels(orgSelected);
  if (!data || data.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: "center" }}>
        No data available for this period.
      </Typography>
    );
  }

  const unitSuffix = unit === "percent" ? "%" : unit === "days" ? " days" : "";

  if (layout === "horizontal") {
    // Horizontal grouped bars — one row per category, bars side-by-side for each comparison level
    const chartData = data.map((row) => {
      const entry: Record<string, any> = { category: row.category };
      for (const key of visibleKeys) {
        entry[key] = row[key] ?? null;
      }
      return entry;
    });

    return (
      <Box
        role="img"
        aria-label={ariaLabel ?? `Grouped comparison bar chart with ${data.length} categories`}
      >
        <ResponsiveContainer width="99%" height={Math.max(height, data.length * 40 + 60)}>
          <BarChart
            layout="vertical"
            data={chartData}
            margin={{ top: 5, right: 50, left: 80, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" horizontal={false} />
            <XAxis
              type="number"
              tickFormatter={(v) => formatTick(v, unit)}
              tick={{ fontSize: 11, fill: "#374151" }}
              domain={unit === "percent" ? [0, 100] : ["auto", "auto"]}
            />
            <YAxis
              type="category"
              dataKey="category"
              tick={{ fontSize: 11, fill: "#374151" }}
              width={76}
            />
            <Tooltip formatter={(v: any) => [`${v}${unitSuffix}`, ""]} />
            {visibleKeys.map((key) => (
              <Bar
                key={key}
                dataKey={key}
                name={BENCHMARK_LABELS[key as keyof typeof BENCHMARK_LABELS] ?? key}
                fill={BENCHMARK_COLOURS[key as keyof typeof BENCHMARK_COLOURS] ?? "#9CA3AF"}
                radius={[0, 3, 3, 0]}
              >
                <LabelList
                  dataKey={key}
                  position="right"
                  formatter={(v: any) => (v != null ? `${v}${unitSuffix}` : "")}
                  style={{ fontSize: 10, fill: "#374151" }}
                />
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      </Box>
    );
  }

  // Default: vertical grouped bars
  const chartData = data.map((row) => {
    const entry: Record<string, any> = { category: row.category };
    for (const key of visibleKeys) {
      entry[key] = row[key] ?? null;
    }
    return entry;
  });

  return (
    <Box
      role="img"
      aria-label={ariaLabel ?? `Grouped comparison bar chart with ${data.length} categories`}
    >
      <ResponsiveContainer width="99%" height={height}>
        <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
          <XAxis
            dataKey="category"
            tick={<AxisTick />}
            interval={0}
            height={70}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "#374151" }}
            tickFormatter={(v) => formatTick(v, unit)}
            domain={unit === "percent" ? [0, 100] : ["auto", "auto"]}
          />
          <Tooltip
            formatter={(v: any, name?: string) => {
              const series = name ?? "";
              return [
                `${v}${unitSuffix}`,
                BENCHMARK_LABELS[series as keyof typeof BENCHMARK_LABELS] ?? series,
              ];
            }}
          />
          {visibleKeys.map((key) => (
            <Bar
              key={key}
              dataKey={key}
              name={key}
              fill={BENCHMARK_COLOURS[key as keyof typeof BENCHMARK_COLOURS] ?? "#9CA3AF"}
              radius={[3, 3, 0, 0]}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </Box>
  );
}
