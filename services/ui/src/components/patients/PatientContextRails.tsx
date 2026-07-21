/**
 * Left episode rail and right clinical-context rail for PatientShell.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import type { PatientDetail, CodedEntityRow } from "@/lib/patientEprApi";
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

function railAccent(type: string | null): string {
  const key = (type ?? "").toLowerCase().replace(/ /g, "_");
  return CONDITION_ACCENT[key] ?? "#475569";
}

function outcomeLabel(outcome: string | null): string {
  const o = (outcome ?? "").toLowerCase();
  if (o === "cancer") return "Cancer confirmed";
  if (o === "benign") return "Benign";
  return outcome ?? "";
}

function RailSection({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography
        variant="caption"
        fontWeight={700}
        color="text.secondary"
        sx={{ textTransform: "uppercase", fontSize: 10, display: "block", mb: 0.5 }}
      >
        {label}
      </Typography>
      {children}
    </Box>
  );
}

export function ContextRail({
  detail,
  loading,
  entities,
  entitiesLoading,
}: {
  detail: PatientDetail | null;
  loading: boolean;
  entities: CodedEntityRow[];
  entitiesLoading: boolean;
}) {
  if (loading || !detail) {
    return (
      <Stack spacing={1.5} sx={{ p: 2 }}>
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} variant="rounded" height={72} />
        ))}
      </Stack>
    );
  }

  const medications = entities
    .filter((e) => e.entity_type === "medication")
    .slice(0, 5);

  return (
    <Box sx={{ p: 2 }} data-testid="epr-context-rail">
      <RailSection label="Episodes">
        {detail.episodes.length === 0 ? (
          <Typography variant="caption" color="text.secondary" fontStyle="italic">
            No episodes recorded.
          </Typography>
        ) : (
          detail.episodes.slice(0, 3).map((ep, i) => {
            const accent = railAccent(ep.condition_type);
            return (
              <Box
                key={ep.episode_id ?? i}
                sx={{
                  position: "relative",
                  border: "1px solid #E2E8F0",
                  borderRadius: "8px",
                  p: "10px 10px 10px 14px",
                  mb: 1.5,
                  bgcolor: "#FAFAFA",
                }}
              >
                <Box
                  aria-hidden="true"
                  sx={{
                    position: "absolute",
                    left: 0,
                    top: 8,
                    bottom: 8,
                    width: 3,
                    borderRadius: 2,
                    bgcolor: accent,
                  }}
                />
                <Typography
                  variant="caption"
                  fontWeight={700}
                  color={accent}
                  sx={{ textTransform: "capitalize", display: "block" }}
                >
                  {ep.condition_type ?? "Episode"}
                </Typography>
                {ep.inferred_outcome && (
                  <Typography variant="caption" color="text.secondary">
                    {outcomeLabel(ep.inferred_outcome)}
                  </Typography>
                )}
                {ep.referral_date && (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: "block" }}
                  >
                    Referred {ep.referral_date.slice(0, 10)}
                  </Typography>
                )}
                {ep.staging_value && (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: "block" }}
                  >
                    Stage {ep.staging_value}
                    {ep.staging_early_late ? ` (${ep.staging_early_late})` : ""}
                  </Typography>
                )}
              </Box>
            );
          })
        )}
      </RailSection>

      {!entitiesLoading && medications.length > 0 && (
        <>
          <Divider sx={{ mb: 2 }} />
          <RailSection label="Medications">
            <Stack spacing={0.5}>
              {medications.map((e, i) => (
                <Typography key={i} variant="caption" color="text.secondary">
                  {e.name}
                </Typography>
              ))}
            </Stack>
          </RailSection>
        </>
      )}
    </Box>
  );
}

export function ClinicalContextRail({
  entities,
  entitiesLoading,
  alertCount,
  onOpenAlerts,
}: {
  entities: CodedEntityRow[];
  entitiesLoading: boolean;
  alertCount: number;
  onOpenAlerts: () => void;
}) {
  const problems = entities.filter((e) => e.entity_type !== "medication");

  return (
    <Box sx={{ p: 2 }} data-testid="epr-clinical-context-rail">
      <Paper variant="outlined" sx={{ p: 1.5, borderRadius: "8px", mb: 1.5 }}>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <LocalHospitalOutlinedIcon sx={{ fontSize: 16, color: "#6D28D9" }} />
          <Typography variant="caption" fontWeight={700}>
            Problem list
          </Typography>
        </Stack>
        <ProblemListView
          entities={problems}
          loading={entitiesLoading}
          maxPerGroup={8}
        />
      </Paper>

      <Paper variant="outlined" sx={{ p: 1.5, borderRadius: "8px" }}>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <WarningAmberOutlinedIcon sx={{ fontSize: 16, color: "#B45309" }} />
          <Typography variant="caption" fontWeight={700}>
            Alerts ({alertCount})
          </Typography>
        </Stack>
        {alertCount === 0 ? (
          <Alert severity="success" sx={{ fontSize: 12, py: 0.5 }}>
            No active alerts.
          </Alert>
        ) : (
          <Alert
            severity="warning"
            sx={{ fontSize: 12, py: 0.5, cursor: "pointer" }}
            onClick={onOpenAlerts}
          >
            {alertCount} active alert{alertCount !== 1 ? "s" : ""}. Open the
            Alerts tab to review.
          </Alert>
        )}
      </Paper>
    </Box>
  );
}
