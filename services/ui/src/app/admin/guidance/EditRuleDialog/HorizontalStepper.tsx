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
 * Top horizontal stepper for the rule editor.
 *
 * Replaces the previous left-hand StepRail column. The horizontal
 * layout returns ~220px of canvas width and signals progress more
 * naturally for first-time users (left-to-right reading order).
 *
 * Each step is a button (jump-able). The current step is highlighted
 * with the canonical 3px accent below the row plus a tinted pill;
 * ready steps show a green tick; not_started steps stay muted.
 *
 * On narrow viewports (xs, sm) the stepper compacts to a horizontal
 * scroll strip with shortened labels so the strip never wraps.
 *
 * While the guided highlight-to-build wizard is working through its
 * own phases inside "Who", `wizardPhase` renders a small, non-numbered
 * breadcrumb (Always true > Situations > Conditions > Review) directly
 * beneath this same row -- deliberately in the SAME persistent header
 * box as the numbered steps, not buried further down in the scrolling
 * canvas. That keeps the whole dialog to one navigation surface: the
 * reviewer only ever has one place to look to answer "where am I and
 * what happens if I click Back". The wizard's own phase count is
 * intentionally NOT promoted to its own numbered/jump-able circles
 * here -- it varies per guideline (one "Conditions" phase per
 * situation, and the situation count is only known after Step 2 runs),
 * so giving it equal billing with Who/Suggest/Save would make this bar
 * resize itself mid-flow and expose steps the reviewer cannot jump to
 * yet (the pathway hasn't been built). See `WizardPhaseBreadcrumb.tsx`.
 *
 * Design Controls: UN-LEO-AI-094 (v2), DI-LEO-AI-512 (v2),
 *                  R-LEO-AI-509 (v2), VT-LEO-AI-511 (v2).
 */

import { motion as fm } from "framer-motion";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";

import { useMotion } from "@leo/design-system";

import {
  STEP_IDS,
  STEP_SHORT_TITLES,
  STEP_STATE_LABELS,
  STEP_TITLES,
  type StepId,
} from "./copy";
import WizardPhaseBreadcrumb from "./HighlightWizard/WizardPhaseBreadcrumb";
import type { WizardStepKind } from "./HighlightWizard/wizardState";

/**
 * Per-step state machine. The previous (now-deleted) StepRail.tsx
 * owned these types; they live here because the horizontal stepper
 * is the only consumer post-Phase-1.
 */
export type StepState = "not_started" | "in_progress" | "ready";

export interface StepDescriptor {
  id: StepId;
  state: StepState;
}

interface Props {
  steps: StepDescriptor[];
  currentStepId: StepId;
  onJump: (stepId: StepId) => void;
  /**
   * The guided wizard's current phase while `currentStepId === "who"`.
   * Null/undefined whenever there's nothing to show (no tree yet, or
   * a different outer step is active) -- see the file doc comment.
   */
  wizardPhase?: WizardStepKind | null;
}

export default function HorizontalStepper({
  steps,
  currentStepId,
  onJump,
  wizardPhase,
}: Props) {
  return (
    <Box
      component="nav"
      role="navigation"
      aria-label="Steps to change this rule"
      sx={{
        px: { xs: 1.5, md: 2.5 },
        py: 1,
        bgcolor: "background.paper",
        borderBottom: "1px solid",
        borderColor: "divider",
        overflowX: "auto",
      }}
    >
      <Stack
        component="ol"
        direction="row"
        spacing={{ xs: 0.5, md: 1 }}
        sx={{
          m: 0,
          p: 0,
          listStyle: "none",
          minWidth: "fit-content",
          alignItems: "stretch",
        }}
      >
        {STEP_IDS.map((id, index) => {
          const descriptor = steps.find((s) => s.id === id) ?? {
            id,
            state: "not_started" as const,
          };
          const isCurrent = id === currentStepId;
          const isLast = index === STEP_IDS.length - 1;
          return (
            <Box
              component="li"
              key={id}
              sx={{
                p: 0,
                m: 0,
                display: "flex",
                alignItems: "center",
                flexShrink: 0,
              }}
            >
              <StepperItem
                stepId={id}
                index={index + 1}
                state={descriptor.state}
                isCurrent={isCurrent}
                onJump={onJump}
              />
              {!isLast && <StepperConnector />}
            </Box>
          );
        })}
      </Stack>
      {currentStepId === "who" && wizardPhase && (
        <Box sx={{ pl: { xs: 4, md: 4.5 }, pt: 0.5 }}>
          <WizardPhaseBreadcrumb step={wizardPhase} />
        </Box>
      )}
    </Box>
  );
}

interface ItemProps {
  stepId: StepId;
  index: number;
  state: StepState;
  isCurrent: boolean;
  onJump: (stepId: StepId) => void;
}

function StepperItem({
  stepId,
  index,
  state,
  isCurrent,
  onJump,
}: ItemProps) {
  const { reducedMotion } = useMotion();
  const title = STEP_TITLES[stepId];
  const shortTitle = STEP_SHORT_TITLES[stepId];
  const stateLabel = STEP_STATE_LABELS[state];
  const isReady = state === "ready";
  const ariaLabel = `Step ${index} of ${STEP_IDS.length}: ${title}. ${stateLabel}.${
    isCurrent ? " Current step." : ""
  }`;

  return (
    <Box
      component="button"
      type="button"
      onClick={() => onJump(stepId)}
      aria-label={ariaLabel}
      aria-current={isCurrent ? "step" : undefined}
      sx={{
        position: "relative",
        display: "flex",
        flexDirection: "row",
        alignItems: "center",
        gap: 1,
        px: { xs: 1, md: 1.5 },
        py: 0.75,
        border: "none",
        borderRadius: 999,
        bgcolor: "transparent",
        color: "text.primary",
        cursor: "pointer",
        transition: "color 120ms ease, transform 120ms ease",
        "&:hover": {
          bgcolor: isCurrent ? "transparent" : "action.hover",
        },
        "&:focus-visible": {
          outline: "2px solid",
          outlineColor: "primary.main",
          outlineOffset: 2,
        },
      }}
    >
      {isCurrent && (
        <fm.div
          layoutId="stepper-active-pill"
          transition={
            reducedMotion
              ? { duration: 0 }
              : { type: "spring", stiffness: 380, damping: 32 }
          }
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: 999,
            background: "var(--mui-palette-primary-50, #EFF6FF)",
            zIndex: 0,
          }}
        />
      )}
      <Box
        aria-hidden="true"
        sx={{
          position: "relative",
          zIndex: 1,
          width: 26,
          height: 26,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "0.85rem",
          fontWeight: 700,
          color: isReady
            ? "success.dark"
            : isCurrent
              ? "primary.dark"
              : "text.secondary",
          bgcolor: isReady
            ? "success.100"
            : isCurrent
              ? "primary.100"
              : "grey.100",
          flexShrink: 0,
        }}
      >
        {isReady ? (
          <CheckCircleRoundedIcon
            fontSize="inherit"
            sx={{ fontSize: "1rem" }}
          />
        ) : (
          index
        )}
      </Box>
      <Box sx={{ position: "relative", zIndex: 1, minWidth: 0, textAlign: "left" }}>
        <Typography
          variant="body2"
          sx={{
            fontWeight: isCurrent ? 700 : 500,
            color: isCurrent ? "primary.dark" : "text.primary",
            lineHeight: 1.2,
            display: { xs: "none", sm: "block" },
            whiteSpace: "nowrap",
          }}
        >
          {title}
        </Typography>
        <Typography
          variant="body2"
          sx={{
            fontWeight: isCurrent ? 700 : 500,
            color: isCurrent ? "primary.dark" : "text.primary",
            lineHeight: 1.2,
            display: { xs: "block", sm: "none" },
            whiteSpace: "nowrap",
          }}
        >
          {shortTitle}
        </Typography>
      </Box>
    </Box>
  );
}

function StepperConnector() {
  return (
    <Box
      aria-hidden="true"
      sx={{
        width: { xs: 16, md: 28 },
        height: "1px",
        bgcolor: "divider",
        mx: { xs: 0.25, md: 0.5 },
        flexShrink: 0,
      }}
    />
  );
}
