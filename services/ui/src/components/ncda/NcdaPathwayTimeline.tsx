/**
 * NCDA pathway timeline (Stage 9a).
 *
 * Renders a four-anchor pathway in plain language for the reviewer:
 *   Urgent referral -> First hospital visit -> Cancer found / Cancer ruled out -> Treatment began
 *
 * Treatment node hides automatically when outcome is cancer_excluded.
 * Per-interval bands are green/amber/red against per-site typical maxima
 * (Stage 8 config) and national breach thresholds. Citation popovers show
 * the encounter snippet behind each anchor.
 *
 * Reading age 9-11 enforced via @/lib/ncdaLabels.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import * as React from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import Popover from "@mui/material/Popover";

import {
  NCDA_BAND_HELPERS,
  NCDA_BREACH_TOOLTIPS,
  NCDA_COHORT_LABELS,
  NCDA_ROLE_LABELS,
} from "@/lib/ncdaLabels";
import {
  IntervalAssessment,
  NcdaPathway,
  PathwayBands,
  assessPathway,
} from "@/lib/ncdaPathway";

const BAND_COLOR: Record<IntervalAssessment["band"], string> = {
  green: "#34a853",
  amber: "#fbbc04",
  red: "#ea4335",
  unknown: "#9aa0a6",
};

interface AnchorNodeProps {
  label: string;
  date?: string | null;
  citationSnippet?: string | null;
  missing?: boolean;
}

function AnchorNode({ label, date, citationSnippet, missing }: AnchorNodeProps) {
  const [anchorEl, setAnchorEl] = React.useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);

  return (
    <Box
      role="button"
      tabIndex={0}
      onClick={(e) => setAnchorEl(e.currentTarget as HTMLElement)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") setAnchorEl(e.currentTarget as HTMLElement);
      }}
      sx={{
        display: "inline-flex",
        flexDirection: "column",
        alignItems: "center",
        cursor: "pointer",
        outline: "none",
        "&:focus-visible": { boxShadow: "0 0 0 2px #1a73e8" },
      }}
      aria-label={`${label}${date ? `, ${date}` : missing ? ", missing" : ""}`}
    >
      <Box
        sx={{
          width: 24,
          height: 24,
          borderRadius: "50%",
          bgcolor: missing ? "#9aa0a6" : "#1a73e8",
          border: "2px solid #fff",
          boxShadow: "0 0 0 1px rgba(0,0,0,0.2)",
        }}
      />
      <Typography variant="caption" sx={{ mt: 0.5, fontWeight: 600 }}>
        {label}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {missing ? "Not found" : date ?? "-"}
      </Typography>
      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        transformOrigin={{ vertical: "top", horizontal: "center" }}
      >
        <Box sx={{ p: 2, maxWidth: 360 }}>
          <Typography variant="body2">
            {citationSnippet?.trim() || "No quote available."}
          </Typography>
        </Box>
      </Popover>
    </Box>
  );
}

interface IntervalBandProps {
  assessment: IntervalAssessment;
}

function IntervalBand({ assessment }: IntervalBandProps) {
  const color = BAND_COLOR[assessment.band];
  const helper = NCDA_BAND_HELPERS[assessment.band];
  const label =
    assessment.days !== null ? `${assessment.days} days` : "No date";
  const breachKey =
    assessment.intervalKey === "dx_to_treatment"
      ? "treatment_31"
      : assessment.intervalKey === "ftr_to_treatment"
        ? "referral_62"
        : "fds_28";
  const breachTooltip = NCDA_BREACH_TOOLTIPS[breachKey];

  return (
    <Tooltip title={`${helper} ${breachTooltip}`}>
      <Box
        sx={{
          display: "inline-flex",
          alignItems: "center",
          flex: 1,
          minWidth: 80,
          height: 8,
          bgcolor: color,
          borderRadius: 4,
          mx: 1,
          position: "relative",
        }}
        aria-label={`${assessment.intervalKey} ${label}`}
      >
        <Typography
          variant="caption"
          sx={{
            position: "absolute",
            top: -22,
            left: "50%",
            transform: "translateX(-50%)",
            color: "text.secondary",
          }}
        >
          {label}
        </Typography>
      </Box>
    </Tooltip>
  );
}

export interface NcdaPathwayTimelineProps {
  pathway: NcdaPathway;
  bands?: PathwayBands | null;
}

export function NcdaPathwayTimeline({ pathway, bands }: NcdaPathwayTimelineProps) {
  const intervals = assessPathway(pathway, bands ?? null);
  const cohortLabel = NCDA_COHORT_LABELS[pathway.cohort];
  const dxOutcome = pathway.dx?.outcome ?? null;
  const dxLabel =
    dxOutcome === "cancer_excluded"
      ? NCDA_ROLE_LABELS.dx_excluded
      : NCDA_ROLE_LABELS.dx_found;
  const showTreatment = dxOutcome === "cancer_found";
  const ftrToDx = intervals.find((i) => i.intervalKey === "ftr_to_dx");
  const dxToTreatment = intervals.find((i) => i.intervalKey === "dx_to_treatment");

  return (
    <Box
      data-testid="ncda-pathway-timeline"
      sx={{ p: 2, border: "1px solid #e0e0e0", borderRadius: 2 }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h6">Cancer pathway</Typography>
        <Chip
          label={cohortLabel}
          color={pathway.tier === "auto" ? "success" : "warning"}
          size="small"
          data-testid="ncda-cohort-chip"
        />
      </Stack>

      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" mt={4}>
        <AnchorNode
          label={NCDA_ROLE_LABELS.ftr}
          date={pathway.ftr?.date}
          citationSnippet={pathway.ftr?.citation_snippet}
          missing={!pathway.ftr}
        />
        {ftrToDx && <IntervalBand assessment={ftrToDx} />}
        <AnchorNode
          label={NCDA_ROLE_LABELS.seen}
          date={pathway.seen?.date}
          citationSnippet={pathway.seen?.citation_snippet}
          missing={pathway.seen_missing || !pathway.seen}
        />
        <AnchorNode
          label={dxLabel}
          date={pathway.dx?.date}
          citationSnippet={pathway.dx?.citation_snippet}
          missing={!pathway.dx}
        />
        {showTreatment && dxToTreatment && (
          <>
            <IntervalBand assessment={dxToTreatment} />
            <AnchorNode
              label={NCDA_ROLE_LABELS.treatment}
              date={pathway.treatment?.date}
              citationSnippet={pathway.treatment?.citation_snippet}
              missing={pathway.treatment_missing || !pathway.treatment}
            />
          </>
        )}
      </Stack>
    </Box>
  );
}

export default NcdaPathwayTimeline;
