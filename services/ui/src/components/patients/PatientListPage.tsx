/**
 * Domain-agnostic patient list page -- filing cabinet UI.
 *
 * Atlas trace:
 *   DO: DO-EBF0B124
 *   DI: DI-0ADA35BF
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EBF0B124")
 *
 * Shows all patients regardless of episode type. Condition-type tabs act as
 * folder tabs (filing cabinet metaphor). FilterBar handles text search and
 * the has-alerts toggle. Cards animate in with framer-motion stagger.
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Pagination from "@mui/material/Pagination";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import { AnimatePresence, motion as fm } from "framer-motion";
import { FilterBar, SegmentedTabs } from "@leo/design-system";
import type { SegmentedTab } from "@leo/design-system";
import type { PatientSummary, PatientsListResponse } from "@/lib/patientEprApi";
import { fetchEprPatientFacets, fetchEprPatients } from "@/lib/patientEprApi";
import { PatientDetailPage } from "./PatientDetailPage";

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// Condition-type colour map for accent strip
// ---------------------------------------------------------------------------

const CONDITION_ACCENT: Record<string, string> = {
  lung: "#1E40AF",
  breast: "#9D174D",
  prostate: "#6D28D9",
  colorectal: "#B45309",
  skin: "#047857",
  haematology: "#0369A1",
  upper_gi: "#7C3AED",
  lower_gi: "#B45309",
  gynaecology: "#BE185D",
  head_and_neck: "#1D4ED8",
  urology: "#4338CA",
};
const ALERT_ACCENT = "#B45309";
const DEFAULT_ACCENT = "#475569";

function accentFor(conditionTypes: string[], hasAlerts: boolean): string {
  if (hasAlerts) return ALERT_ACCENT;
  const first = conditionTypes[0];
  if (!first) return DEFAULT_ACCENT;
  return CONDITION_ACCENT[first.toLowerCase().replace(/ /g, "_")] ?? DEFAULT_ACCENT;
}

// ---------------------------------------------------------------------------
// PatientCard
// ---------------------------------------------------------------------------

function PatientCard({
  patient,
  onSelect,
  index,
}: {
  patient: PatientSummary;
  onSelect: (id: string) => void;
  index: number;
}) {
  const accent = accentFor(patient.condition_types, patient.active_alert_count > 0);

  return (
    <fm.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{
        duration: 0.22,
        ease: "easeOut",
        delay: Math.min(index, 12) * 0.04,
      }}
      whileHover={{ y: -2, boxShadow: "0 8px 18px rgba(15, 23, 42, 0.08)" }}
      role="button"
      tabIndex={0}
      onClick={() => onSelect(patient.patient_id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onSelect(patient.patient_id);
      }}
      style={{
        position: "relative",
        borderRadius: 12,
        border: "1px solid #E2E8F0",
        padding: "18px 18px 18px 21px",
        cursor: "pointer",
        background: "#FFFFFF",
        minHeight: 92,
        outline: "none",
      }}
    >
      {/* Condition-type accent strip */}
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          left: 0,
          top: 14,
          bottom: 14,
          width: 3,
          borderRadius: 2,
          background: accent,
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
            <WarningAmberOutlinedIcon sx={{ color: ALERT_ACCENT, fontSize: 16 }} />
            <Typography variant="caption" color={ALERT_ACCENT} fontWeight={600}>
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
    </fm.div>
  );
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function PatientListSkeleton() {
  return (
    <Stack spacing={1.5}>
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} variant="rounded" height={92} />
      ))}
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function PatientListPage() {
  const [data, setData] = useState<PatientsListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [facets, setFacets] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [draftSearch, setDraftSearch] = useState("");
  const [page, setPage] = useState(1);
  const [conditionType, setConditionType] = useState("all");
  const [hasAlerts, setHasAlerts] = useState(false);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);

  useEffect(() => {
    fetchEprPatientFacets()
      .then((r) => setFacets(r.condition_types))
      .catch(() => {});
  }, []);

  const load = useCallback(
    async (pg: number, q: string, ct: string, alerts: boolean) => {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchEprPatients(
          pg,
          PAGE_SIZE,
          q || undefined,
          ct === "all" ? undefined : ct,
          alerts || undefined
        );
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
    load(page, search, conditionType, hasAlerts);
  }, [load, page, search, conditionType, hasAlerts]);

  function handleSearch() {
    setPage(1);
    setSearch(draftSearch.trim());
  }

  function handleTabChange(id: string) {
    setConditionType(id);
    setPage(1);
  }

  function handleAlertsToggle() {
    setHasAlerts((v) => !v);
    setPage(1);
  }

  const conditionTabs = useMemo<SegmentedTab[]>(
    () => [
      { id: "all", label: "All", icon: <PeopleOutlineIcon sx={{ fontSize: 15 }} /> },
      ...facets.map((ct) => ({
        id: ct,
        label: ct.charAt(0).toUpperCase() + ct.slice(1).replace(/_/g, " "),
        icon: <FolderOutlinedIcon sx={{ fontSize: 15 }} />,
      })),
    ],
    [facets]
  );

  if (selectedPatientId) {
    return (
      <PatientDetailPage
        patientId={selectedPatientId}
        onBack={() => setSelectedPatientId(null)}
      />
    );
  }

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;
  const listKey = `${conditionType}-${hasAlerts}`;

  return (
    <Box sx={{ p: { xs: 2, sm: 3 }, maxWidth: 1400, mx: "auto" }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2.5 }}>
        <PeopleOutlineIcon sx={{ color: "#1E40AF" }} />
        <Typography variant="h5" component="h1" fontWeight={700}>
          Patients
        </Typography>
        {data && (
          <Chip
            label={`${data.total.toLocaleString()} total`}
            size="small"
            sx={{ ml: 0.5 }}
          />
        )}
      </Stack>

      {/* Condition-type folder tabs */}
      {conditionTabs.length > 1 && (
        <Box sx={{ mb: 2 }}>
          <SegmentedTabs
            tabs={conditionTabs}
            value={conditionType}
            onChange={handleTabChange}
            aria-label="Filter by condition type"
          />
        </Box>
      )}

      {/* Search + alert filter */}
      <Box sx={{ mb: 2.5 }}>
        <FilterBar
          search={draftSearch}
          onSearchChange={setDraftSearch}
          onSubmit={handleSearch}
          searchPlaceholder="Search by patient ID or NHS number"
          aria-label="Patient filters"
          chips={[
            {
              id: "has-alerts",
              label: "Has alerts",
              active: hasAlerts,
              onToggle: handleAlertsToggle,
            },
          ]}
        />
      </Box>

      {/* Error */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* Patient list with AnimatePresence for tab transitions */}
      {loading && !data && <PatientListSkeleton />}

      {!loading && data && data.patients.length === 0 && (
        <Alert severity="info">
          {search || conditionType !== "all" || hasAlerts
            ? "No patients match this filter."
            : "No patients found for your organisation."}
        </Alert>
      )}

      <AnimatePresence mode="wait">
        {!loading && data && data.patients.length > 0 && (
          <fm.div
            key={listKey}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.15 }}
          >
            <Stack spacing={1.5}>
              {data.patients.map((p, i) => (
                <PatientCard
                  key={p.patient_id}
                  patient={p}
                  onSelect={setSelectedPatientId}
                  index={i}
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
          </fm.div>
        )}
      </AnimatePresence>

      {/* Spinner for subsequent loads (page/filter changes) */}
      {loading && data && (
        <Box sx={{ position: "fixed", bottom: 24, right: 24 }}>
          <CircularProgress size={24} aria-label="Loading" role="status" />
        </Box>
      )}
    </Box>
  );
}
