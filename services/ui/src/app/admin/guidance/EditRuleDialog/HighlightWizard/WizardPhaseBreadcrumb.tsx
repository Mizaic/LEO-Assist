/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
"use client";

/**
 * Small, plain, non-numbered breadcrumb showing which phase of the
 * guided "Who" step the reviewer is in (Always true > Situations >
 * Conditions > Review).
 *
 * Rendered by `HorizontalStepper` directly beneath the "Who" pill in
 * the outer rule-editor stepper -- NOT inside the wizard's own canvas.
 * That keeps the whole screen down to a single navigation surface:
 * the outer numbered Who/Suggest/Save stepper, with this breadcrumb
 * read as a continuation of the same bar rather than a second,
 * separately-positioned wizard. See `HorizontalStepper.tsx`'s doc
 * comment for the full rationale.
 */
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";

import { WIZARD_CHROME } from "./copy";
import type { WizardStepKind } from "./wizardState";

const BREADCRUMB_STEPS: WizardStepKind[] = [
  "prerequisites",
  "pathway-split",
  "pathway-conditions",
  "review",
];

interface Props {
  step: WizardStepKind;
}

export default function WizardPhaseBreadcrumb({ step }: Props) {
  const currentIndex = BREADCRUMB_STEPS.indexOf(step);

  return (
    <Stack
      direction="row"
      spacing={0.5}
      alignItems="center"
      flexWrap="wrap"
      role="status"
      aria-live="polite"
    >
      {BREADCRUMB_STEPS.map((phase, index) => (
        <BreadcrumbPhase
          key={phase}
          label={WIZARD_CHROME.breadcrumbLabels[phase]}
          state={
            index < currentIndex
              ? "done"
              : index === currentIndex
                ? "current"
                : "upcoming"
          }
          showSeparator={index > 0}
        />
      ))}
    </Stack>
  );
}

type PhaseState = "done" | "current" | "upcoming";

function BreadcrumbPhase({
  label,
  state,
  showSeparator,
}: {
  label: string;
  state: PhaseState;
  showSeparator: boolean;
}) {
  return (
    <Stack direction="row" spacing={0.5} alignItems="center">
      {showSeparator && (
        <Typography variant="caption" color="text.disabled" sx={{ px: 0.25 }}>
          &gt;
        </Typography>
      )}
      {state === "done" && (
        <CheckCircleRoundedIcon
          fontSize="inherit"
          sx={{ fontSize: 14, color: "success.main" }}
        />
      )}
      <Typography
        variant="caption"
        sx={{
          fontWeight: state === "current" ? 700 : 400,
          color:
            state === "current"
              ? "text.primary"
              : state === "done"
                ? "text.secondary"
                : "text.disabled",
        }}
      >
        {label}
      </Typography>
    </Stack>
  );
}
