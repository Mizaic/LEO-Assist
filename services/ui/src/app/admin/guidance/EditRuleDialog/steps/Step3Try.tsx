/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

/**
 * Step 3 -- "Test your change safely".
 *
 * Hosts the sandbox-only TestPatientsPanel. Production is never
 * touched from here -- the sandbox compiles the unsaved draft into
 * a throwaway bitmap, replays the saved test patients through it,
 * then deletes the sandbox keys.
 *
 * Design Controls: DI-LEO-AI-234, DO-LEO-AI-234, VT-LEO-AI-510;
 * Phase 1 safety fix: DI-DD86CCBE, VT-D7B8FBA9 (see Atlas).
 */

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import TestPatientsPanel, {
  type SandboxReportState,
} from "../TestPatientsPanel";
import { STEP_HELPERS, STEP_TITLES } from "../copy";

interface Props {
  ruleId: string;
  guidelineId?: string;
  ruleName?: string;
  recommendationText?: string;
  draftRule: Record<string, unknown> | null;
  /** Phase 4 -- propagates sandbox replay summaries up to the
   *  EditRuleDialog so the SentenceCanvas on Step 1 can render
   *  inline impact badges. */
  onSandboxReportChange?: (state: SandboxReportState | null) => void;
}

export default function Step3Try({
  ruleId,
  guidelineId,
  ruleName,
  recommendationText,
  draftRule,
  onSandboxReportChange,
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
        ruleName={ruleName}
        recommendationText={recommendationText}
        draftRule={draftRule}
        onReportChange={onSandboxReportChange}
      />
    </Stack>
  );
}
