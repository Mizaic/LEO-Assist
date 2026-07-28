/**
 * Multi-step coach tour built on the CoachMark visual shell.
 *
 * Caller controls when the tour runs via `active`. Completion is
 * persisted to localStorage (`leo-tour-${tourId}-done`) so it does
 * not auto-replay; deliberate replay bypasses that by setting
 * `active` true again from a Guide me / Replay trigger.
 *
 * Atlas trace: DI-LEO-AI-121 / VT-LEO-AI-116 / DO-9539333E
 */
"use client";

import { useCallback, useEffect, useId, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { useMotion } from "@leo/design-system";

export interface TourStep {
  id: string;
  title: string;
  body: string;
  anchorSelector: string;
}

export interface CoachTourProps {
  tourId: string;
  steps: TourStep[];
  active: boolean;
  onFinish: () => void;
}

function persistDone(tourId: string): void {
  try {
    window.localStorage.setItem(`leo-tour-${tourId}-done`, "true");
  } catch {
    /* ignore */
  }
}

const ANCHOR_POLL_MS = 100;
const ANCHOR_POLL_BUDGET_MS = 600;

function measureAnchor(selector: string): DOMRect | null {
  if (typeof document === "undefined") return null;
  const el = document.querySelector(selector);
  if (!(el instanceof HTMLElement)) return null;
  return el.getBoundingClientRect();
}

export default function CoachTour({
  tourId,
  steps,
  active,
  onFinish,
}: CoachTourProps) {
  const titleId = useId();
  const bodyId = useId();
  const { reducedMotion } = useMotion();
  const [stepIndex, setStepIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  const finish = useCallback(() => {
    persistDone(tourId);
    setStepIndex(0);
    onFinish();
  }, [tourId, onFinish]);

  useEffect(() => {
    if (!active) {
      setStepIndex(0);
      setRect(null);
      return;
    }
    setStepIndex(0);
  }, [active]);

  useEffect(() => {
    if (!active || steps.length === 0) return;
    const step = steps[stepIndex];
    if (!step) {
      finish();
      return;
    }

    let cancelled = false;
    let elapsed = 0;
    const tryMeasure = () => {
      if (cancelled) return;
      const next = measureAnchor(step.anchorSelector);
      if (next) {
        setRect(next);
        return;
      }
      elapsed += ANCHOR_POLL_MS;
      if (elapsed >= ANCHOR_POLL_BUDGET_MS) {
        // Skip missing anchors (wizard phases not yet mounted) rather than hang.
        if (stepIndex < steps.length - 1) {
          setStepIndex((i) => i + 1);
        } else {
          finish();
        }
        return;
      }
      window.setTimeout(tryMeasure, ANCHOR_POLL_MS);
    };
    tryMeasure();
    return () => {
      cancelled = true;
    };
  }, [active, finish, stepIndex, steps]);

  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") finish();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, finish]);

  if (!active || steps.length === 0) return null;
  const step = steps[stepIndex];
  if (!step) return null;

  const top = rect ? rect.bottom + window.scrollY + 8 : 16;
  const left = rect ? rect.left + window.scrollX : 16;
  const isLast = stepIndex >= steps.length - 1;
  const transition = reducedMotion
    ? undefined
    : "opacity 160ms ease-out, transform 160ms ease-out";

  return (
    <Box
      role="dialog"
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      data-testid="coach-tour"
      data-tour-step={step.id}
      sx={{
        position: "absolute",
        top,
        left,
        zIndex: 1400,
        maxWidth: 320,
        p: 2,
        bgcolor: "background.paper",
        border: "2px solid",
        borderColor: "primary.main",
        borderRadius: 2,
        boxShadow: 4,
        opacity: 1,
        transform: "translateY(0)",
        transition,
        "@starting-style": reducedMotion
          ? undefined
          : { opacity: 0, transform: "translateY(4px)" },
      }}
    >
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mb: 0.5 }}
      >
        {`Step ${stepIndex + 1} of ${steps.length}`}
      </Typography>
      <Typography id={titleId} variant="h6" component="h3" sx={{ mb: 0.5 }}>
        {step.title}
      </Typography>
      <Typography id={bodyId} variant="body2" sx={{ mb: 1.5 }}>
        {step.body}
      </Typography>
      <Stack direction="row" justifyContent="space-between" spacing={1}>
        <Button
          size="small"
          variant="text"
          onClick={finish}
          data-testid="coach-tour-skip"
        >
          Skip tour
        </Button>
        <Stack direction="row" spacing={1}>
          <Button
            size="small"
            variant="outlined"
            disabled={stepIndex === 0}
            onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
            data-testid="coach-tour-back"
          >
            Back
          </Button>
          <Button
            size="small"
            variant="contained"
            onClick={() => {
              if (isLast) finish();
              else setStepIndex((i) => i + 1);
            }}
            data-testid="coach-tour-next"
          >
            {isLast ? "Done" : "Next"}
          </Button>
        </Stack>
      </Stack>
    </Box>
  );
}
