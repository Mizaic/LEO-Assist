"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import Pagination from "@mui/material/Pagination";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Skeleton from "@mui/material/Skeleton";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TableSortLabel from "@mui/material/TableSortLabel";
import Typography from "@mui/material/Typography";
import PatientCaseRow from "./PatientCaseRow";
import type { MissionPatient } from "@/lib/missionControlApi";
import type { MissionControlFilters } from "@/lib/missionControlFilters";

const COLUMNS = [
  { id: "expand", label: "", sortable: false },
  { id: "status", label: "Status", sortable: false },
  { id: "patient", label: "Patient", sortable: false },
  { id: "cancer_type", label: "Cancer type", sortable: true },
  { id: "cancer_stage", label: "Stage", sortable: false },
  { id: "referral_date", label: "Key dates", sortable: true },
  { id: "diagnostic_interval", label: "Time to diagnosis", sortable: true },
  { id: "review", label: "Review", sortable: false },
  { id: "open", label: "", sortable: false },
];

interface Props {
  patients: MissionPatient[];
  total: number;
  page: number;
  pageSize: number;
  sortBy: string;
  sortDir: "ASC" | "DESC";
  loading: boolean;
  error: string | null;
  onSortChange: (col: string) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  onOpenPatient: (patient: MissionPatient) => void;
  filters: MissionControlFilters;
}

export default function PatientCaseTable({
  patients,
  total,
  page,
  pageSize,
  sortBy,
  sortDir,
  loading,
  error,
  onSortChange,
  onPageChange,
  onPageSizeChange,
  onOpenPatient,
}: Props) {
  const pageCount = Math.ceil(total / pageSize) || 1;

  return (
    <Box>
      {/* Result count */}
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {loading ? "Loading..." : `Showing ${patients.length} of ${total} patients`}
      </Typography>

      <TableContainer component={Paper} elevation={0} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2 }}>
        <Table size="small" aria-label="Patient case list">
          <TableHead>
            <TableRow sx={{ bgcolor: "grey.50" }}>
              {COLUMNS.map((col) => (
                <TableCell key={col.id} sx={{ fontWeight: 600 }}>
                  {col.sortable ? (
                    <TableSortLabel
                      active={sortBy === col.id}
                      direction={sortBy === col.id ? sortDir.toLowerCase() as "asc" | "desc" : "desc"}
                      onClick={() => onSortChange(col.id)}
                    >
                      {col.label}
                    </TableSortLabel>
                  ) : (
                    col.label
                  )}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {loading && (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {COLUMNS.map((col) => (
                    <TableCell key={col.id}>
                      <Skeleton width="80%" height={20} />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
            {!loading && error && (
              <TableRow>
                <TableCell colSpan={COLUMNS.length}>
                  <Alert severity="error">{error}</Alert>
                </TableCell>
              </TableRow>
            )}
            {!loading && !error && patients.length === 0 && (
              <TableRow>
                <TableCell colSpan={COLUMNS.length}>
                  <Alert severity="info">
                    No patients found for the current filters. Try changing the date range or
                    pathway filter.
                  </Alert>
                </TableCell>
              </TableRow>
            )}
            {!loading && !error && patients.map((patient) => (
              <PatientCaseRow
                key={patient.patient_id}
                patient={patient}
                onOpen={onOpenPatient}
              />
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Pagination */}
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          mt: 1.5,
          flexWrap: "wrap",
          gap: 1,
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Typography variant="caption" color="text.secondary">
            Rows per page
          </Typography>
          <Select
            size="small"
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            sx={{ fontSize: "0.75rem" }}
          >
            {[25, 50, 100].map((n) => (
              <MenuItem key={n} value={n}>
                {n}
              </MenuItem>
            ))}
          </Select>
        </Box>
        <Pagination
          count={pageCount}
          page={page}
          onChange={(_, p) => onPageChange(p)}
          size="small"
          shape="rounded"
        />
      </Box>
    </Box>
  );
}
