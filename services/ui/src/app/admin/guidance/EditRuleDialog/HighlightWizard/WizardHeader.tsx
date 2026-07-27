/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
"use client";

/**
 * Chrome shared by every wizard step: just the Back button.
 *
 * The "where am I within Who" breadcrumb used to live here too, but
 * it moved up into `HorizontalStepper.tsx` (attached to the outer
 * rule-editor's "Who" pill) so the whole screen reads as one
 * navigation surface instead of two separately-positioned ones -- see
 * `WizardPhaseBreadcrumb.tsx` and `HorizontalStepper.tsx` for the
 * rationale. This component only answers "can I go back right now",
 * rendered right above the step content it controls.
 */
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import ArrowBackRoundedIcon from "@mui/icons-material/ArrowBackRounded";

import { WIZARD_CHROME } from "./copy";
import type { WizardStepKind } from "./wizardState";

interface Props {
  step: WizardStepKind;
  onBack: () => void;
}

export default function WizardHeader({ step, onBack }: Props) {
  const isFirstStep = step === "prerequisites";
  if (isFirstStep) return null;

  return (
    <Stack direction="row" justifyContent="flex-end">
      <Button
        size="small"
        startIcon={<ArrowBackRoundedIcon fontSize="small" />}
        onClick={onBack}
      >
        {WIZARD_CHROME.backLabel}
      </Button>
    </Stack>
  );
}
