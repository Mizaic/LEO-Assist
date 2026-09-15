/**
 * OverviewPanel -- clinical summary for the Overview tab.
 *
 * Order: next job (alerts), Latest SBAR, episodes, problems and medicines.
 * Demographics live in PatientHeader.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import HealingOutlinedIcon from "@mui/icons-material/HealingOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import MedicationOutlinedIcon from "@mui/icons-material/MedicationOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import { EmptyState, NudgeStrip, color, radius } from "@leo/design-system";
import type {
  PatientDetail,
  AssessmentRow,
  CodedEntityRow,
} from "@/lib/patientEprApi";
import { fetchEprAssessments } from "@/lib/patientEprApi";
import { LeoSbarHost } from "@/components/sbar-final";
import { OverviewEpisodeCard } from "./OverviewEpisodeCard";
import { ProblemListView } from "./ProblemListView";

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

function Surface({
  children,
  testId,
}: {
  children: React.ReactNode;
  testId?: string;
}) {
  return (
    <Box
      data-testid={testId}
      sx={{
        p: "18px",
        borderRadius: `${radius.md}px`,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: color.surface.raised,
      }}
    >
      {children}
    </Box>
  );
}

function SbarSummaryPanel({ patientId }: { patientId: string }) {
  const [rows, setRows] = useState<AssessmentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchEprAssessments(patientId)
      .then(setRows)
      .catch((err) =>
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load the latest SBAR.",
        ),
      )
      .finally(() => setLoading(false));
  }, [patientId]);

  if (loading) return <Skeleton variant="rounded" height={120} />;
  if (error) return <Alert severity="error">{error}</Alert>;
  if (rows.length === 0) {
    return (
      <Typography variant="body2" sx={{ color: color.text.caption }}>
        No SBAR summaries on record.
      </Typography>
    );
  }

  const latest = rows[0];
  if (!latest.assessment_id) {
    return (
      <Typography variant="body2" sx={{ color: color.text.caption }}>
        SBAR draft in progress.
      </Typography>
    );
  }

  return (
    <Box>
      {latest.created_at && (
        <Typography
          variant="caption"
          sx={{ display: "block", mb: 1, color: color.text.caption }}
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
  entities?: CodedEntityRow[];
  entitiesLoading?: boolean;
  onOpenAlerts?: () => void;
}

function NextJobNudge({
  count,
  onOpenAlerts,
}: {
  count: number;
  onOpenAlerts?: () => void;
}) {
  if (count <= 0) return null;
  return (
    <Box data-testid="epr-next-job">
      <NudgeStrip
        severity="warning"
        icon={<WarningAmberOutlinedIcon fontSize="small" />}
        message={`${count} alert${count !== 1 ? "s" : ""} need a look.`}
        actionLabel="Open alerts"
        actionAriaLabel="Open the Alerts tab"
        onAction={onOpenAlerts}
      />
    </Box>
  );
}

function EpisodesSection({
  episodes,
}: {
  episodes: PatientDetail["episodes"];
}) {
  return (
    <Surface>
      <SectionHeader
        icon={
          <HealingOutlinedIcon sx={{ color: color.status.success, fontSize: 18 }} />
        }
        title={`Episodes (${episodes.length})`}
      />
      {episodes.length === 0 ? (
        <EmptyState
          icon={<HealingOutlinedIcon />}
          title="No episodes recorded"
          body="New episodes will show here when this patient is referred."
          data-testid="epr-episodes-empty"
        />
      ) : (
        <Grid container spacing={1.5}>
          {episodes.map((ep, i) => (
            <Grid size={{ xs: 12, sm: 6, lg: 4 }} key={ep.episode_id ?? String(i)}>
              <OverviewEpisodeCard ep={ep} index={i} />
            </Grid>
          ))}
        </Grid>
      )}
    </Surface>
  );
}

function MedicinesList({
  medicines,
  loading,
}: {
  medicines: CodedEntityRow[];
  loading: boolean;
}) {
  if (loading) return <Skeleton variant="rounded" height={72} />;
  if (medicines.length === 0) {
    return (
      <Typography variant="body2" sx={{ color: color.text.caption }}>
        No medicines recorded.
      </Typography>
    );
  }
  return (
    <Stack spacing={0.75} component="ul" sx={{ m: 0, pl: 2 }}>
      {medicines.map((e, i) => (
        <Typography
          key={`${e.name}-${i}`}
          component="li"
          variant="body2"
          sx={{ color: color.text.secondary }}
        >
          {e.name}
        </Typography>
      ))}
    </Stack>
  );
}

function ContextSection({
  patientId,
  problems,
  medicines,
  entitiesLoading,
}: {
  patientId: string;
  problems: CodedEntityRow[];
  medicines: CodedEntityRow[];
  entitiesLoading: boolean;
}) {
  return (
    <Grid container spacing={2} data-testid="epr-overview-context">
      <Grid size={{ xs: 12, md: 7 }}>
        <Surface>
          <SectionHeader
            icon={
              <LocalHospitalOutlinedIcon
                sx={{ color: color.brand.secondaryHover, fontSize: 18 }}
              />
            }
            title="Problem list"
          />
          <ProblemListView
            patientId={patientId}
            entities={problems}
            loading={entitiesLoading}
          />
        </Surface>
      </Grid>
      <Grid size={{ xs: 12, md: 5 }}>
        <Surface testId="epr-overview-medicines">
          <SectionHeader
            icon={
              <MedicationOutlinedIcon sx={{ color: color.status.info, fontSize: 18 }} />
            }
            title="Medicines"
          />
          <MedicinesList medicines={medicines} loading={entitiesLoading} />
        </Surface>
      </Grid>
    </Grid>
  );
}

export function OverviewPanel({
  detail,
  loading,
  entities = [],
  entitiesLoading = false,
  onOpenAlerts,
}: Props) {
  if (loading || !detail) {
    return (
      <Stack spacing={2}>
        <Skeleton variant="rounded" height={88} />
        <Skeleton variant="rounded" height={320} />
      </Stack>
    );
  }

  const problems = entities.filter((e) => e.entity_type !== "medication");
  const medicines = entities.filter((e) => e.entity_type === "medication");

  return (
    <Stack spacing={2} data-testid="epr-overview-panel">
      <NextJobNudge count={detail.active_alert_count} onOpenAlerts={onOpenAlerts} />
      <Surface testId="epr-latest-sbar">
        <SectionHeader
          icon={
            <AssessmentOutlinedIcon sx={{ color: color.status.success, fontSize: 18 }} />
          }
          title="Latest SBAR"
        />
        <SbarSummaryPanel patientId={detail.patient_id} />
      </Surface>
      <EpisodesSection episodes={detail.episodes} />
      <ContextSection
        patientId={detail.patient_id}
        problems={problems}
        medicines={medicines}
        entitiesLoading={entitiesLoading}
      />
    </Stack>
  );
}
