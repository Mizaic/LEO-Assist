/**
 * Consumer-grade patient detail page (EPR view).
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5D3EA371")
 *
 * Shows all episodes and a full activity timeline regardless of episode type.
 * No cancer-specific fields are shown by default.
 */
"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import HealingOutlinedIcon from "@mui/icons-material/HealingOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import type { PatientDetail, TimelineItem } from "@/lib/patientEprApi";
import {
  fetchEprPatientDetail,
  fetchEprPatientTimeline,
} from "@/lib/patientEprApi";
import { ActivityTimeline } from "./ActivityTimeline";

interface Props {
  patientId: string;
  onBack: () => void;
}

function EpisodeCard({
  episode,
}: {
  episode: NonNullable<PatientDetail["episodes"][number]>;
}) {
  const accentColor =
    episode.inferred_outcome === "cancer" ? "#B45309" : "#1E40AF";

  return (
    <Box
      sx={{
        position: "relative",
        borderRadius: "12px",
        border: "1px solid #E2E8F0",
        p: "14px 14px 14px 17px",
        bgcolor: "#FAFAFA",
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
          bgcolor: accentColor,
        }}
      />
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
        <Chip
          label={episode.condition_type ?? "Unspecified"}
          size="small"
          sx={{ fontSize: 11, height: 20 }}
        />
        {episode.status && (
          <Chip
            label={episode.status}
            size="small"
            variant="outlined"
            sx={{ fontSize: 11, height: 20 }}
          />
        )}
        {episode.inferred_outcome && (
          <Chip
            label={episode.inferred_outcome.replace(/_/g, " ")}
            size="small"
            variant="outlined"
            sx={{ fontSize: 11, height: 20, color: accentColor }}
          />
        )}
      </Stack>
      <Stack
        direction="row"
        spacing={2}
        sx={{ mt: 0.75 }}
        flexWrap="wrap"
      >
        {episode.referral_date && (
          <Typography variant="caption" color="text.secondary">
            Referral: {episode.referral_date.slice(0, 10)}
          </Typography>
        )}
        {episode.end_date && (
          <Typography variant="caption" color="text.secondary">
            Ended: {episode.end_date.slice(0, 10)}
          </Typography>
        )}
      </Stack>
    </Box>
  );
}

function DetailSkeleton() {
  return (
    <Stack spacing={2}>
      <Skeleton variant="rounded" height={48} width={200} />
      <Skeleton variant="rounded" height={100} />
      <Skeleton variant="rounded" height={300} />
    </Stack>
  );
}

export function PatientDetailPage({ patientId, onBack }: Props) {
  const [detail, setDetail] = useState<PatientDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [detailLoading, setDetailLoading] = useState(true);
  const [timelineLoading, setTimelineLoading] = useState(true);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  useEffect(() => {
    setDetailLoading(true);
    setDetailError(null);
    fetchEprPatientDetail(patientId)
      .then(setDetail)
      .catch((err) =>
        setDetailError(
          err instanceof Error
            ? err.message
            : "Unable to load patient record."
        )
      )
      .finally(() => setDetailLoading(false));
  }, [patientId]);

  useEffect(() => {
    setTimelineLoading(true);
    setTimelineError(null);
    fetchEprPatientTimeline(patientId)
      .then(setTimeline)
      .catch((err) =>
        setTimelineError(
          err instanceof Error ? err.message : "Unable to load timeline."
        )
      )
      .finally(() => setTimelineLoading(false));
  }, [patientId]);

  return (
    <Box>
      {/* Back button */}
      <Button
        startIcon={<ArrowBackIcon />}
        onClick={onBack}
        size="small"
        sx={{ mb: 2 }}
      >
        Back to patients
      </Button>

      {detailError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {detailError}
        </Alert>
      )}

      {detailLoading && <DetailSkeleton />}

      {!detailLoading && detail && (
        <>
          {/* Patient header */}
          <Box
            sx={{
              borderRadius: "12px",
              border: "1px solid #E2E8F0",
              p: "18px 18px 18px 21px",
              mb: 3,
              bgcolor: "#FFFFFF",
              position: "relative",
            }}
          >
            <Box
              aria-hidden="true"
              sx={{
                position: "absolute",
                left: 0,
                top: 14,
                bottom: 14,
                width: 3,
                borderRadius: 2,
                bgcolor:
                  detail.active_alert_count > 0 ? "#B45309" : "#1E40AF",
              }}
            />
            <Stack
              direction="row"
              justifyContent="space-between"
              alignItems="flex-start"
              flexWrap="wrap"
              gap={1}
            >
              <Box>
                <Typography variant="h6" component="h1" fontWeight={700}>
                  {detail.patient_id}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {detail.birth_date ?? "DOB unknown"} &middot;{" "}
                  {detail.gender ?? "Unknown gender"} &middot;{" "}
                  {detail.practice_name ?? "Practice unknown"}
                </Typography>
              </Box>
              {detail.active_alert_count > 0 && (
                <Chip
                  icon={
                    <WarningAmberOutlinedIcon
                      fontSize="small"
                      sx={{ color: "#B45309 !important" }}
                    />
                  }
                  label={`${detail.active_alert_count} active alert${
                    detail.active_alert_count !== 1 ? "s" : ""
                  }`}
                  sx={{
                    bgcolor: "#FEF3C7",
                    color: "#B45309",
                    fontWeight: 600,
                    fontSize: 12,
                  }}
                />
              )}
            </Stack>
          </Box>

          {/* Episodes */}
          <Stack
            direction="row"
            spacing={1}
            alignItems="center"
            sx={{ mb: 1.5 }}
          >
            <HealingOutlinedIcon sx={{ color: "#047857", fontSize: 18 }} />
            <Typography variant="subtitle2" fontWeight={700}>
              Episodes ({detail.episodes.length})
            </Typography>
          </Stack>

          {detail.episodes.length === 0 ? (
            <Alert severity="info" sx={{ mb: 3 }}>
              No episodes on record for this patient.
            </Alert>
          ) : (
            <Stack spacing={1} sx={{ mb: 3 }}>
              {detail.episodes.map((ep, i) => (
                <EpisodeCard
                  key={ep.episode_id ?? String(i)}
                  episode={ep}
                />
              ))}
            </Stack>
          )}

          <Divider sx={{ mb: 3 }} />

          {/* Activity timeline */}
          <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>
            Activity timeline
          </Typography>
          <ActivityTimeline
            items={timeline}
            loading={timelineLoading}
            error={timelineError}
          />
        </>
      )}
    </Box>
  );
}
