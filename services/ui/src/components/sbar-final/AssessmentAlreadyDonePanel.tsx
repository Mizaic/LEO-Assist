/**
 * Collapsed disclosure for completed guideline actions.
 *
 * Atlas trace:
 *   DI: DI-B3B44F09
 *   DI: DI-613A48DA
 *   DO: DO-124AC2C4
 */
"use client";

import Box from "@mui/material/Box";
import { ProgressiveReveal } from "@leo/design-system";

import MarkdownEditor from "@/components/markdown-editor/MarkdownEditor";

export interface AssessmentAlreadyDonePanelProps {
  doneBody: string;
  count: number;
  testIdPrefix: string;
  fontSize: string;
  bodyPadding: string;
}

export function AssessmentAlreadyDonePanel({
  doneBody,
  count,
  testIdPrefix,
  fontSize,
  bodyPadding,
}: AssessmentAlreadyDonePanelProps): JSX.Element | null {
  if (!doneBody || count < 1) {
    return null;
  }
  return (
    <Box
      sx={{ px: 1.75, pb: 1, pt: 0.25 }}
      data-testid={`${testIdPrefix}-section-assessment-already-done`}
    >
      <ProgressiveReveal summary={`Already done (${count})`}>
        <Box
          sx={{
            "& .md-editor": {
              border: "none",
              background: "transparent",
            },
            "& .md-editor .tiptap": {
              padding: bodyPadding,
              fontSize,
            },
          }}
        >
          <MarkdownEditor mode="view" initialContent={doneBody} minHeight={0} />
        </Box>
      </ProgressiveReveal>
    </Box>
  );
}
