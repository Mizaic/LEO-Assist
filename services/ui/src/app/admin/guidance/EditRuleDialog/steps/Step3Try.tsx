"use client";

/**
 * Step 3 -- "Try it on real patients".
 *
 * Hosts the existing TestPatientsPanel unchanged. The panel handles
 * its own state (saved patients, replay reports, sandbox compile,
 * Build / Generate dialogs). The reason for moving it into its own
 * step is purely about focus -- the test-patients section dominates
 * vertical space and used to push the actual rule edit off screen.
 *
 * Design Controls: DI-LEO-AI-234, DO-LEO-AI-234, VT-LEO-AI-510.
 */

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import TestPatientsPanel from "../TestPatientsPanel";
import { STEP_HELPERS, STEP_TITLES } from "../copy";

interface Props {
  ruleId: string;
  guidelineId?: string;
  ruleSignature: string;
  ruleName?: string;
  recommendationText?: string;
  draftRule: Record<string, unknown> | null;
}

export default function Step3Try({
  ruleId,
  guidelineId,
  ruleSignature,
  ruleName,
  recommendationText,
  draftRule,
}: Props) {
  return (
    <Stack spacing={2} sx={{ minWidth: 0 }}>
      <Box>
        <Typography
          variant="h6"
          component="h3"
          sx={{ fontWeight: 700, fontSize: "1.05rem" }}
        >
          {STEP_TITLES.try}
        </Typography>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ lineHeight: 1.5, mt: 0.5 }}
        >
          {STEP_HELPERS.try}
        </Typography>
      </Box>
      <TestPatientsPanel
        ruleId={ruleId}
        guidelineId={guidelineId}
        ruleSignature={ruleSignature}
        ruleName={ruleName}
        recommendationText={recommendationText}
        draftRule={draftRule}
      />
    </Stack>
  );
}
