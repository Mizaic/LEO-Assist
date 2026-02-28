"use client";

import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import { Virtuoso } from "react-virtuoso";
import type { Episode, PathwayRisk, RiskLevel } from "@/lib/pathwayRisk";

type EpisodeWithRisk = Episode & { risk: PathwayRisk };

const RISK_CONFIG: Record<
  RiskLevel,
  { label: string; chipColor: "error" | "warning" | "success" | "default" }
> = {
  breached: { label: "Overdue", chipColor: "error" },
  "at-risk": { label: "At risk", chipColor: "warning" },
  "on-track": { label: "On track", chipColor: "success" },
  completed: { label: "Completed", chipColor: "default" },
  unknown: { label: "Unknown", chipColor: "default" },
};

const BORDER_COLORS: Record<RiskLevel, string> = {
  breached: "#dc2626",
  "at-risk": "#d97706",
  "on-track": "#16a34a",
  completed: "#d1d5db",
  unknown: "#d1d5db",
};

const MILESTONE_LABELS: Record<string, string> = {
  presentation: "Presentation",
  referral: "Referral",
  first_clinic: "First Specialist Clinic",
  diagnosis: "Diagnosis",
  treatment_decision: "Treatment Decision",
  first_treatment: "First Treatment",
};

function BreachCountdown({ risk }: { risk: PathwayRisk }) {
  const worst = risk.worstBreach;
  if (!worst || worst.achieved) return null;

  const remaining = worst.daysRemaining ?? 0;

  if (remaining < 0) {
    return (
      <Typography
        variant="caption"
        sx={{ color: "error.main", fontWeight: 600 }}
      >
        {worst.target.label}: {Math.abs(remaining)} days overdue
      </Typography>
    );
  }

  return (
    <Typography
      variant="caption"
      sx={{
        color: remaining <= 7 ? "error.main" : "warning.main",
        fontWeight: 600,
      }}
    >
      {worst.target.label}: {remaining} days left
    </Typography>
  );
}

function NextMilestone({ milestoneName }: { milestoneName: string | null }) {
  if (!milestoneName) return null;
  return (
    <Typography variant="caption" color="text.secondary">
      Next: {MILESTONE_LABELS[milestoneName] ?? milestoneName}
    </Typography>
  );
}

export default function EpisodeList({
  episodes,
  selected,
  onSelect,
}: {
  episodes: EpisodeWithRisk[];
  selected: EpisodeWithRisk | null;
  onSelect: (e: EpisodeWithRisk) => void;
}) {
  if (!episodes.length) {
    return (
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: 200,
        }}
      >
        <Typography variant="body2" color="text.secondary">
          No referral pathways match your filters.
        </Typography>
      </Box>
    );
  }

  return (
    <Virtuoso
      data={episodes}
      style={{ height: "70vh" }}
      itemContent={(_index, ep) => {
        const isSelected = selected?.episode_id === ep.episode_id;
        const riskCfg = RISK_CONFIG[ep.risk.level];
        const borderColor = BORDER_COLORS[ep.risk.level];

        return (
          <Box sx={{ pb: 1 }}>
            <Card
              onClick={() => onSelect(ep)}
              sx={{
                cursor: "pointer",
                borderLeft: "4px solid",
                borderLeftColor: borderColor,
                border: isSelected ? "2px solid" : undefined,
                borderColor: isSelected ? "primary.main" : undefined,
                bgcolor: isSelected ? "primary.50" : "background.paper",
                transition: "box-shadow 0.15s ease",
                "&:hover": { boxShadow: 3 },
              }}
            >
              <Box sx={{ px: 2, py: 1.5 }}>
                <Box
                  sx={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    mb: 0.5,
                  }}
                >
                  <Typography
                    variant="body2"
                    sx={{ fontWeight: 600, fontSize: "0.85rem" }}
                  >
                    {ep.condition_type || "Unknown type"}
                  </Typography>
                  <Box sx={{ display: "flex", gap: 0.5, alignItems: "center" }}>
                    {ep.status === "merged" && (
                      <Chip label="Merged" size="small" variant="outlined" />
                    )}
                    {ep.merged_from && ep.merged_from.length > 0 && (
                      <Chip label="Primary" size="small" color="info" />
                    )}
                    {ep.needs_review && (
                      <Chip label="Review" size="small" color="warning" variant="outlined" />
                    )}
                    <Chip
                      label={riskCfg.label}
                      size="small"
                      color={riskCfg.chipColor}
                    />
                  </Box>
                </Box>

                <Box
                  sx={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    mb: 0.25,
                  }}
                >
                  <Typography variant="caption" color="text.secondary">
                    {ep.patient_id && `Patient: ${ep.patient_id}`}
                    {ep.referral_date && ` | Referred: ${ep.referral_date}`}
                    {ep.confidence != null && ` | Confidence: ${ep.confidence}%`}
                  </Typography>
                </Box>

                <Box
                  sx={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 1,
                  }}
                >
                  <BreachCountdown risk={ep.risk} />
                  <NextMilestone
                    milestoneName={ep.risk.nextExpectedMilestone}
                  />
                </Box>
              </Box>
            </Card>
          </Box>
        );
      }}
    />
  );
}
