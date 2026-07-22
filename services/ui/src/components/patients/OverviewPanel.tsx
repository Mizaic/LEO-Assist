/**
 * OverviewPanel -- clinical summary for the Overview tab.
 *
 * Layout: compact episode strip, then Latest SBAR as the primary pane.
 * Demographics live in PatientHeader; problems/alerts live in the right rail.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import HealingOutlinedIcon from "@mui/icons-material/HealingOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import type {
  PatientDetail,
  EpisodeSummaryEpr,
  AssessmentRow,
  CodedEntityRow,
} from "@/lib/patientEprApi";
import { fetchEprAssessments } from "@/lib/patientEprApi";
import { LeoSbarHost } from "@/components/sbar-final";
import { ProblemListView } from "./ProblemListView";

const CONDITION_ACCENT: Record<string, string> = {
  lung: "#1E40AF",
  breast: "#9D174D",
  prostate: "#6D28D9",
  colorectal: "#B45309",
  lower_gi: "#B45309",
  upper_gi: "#7C3AED",
  skin: "#047857",
  haematology: "#0369A1",
  gynaecology: "#BE185D",
  head_and_neck: "#1D4ED8",
  urology: "#4338CA",
};

function accentFor(type: string | null): string {
  const key = (type ?? "").toLowerCase().replace(/ /g, "_");
  return CONDITION_ACCENT[key] ?? "#475569";
}

function outcomeColor(outcome: string | null): string {
  const o = (outcome ?? "").toLowerCase();
  if (o === "cancer") return "#B91C1C";
  if (o === "benign") return "#047857";
  return "#475569";
}

function outcomeLabel(outcome: string | null): string {
  if (!outcome) return "";
  const o = outcome.toLowerCase();
  if (o === "cancer") return "Cancer confirmed";
  if (o === "benign") return "Benign";
  if (o.includes("watch")) return "Watchful waiting";
  return outcome;
}

function SectionHeader({
  icon,
  title,
}: {
  icon: React.ReactElement;
  title: string;
}) {
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
      {icon}
      <Typography variant="subtitle2" fontWeight={700} component="h2">
        {title}
      </Typography>
    </Stack>
  );
}

function EpisodeCard({ ep }: { ep: EpisodeSummaryEpr }) {
  const accent = accentFor(ep.condition_type);
  const stagingText = [ep.staging_value, ep.staging_early_late]
    .filter(Boolean)
    .join(" - ");
  const isActive = (ep.status ?? "").toLowerCase() === "active";
  const statusColor = isActive ? "#047857" : "#64748B";

  return (
    <Box
      sx={{
        position: "relative",
        border: "1px solid #E2E8F0",
        borderRadius: "10px",
        p: "12px 14px 12px 18px",
        bgcolor: "#FAFAFA",
        height: "100%",
      }}
    >
      <Box
        aria-hidden="true"
        sx={{
          position: "absolute",
          left: 0,
          top: 10,
          bottom: 10,
          width: 3,
          borderRadius: 2,
          bgcolor: accent,
        }}
      />
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        flexWrap="wrap"
        sx={{ mb: 0.5 }}
      >
        <Typography
          variant="body2"
          fontWeight={700}
          sx={{ textTransform: "capitalize" }}
        >
          {ep.condition_type ?? "Episode"}
        </Typography>
        <Chip
          label={ep.status ?? "unknown"}
          size="small"
          sx={{
            height: 18,
            fontSize: 10,
            bgcolor: `${statusColor}18`,
            color: statusColor,
            textTransform: "capitalize",
          }}
        />
        {ep.inferred_outcome && (
          <Chip
            label={outcomeLabel(ep.inferred_outcome)}
            size="small"
            sx={{
              height: 18,
              fontSize: 10,
              bgcolor: `${outcomeColor(ep.inferred_outcome)}15`,
              color: outcomeColor(ep.inferred_outcome),
            }}
          />
        )}
      </Stack>
      <Stack direction="row" spacing={1.5} flexWrap="wrap">
        {ep.referral_date && (
          <Typography variant="caption" color="text.secondary">
            Referred {ep.referral_date.slice(0, 10)}
          </Typography>
        )}
        {stagingText && (
          <Typography variant="caption" color="text.secondary">
            Stage {stagingText}
          </Typography>
        )}
      </Stack>
    </Box>
  );
}

function SbarSummaryPanel({ patientId }: { patientId: string }) {
  const [rows, setRows] = useState<AssessmentRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchEprAssessments(patientId)
      .then(setRows)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [patientId]);

  if (loading) return <Skeleton variant="rounded" height={120} />;

  if (rows.length === 0) {
    return (
      <Typography variant="caption" color="text.secondary" fontStyle="italic">
        No SBAR summaries on record.
      </Typography>
    );
  }

  const latest = rows[0];
  if (!latest.assessment_id) {
    return (
      <Typography variant="caption" color="text.secondary" fontStyle="italic">
        SBAR draft in progress.
      </Typography>
    );
  }

  return (
    <Box>
      {latest.created_at && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mb: 1 }}
        >
          {latest.episode_label} -- {latest.created_at.slice(0, 10)}
        </Typography>
      )}
      <LeoSbarHost
        assessmentId={latest.assessment_id}
        testId={`epr-sbar-${latest.assessment_id}`}
      />
    </Box>
  );
}

interface Props {
  detail: PatientDetail | null;
  loading?: boolean;
  /** Used below xl when the right clinical-context rail is hidden. */
  entities?: CodedEntityRow[];
  entitiesLoading?: boolean;
}

