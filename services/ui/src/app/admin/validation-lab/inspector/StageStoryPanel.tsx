/**
 * Plain-English evidence for one Validation Lab pipeline step.
 *
 * Atlas: DI-257D6883 / DO-158BE606 / VT-825F42CC
 */
"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import type { LabWorkItem } from "../inspectorTypes";
import type { StageStory } from "./stageEvidence";
import { StageWorkPreview } from "./StageWorkPreview";

interface Props {
  story: StageStory;
  items?: LabWorkItem[];
  loading?: boolean;
  onMarkWrong?: (text: string) => void;
}

export function StageStoryPanel({ story, items, loading, onMarkWrong }: Props) {
  const shown = items ?? story.items ?? [];
  const empty = Boolean(story.empty) && !story.lines.length && !shown.length;
  return (
    <Box data-testid="validation-lab-stage-evidence" sx={{ mb: 1.5 }}>
      {story.headline && (shown.length || story.kind === "persist") ? (
        <Typography variant="body2" fontWeight={600} sx={{ mb: 0.75 }}>
          {story.headline}
        </Typography>
      ) : null}
      {empty ? (
        <Typography variant="body2" color="text.secondary">
          {story.empty}
        </Typography>
      ) : null}
      {story.lines.map((line) => (
        <Typography key={line} variant="body2" sx={{ mb: 0.5 }}>
          {line}
        </Typography>
      ))}
      {shown.length ? (
        <StageWorkPreview
          preview={{ headline: "", items: shown }}
          loading={Boolean(loading)}
          onMarkWrong={onMarkWrong}
        />
      ) : null}
    </Box>
  );
}
