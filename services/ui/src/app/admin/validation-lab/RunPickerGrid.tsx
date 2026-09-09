/**
 * Paginated, searchable pipeline-run picker.
 * Replaces ClinicalPatientPicker + ClinicalPatientLists.
 *
 * Atlas: DI-238DA59A / DI-562F2C9E
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Pagination from "@mui/material/Pagination";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ClearIcon from "@mui/icons-material/Clear";
import SearchIcon from "@mui/icons-material/Search";

import type { ClinicalPipelineRun } from "./labFindingsApi";
import { listClinicalRunsPage } from "./labFindingsApi";
import { investigationKey } from "./ncrInvestigationCases";
import { glassPanel } from "./clinicalDoorChrome";
import { NhsGroupRows, RunDataRow, type SortCol, type SortDir, GridSortHeader } from "./RunPickerRows";

const PAGE_SIZE = 25;

interface NhsGroup {
  nhsKey: string;
  patientName: string;
  runs: ClinicalPipelineRun[];
}

function groupByNhs(rows: ClinicalPipelineRun[]): NhsGroup[] {
  const map = new Map<string, ClinicalPipelineRun[]>();
  for (const row of rows) {
    const k = row.nhs_number || row.patient_id || investigationKey(row);
    map.set(k, [...(map.get(k) || []), row]);
  }
  return Array.from(map.entries()).map(([nhsKey, runs]) => ({
    nhsKey,
    patientName: runs[0].patient_name || runs[0].patient_id || "Patient",
    runs,
  }));
}

export interface RunPickerGridProps {
  linkedCases: ClinicalPipelineRun[];
  onPick: (row: ClinicalPipelineRun) => void;
}

// LONG FUNCTION: orchestrates server-side search, pagination, sort, and
// master-detail expansion for the run picker.
export function RunPickerGrid({ linkedCases, onPick }: RunPickerGridProps) {
  const [query, setQuery] = useState("");
  const [committed, setCommitted] = useState("");
  const [page, setPage] = useState(0);
  const [sortCol, setSortCol] = useState<SortCol>("created_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [rows, setRows] = useState<ClinicalPipelineRun[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expandedNhs, setExpandedNhs] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const linkedKeys = new Set(linkedCases.map(investigationKey));

  const load = useCallback(async (q: string, pg: number) => {
    setLoading(true);
    setError("");
    try {
      const data = await listClinicalRunsPage({ q, page: pg, per_page: PAGE_SIZE });
      setRows(data.rows);
      setTotal(data.total);
      setExpandedNhs(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load runs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(committed, page);
  }, [committed, page, load]);

  const handleQuery = (v: string) => {
    setQuery(v);
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      setPage(0);
      setCommitted(v.trim());
    }, 350);
  };

  const handleSort = (col: SortCol) => {
    setSortDir((d) => (col === sortCol ? (d === "asc" ? "desc" : "asc") : "desc"));
    setSortCol(col);
  };

  const sorted = [...rows].sort((a, b) => {
    const m = sortDir === "asc" ? 1 : -1;
    if (sortCol === "created_at") {
      return m * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
    }
    return m * (a.status || "").localeCompare(b.status || "");
  });

  // Only group by NHS when a NHS search returns more than one result for the same patient
  const isNhsSearch = sorted.length > 1 && sorted[0]?.matched_on === "nhs";
  const groups = isNhsSearch ? groupByNhs(sorted) : null;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <Box sx={{ ...glassPanel, overflow: "hidden" }}>
      {/* Search bar */}
      <Box sx={{ p: 2, borderBottom: "1px solid", borderColor: "divider" }}>
        <TextField
          fullWidth
          size="small"
          value={query}
          onChange={(e) => handleQuery(e.target.value)}
          placeholder="Search by NHS number or UBRN (referral number)"
          inputProps={{ "aria-label": "Search pipeline runs" }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                {loading ? (
                  <CircularProgress size={16} aria-label="Loading" role="status" />
                ) : (
                  <SearchIcon sx={{ fontSize: 18, color: "text.secondary" }} />
                )}
              </InputAdornment>
            ),
            endAdornment: query ? (
              <InputAdornment position="end">
                <IconButton
                  size="small"
                  onClick={() => { setQuery(""); setPage(0); setCommitted(""); }}
                  aria-label="Clear search"
                >
                  <ClearIcon sx={{ fontSize: 16 }} />
                </IconButton>
              </InputAdornment>
            ) : null,
          }}
        />
      </Box>

      {error && (
        <Typography color="error" sx={{ px: 2, py: 1, fontSize: 13 }}>
          {error}
        </Typography>
      )}

      {/* Grid table */}
      <Box sx={{ overflowX: "auto" }}>
        <table
          role="grid"
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontFamily: "Albert Sans, Arial, sans-serif",
          }}
        >
          <thead>
            <tr>
              <GridSortHeader col="created_at" label="Date" current={sortCol} dir={sortDir} onSort={handleSort} />
              <th style={TH}>Patient</th>
              <th style={TH}>NHS</th>
              <th style={TH}>UBRN</th>
              <GridSortHeader col="status" label="Status" current={sortCol} dir={sortDir} onSort={handleSort} />
              <th style={{ ...TH, width: 52 }} aria-label="Add" />
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 && !loading && (
              <tr>
                <td colSpan={6} style={EMPTY_TD}>
                  {committed ? "No runs match that search." : "Loading recent runs..."}
                </td>
              </tr>
            )}
            {groups
              ? groups.map((g) => (
                  <NhsGroupRows
                    key={g.nhsKey}
                    group={g}
                    expandedNhs={expandedNhs}
                    onToggle={(k) => setExpandedNhs(expandedNhs === k ? null : k)}
                    linkedKeys={linkedKeys}
                    onPick={onPick}
                  />
                ))
              : sorted.map((row, i) => (
                  <RunDataRow
                    key={investigationKey(row)}
                    row={row}
                    index={i}
                    indent={false}
                    linkedKeys={linkedKeys}
                    onPick={onPick}
                  />
                ))}
          </tbody>
        </table>
      </Box>

      {/* Pagination */}
      {totalPages > 1 && (
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{ px: 2, py: 1.5, borderTop: "1px solid", borderColor: "divider" }}
        >
          <Typography variant="caption" color="text.secondary">
            {total} runs
          </Typography>
          <Pagination
            count={totalPages}
            page={page + 1}
            onChange={(_, p) => setPage(p - 1)}
            size="small"
            siblingCount={1}
          />
        </Stack>
      )}
    </Box>
  );
}

const TH: React.CSSProperties = {
  textAlign: "left",
  fontSize: 11,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "#6B7280",
  padding: "8px 12px",
  borderBottom: "1px solid #E5E7EB",
  background: "#F9FAFB",
  position: "sticky",
  top: 0,
  zIndex: 1,
  whiteSpace: "nowrap",
};

const EMPTY_TD: React.CSSProperties = {
  textAlign: "center",
  padding: "32px 16px",
  color: "#9CA3AF",
  fontSize: 14,
};
