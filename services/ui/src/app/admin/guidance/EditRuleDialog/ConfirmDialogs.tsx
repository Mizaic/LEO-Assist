/**
 * Phase 7 confirm dialogs for destructive edits.
 *
 * Wraps two semantically-destructive edits in a before/after preview
 * the reviewer must explicitly accept:
 *
 *   - Root-group kind change (AND <-> OR <-> NOT <-> AT_LEAST).
 *     ``ConfirmKindChangeDialog`` shows the rule sentence as it
 *     reads now and as it will read after the change, both rendered
 *     by ``treeToSentence``.
 *
 *   - OBSERVATION leaf operator flip across the threshold direction
 *     (e.g. ``<`` -> ``>``). ``ConfirmObservationFlipDialog`` shows
 *     the same before/after as a single observation sentence so the
 *     reviewer sees the inverted clinical meaning.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

import * as React from "react";
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Stack,
  Typography,
} from "@mui/material";
import {
  CONFIRM_KIND_CHANGE,
  CONFIRM_OBSERVATION_FLIP,
  OBSERVATION_OPERATOR_PHRASES,
  friendlyTerm,
  recencyLabel,
} from "./copy";
import { treeToSentence } from "./treeToSentence";
import type {
  EditableLogicNode,
  EditableObservationPayload,
  LogicNodeKind,
} from "./types";

interface ConfirmKindChangeDialogProps {
  open: boolean;
  /** Tree before the change (current state). */
  before: EditableLogicNode | null;
  /** Tree after the proposed change (root.kind swapped). */
  after: EditableLogicNode | null;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Confirm a destructive root-group kind change, with the before/after
 * sentence rendered by ``treeToSentence`` so the reviewer sees the
 * impact in plain English before committing.
 */
export function ConfirmKindChangeDialog({
  open,
  before,
  after,
  onConfirm,
  onCancel,
}: ConfirmKindChangeDialogProps) {
  const beforeSentence = before ? treeToSentence(before).lead : "";
  const afterSentence = after ? treeToSentence(after).lead : "";
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      aria-label={CONFIRM_KIND_CHANGE.ariaLabel}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle>{CONFIRM_KIND_CHANGE.title}</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>
          {CONFIRM_KIND_CHANGE.body}
        </DialogContentText>
        <BeforeAfter
          beforeLabel={CONFIRM_KIND_CHANGE.beforeLabel}
          beforeText={beforeSentence}
          afterLabel={CONFIRM_KIND_CHANGE.afterLabel}
          afterText={afterSentence}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} color="inherit">
          {CONFIRM_KIND_CHANGE.cancelLabel}
        </Button>
        <Button onClick={onConfirm} variant="contained" autoFocus>
          {CONFIRM_KIND_CHANGE.confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

interface ConfirmObservationFlipProps {
  open: boolean;
  /** Observation payload before the operator flip. */
  before: EditableObservationPayload | null;
  /** Observation payload after the operator flip. */
  after: EditableObservationPayload | null;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Confirm an OBSERVATION leaf operator flip across the threshold
 * direction. Renders a one-line sentence of the leaf in both states.
 */
export function ConfirmObservationFlipDialog({
  open,
  before,
  after,
  onConfirm,
  onCancel,
}: ConfirmObservationFlipProps) {
  const beforeSentence = before ? observationOneLiner(before) : "";
  const afterSentence = after ? observationOneLiner(after) : "";
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      aria-label={CONFIRM_OBSERVATION_FLIP.ariaLabel}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle>{CONFIRM_OBSERVATION_FLIP.title}</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>
          {CONFIRM_OBSERVATION_FLIP.body}
        </DialogContentText>
        <BeforeAfter
          beforeLabel={CONFIRM_OBSERVATION_FLIP.beforeLabel}
          beforeText={beforeSentence}
          afterLabel={CONFIRM_OBSERVATION_FLIP.afterLabel}
          afterText={afterSentence}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} color="inherit">
          {CONFIRM_OBSERVATION_FLIP.cancelLabel}
        </Button>
        <Button onClick={onConfirm} variant="contained" autoFocus>
          {CONFIRM_OBSERVATION_FLIP.confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function BeforeAfter({
  beforeLabel,
  beforeText,
  afterLabel,
  afterText,
}: {
  beforeLabel: string;
  beforeText: string;
  afterLabel: string;
  afterText: string;
}) {
  return (
    <Stack spacing={1.5}>
      <Box>
        <Typography
          variant="overline"
          color="text.secondary"
          sx={{ display: "block", lineHeight: 1.2 }}
        >
          {beforeLabel}
        </Typography>
        <Typography variant="body2" sx={{ fontStyle: "italic" }}>
          {beforeText || "(empty rule)"}
        </Typography>
      </Box>
      <Box>
        <Typography
          variant="overline"
          color="text.secondary"
          sx={{ display: "block", lineHeight: 1.2 }}
        >
          {afterLabel}
        </Typography>
        <Typography
          variant="body2"
          sx={{ fontStyle: "italic", fontWeight: 600 }}
        >
          {afterText || "(empty rule)"}
        </Typography>
      </Box>
    </Stack>
  );
}

/**
 * Render an OBSERVATION leaf as a single short sentence for the
 * confirm dialog. Kept local (instead of going through
 * ``treeToSentence``) so the dialog can describe the leaf without
 * the surrounding "Applies to patients who has ..." preamble.
 */
function observationOneLiner(obs: EditableObservationPayload): string {
  const term = friendlyTerm(obs.observable_term) || "this lab value";
  const op = OBSERVATION_OPERATOR_PHRASES[obs.operator] ?? obs.operator;
  let valuePart: string;
  if (obs.operator === "between" && Array.isArray(obs.value)) {
    valuePart = `${obs.value[0]} and ${obs.value[1]}`;
  } else if (Array.isArray(obs.value)) {
    valuePart = String(obs.value[0]);
  } else {
    valuePart = String(obs.value);
  }
  const unit = obs.unit ? ` ${obs.unit}` : "";
  const recency = recencyLabel(obs.within_days);
  return `${term} ${op} ${valuePart}${unit}, ${recency}`;
}

// Re-export the kind-change predicate so call sites can import it
// from the same place as the dialog.
export type { LogicNodeKind };
