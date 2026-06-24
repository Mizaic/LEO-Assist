/**
 * Domain-agnostic patient list page.
 *
 * Atlas trace:
 *   DO: DO-EBF0B124
 *   DI: DI-0ADA35BF
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EBF0B124")
 *
 * Shows all patients regardless of episode type. No cancer-specific columns.
 * Replaces MissionControl as the default /care/patients page.
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import InputAdornment from "@mui/material/InputAdornment";
import Pagination from "@mui/material/Pagination";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import SearchIcon from "@mui/icons-material/Search";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import type { PatientSummary, PatientsListResponse } from "@/lib/patientEprApi";
import { fetchEprPatients } from "@/lib/patientEprApi";
import { PatientDetailPage } from "./PatientDetailPage";

const PAGE_SIZE = 20;

function PatientCard({
  patient,
  onSelect,
}: {
  patient: PatientSummary;
  onSelect: (id: string) => void;
}) {
  return (
    <Box
      role="button"
      tabIndex={0}
      onClick={() => onSelect(patient.patient_id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onSelect(patient.patient_id);
      }}
      sx={{
        position: "relative",
        borderRadius: "12px",
        border: "1px solid #E2E8F0",
        p: "18px 18px 18px 21px",
        cursor: "pointer",
        bgcolor: "#FFFFFF",
        minHeight: 92,
        transition: "box-shadow 120ms ease-out",
        "&:hover": { boxShadow: "0 2px 8px rgba(0,0,0,0.08)" },
        "&:focus-visible": {
          outline: "2px solid #1E40AF",
          outlineOffset: 2,
        },
      }}
    >
      {/* Left accent strip */}
      <Box
        aria-hidden="true"
        sx={{
          position: "absolute",
          left: 0,
          top: 14,
          bottom: 14,
          width: 3,
          borderRadius: 2,
          bgcolor: patient.active_alert_count > 0 ? "#B45309" : "#1E40AF",
        }}
      />
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
        <Box>
          <Typography variant="body2" fontWeight={600} sx={{ mb: 0.25 }}>
            {patient.patient_id}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {patient.birth_date ?? "DOB unknown"} &middot;{" "}
            {patient.gender ?? "Unknown gender"} &middot;{" "}
            {patient.practice_name ?? "Practice unknown"}
          </Typography>
        </Box>
        {patient.active_alert_count > 0 && (
          <Stack direction="row" spacing={0.5} alignItems="center">
            <WarningAmberOutlinedIcon
              sx={{ color: "#B45309", fontSize: 16 }}
            />
            <Typography variant="caption" color="#B45309" fontWeight={600}>
              {patient.active_alert_count}{" "}
              {patient.active_alert_count === 1 ? "alert" : "alerts"}
            </Typography>
          </Stack>
        )}
      </Stack>
      <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap">
        <Chip
          label={`${patient.episode_count} episode${patient.episode_count !== 1 ? "s" : ""}`}
          size="small"
          sx={{ height: 20, fontSize: 11 }}
        />
        {patient.condition_types.slice(0, 3).map((ct) => (
          <Chip
            key={ct}
            label={ct}
            size="small"
            variant="outlined"
            sx={{ height: 20, fontSize: 11 }}
          />
        ))}
        {patient.last_activity && (
          <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }}>
            Last activity: {patient.last_activity.slice(0, 10)}
          </Typography>
        )}
      </Stack>
    </Box>
  );
}

function PatientListSkeleton() {
  return (
    <Stack spacing={1.5}>
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} variant="rounded" height={92} />
      ))}
    </Stack>
  );
}

export default function PatientListPage() {
  const [data, setData] = useState<PatientsListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [draftSearch, setDraftSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);

  const load = useCallback(
    async (pg: number, q: string) => {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchEprPatients(pg, PAGE_SIZE, q || undefined);
        setData(result);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load patients. Please try again."
        );
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    load(page, search);
  }, [load, page, search]);

  function handleSearch() {
    setPage(1);
    setSearch(draftSearch.trim());
  }

  if (selectedPatientId) {
    return (
      <PatientDetailPage
        patientId={selectedPatientId}
        onBack={() => setSelectedPatientId(null)}
      />
    );
  }

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  return (
    <Box>
      {/* Header */}
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ mb: 2 }}
      >
        <Stack direction="row" spacing={1} alignItems="center">
          <PeopleOutlineIcon sx={{ color: "#1E40AF" }} />
          <Typography variant="h5" component="h1" fontWeight={700}>
            Patients
          </Typography>
          {data && (
            <Chip
              label={`${data.total.toLocaleString()} total`}
              size="small"
              sx={{ ml: 1 }}
            />
          )}
        </Stack>
      </Stack>

      {/* Search */}
      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        <TextField
          size="small"
          placeholder="Search by patient ID or NHS number"
          value={draftSearch}
          onChange={(e) => setDraftSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          aria-label="Search patients"
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
          sx={{ flex: 1 }}
        />
        <Button variant="contained" onClick={handleSearch} size="small">
          Search
        </Button>
      </Stack>

      {/* Content */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {loading && <PatientListSkeleton />}

      {!loading && data && data.patients.length === 0 && (
        <Alert severity="info">
          {search
            ? "No patients match this search."
            : "No patients found for your organisation."}
        </Alert>
      )}

      {!loading && data && data.patients.length > 0 && (
        <>
          <Stack spacing={1.5}>
            {data.patients.map((p) => (
              <PatientCard
                key={p.patient_id}
                patient={p}
                onSelect={setSelectedPatientId}
              />
            ))}
          </Stack>

          {totalPages > 1 && (
            <Box sx={{ mt: 3, display: "flex", justifyContent: "center" }}>
              <Pagination
                count={totalPages}
                page={page}
                onChange={(_, pg) => setPage(pg)}
                color="primary"
                shape="rounded"
              />
            </Box>
          )}
        </>
      )}

      {loading && data && (
        <Box
          sx={{
            position: "fixed",
            bottom: 24,
            right: 24,
          }}
        >
          <CircularProgress
            size={24}
            aria-label="Loading"
            role="status"
          />
        </Box>
      )}
    </Box>
  );
}
