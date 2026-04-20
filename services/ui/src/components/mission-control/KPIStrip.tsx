/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-EE78E305
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EE78E305")
 */
"use client";

import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import Skeleton from "@mui/material/Skeleton";
import {
  People,
  CheckCircle,
  HighlightOff,
  Schedule,
  VerifiedUser,
  PendingActions,
} from "@mui/icons-material";
import type { MissionKPICohort, MissionKPIs } from "@/lib/missionControlApi";
import { getDiagnosticIntervalColour } from "@/lib/pathwayLabels";

interface KPICardProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  tooltip: string;
  highlight?: "success" | "warning" | "error" | "neutral";
  subValue?: string;
}

const HIGHLIGHT_COLOURS = {
  success: "#4caf50",
  warning: "#ff9800",
  error: "#f44336",
  neutral: "text.primary",
};

function KPICard({
  icon,
  label,
  value,
  tooltip,
  highlight = "neutral",
  subValue,
}: KPICardProps) {
  const colour = HIGHLIGHT_COLOURS[highlight];
  return (
    <Tooltip title={tooltip} arrow placement="bottom">
      <Card
        elevation={0}
        sx={{
          flex: 1,
          minWidth: 120,
          px: 2,
          py: 1.5,
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 2,
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          cursor: "default",
        }}
      >
        <Box sx={{ color: colour, display: "flex" }}>{icon}</Box>
        <Box>
          <Typography
            variant="h5"
            sx={{ fontWeight: 700, color: colour, lineHeight: 1.1 }}
          >
            {value}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
            {label}
          </Typography>
          {subValue ? (
            <Typography
              variant="caption"
              color="text.secondary"
              data-testid="kpi-sub-value"
              sx={{ display: "block", whiteSpace: "nowrap", fontSize: 11 }}
            >
              {subValue}
            </Typography>
          ) : null}
        </Box>
      </Card>
    </Tooltip>
  );
}

function KPISkeleton() {
  return (
    <Card
      elevation={0}
      sx={{
        flex: 1,
        minWidth: 120,
        px: 2,
        py: 1.5,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
      }}
    >
      <Skeleton width={48} height={32} />
      <Skeleton width={80} height={14} />
    </Card>
  );
}

interface Props {
  kpis: MissionKPIs | null;
  loading: boolean;
}

