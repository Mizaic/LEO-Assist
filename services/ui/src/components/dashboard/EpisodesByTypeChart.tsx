"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import Typography from "@mui/material/Typography";

interface DataItem {
  cancer_type: string;
  status: string;
  count: number;
}

export default function EpisodesByTypeChart({ data }: { data: DataItem[] }) {
  if (!data.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No episode data available.
      </Typography>
    );
  }

  const grouped = new Map<string, { cancer_type: string; active: number; closed: number; total: number }>();
  for (const row of data) {
    const key = row.cancer_type || "Unknown";
    const entry = grouped.get(key) ?? { cancer_type: key, active: 0, closed: 0, total: 0 };
    if (row.status === "active") entry.active += row.count;
    else entry.closed += row.count;
    entry.total += row.count;
    grouped.set(key, entry);
  }

  const chartData = Array.from(grouped.values()).sort((a, b) => b.total - a.total).slice(0, 12);

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
        <XAxis
          dataKey="cancer_type"
          tick={{ fontSize: 11 }}
          angle={-30}
          textAnchor="end"
          height={60}
        />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="active" fill="#14B8A6" name="Active" stackId="a" />
        <Bar dataKey="closed" fill="#1F3A8A" name="Closed" stackId="a" />
      </BarChart>
    </ResponsiveContainer>
  );
}
