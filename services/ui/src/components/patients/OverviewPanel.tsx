/**
 * OverviewPanel -- clinical summary for the Overview tab.
 *
 * Column 1: Demographics + GP
 * Column 2: Active episodes with stage and outcome
 * Column 3: Problem list (coded entities) + alerts summary
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
import Divider from "@mui/material/Divider";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import HealingOutlinedIcon from "@mui/icons-material/HealingOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import type { PatientDetail, EpisodeSummaryEpr, CodedEntityRow, AssessmentRow } from "@/lib/patientEprApi";
import { fetchCodedEntities, fetchEprAssessments } from "@/lib/patientEprApi";
import { SbarFinalView, type SbarBackgroundPart, type CompletenessFinding } from "@/components/sbar-final";

const ENTITY_TYPE_LABEL: Record<string, string> = {
  disorder: "Conditions",
  disease: "Conditions",
  finding: "Clinical findings",
  situation: "Situations",
  observable: "Lab results",
  procedure: "Procedures",
  medication: "Medications",
  concept: "Other codes",
};

const CONDITION_ACCENT: Record<string, string> = {
  lung: "#1E40AF", breast: "#9D174D", prostate: "#6D28D9",
  colorectal: "#B45309", lower_gi: "#B45309", upper_gi: "#7C3AED",
  skin: "#047857", haematology: "#0369A1", gynaecology: "#BE185D",
  head_and_neck: "#1D4ED8", urology: "#4338CA",
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

function SectionHeader({ icon, title }: { icon: React.ReactElement; title: string }) {
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
      {icon}
      <Typography variant="subtitle2" fontWeight={700} component="h2">{title}</Typography>
    </Stack>
  );
}

function EpisodeCard({ ep }: { ep: EpisodeSummaryEpr }) {
  const accent = accentFor(ep.condition_type);
  const stagingText = [ep.staging_value, ep.staging_early_late].filter(Boolean).join(" - ");
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
        mb: 1.5,
      }}
    >
      <Box
        aria-hidden="true"
        sx={{
          position: "absolute", left: 0, top: 10, bottom: 10,
          width: 3, borderRadius: 2, bgcolor: accent,
        }}
      />
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" sx={{ mb: 0.5 }}>
        <Typography variant="body2" fontWeight={700} sx={{ textTransform: "capitalize" }}>
          {ep.condition_type ?? "Episode"}
        </Typography>
        <Chip
          label={ep.status ?? "unknown"}
          size="small"
          sx={{ height: 18, fontSize: 10, bgcolor: `${statusColor}18`, color: statusColor, textTransform: "capitalize" }}
        />
        {ep.inferred_outcome && (
          <Chip
            label={outcomeLabel(ep.inferred_outcome)}
            size="small"
            sx={{ height: 18, fontSize: 10, bgcolor: `${outcomeColor(ep.inferred_outcome)}15`, color: outcomeColor(ep.inferred_outcome) }}
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

function ProblemList({ patientId }: { patientId: string }) {
  const [entities, setEntities] = useState<CodedEntityRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCodedEntities(patientId)
      .then(setEntities)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [patientId]);

  if (loading) {
    return <Stack spacing={0.75}>{[1, 2, 3].map((i) => <Skeleton key={i} height={22} />)}</Stack>;
  }

  if (entities.length === 0) {
    return (
      <Typography variant="caption" color="text.secondary" fontStyle="italic">
        No coded problems on record.
      </Typography>
    );
  }

  const grouped = entities.reduce<Record<string, CodedEntityRow[]>>((acc, e) => {
    const key = e.entity_type;
    if (!acc[key]) acc[key] = [];
    acc[key].push(e);
    return acc;
  }, {});

  return (
    <Stack spacing={1.5}>
      {Object.entries(grouped).map(([type, items]) => (
        <Box key={type}>
          <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ textTransform: "uppercase", fontSize: 10, display: "block", mb: 0.5 }}>
            {ENTITY_TYPE_LABEL[type] ?? type}
          </Typography>
          <Stack direction="row" flexWrap="wrap" gap={0.5}>
            {items.slice(0, 6).map((e, i) => (
              <Chip
                key={i}
                label={e.name}
                size="small"
                sx={{ height: 20, fontSize: 10, bgcolor: "#F1F5F9", color: "#334155" }}
              />
            ))}
            {items.length > 6 && (
              <Chip
                label={`+${items.length - 6} more`}
                size="small"
                sx={{ height: 20, fontSize: 10, bgcolor: "#E2E8F0", color: "#64748B" }}
              />
            )}
          </Stack>
        </Box>
      ))}
    </Stack>
  );
}

function buildSbarMarkdown(row: AssessmentRow): string {
  if (row.content) return row.content;
  const parts: string[] = [];
  if (row.situation) parts.push(`## Situation\n\n${row.situation}`);
  if (row.background) parts.push(`## Background\n\n${row.background}`);
  if (row.assessment) parts.push(`## Assessment\n\n${row.assessment}`);
  if (row.recommendation) parts.push(`## Recommendation\n\n${row.recommendation}`);
  return parts.join("\n\n");
}

function parseSafe<T>(json: string | null): T | undefined {
  if (!json) return undefined;
  try { return JSON.parse(json) as T; } catch { return undefined; }
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
  const markdown = buildSbarMarkdown(latest);

  if (!markdown.trim()) {
    return (
      <Typography variant="caption" color="text.secondary" fontStyle="italic">
        SBAR draft in progress.
      </Typography>
    );
  }

  const backgroundParts = parseSafe<SbarBackgroundPart[]>(latest.background_parts);
  const completenessFinding = parseSafe<CompletenessFinding>(latest.completeness_result_json);

  return (
    <Box>
      {latest.created_at && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
          {latest.episode_label} -- {latest.created_at.slice(0, 10)}
        </Typography>
      )}
      <SbarFinalView
        markdown={markdown}
        backgroundParts={backgroundParts}
        completenessFinding={completenessFinding}
        dense
        testIdPrefix={`epr-sbar-${latest.assessment_id}`}
      />
    </Box>
  );
}

interface Props {
  detail: PatientDetail | null;
  loading?: boolean;
}

function OverviewSkeleton() {
  return (
    <Grid container spacing={2}>
      {[1, 2, 3].map((i) => (
        <Grid item xs={12} md={4} key={i}>
          <Skeleton variant="rounded" height={220} />
        </Grid>
      ))}
    </Grid>
  );
}

import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";

export function OverviewPanel({ detail, loading }: Props) {
  if (loading || !detail) return <OverviewSkeleton />;

  const nhsDisplay = detail.nhs_number
    ? detail.nhs_number.replace(/(\d{3})(\d{3})(\d{4})/, "$1 $2 $3")
    : "Not available";

  return (
    <Grid container spacing={2}>
      {/* Column 1: Demographics */}
      <Grid item xs={12} md={3}>
        <Paper variant="outlined" sx={{ p: 2, borderRadius: "10px", height: "100%" }}>
          <SectionHeader
            icon={<PersonOutlineIcon sx={{ color: "#1E40AF", fontSize: 18 }} />}
            title="Patient details"
          />
          <Stack spacing={1.25}>
            {[
              { label: "Date of birth", value: detail.birth_date?.slice(0, 10) ?? "Not recorded" },
              { label: "Sex", value: detail.gender ?? "Not recorded" },
              { label: "GP practice", value: detail.practice_name ?? "Not recorded" },
            ].map(({ label, value }) => (
              <Box key={label}>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
                <Typography variant="body2" fontWeight={500}>{value}</Typography>
              </Box>
            ))}
          </Stack>
          <Divider sx={{ my: 2 }} />
          <Box>
            <Typography variant="caption" color="text.secondary">NHS number</Typography>
            <Typography variant="body2" fontWeight={500} fontFamily="monospace">
              {nhsDisplay}
            </Typography>
          </Box>
        </Paper>
      </Grid>

      {/* Column 2: Episodes */}
      <Grid item xs={12} md={3}>
        <Paper variant="outlined" sx={{ p: 2, borderRadius: "10px", height: "100%" }}>
          <SectionHeader
            icon={<HealingOutlinedIcon sx={{ color: "#047857", fontSize: 18 }} />}
            title={`Episodes (${detail.episodes.length})`}
          />
          {detail.episodes.length === 0 ? (
            <Alert severity="info" sx={{ fontSize: 13 }}>No episodes recorded.</Alert>
          ) : (
            detail.episodes.map((ep, i) => (
              <EpisodeCard key={ep.episode_id ?? String(i)} ep={ep} />
            ))
          )}
        </Paper>
      </Grid>

      {/* Column 3: SBAR summary */}
      <Grid item xs={12} md={3}>
        <Paper variant="outlined" sx={{ p: 2, borderRadius: "10px", height: "100%" }}>
          <SectionHeader
            icon={<AssessmentOutlinedIcon sx={{ color: "#047857", fontSize: 18 }} />}
            title="Latest SBAR"
          />
          <SbarSummaryPanel patientId={detail.patient_id} />
        </Paper>
      </Grid>

      {/* Column 4: Problem list + alerts */}
      <Grid item xs={12} md={3}>
        <Paper variant="outlined" sx={{ p: 2, borderRadius: "10px", height: "100%" }}>
          <SectionHeader
            icon={<LocalHospitalOutlinedIcon sx={{ color: "#6D28D9", fontSize: 18 }} />}
            title="Problem list"
          />
          <ProblemList patientId={detail.patient_id} />

          <Divider sx={{ my: 2 }} />

          <SectionHeader
            icon={<WarningAmberOutlinedIcon sx={{ color: "#B45309", fontSize: 18 }} />}
            title={`Alerts (${detail.active_alert_count})`}
          />
          {detail.active_alert_count === 0 ? (
            <Alert severity="success" sx={{ fontSize: 13 }}>No active alerts.</Alert>
          ) : (
            <Alert severity="warning" sx={{ fontSize: 13 }}>
              {detail.active_alert_count} active alert{detail.active_alert_count !== 1 ? "s" : ""}.
              Open the Alerts tab to review.
            </Alert>
          )}
        </Paper>
      </Grid>
    </Grid>
  );
}
