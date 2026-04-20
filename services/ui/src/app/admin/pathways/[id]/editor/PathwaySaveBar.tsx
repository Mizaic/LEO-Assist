/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

// -- PathwaySaveBar.tsx --------------------------------------------------------
// Sticky bottom bar showing the current dirty / saving / saved state of the
// pathway, plus a Save shortcut. The intent is to give users an unambiguous
// answer to "is my work persisted?" no matter where they scroll on the canvas.
//
// Stateless / prop-driven so the parent owns dirty tracking. Phase 6b-iv will
// wire this to a `useDirtyGuard` hook that also installs `beforeunload`.

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import SaveIcon from "@mui/icons-material/Save";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

import { formatSaveTime } from "./utils";

export type SaveBarState = "idle" | "dirty" | "saving" | "saved" | "error";

export interface PathwaySaveBarProps {
  state: SaveBarState;
  lastSaved: Date | null;
  errorMessage?: string | null;
  onSave: () => void;
  onDismissError?: () => void;
}

function describeState(
  state: SaveBarState,
  lastSaved: Date | null,
  errorMessage: string | null | undefined,
): { label: string; tone: "success" | "warning" | "error" | "info" } {
  if (state === "saving") {
    return { label: "Saving...", tone: "info" };
  }
  if (state === "error") {
    return {
      label: errorMessage ? `Save failed: ${errorMessage}` : "Save failed",
      tone: "error",
    };
  }
  if (state === "dirty") {
    return { label: "Unsaved changes", tone: "warning" };
  }
  if (state === "saved" && lastSaved) {
    return { label: `Saved ${formatSaveTime(lastSaved)}`, tone: "success" };
  }
  return { label: "All changes saved", tone: "success" };
}

function ToneIcon({
  tone,
}: {
  tone: "success" | "warning" | "error" | "info";
}) {
  if (tone === "success")
    return (
      <CheckCircleOutlineIcon
        sx={{ fontSize: "1rem", color: "success.main" }}
      />
    );
  if (tone === "warning")
    return (
      <WarningAmberIcon sx={{ fontSize: "1rem", color: "warning.main" }} />
    );
  if (tone === "error")
    return (
      <WarningAmberIcon sx={{ fontSize: "1rem", color: "error.main" }} />
    );
  return <CircularProgress size={12} color="inherit" />;
}

export function PathwaySaveBar({
  state,
  lastSaved,
  errorMessage,
  onSave,
  onDismissError,
}: PathwaySaveBarProps) {
  const description = describeState(state, lastSaved, errorMessage);
  const isSaving = state === "saving";
  const showSaveAction = state === "dirty" || state === "error";

  return (
    <Box
      data-testid="pathway-save-bar"
      sx={{
        position: "sticky",
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: 5,
        px: 2,
        py: 1,
        borderTop: 1,
        borderColor: "divider",
        bgcolor: "background.paper",
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        boxShadow: "0 -2px 8px rgba(15, 23, 42, 0.04)",
      }}
      role="status"
      aria-live="polite"
    >
      <Stack direction="row" alignItems="center" spacing={0.75}>
        <ToneIcon tone={description.tone} />
        <Typography
          variant="caption"
          sx={{
            fontWeight: 600,
            color:
              description.tone === "success"
                ? "success.main"
                : description.tone === "warning"
                  ? "warning.main"
                  : description.tone === "error"
                    ? "error.main"
                    : "text.secondary",
          }}
        >
          {description.label}
        </Typography>
      </Stack>
      <Box sx={{ flex: 1 }} />
      {state === "error" && onDismissError ? (
        <Button
          size="small"
          variant="text"
          onClick={onDismissError}
          sx={{ textTransform: "none", fontSize: "0.72rem" }}
        >
          Dismiss
        </Button>
      ) : null}
      {showSaveAction ? (
        <Button
          size="small"
          variant="contained"
          startIcon={
            isSaving ? (
              <CircularProgress size={13} color="inherit" />
            ) : (
              <SaveIcon />
            )
          }
          onClick={onSave}
          disabled={isSaving}
          sx={{ textTransform: "none" }}
          aria-label="Save pathway"
        >
          {isSaving ? "Saving..." : "Save now"}
        </Button>
      ) : null}
    </Box>
  );
}
