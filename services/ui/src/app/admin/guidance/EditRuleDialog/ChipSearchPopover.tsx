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
 * Concept search rendered as a popover anchored to the chip or
 * +Add button the reviewer just clicked.
 *
 * Replaces the previous always-visible right-hand search column.
 * Direct manipulation: the search appears at the cursor, picking a
 * result mutates the chip in place, and dismissing the popover
 * (X / ESC / click-outside / picking a result) returns focus to
 * the canvas with the chip updated.
 *
 * Modes:
 *   - "replace"        -- swap the focused CONCEPT chip's SNOMED code
 *   - "add"            -- insert a new CONCEPT child under a group
 *   - "replace_action" -- swap the recommended procedure (rendered
 *                          inside Step 2 in a slightly different place,
 *                          but uses the same popover for consistency)
 *
 * Always closeable. The MUI Popover handles ESC + click-outside; we
 * also render an explicit X so the affordance is obvious to a
 * first-time user.
 *
 * Design Controls: UN-LEO-AI-094 (v2), DI-LEO-AI-512 (v2),
 *                  R-LEO-AI-509 (v2), VT-LEO-AI-511 (v2).
 */

import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import ConceptSearchPanel, { type ObservationSeed } from "./ConceptSearchPanel";
import type { LogicCriterion } from "./types";

interface Props {
  open: boolean;
  anchorEl: HTMLElement | null;
  mode: "replace" | "add" | "replace_action";
  focusLabel: string | null;
  initialQuery: string;
  onPick: (criterion: LogicCriterion) => void;
  /**
   * Phase 6b: forwarded to ConceptSearchPanel. When the popover is in
   * "add" mode (i.e. inserting a new leaf under a group) the parent
   * may pass a handler that inserts an OBSERVATION leaf instead of a
   * CONCEPT when the reviewer picks "Compare value..." on an
   * observable-looking hit.
   */
  onPickObservation?: (seed: ObservationSeed) => void;
  onClose: () => void;
}

export default function ChipSearchPopover({
  open,
  anchorEl,
  mode,
  focusLabel,
  initialQuery,
  onPick,
  onPickObservation,
  onClose,
}: Props) {
  const heading =
    mode === "replace_action"
      ? "Swap the recommended procedure"
      : mode === "replace"
        ? "Swap this symptom or sign"
        : "Add a symptom or sign";

  return (
    <Popover
      open={open}
      anchorEl={anchorEl}
      onClose={onClose}
      disableRestoreFocus
      anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      transformOrigin={{ vertical: "top", horizontal: "left" }}
      slotProps={{
        paper: {
          "aria-label": heading,
          sx: {
            width: { xs: "calc(100vw - 32px)", sm: 420 },
            maxWidth: "calc(100vw - 32px)",
            mt: 0.5,
            borderRadius: 2,
            boxShadow:
              "0 4px 12px rgba(15, 23, 42, 0.08), 0 16px 40px rgba(15, 23, 42, 0.12)",
            overflow: "hidden",
          },
        },
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        spacing={1}
        sx={{
          px: 1.5,
          py: 1,
          borderBottom: "1px solid",
          borderColor: "divider",
          bgcolor: "background.paper",
        }}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            variant="subtitle2"
            sx={{ fontWeight: 700, lineHeight: 1.2 }}
          >
            {heading}
          </Typography>
          {focusLabel && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mt: 0.25 }}
            >
              {focusLabel}
            </Typography>
          )}
        </Box>
        <Tooltip title="Close (ESC)">
          <IconButton
            onClick={onClose}
            size="small"
            aria-label="Close search"
            sx={{ color: "text.secondary" }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
      <Box sx={{ p: 1.5 }}>
        <ConceptSearchPanel
          mode={mode}
          focusLabel={null}
          initialQuery={initialQuery}
          onPick={onPick}
          onPickObservation={mode === "add" ? onPickObservation : undefined}
        />
      </Box>
    </Popover>
  );
}
