"use client";

/**
 * Atlas trace:
 *   DO: DO-A9863AB6
 *   DI: DI-758B73A5
 */

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  Legend,
} from "recharts";

import { runMetric, type MetricRunResult, type AuditTile } from "@/lib/auditTemplateApi";

interface MetricTileProps {
  tile: AuditTile;
  orgId: string;
}

function KpiStrip({ rows }: { rows: Record<string, unknown>[] }) {
  return (
    <Box sx={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
      {rows.map((row, i) => {
        const keys = Object.keys(row);
        const label = keys[0];
        const value = keys[1];
        return (
          <Box
            key={i}
            sx={{
              textAlign: "center",
              p: 1.5,
              bgcolor: "grey.50",
              borderRadius: 1,
              minWidth: 100,
            }}
          >
            <Typography variant="h4" fontWeight={700} color="primary.main">
              {String(row[value] ?? "-")}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {String(row[label] ?? "")}
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
}

function BarTile({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return null;
  const keys = Object.keys(rows[0]);
  const catKey = keys[0];
  const valKeys = keys.slice(1);
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 24, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey={catKey} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <RechartsTooltip />
        {valKeys.map((k) => (
          <Bar key={k} dataKey={k} fill="#1976d2" />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

function LineTile({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return null;
  const keys = Object.keys(rows[0]);
  const catKey = keys[0];
  const valKeys = keys.slice(1);
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 24, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey={catKey} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <RechartsTooltip />
        <Legend />
        {valKeys.map((k, i) => (
          <Line
            key={k}
            dataKey={k}
            stroke={i === 0 ? "#1976d2" : "#9c27b0"}
            dot={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function TableTile({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <Typography variant="body2">No data</Typography>;
  const cols = Object.keys(rows[0]);
  return (
    <Box sx={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr>
            {cols.map((c) => (
              <th
                key={c}
                style={{
                  textAlign: "left",
                  padding: "4px 8px",
                  borderBottom: "2px solid #e0e0e0",
                  whiteSpace: "nowrap",
                }}
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ background: i % 2 ? "#fafafa" : "#fff" }}>
              {cols.map((c) => (
                <td key={c} style={{ padding: "4px 8px", borderBottom: "1px solid #f0f0f0" }}>
                  {String(row[c] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Box>
  );
}

function toObjects(result: MetricRunResult): Record<string, unknown>[] {
  return result.rows.map((row) =>
    Object.fromEntries(result.columns.map((col, i) => [col, (row as unknown[])[i]]))
  );
}

function TileBody({ tile, result }: { tile: AuditTile; result: MetricRunResult }) {
  const rows = toObjects(result);
  switch (tile.tile_type) {
    case "kpi_strip":
      return <KpiStrip rows={rows} />;
    case "bar_chart":
      return <BarTile rows={rows} />;
    case "line_chart":
      return <LineTile rows={rows} />;
    case "table":
    case "interval_plot":
      return <TableTile rows={rows} />;
    case "text":
      return (
        <Typography variant="body2" color="text.secondary">
          {rows.map((r) => Object.values(r).join(" ")).join("\n")}
        </Typography>
      );
    default:
      return <TableTile rows={rows} />;
  }
}

export default function MetricTile({ tile, orgId }: MetricTileProps) {
  const [result, setResult] = useState<MetricRunResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    runMetric(tile.metric_id, {
      scope_org_ids: [orgId],
      ...tile.param_overrides,
    })
      .then((r) => {
        if (!cancelled) setResult(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tile.metric_id, tile.param_overrides, orgId]);

  return (
    <Box
      sx={{
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        p: 2,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: 1,
      }}
    >
      <Typography variant="subtitle2" fontWeight={600}>
        {tile.label}
      </Typography>
      <Box sx={{ flex: 1, overflow: "hidden" }}>
        {loading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
            <CircularProgress size={24} />
          </Box>
        )}
        {error && <Alert severity="error" sx={{ fontSize: 12 }}>{error}</Alert>}
        {!loading && !error && result && <TileBody tile={tile} result={result} />}
      </Box>
    </Box>
  );
}
