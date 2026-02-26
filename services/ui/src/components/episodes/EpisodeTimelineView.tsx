"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Stepper from "@mui/material/Stepper";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import StepContent from "@mui/material/StepContent";

const MILESTONE_ORDER = [
  "presentation",
  "referral",
  "first_clinic",
  "diagnosis",
  "treatment_decision",
  "first_treatment",
];

const MILESTONE_LABELS: Record<string, string> = {
  presentation: "Presentation",
  referral: "Referral",
  first_clinic: "First Specialist Clinic",
  diagnosis: "Diagnosis",
  treatment_decision: "Treatment Decision",
  first_treatment: "First Treatment",
};

const MILESTONE_COLORS: Record<string, string> = {
  presentation: "#6366f1",
  referral: "#14B8A6",
  first_clinic: "#f59e0b",
  diagnosis: "#1F3A8A",
  treatment_decision: "#8b5cf6",
  first_treatment: "#16a34a",
};

interface Milestone {
  encounter_id: string;
  date: string;
  milestone_type: string;
}

interface Episode {
  episode_id: string;
  patient_id?: string;
  cancer_type: string;
  status: string;
  referral_date?: string;
  milestones?: Milestone[];
}

function daysBetween(d1: string, d2: string): number | null {
  try {
    const ms = new Date(d2).getTime() - new Date(d1).getTime();
    return Math.round(ms / 86400000);
  } catch {
    return null;
  }
}

export default function EpisodeTimelineView({ episode }: { episode: Episode }) {
  const milestones = episode.milestones ?? [];
  const sorted = [...milestones].sort((a, b) => {
    const ia = MILESTONE_ORDER.indexOf(a.milestone_type);
    const ib = MILESTONE_ORDER.indexOf(b.milestone_type);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 3 }}>
        <Typography variant="h6">{episode.cancer_type || "Episode"}</Typography>
        <Chip
          label={episode.status}
          size="small"
          color={episode.status === "active" ? "success" : "default"}
          sx={{ textTransform: "capitalize" }}
        />
      </Box>

      <Box sx={{ display: "flex", gap: 2, mb: 3, flexWrap: "wrap" }}>
        <InfoChip label="Episode" value={episode.episode_id} />
        {episode.patient_id && <InfoChip label="Patient" value={episode.patient_id} />}
        {episode.referral_date && <InfoChip label="Referral" value={episode.referral_date} />}
      </Box>

      {sorted.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No milestones recorded for this episode yet.
        </Typography>
      ) : (
        <Stepper orientation="vertical" activeStep={sorted.length - 1}>
          {sorted.map((m, idx) => {
            const prev = idx > 0 ? sorted[idx - 1] : null;
            const gap = prev ? daysBetween(prev.date, m.date) : null;
            const color = MILESTONE_COLORS[m.milestone_type] ?? "#64748b";
            return (
              <Step key={m.encounter_id + m.milestone_type} completed>
                <StepLabel
                  StepIconProps={{
                    sx: { color: `${color} !important` },
                  }}
                >
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <Typography sx={{ fontWeight: 600, fontSize: "0.9rem" }}>
                      {MILESTONE_LABELS[m.milestone_type] ?? m.milestone_type}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {m.date}
                    </Typography>
                    {gap != null && (
                      <Chip
                        label={`${gap}d`}
                        size="small"
                        variant="outlined"
                        sx={{ fontSize: "0.7rem", height: 20, ml: 0.5 }}
                        color={gap > 60 ? "error" : "default"}
                      />
                    )}
                  </Box>
                </StepLabel>
                <StepContent>
                  <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>
                    {m.encounter_id}
                  </Typography>
                </StepContent>
              </Step>
            );
          })}
        </Stepper>
      )}
    </Box>
  );
}

function InfoChip({ label, value }: { label: string; value: string }) {
  return (
    <Box
      sx={{
        px: 1.5,
        py: 0.5,
        borderRadius: 1.5,
        bgcolor: "grey.100",
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
      }}
    >
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
        {label}:
      </Typography>
      <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: "0.75rem" }}>
        {value}
      </Typography>
    </Box>
  );
}
