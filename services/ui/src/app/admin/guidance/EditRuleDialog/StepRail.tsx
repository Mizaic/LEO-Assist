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
 * Left-column numbered step rail for the widescreen rule editor.
 *
 * Lists the four jobs in display order (Who -> Suggest -> Try -> Save)
 * with one of three states per step: not_started, in_progress, ready.
 *
 * The rail is the canonical "where am I?" widget. It is jump-able
 * (every step is a button) so a confident user can skip ahead, while
 * the dialog footer's Back/Next still works for users who prefer
 * linear navigation.
 *
 * Visual conventions follow design-system-ui.mdc:
 *   - 12px corner radius on the active card.
 *   - 3px-wide left accent strip on the current step.
 *   - 8pt grid spacing; no raw hex colours.
 *
 * Design Controls: DI-LEO-AI-234, DO-LEO-AI-234, VT-LEO-AI-510.
 */

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";

import {
  ALL_READY_LABEL,
  STEP_IDS,
  STEP_SHORT_TITLES,
  STEP_STATE_LABELS,
  STEP_TITLES,
  type StepId,
} from "./copy";

export type StepState = "not_started" | "in_progress" | "ready";

export interface StepDescriptor {
  id: StepId;
  state: StepState;
}

interface Props {
  steps: StepDescriptor[];
  currentStepId: StepId;
  onJump: (stepId: StepId) => void;
}

const STATE_TONE: Record<
  StepState,
  { fg: string; bg: string; border: string }
> = {
  not_started: {
    fg: "text.secondary",
    bg: "grey.50",
    border: "grey.200",
  },
  in_progress: {
    fg: "primary.dark",
    bg: "primary.50",
    border: "primary.100",
  },
  ready: {
    fg: "success.dark",
    bg: "success.50",
    border: "success.100",
  },
};

export default function StepRail({ steps, currentStepId, onJump }: Props) {
  const allReady = steps.every((s) => s.state === "ready");

  return (
    <Box
      component="nav"
      role="navigation"
      aria-label="Steps to change this rule"
      sx={{
        position: "sticky",
        top: 0,
        alignSelf: "flex-start",
        height: "100%",
        p: 1.5,
        borderRight: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
      }}
    >
      <Typography
        variant="overline"
        sx={{
          display: "block",
          color: "text.secondary",
          letterSpacing: 0.5,
          mb: 1,
        }}
      >
        Your steps
      </Typography>
      <Stack
        component="ol"
        spacing={1}
        sx={{ m: 0, p: 0, listStyle: "none" }}
      >
        {STEP_IDS.map((id, index) => {
          const descriptor = steps.find((s) => s.id === id) ?? {
            id,
            state: "not_started" as const,
          };
          const isCurrent = id === currentStepId;
          return (
            <Box component="li" key={id} sx={{ p: 0, m: 0 }}>
              <StepRailItem
                stepId={id}
                index={index + 1}
                state={descriptor.state}
                isCurrent={isCurrent}
                onJump={onJump}
              />
            </Box>
          );
        })}
      </Stack>
      {allReady && (
        <Stack
          direction="row"
          alignItems="center"
          spacing={1}
          sx={{
            mt: 2,
            p: 1.25,
            borderRadius: 1.5,
            bgcolor: "success.50",
            border: "1px solid",
            borderColor: "success.100",
            color: "success.dark",
          }}
          role="status"
          aria-label={ALL_READY_LABEL}
        >
          <CheckCircleRoundedIcon fontSize="small" />
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {ALL_READY_LABEL}
          </Typography>
        </Stack>
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

function StepRailItem({
  stepId,
  index,
  state,
  isCurrent,
  onJump,
}: ItemProps) {
  const tone = STATE_TONE[state];
  const title = STEP_TITLES[stepId];
  const shortTitle = STEP_SHORT_TITLES[stepId];
  const stateLabel = STEP_STATE_LABELS[state];
  const ariaLabel = `Step ${index} of 4: ${title}. ${stateLabel}.${
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
        display: "block",
        width: "100%",
        textAlign: "left",
        p: 1.25,
        pl: 1.75,
        borderRadius: "12px",
        border: "1px solid",
        borderColor: isCurrent ? "primary.main" : "divider",
        bgcolor: isCurrent ? "primary.50" : "background.paper",
        cursor: "pointer",
        transition: "background-color 120ms ease, border-color 120ms ease",
        "&:hover": {
          bgcolor: isCurrent ? "primary.50" : "action.hover",
        },
        "&:focus-visible": {
          outline: "2px solid",
          outlineColor: "primary.main",
          outlineOffset: 2,
        },
      }}
    >
      {isCurrent && (
        <Box
          aria-hidden="true"
          sx={{
            position: "absolute",
            left: 0,
            top: 14,
            bottom: 14,
            width: 3,
            borderRadius: 2,
            bgcolor: "primary.main",
          }}
        />
      )}
      <Stack direction="row" alignItems="center" spacing={1}>
        <Box
          aria-hidden="true"
          sx={{
            width: 26,
            height: 26,
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "0.85rem",
            fontWeight: 700,
            color: state === "ready" ? "success.dark" : "primary.dark",
            bgcolor:
              state === "ready"
                ? "success.100"
                : isCurrent
                  ? "primary.100"
                  : "grey.100",
            flexShrink: 0,
          }}
        >
          {state === "ready" ? (
            <CheckCircleRoundedIcon
              fontSize="inherit"
              sx={{ fontSize: "1rem" }}
            />
          ) : (
            index
          )}
        </Box>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography
            variant="body2"
            sx={{
              fontWeight: 700,
              lineHeight: 1.3,
              color: "text.primary",
              display: { xs: "none", md: "block" },
            }}
          >
            {title}
          </Typography>
          <Typography
            variant="body2"
            sx={{
              fontWeight: 700,
              lineHeight: 1.3,
              color: "text.primary",
              display: { xs: "block", md: "none" },
            }}
          >
            {shortTitle}
          </Typography>
          <Typography
            variant="caption"
            sx={{ color: tone.fg, display: "block", mt: 0.25 }}
          >
            {stateLabel}
          </Typography>
        </Box>
      </Stack>
    </Box>
  );
}
