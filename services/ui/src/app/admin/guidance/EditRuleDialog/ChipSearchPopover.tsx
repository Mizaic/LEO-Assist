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

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Popover, { type PopoverActions } from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import { SEARCH_PANEL } from "./copy";
import ConceptSearchPanel, { type ObservationSeed } from "./ConceptSearchPanel";
import MultiConceptPicker from "./MultiConceptPicker";
import type { LogicCriterion } from "./types";

interface Props {
  open: boolean;
  anchorEl: HTMLElement | null;
  mode: "replace" | "add" | "replace_action";
  /** When ``mode`` is ``replace``, distinguishes symptom vs lab-value chips. */
  replaceKind?: "concept" | "observation" | null;
  focusLabel: string | null;
  initialQuery: string;
  /**
   * Only meaningful when ``mode === "add"``: swaps the single-pick
   * ConceptSearchPanel for MultiConceptPicker, so the reviewer can
   * tick more than one SNOMED code and confirm them together as one
   * criterion (see MultiConceptPicker's own doc comment for why that
   * is not the same as adding several separate leaves). The
   * highlight-to-build wizard's own row-click and highlighted-selection
   * add flows set this; the Advanced/Sentence editor's "+Add" does not.
   * MultiConceptPicker now also supports operator / value / unit on
   * observable hits (same OBSERVATION path as "Compare value...").
   */
  multiPick?: boolean;
  onPick: (criterion: LogicCriterion) => void;
  /**
   * Bulk-add from "Ask LEO for ideas" (several sibling CONCEPT leaves).
   * Only forwarded in ``add`` mode when the host supports multi-add.
   */
  onAddMany?: (criteria: LogicCriterion[]) => void;
  /**
   * Phase 6b: forwarded to ConceptSearchPanel ("Compare value...") and
   * MultiConceptPicker (operator / value / unit on a ticked observable).
   * When the popover is in "add" mode the parent inserts an OBSERVATION
   * leaf instead of a CONCEPT.
   */
  onPickObservation?: (seed: ObservationSeed) => void;
  onClose: () => void;
}

export default function ChipSearchPopover({
  open,
  anchorEl,
  mode,
  replaceKind = null,
  focusLabel,
  initialQuery,
  multiPick = false,
  onPick,
  onAddMany,
  onPickObservation,
  onClose,
}: Props) {
  const heading =
    mode === "replace_action"
      ? SEARCH_PANEL.headings.replace_action
      : mode === "replace" && replaceKind === "observation"
        ? SEARCH_PANEL.headings.replace_observation
        : mode === "replace"
          ? SEARCH_PANEL.headings.replace
          : SEARCH_PANEL.headings.add;
  const showMultiPicker = mode === "add" && multiPick;

  // MUI's Popover computes its position once, when it opens, from the
  // paper's height at that moment -- it does not reposition itself
  // just because that paper's own natural (shrink-to-fit) height
  // grows afterwards. This paper's height is NOT fixed: it starts
  // small (just the query box) and grows as results arrive, and, in
  // multi-pick mode, again each time a ticked result adds a "Depth"
  // stepper row. Without this, a popover that fit comfortably the
  // moment it opened can grow past the bottom of the screen as the
  // reviewer interacts with it, with nothing left to reposition it.
  // Observing the paper itself (not an inner, already-clipped Box)
  // and re-running the same positioning logic on every resize keeps
  // it anchored correctly -- shifting up, never off-screen -- no
  // matter how tall its content gets.
  const popoverActionRef = useRef<PopoverActions>(null);
  // A callback ref (backed by state), not a plain useRef: MUI's Modal
  // portal defers actually mounting the paper into the DOM by one
  // render past this component's own mount (an SSR-safety pattern),
  // so a plain ref read inside a `[open]`-only effect can run before
  // the node exists and never re-check it. Setting state from the ref
  // callback re-runs the effect below the moment the real node shows
  // up, however many renders that takes.
  const [paperNode, setPaperNode] = useState<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!open || !paperNode || typeof ResizeObserver === "undefined") {
      return undefined;
    }
    const observer = new ResizeObserver(() => {
      popoverActionRef.current?.updatePosition();
    });
    observer.observe(paperNode);
    return () => observer.disconnect();
  }, [open, paperNode]);

  return (
    <Popover
      open={open}
      anchorEl={anchorEl}
      onClose={onClose}
      action={popoverActionRef}
      disableRestoreFocus
      anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      transformOrigin={{ vertical: "top", horizontal: "left" }}
      slotProps={{
        paper: {
          ref: setPaperNode,
          "aria-label": heading,
          sx: {
            width: { xs: "calc(100vw - 32px)", sm: 420 },
            maxWidth: "calc(100vw - 32px)",
            maxHeight: "min(70vh, calc(100vh - 32px))",
            mt: 0.5,
            borderRadius: 2,
            boxShadow:
              "0 4px 12px rgba(15, 23, 42, 0.08), 0 16px 40px rgba(15, 23, 42, 0.12)",
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
          },
        },
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        spacing={1}
        sx={{
          flexShrink: 0,
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
      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
          p: 1.5,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {showMultiPicker ? (
          <MultiConceptPicker
            initialQuery={initialQuery}
            embedded
            onConfirm={onPick}
            onConfirmObservation={
              mode === "add" ? onPickObservation : undefined
            }
          />
        ) : (
          <ConceptSearchPanel
            mode={mode}
            focusLabel={null}
            showHeading={false}
            embedded
            initialQuery={initialQuery}
            onPick={onPick}
            onAddMany={mode === "add" ? onAddMany : undefined}
            onPickObservation={mode === "add" ? onPickObservation : undefined}
            filterToObservable={replaceKind === "observation"}
          />
        )}
      </Box>
    </Popover>
  );
}
