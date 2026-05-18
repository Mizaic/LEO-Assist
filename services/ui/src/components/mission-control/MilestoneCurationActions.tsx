/**
 * Footer button row for MilestoneCurationDialog. Split out of
 * MilestoneCurationParts so the parts file stays under the 500-LOC
 * budget after the notice-stage buttons landed (DI-50C7E89C).
 *
 * Atlas trace:
 *   DO: DO-7986A957, DO-128CB534
 *   DI: DI-4B99678C, DI-F5E030ED, DI-50C7E89C
 */
"use client";

import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import type { Busy, Stage } from "./MilestoneCurationParts";

export function DialogActionsRow({
  stage,
  busy,
  episodesEmpty,
  noEpisode,
  selectedCount,
  slotCount,
  onClose,
  onProceed,
  onPickDifferent,
  onReplace,
  onConfirmAttach,
}: {
  stage: Stage;
  busy: Busy;
  episodesEmpty: boolean;
  // True when the curator has not yet picked a target episode.
  // Continue stays disabled in that state so we never write to a
  // pathway the curator did not select (DI-74AF7AD8).
  noEpisode: boolean;
  selectedCount: number;
  // Number of milestone slots picked (DI-F5E030ED). Continue is
  // disabled when this is 0 so we never try an empty-slot attach.
  slotCount: number;
  onClose: () => void;
  onProceed: () => void;
  onPickDifferent: () => void;
  onReplace: () => void;
  onConfirmAttach: () => void;
}) {
  const noneSelected = selectedCount === 0;
  const noSlot = slotCount === 0;
  if (stage === "result") {
    return (
      <Button onClick={onClose} data-testid="milestone-dialog-close">
        Close
      </Button>
    );
  }
  return (
    <>
      <Button
        onClick={onClose}
        disabled={Boolean(busy)}
        data-testid="milestone-dialog-cancel"
      >
        Cancel
      </Button>
      {stage === "pick" && (
        <Button
          variant="contained"
          onClick={onProceed}
          disabled={
            Boolean(busy) ||
            episodesEmpty ||
            noEpisode ||
            noneSelected ||
            noSlot
          }
          data-testid="milestone-dialog-next"
        >
          Continue
        </Button>
      )}
      {stage === "conflict" && (
        <>
          <Button
            onClick={onPickDifferent}
            disabled={Boolean(busy)}
            data-testid="milestone-dialog-pick-different-slot"
          >
            Pick a different slot
          </Button>
          <Button
            color="warning"
            variant="contained"
            onClick={onReplace}
            disabled={Boolean(busy) || noneSelected}
            startIcon={
              busy === "replace" ? (
                <CircularProgress size={14} color="inherit" />
              ) : null
            }
            data-testid="milestone-dialog-replace"
          >
            Replace existing
          </Button>
        </>
      )}
      {stage === "notice" && (
        <>
          <Button
            onClick={onPickDifferent}
            disabled={Boolean(busy)}
            data-testid="milestone-dialog-pick-different-slot"
          >
            Pick a different slot
          </Button>
          <Button
            variant="contained"
            onClick={onConfirmAttach}
            disabled={Boolean(busy) || noneSelected}
            startIcon={
              busy === "attach" ? (
                <CircularProgress size={14} color="inherit" />
              ) : null
            }
            data-testid="milestone-dialog-add-anyway"
          >
            Add anyway
          </Button>
        </>
      )}
      {stage === "confirm" && (
        <Button
          variant="contained"
          onClick={onConfirmAttach}
          disabled={Boolean(busy)}
          startIcon={
            busy === "attach" ? (
              <CircularProgress size={14} color="inherit" />
            ) : null
          }
          data-testid="milestone-dialog-confirm-attach"
        >
          Confirm
        </Button>
      )}
    </>
  );
}
