/**
 * Multi-step coach tour with spotlight cut-out.
 *
 * Caller controls when the tour runs via `active`. Optional
 * `prepareStep` syncs page/wizard state before measuring the anchor.
 * Missing anchors after prepare + poll are omitted (not shown with
 * lying copy). Completion persists to localStorage
 * (`leo-tour-${tourId}-done`).
 *
 * Atlas trace: DI-LEO-AI-121 / VT-LEO-AI-116 / DO-9539333E
 */
"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { useMotion } from "@leo/design-system";

import {
  BUBBLE_MAX_WIDTH,
  bubblePosition,
  measureAnchor,
  spotlightBox,
} from "./coachTourLayout";

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
  /**
   * Called before measuring each step so the host can open sections /
   * advance the wizard. Return false to omit the step from this run.
   */
  prepareStep?: (step: TourStep) => void | boolean | Promise<void | boolean>;
}

function persistDone(tourId: string): void {
  try {
    window.localStorage.setItem(`leo-tour-${tourId}-done`, "true");
  } catch {
    /* ignore */
  }
}

const ANCHOR_POLL_MS = 100;
const ANCHOR_POLL_BUDGET_MS = 1200;

export default function CoachTour({
  tourId,
  steps,
  active,
  onFinish,
  prepareStep,
}: CoachTourProps) {
  const titleId = useId();
  const bodyId = useId();
  const { reducedMotion } = useMotion();
  const [stepIndex, setStepIndex] = useState(0);
  const [committedIndex, setCommittedIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [pulse, setPulse] = useState(false);
  const [mounted, setMounted] = useState(false);
  const prepareGen = useRef(0);
  const onFinishRef = useRef(onFinish);
  const prepareStepRef = useRef(prepareStep);
  onFinishRef.current = onFinish;
  prepareStepRef.current = prepareStep;

  const finish = useCallback(() => {
    persistDone(tourId);
    setStepIndex(0);
    setCommittedIndex(0);
    setRect(null);
    onFinishRef.current();
  }, [tourId]);

  useEffect(() => {
    if (!active) {
      setStepIndex(0);
      setCommittedIndex(0);
      setRect(null);
      setPulse(false);
      return;
    }
    setStepIndex(0);
    setCommittedIndex(0);
  }, [active]);

  useEffect(() => {
    if (!active || steps.length === 0) return;
    const step = steps[stepIndex];
    if (!step) {
      finish();
      return;
    }

    let cancelled = false;
    const gen = ++prepareGen.current;

    const run = async () => {
      const prepare = prepareStepRef.current;
      if (prepare) {
        const ok = await prepare(step);
        if (cancelled || gen !== prepareGen.current) return;
        if (ok === false) {
          if (stepIndex < steps.length - 1) setStepIndex(stepIndex + 1);
          else finish();
          return;
        }
      }

      let elapsed = 0;
      const tryMeasure = () => {
        if (cancelled || gen !== prepareGen.current) return;
        const next = measureAnchor(step.anchorSelector);
        if (next && next.width > 0 && next.height > 0) {
          setRect(next);
          setCommittedIndex(stepIndex);
          if (!reducedMotion) {
            setPulse(true);
            window.setTimeout(() => {
              if (!cancelled) setPulse(false);
            }, 900);
          }
          return;
        }
        elapsed += ANCHOR_POLL_MS;
        if (elapsed >= ANCHOR_POLL_BUDGET_MS) {
          if (stepIndex < steps.length - 1) setStepIndex(stepIndex + 1);
          else finish();
          return;
        }
        window.setTimeout(tryMeasure, ANCHOR_POLL_MS);
      };
      tryMeasure();
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [active, finish, reducedMotion, stepIndex, steps]);

  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") finish();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, finish]);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!active || steps.length === 0 || !mounted) return null;
  const step = steps[committedIndex];
  if (!step || !rect) return null;

  const preparing = stepIndex !== committedIndex;
  const { top, left } = bubblePosition(rect);
  const spot = spotlightBox(rect);
  const isLast = committedIndex >= steps.length - 1;
  const transition = reducedMotion
    ? undefined
    : "opacity 160ms ease-out, transform 160ms ease-out";

  // Portal to body so Dialog transform / overflow cannot clip or re-root fixed.
  return createPortal(
    <>
      {spot && (
        <Box
          aria-hidden
          data-testid="coach-tour-spotlight"
          data-pulse={pulse ? "true" : "false"}
          sx={{
            position: "fixed",
            top: spot.top,
            left: spot.left,
            width: spot.width,
            height: spot.height,
            zIndex: 1500,
            pointerEvents: "none",
            borderRadius: 2,
            boxShadow: "0 0 0 9999px rgba(15, 23, 42, 0.45)",
            outline: "2px solid rgba(37, 99, 235, 0.9)",
            outlineOffset: 2,
            animation:
              pulse && !reducedMotion
                ? "coach-tour-pulse 0.45s ease-in-out 2"
                : undefined,
            "@keyframes coach-tour-pulse": {
              "0%, 100%": { outlineWidth: "2px" },
              "50%": { outlineWidth: "4px" },
            },
          }}
        />
      )}
      <Box
        role="dialog"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
        data-testid="coach-tour"
        data-tour-step={step.id}
        aria-busy={preparing || undefined}
        sx={{
          position: "fixed",
          top,
          left,
          zIndex: 1501,
          maxWidth: BUBBLE_MAX_WIDTH,
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
          {`Step ${committedIndex + 1} of ${steps.length}`}
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
              disabled={committedIndex === 0 || preparing}
              onClick={() => setStepIndex(Math.max(0, committedIndex - 1))}
              data-testid="coach-tour-back"
            >
              Back
            </Button>
            <Button
              size="small"
              variant="contained"
              disabled={preparing}
              onClick={() => {
                if (isLast) finish();
                else setStepIndex(committedIndex + 1);
              }}
              data-testid="coach-tour-next"
            >
              {isLast ? "Done" : "Next"}
            </Button>
          </Stack>
        </Stack>
      </Box>
    </>,
    document.body,
  );
}
