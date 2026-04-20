/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-3AD4D385
 *   DI: DI-9DCBC4BA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-3AD4D385")
 */
"use client";

import Box from "@mui/material/Box";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TableSortLabel from "@mui/material/TableSortLabel";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import { useState } from "react";
import { exportRunUrl, type RunResult } from "@/lib/researchApi";

interface Props {
  result: RunResult | null;
  runId?: string;
}

type SortDir = "asc" | "desc";

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "-";
  if (typeof v === "number") {
    return Number.isInteger(v) ? String(v) : v.toFixed(3);
  }
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) {
    return v
      .map((item) =>
        item === null || item === undefined
          ? "-"
          : typeof item === "object"
          ? JSON.stringify(item)
          : String(item)
      )
      .join(" · ");
  }
  if (typeof v === "object") {
    return Object.entries(v as Record<string, unknown>)
      .map(([k, val]) => `${k}: ${val}`)
      .join(", ");
  }
  return String(v);
}

function humaniseKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ResultsTable({ result, runId }: Props) {
  const [sortKey, setSortKey] = useState<string>("rank");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  if (!result || !result.items.length) {
    return (
      <Box sx={{ py: 2 }}>
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          No items to show.
        </Typography>
      </Box>
    );
  }

  // Determine column keys from first item, but skip internal/id columns
  const allKeys = Object.keys(result.items[0]).filter(
    (k) => !["node_id", "node_a", "node_b", "component_id", "community_id"].includes(k)
  );

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sorted = [...result.items].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    const mult = sortDir === "asc" ? 1 : -1;
    if (typeof av === "number" && typeof bv === "number") {
      return (av - bv) * mult;
    }
    return String(av).localeCompare(String(bv)) * mult;
  });

  return (
    <Box>
      {runId && (
        <Box sx={{ mb: 1, display: "flex", justifyContent: "flex-end" }}>
          <Button
            component="a"
            href={exportRunUrl(runId)}
            download
            size="small"
            startIcon={<DownloadOutlinedIcon />}
            variant="outlined"
          >
            Export to CSV
          </Button>
        </Box>
      )}

      <Box sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              {allKeys.map((key) => (
                <TableCell key={key} sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>
                  <TableSortLabel
                    active={sortKey === key}
                    direction={sortKey === key ? sortDir : "asc"}
                    onClick={() => handleSort(key)}
                  >
                    {humaniseKey(key)}
                  </TableSortLabel>
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {sorted.map((row, i) => (
              <TableRow
                key={i}
                hover
                sx={{ "&:last-child td": { borderBottom: 0 } }}
              >
                {allKeys.map((key) => (
                  <TableCell key={key} sx={{ fontSize: "0.8125rem" }}>
                    {formatValue(row[key])}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>

      {result.total_count > result.items.length && (
        <Typography
          variant="caption"
          sx={{ color: "text.secondary", mt: 1, display: "block" }}
        >
          Showing {result.items.length} of {result.total_count} results.
          Increase the detail level to see more.
        </Typography>
      )}
    </Box>
  );
}
