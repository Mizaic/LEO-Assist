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
import type { MissionKPIs } from "@/lib/missionControlApi";
import { getDiagnosticIntervalColour } from "@/lib/pathwayLabels";

interface KPICardProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  tooltip: string;
  highlight?: "success" | "warning" | "error" | "neutral";
}

const HIGHLIGHT_COLOURS = {
  success: "#4caf50",
  warning: "#ff9800",
  error: "#f44336",
  neutral: "text.primary",
};

function KPICard({ icon, label, value, tooltip, highlight = "neutral" }: KPICardProps) {
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

  return (
    <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap" }}>
      <KPICard
        icon={<People fontSize="small" />}
        label="Patients in view"
        value={kpis?.total_patients ?? 0}
        tooltip="Total patients who match your current filters"
      />
      <KPICard
        icon={<CheckCircle fontSize="small" />}
        label="Confirmed cancer"
        value={kpis?.confirmed_cancer ?? 0}
        tooltip="Patients with a completed cancer pathway in this period"
        highlight="neutral"
      />
      <KPICard
        icon={<HighlightOff fontSize="small" />}
        label="Pathway closures"
        value={kpis?.pathway_closures ?? 0}
        tooltip="Patients whose cancer pathway was closed without a cancer diagnosis"
        highlight="neutral"
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
  );
}