export default function KPIStrip({ kpis, loading }: Props) {
  if (loading) {
    return (
      <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap" }}>
        {Array.from({ length: 6 }).map((_, i) => (
          <KPISkeleton key={i} />
        ))}
      </Box>
    );
  }

  const medianDays = kpis?.median_diagnostic_interval_days ?? null;
  const intervalColour = getDiagnosticIntervalColour(medianDays);
  const safetyRate = kpis?.safety_netting_rate ?? 0;
  const safetyPct = Math.round(safetyRate * 100);
  const safetyColour: "success" | "warning" | "error" =
    safetyRate >= 0.8 ? "success" : safetyRate >= 0.5 ? "warning" : "error";
  const needsReview = kpis?.needs_review_count ?? 0;

  // DI-LEO-AI-214: headline figure is a PATIENT count to match the
  // tooltip ("Patients with..."). Episode count appears as a sub-line
  // because a patient can have several pathways open in the window.
  const inView = kpis?.total_patients ?? 0;
  const confirmedPatients = kpis?.confirmed_cancer_patients ?? 0;
  const confirmedEpisodes = kpis?.confirmed_cancer ?? 0;
  const closurePatients = kpis?.pathway_closure_patients ?? 0;
  const closureEpisodes = kpis?.pathway_closures ?? 0;

  // DI-LEO-AI-214: surface the cohort denominator so users always know
  // how many patients exist in the dataset behind the filtered view,
  // and why some are hidden (no pathway / outside window / missing
  // referral date).
  const cohort = kpis?.cohort;
  const cohortTotal = cohort?.total_patients ?? 0;
  const excludedTotal = cohort?.excluded_total ?? 0;
  const cohortLine = cohort
    ? buildCohortDenominatorLine(inView, cohort)
    : null;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap" }}>
        <KPICard
          icon={<People fontSize="small" />}
          label="Patients in view"
          value={inView}
          tooltip="Patients with at least one pathway whose referral date falls in the selected period."
          subValue={
            cohortTotal > 0 && excludedTotal > 0
              ? `of ${cohortTotal} in cohort`
              : undefined
          }
        />
        <KPICard
          icon={<CheckCircle fontSize="small" />}
          label="Confirmed cancer"
          value={confirmedPatients}
          tooltip="Patients with at least one pathway in the selected period where a cancer diagnosis was recorded (NCDA definition)."
          highlight="neutral"
          subValue={
            confirmedEpisodes > 0
              ? `${confirmedEpisodes} pathway${
                  confirmedEpisodes === 1 ? "" : "s"
                }`
              : undefined
          }
        />
        <KPICard
          icon={<HighlightOff fontSize="small" />}
          label="Pathway closures"
          value={closurePatients}
          tooltip="Patients with at least one pathway in the selected period that closed without a cancer diagnosis (benign, no follow-up, or stale)."
          highlight="neutral"
          subValue={
            closureEpisodes > 0
              ? `${closureEpisodes} pathway${
                  closureEpisodes === 1 ? "" : "s"
                }`
              : undefined
          }
        />
        <KPICard
          icon={<Schedule fontSize="small" />}
          label="Median time to diagnosis"
          value={medianDays != null ? `${medianDays}d` : "--"}
          tooltip="Median number of days from first GP referral to cancer diagnosis (NCDA 62-day target)"
          highlight={intervalColour}
        />
        <KPICard
          icon={<VerifiedUser fontSize="small" />}
          label="Safety netting rate"
          value={`${safetyPct}%`}
          tooltip="Percentage of pathways with a safety netting milestone recorded (target: 80%)"
          highlight={safetyColour}
        />
        <KPICard
          icon={<PendingActions fontSize="small" />}
          label="Needs review"
          value={needsReview}
          tooltip="Episodes that have not yet been marked as reviewed by an auditor"
          highlight={needsReview > 0 ? "warning" : "success"}
        />
      </Box>
      {cohortLine ? (
        <Typography
          data-testid="kpi-cohort-denominator"
          variant="caption"
          color="text.secondary"
          sx={{ pl: 0.5 }}
        >
          {cohortLine}
        </Typography>
      ) : null}
    </Box>
  );
}

/**
 * DI-LEO-AI-214: format the cohort denominator line as a single plain-
 * English sentence (reading age 9-11). Examples:
 *   "Showing 89 of 107 patients - 18 hidden (8 no pathway, 7 missing
 *    referral date, 3 outside the date range)."
 *   "Showing all 107 patients in the cohort."
 */
export function buildCohortDenominatorLine(
  inView: number,
  cohort: MissionKPICohort,
): string {
  if (cohort.total_patients <= 0) return "";
  if (cohort.excluded_total <= 0) {
    return `Showing all ${cohort.total_patients} patients in the cohort.`;
  }
  const reasons: string[] = [];
  if (cohort.excluded_no_pathway > 0) {
    reasons.push(`${cohort.excluded_no_pathway} no pathway`);
  }
  if (cohort.excluded_missing_referral_date > 0) {
    reasons.push(
      `${cohort.excluded_missing_referral_date} missing referral date`,
    );
  }
  if (cohort.excluded_outside_window > 0) {
    reasons.push(
      `${cohort.excluded_outside_window} outside the date range`,
    );
  }
  const reasonText = reasons.length ? ` (${reasons.join(", ")})` : "";
  return (
    `Showing ${inView} of ${cohort.total_patients} patients - ` +
    `${cohort.excluded_total} hidden${reasonText}.`
  );
}
