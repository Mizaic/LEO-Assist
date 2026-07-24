/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * Chrome shared by every wizard step: a "Step X of 3" progress
 * indicator plus Back / "Skip to Advanced view" navigation. Kept
 * separate from the orchestrator so `index.tsx` stays focused on
 * phase transitions rather than layout.
 */
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ArrowBackRoundedIcon from "@mui/icons-material/ArrowBackRounded";

import { WIZARD_CHROME } from "./copy";
import type { WizardStepKind } from "./wizardState";

const STEP_ORDER: WizardStepKind[] = [
  "prerequisites",
  "pathway-split",
  "pathway-conditions",
];

interface Props {
  step: WizardStepKind;
  onBack: () => void;
  onSkipToManual: () => void;
}

export default function WizardHeader({ step, onBack, onSkipToManual }: Props) {
  const isFirstStep = step === "prerequisites";
  const isReview = step === "review";
  const stepIndex = STEP_ORDER.indexOf(step) + 1;

  return (
    <Stack
      direction="row"
      alignItems="center"
      justifyContent="space-between"
      spacing={1}
      flexWrap="wrap"
      sx={{ rowGap: 1 }}
    >
      <Box role="status" aria-live="polite">
        {isReview ? (
          <Typography variant="caption" sx={{ fontWeight: 700, color: "text.secondary" }}>
            {WIZARD_CHROME.stepNames.review}
          </Typography>
        ) : (
          <Stack direction="row" spacing={1} alignItems="baseline">
            <Typography variant="caption" sx={{ fontWeight: 700 }}>
              {WIZARD_CHROME.stepLabel(stepIndex, STEP_ORDER.length)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {WIZARD_CHROME.stepNames[step]}
            </Typography>
          </Stack>
        )}
      </Box>
      <Stack direction="row" spacing={1}>
        {!isFirstStep && (
          <Button
            size="small"
            startIcon={<ArrowBackRoundedIcon fontSize="small" />}
            onClick={onBack}
          >
            {WIZARD_CHROME.backLabel}
          </Button>
        )}
        <Button size="small" variant="text" onClick={onSkipToManual}>
          {WIZARD_CHROME.skipToAdvancedLabel}
        </Button>
      </Stack>
    </Stack>
  );
}
