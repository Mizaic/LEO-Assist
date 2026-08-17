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

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Pagination from "@mui/material/Pagination";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import { AnimatePresence, motion as fm } from "framer-motion";
import { FilterBar, SegmentedTabs } from "@leo/design-system";
import type { SegmentedTab } from "@leo/design-system";
import type { PatientSummary, PatientsListResponse } from "@/lib/patientEprApi";
import { fetchEprPatientFacets, fetchEprPatients } from "@/lib/patientEprApi";

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// Condition-type colour map for accent strip
// ---------------------------------------------------------------------------

const CONDITION_ACCENT: Record<string, string> = {
  lung: "#002178",
  breast: "#9D174D",
  prostate: "#6D28D9",
  colorectal: "#B45309",
  skin: "#047857",
  haematology: "#0369A1",
  upper_gi: "#7C3AED",
  lower_gi: "#B45309",
  gynaecology: "#BE185D",
  head_and_neck: "#0d46d6",
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
// Semantic tag display helpers
// ---------------------------------------------------------------------------

const TAG_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  disorder: { label: "Disorder", color: "#991B1B", bg: "#FEE2E2" },
  disease: { label: "Disease", color: "#991B1B", bg: "#FEE2E2" },
  clinical_finding: { label: "Finding", color: "#0369A1", bg: "#E0F2FE" },
  finding: { label: "Finding", color: "#0369A1", bg: "#E0F2FE" },
  procedure: { label: "Procedure", color: "#7C3AED", bg: "#EDE9FE" },
  observable_entity: { label: "Observable", color: "#0891B2", bg: "#CFFAFE" },
  situation: { label: "Situation", color: "#B45309", bg: "#FEF3C7" },
  product: { label: "Product", color: "#4D7C0F", bg: "#ECFCCB" },
};

function SemanticChip({ tag }: { tag: string }) {
  const cfg = TAG_CONFIG[tag.toLowerCase()] ?? {
    label: tag.replace(/_/g, " "),
    color: "#475569",
    bg: "#F1F5F9",
  };
  return (
    <Chip
      label={cfg.label}
      size="small"
      sx={{
        height: 20,
        fontSize: 10,
        fontWeight: 600,
        bgcolor: cfg.bg,
        color: cfg.color,
        border: "none",
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// PatientCard
// ---------------------------------------------------------------------------

function avatarInitials(patientId: string): string {
  const parts = patientId.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return patientId.slice(0, 2).toUpperCase();
}

function CountChip({
  icon,
  label,
}: {
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <Stack
      direction="row"
      spacing={0.4}
      alignItems="center"
      sx={{
        bgcolor: "#F8FAFC",
        border: "1px solid #E2E8F0",
        borderRadius: "6px",
        px: 0.75,
        py: "2px",
        flexShrink: 0,
      }}
    >
      {icon}
      <Typography variant="caption" fontWeight={500} sx={{ fontSize: 10 }}>
        {label}
      </Typography>
    </Stack>
  );
}

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
  const iconSx = { fontSize: 11, color: "#64748B" };

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
        borderLeft: `4px solid ${accent}`,
        padding: "14px 16px",
        cursor: "pointer",
        background: "#FFFFFF",
        outline: "none",
      }}
    >
      <Stack direction="row" spacing={1.5} alignItems="flex-start">
        {/* Avatar */}
        <Box
          aria-hidden="true"
          sx={{
            flexShrink: 0,
            width: 40,
            height: 40,
            borderRadius: "50%",
            bgcolor: accent,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontWeight: 700,
            fontSize: 13,
          }}
        >
          {avatarInitials(patient.patient_id)}
        </Box>

        <Box sx={{ flex: 1, minWidth: 0 }}>
          {/* Row 1: identity + alert badge */}
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="flex-start"
            spacing={1}
          >
            <Box sx={{ minWidth: 0 }}>
              <Typography
                variant="body2"
                fontWeight={700}
                sx={{ mb: 0.15, lineHeight: 1.3 }}
                noWrap
              >
                {patient.patient_id}
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap>
                {patient.birth_date ?? "DOB unknown"}
                {" \u00B7 "}
                {patient.gender ?? "unknown"}
                {patient.practice_name ? ` \u00B7 ${patient.practice_name}` : ""}
              </Typography>
            </Box>
            {patient.active_alert_count > 0 && (
              <Stack
                direction="row"
                spacing={0.4}
                alignItems="center"
                sx={{ flexShrink: 0 }}
              >
                <WarningAmberOutlinedIcon sx={{ color: ALERT_ACCENT, fontSize: 14 }} />
                <Typography
                  variant="caption"
                  color={ALERT_ACCENT}
                  fontWeight={700}
                  sx={{ fontSize: 11 }}
                >
                  {patient.active_alert_count}
                </Typography>
              </Stack>
            )}
          </Stack>

          {/* Row 2: activity counts */}
          <Stack direction="row" spacing={0.75} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
            <CountChip
              icon={<MedicalServicesOutlinedIcon sx={iconSx} />}
              label={`${patient.encounter_count} enc`}
            />
            {patient.referral_count > 0 && (
              <CountChip
                icon={<AssignmentOutlinedIcon sx={iconSx} />}
                label={`${patient.referral_count} referral${patient.referral_count !== 1 ? "s" : ""}`}
              />
            )}
            {patient.document_count > 0 && (
              <CountChip
                icon={<ArticleOutlinedIcon sx={iconSx} />}
                label={`${patient.document_count} doc${patient.document_count !== 1 ? "s" : ""}`}
              />
            )}
            {patient.coded_concept_count > 0 && (
              <CountChip
                icon={<BiotechOutlinedIcon sx={iconSx} />}
                label={`${patient.coded_concept_count} coded`}
              />
            )}
            {patient.last_activity && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ ml: "auto", fontSize: 10, alignSelf: "center" }}
              >
                {patient.last_activity.slice(0, 10)}
              </Typography>
            )}
          </Stack>

          {/* Row 3: semantic tag chips + condition type chips */}
          {(patient.semantic_tags.length > 0 || patient.condition_types.length > 0) && (
            <Stack
              direction="row"
              spacing={0.5}
              sx={{ mt: 0.75 }}
              flexWrap="wrap"
              useFlexGap
            >
              {patient.condition_types.slice(0, 2).map((ct) => (
                <Chip
                  key={ct}
                  label={ct}
                  size="small"
                  variant="outlined"
                  sx={{ height: 20, fontSize: 10 }}
                />
              ))}
              {patient.semantic_tags.slice(0, 4).map((tag) => (
                <SemanticChip key={tag} tag={tag} />
              ))}
            </Stack>
          )}
        </Box>
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
  const router = useRouter();
  const [data, setData] = useState<PatientsListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [facets, setFacets] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [draftSearch, setDraftSearch] = useState("");
  const [page, setPage] = useState(1);
  const [conditionType, setConditionType] = useState("all");
  const [hasAlerts, setHasAlerts] = useState(false);

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

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;
  const listKey = `${conditionType}-${hasAlerts}`;

  return (
    <Box sx={{ p: { xs: 2, sm: 3 }, maxWidth: 1400, mx: "auto" }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2.5 }}>
        <PeopleOutlineIcon sx={{ color: "#002178" }} />
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
                  onSelect={(id) => router.push(`/care/patients/${encodeURIComponent(id)}`)}
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