function OverviewSkeleton() {
  return (
    <Stack spacing={2}>
      <Skeleton variant="rounded" height={88} />
      <Skeleton variant="rounded" height={320} />
    </Stack>
  );
}

export function OverviewPanel({
  detail,
  loading,
  entities = [],
  entitiesLoading = false,
}: Props) {
  if (loading || !detail) return <OverviewSkeleton />;

  const alertCount = detail.active_alert_count;
  const problems = entities.filter((e) => e.entity_type !== "medication");

  return (
    <Stack spacing={2} data-testid="epr-overview-panel">
      <Paper variant="outlined" sx={{ p: 2, borderRadius: "10px" }}>
        <SectionHeader
          icon={<HealingOutlinedIcon sx={{ color: "#047857", fontSize: 18 }} />}
          title={`Episodes (${detail.episodes.length})`}
        />
        {detail.episodes.length === 0 ? (
          <Alert severity="info" sx={{ fontSize: 13 }}>
            No episodes recorded.
          </Alert>
        ) : (
          <Grid container spacing={1.5}>
            {detail.episodes.map((ep, i) => (
              <Grid size={{ xs: 12, sm: 6, lg: 4 }} key={ep.episode_id ?? String(i)}>
                <EpisodeCard ep={ep} />
              </Grid>
            ))}
          </Grid>
        )}
      </Paper>

      <Paper
        variant="outlined"
        sx={{ p: 2, borderRadius: "10px" }}
        data-testid="epr-latest-sbar"
      >
        <SectionHeader
          icon={
            <AssessmentOutlinedIcon sx={{ color: "#047857", fontSize: 18 }} />
          }
          title="Latest SBAR"
        />
        <SbarSummaryPanel patientId={detail.patient_id} />
      </Paper>

      {/* Visible only when the xl clinical-context rail is hidden. */}
      <Grid
        container
        spacing={2}
        sx={{ display: { xs: "flex", xl: "none" } }}
        data-testid="epr-overview-context-fallback"
      >
        <Grid size={{ xs: 12, md: 7 }}>
          <Paper variant="outlined" sx={{ p: 2, borderRadius: "10px" }}>
            <SectionHeader
              icon={
                <LocalHospitalOutlinedIcon
                  sx={{ color: "#6D28D9", fontSize: 18 }}
                />
              }
              title="Problem list"
            />
            <ProblemListView
              patientId={detail.patient_id}
              entities={problems}
              loading={entitiesLoading}
            />
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <Paper variant="outlined" sx={{ p: 2, borderRadius: "10px" }}>
            <SectionHeader
              icon={
                <WarningAmberOutlinedIcon
                  sx={{ color: "#B45309", fontSize: 18 }}
                />
              }
              title={`Alerts (${alertCount})`}
            />
            {alertCount === 0 ? (
              <Alert severity="success" sx={{ fontSize: 13 }}>
                No active alerts.
              </Alert>
            ) : (
              <Alert severity="warning" sx={{ fontSize: 13 }}>
                {alertCount} active alert{alertCount !== 1 ? "s" : ""}. Open the
                Alerts tab to review.
              </Alert>
            )}
          </Paper>
        </Grid>
      </Grid>
    </Stack>
  );
}
