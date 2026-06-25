"use client";

/**
 * Atlas trace:
 *   DO: DO-A9863AB6
 *   DI: DI-758B73A5
 */

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Skeleton from "@mui/material/Skeleton";
import Tooltip from "@mui/material/Tooltip";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
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

const CHART_PALETTE = ["#1E40AF", "#047857", "#9333EA", "#B45309", "#0E7490"];

interface MetricTileProps {
  tile: AuditTile;
  orgId: string;
}

function KpiStrip({ rows }: { rows: Record<string, unknown>[] }) {
  return (
    <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", pt: 0.5 }}>
      {rows.map((row, i) => {
        const keys = Object.keys(row);
        const labelKey = keys[0];
        const valueKey = keys[1] ?? keys[0];
        return (
          <Box
            key={i}
            sx={{
              flex: "1 1 80px",
              textAlign: "center",
              px: 1.5,
              py: 1.25,
              bgcolor: "grey.50",
              borderRadius: 1.5,
              border: "1px solid",
              borderColor: "divider",
              minWidth: 80,
            }}
          >
            <Typography
              variant="h5"
              fontWeight={700}
              sx={{ color: CHART_PALETTE[i % CHART_PALETTE.length], lineHeight: 1.1 }}
            >
              {String(row[valueKey] ?? "-")}
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
              {String(row[labelKey] ?? "")}
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
}

function BarTile({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <EmptyData />;
  const keys = Object.keys(rows[0]);
  const catKey = keys[0];
  const valKeys = keys.slice(1);
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 32, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey={catKey} tick={{ fontSize: 10 }} angle={-30} textAnchor="end" />
        <YAxis tick={{ fontSize: 10 }} />
        <RechartsTooltip contentStyle={{ fontSize: 12 }} />
        {valKeys.map((k, i) => (
          <Bar key={k} dataKey={k} fill={CHART_PALETTE[i % CHART_PALETTE.length]} radius={[3, 3, 0, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

function LineTile({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <EmptyData />;
  const keys = Object.keys(rows[0]);
  const catKey = keys[0];
  const valKeys = keys.slice(1);
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 32, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey={catKey} tick={{ fontSize: 10 }} angle={-30} textAnchor="end" />
        <YAxis tick={{ fontSize: 10 }} />
        <RechartsTooltip contentStyle={{ fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {valKeys.map((k, i) => (
          <Line
            key={k}
            dataKey={k}
            stroke={CHART_PALETTE[i % CHART_PALETTE.length]}
            strokeWidth={2}
            dot={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function TableTile({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <EmptyData />;
  const cols = Object.keys(rows[0]);
  return (
    <Box sx={{ overflowX: "auto", mt: 0.5 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ background: "#F8FAFC" }}>
            {cols.map((c) => (
              <th
                key={c}
                style={{
                  textAlign: "left",
                  padding: "6px 10px",
                  borderBottom: "2px solid #E2E8F0",
                  whiteSpace: "nowrap",
                  fontWeight: 600,
                  color: "#374151",
                }}
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td
                  key={c}
                  style={{
                    padding: "5px 10px",
                    borderBottom: "1px solid #F1F5F9",
                    color: "#1F2937",
                  }}
                >
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

function EmptyData() {
  return (
    <Typography variant="caption" color="text.disabled" sx={{ display: "block", py: 2, textAlign: "center" }}>
      No data for this period
    </Typography>
  );
}

function TileLoadingSkeleton({ type }: { type: AuditTile["tile_type"] }) {
  if (type === "kpi_strip") {
    return (
      <Box sx={{ display: "flex", gap: 2, pt: 0.5 }}>
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} variant="rounded" width={90} height={60} />
        ))}
      </Box>
    );
  }
  if (type === "table") {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75, mt: 1 }}>
        <Skeleton variant="rounded" height={22} width="100%" />
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} variant="rounded" height={18} width="100%" sx={{ opacity: 0.6 - i * 0.1 }} />
        ))}
      </Box>
    );
  }
  return <Skeleton variant="rounded" width="100%" height={200} sx={{ mt: 1 }} />;
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
        <Typography variant="body2" color="text.secondary" sx={{ pt: 0.5, lineHeight: 1.6 }}>
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
    setResult(null);
    runMetric(tile.metric_id, tile.param_overrides, orgId || undefined)
      .then((r) => { if (!cancelled) setResult(r); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [tile.metric_id, tile.param_overrides, orgId]);

  return (
    <Box
      sx={{
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1.5,
        p: 2,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: 0.75,
        position: "relative",
        overflow: "hidden",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 1 }}>
        <Typography variant="subtitle2" fontWeight={600} color="text.primary">
          {tile.label}
        </Typography>
        {error && (
          <Tooltip title={error} placement="top">
            <ErrorOutlineIcon sx={{ fontSize: 16, color: "warning.main", flexShrink: 0, mt: 0.25 }} />
          </Tooltip>
        )}
      </Box>

      <Box sx={{ flex: 1, overflow: "hidden" }}>
        {loading && <TileLoadingSkeleton type={tile.tile_type} />}
        {!loading && error && (
          <Typography variant="caption" color="warning.dark" sx={{ display: "block", pt: 0.5 }}>
            {error}
          </Typography>
        )}
        {!loading && !error && result && <TileBody tile={tile} result={result} />}
        {!loading && !error && result && result.rows.length === 0 && tile.tile_type !== "kpi_strip" && (
          <EmptyData />
        )}
      </Box>
    </Box>
  );
}
