/**
 * Care rule and missing-information outcomes for Decide.
 *
 * Atlas: DI-49BA8E04 / VT-592D30E9
 *
 * Atlas trace:
 *   DO: DO-7B63A6BE
 *   DI: DI-49BA8E04
 *   Risks: R-823853D7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7B63A6BE")
 */
"use client";

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { StageStory } from "./inspector/stageEvidence";

interface Props {
  guideline: StageStory | null;
  completeness: StageStory | null;
}

export function DecideOutcomes({ guideline, completeness }: Props) {
  if (!guideline && !completeness) return null;
  return (
    <Stack spacing={1.25} sx={{ mb: 2 }} data-testid="validation-lab-decide-outcomes">
      <OutcomeCard title="Care rule" story={guideline} />
      <OutcomeCard title="Missing information" story={completeness} />
    </Stack>
  );
}

function OutcomeCard({ title, story }: { title: string; story: StageStory | null }) {
  if (!story) return null;
  const lines = story.lines.length ? story.lines : [story.empty || "No result yet."];
  return (
    <Box
      sx={{
        p: 1.25,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: "8px",
        bgcolor: "#FFFFFF",
      }}
    >
      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>
        {title}
      </Typography>
      {lines.map((line) => (
        <Typography key={line} variant="body2" color="text.secondary">
          {line}
        </Typography>
      ))}
    </Box>
  );
}
