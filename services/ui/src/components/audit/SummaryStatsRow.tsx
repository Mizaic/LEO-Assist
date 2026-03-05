"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import { BENCHMARK_COLOURS, BENCHMARK_LABELS } from "./BenchmarkLegend";

export interface StatValue {
  value: number | string | null | undefined;
  n?: number;
  iqr?: [number | null, number | null];
}

export interface SummaryStatRow {
  label: string;
  unit?: string;
  practice?: StatValue | null;
  similar?: StatValue | null;
  alliance?: StatValue | null;
  national?: StatValue | null;
}

interface SummaryStatsTableProps {
  rows: SummaryStatRow[];
  visibleKeys?: Array<"practice" | "similar" | "alliance" | "national">;
  caption?: string;
}

function renderCell(sv: StatValue | null | undefined, unit?: string) {
  if (!sv || sv.value == null) return <Typography variant="body2" color="text.secondary">—</Typography>;
  const display = typeof sv.value === "number" ? sv.value.toLocaleString("en-GB", { maximumFractionDigits: 1 }) : sv.value;
  return (
    <Box>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        {display}{unit ? ` ${unit}` : ""}
      </Typography>
      {sv.iqr && sv.iqr[0] != null && (
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.72rem" }}>
          IQR: {sv.iqr[0]}–{sv.iqr[1]}
        </Typography>
      )}
      {sv.n != null && (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ fontSize: "0.72rem" }}>
          n={sv.n}
        </Typography>
      )}
    </Box>
  );
}

export default function SummaryStatsTable({
  rows,
  visibleKeys = ["practice", "similar", "alliance", "national"],
  caption,
}: SummaryStatsTableProps) {
  return (
    <Box sx={{ overflowX: "auto" }}>
      <Table size="small" aria-label={caption ?? "NCDA summary statistics"}>
        {caption && <caption style={{ captionSide: "top", textAlign: "left", padding: "4px 0", fontSize: "0.8rem", color: "#6B7280" }}>{caption}</caption>}
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 700, fontSize: "0.8rem", minWidth: 160 }}>Metric</TableCell>
            {visibleKeys.map((key) => (
              <TableCell
                key={key}
                align="center"
                sx={{
                  fontWeight: 700,
                  fontSize: "0.8rem",
                  color: BENCHMARK_COLOURS[key],
                  whiteSpace: "nowrap",
                }}
              >
                {BENCHMARK_LABELS[key]}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.label} hover>
              <TableCell sx={{ fontSize: "0.82rem", py: 1 }}>{row.label}</TableCell>
              {visibleKeys.map((key) => (
                <TableCell key={key} align="center" sx={{ py: 1 }}>
                  {renderCell(row[key], row.unit)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
