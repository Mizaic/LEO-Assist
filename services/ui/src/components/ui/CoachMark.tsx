/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-9539333E
 *   DI: DI-29EEE9C3
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-9539333E")
 */
"use client";

import { useCallback, useEffect, useId, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

interface CoachMarkProps {
  tourId: string;
  title: string;
  body: string;
  anchorRef: React.RefObject<HTMLElement | null>;
  onDismiss?: () => void;
}

function isDismissed(tourId: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(`leo-tour-${tourId}-done`) === "true";
  } catch {
    return false;
  }
}

function persistDismissed(tourId: string): void {
  try {
    window.localStorage.setItem(`leo-tour-${tourId}-done`, "true");
  } catch {
    /* ignore */
  }
}

/**
 * Dismissable coach mark. Renders an overlay attached to an anchor by ref
 * and records dismissal in localStorage so the tour does not repeat.
 * Respects prefers-reduced-motion by not animating entry when set.
 *
 * See DI-LEO-AI-121 / VT-LEO-AI-116 TC-003.
 */
export default function CoachMark({
  tourId,
  title,
  body,
  anchorRef,
  onDismiss,
}: CoachMarkProps) {
  const titleId = useId();
  const bodyId = useId();
  const [visible, setVisible] = useState(false);
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (isDismissed(tourId)) return;
    setVisible(true);
    const element = anchorRef.current;
    if (element) setRect(element.getBoundingClientRect());
  }, [anchorRef, tourId]);

  const dismiss = useCallback(() => {
    persistDismissed(tourId);
    setVisible(false);
    onDismiss?.();
  }, [tourId, onDismiss]);

  useEffect(() => {
    if (!visible) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visible, dismiss]);

  if (!visible) return null;

  const top = rect ? rect.bottom + window.scrollY + 8 : 16;
  const left = rect ? rect.left + window.scrollX : 16;

  return (
    <Box
      role="dialog"
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      data-testid="coach-mark"
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
      }}
    >
      <Typography id={titleId} variant="h6" component="h3" sx={{ mb: 0.5 }}>
        {title}
      </Typography>
      <Typography id={bodyId} variant="body2" sx={{ mb: 1.5 }}>
        {body}
      </Typography>
      <Stack direction="row" justifyContent="flex-end" spacing={1}>
        <Button size="small" onClick={dismiss} variant="contained">
          Got it
        </Button>
      </Stack>
    </Box>
  );
}
