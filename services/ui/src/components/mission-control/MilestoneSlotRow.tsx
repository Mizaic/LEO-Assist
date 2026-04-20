/**
 * MilestoneSlotRow -- one row inside the Reconcile Pathway drawer.
 *
 * Each row shows the engine's pick, a short rationale snippet,
 * the lock status, and four reviewer actions:
 *   - Confirm        -- accept the engine's pick (writes a lock)
 *   - Replace        -- swap the encounter for another from the patient
 *                       (the parent owns the encounter picker)
 *   - Detach         -- mark the slot as empty
 *   - Not applicable -- mark the slot as not relevant for this pathway
 *
 * The row never mutates anything itself; the parent drawer collects
 * staged actions and submits them in one PATCH call so the API can
 * compute the bucket flip safety check up front.
 *
 * Atlas trace:
 *   DO: services/ui/src/components/mission-control/MilestoneSlotRow.tsx
 *   DI: DI-9DCC9F84 (Reconcile pathway)
 *   DI: DI-C424BB44 (VerificationLock primitive)
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonGroup from "@mui/material/ButtonGroup";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import LockChip from "./LockChip";
import type {
  ReconcileActionType,
  VerificationLockSummary,
} from "@/lib/missionControlApi";

export interface SlotRowData {
  /** Stable slot id used by the API (e.g. "diagnosis", "first_seen"). */
  slot: string;
  /** Plain-language label shown to the reviewer. */
  label: string;
  /** Engine-picked encounter id (or null if no pick yet). */
  engineEncounterId: string | null;
  /** Engine-picked milestone type (or null). */
  engineMilestoneType: string | null;
  /** Engine rationale snippet -- short plain-English text. */
  rationale: string | null;
  /** Existing lock for this slot, if one is on the graph. */
  lock?: VerificationLockSummary | null;
}

export interface StagedAction {
  slot: string;
  action: ReconcileActionType;
  encounterId: string | null;
  milestoneType: string | null;
}

interface Props {
  row: SlotRowData;
  staged?: StagedAction;
  /** Stage an action against this slot. */
  onStage: (action: StagedAction) => void;
  /** Open the patient-scoped encounter picker for the Replace flow.
   * The picker lives in the parent so it can be reused. */
  onReplaceClick: (slot: string) => void;
  /** Disable all actions while a write is in flight. */
  disabled?: boolean;
}

const ACTION_LABELS: Record<ReconcileActionType, string> = {
  confirm: "Confirm",
  replace: "Replace",
  detach: "Detach",
  not_applicable: "Not applicable",
};

function actionDescription(staged: StagedAction): string {
  if (staged.action === "confirm") return "Will keep the engine's pick.";
  if (staged.action === "replace") {
    return staged.encounterId
      ? `Will replace with ${staged.encounterId}.`
      : "Pick a replacement encounter.";
  }
  if (staged.action === "detach") return "Will leave this slot empty.";
  return "Will mark this slot as not applicable.";
}

export default function MilestoneSlotRow({
  row,
  staged,
  onStage,
  onReplaceClick,
  disabled = false,
}: Props) {
  const isLocked = Boolean(row.lock);
  const handle = (action: ReconcileActionType) => {
    if (action === "replace") {
      onReplaceClick(row.slot);
      return;
    }
    onStage({
      slot: row.slot,
      action,
      encounterId: action === "confirm" ? row.engineEncounterId : null,
      milestoneType: action === "confirm" ? row.engineMilestoneType : null,
    });
  };
  return (
    <Box
      data-testid={`slot-row-${row.slot}`}
      sx={{
        border: 1,
        borderColor: "divider",
        borderRadius: 1,
        p: 2,
        display: "flex",
        flexDirection: "column",
        gap: 1,
        opacity: disabled ? 0.7 : 1,
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2">{row.label}</Typography>
        <LockChip lock={row.lock ?? null} size="small" />
      </Stack>

      <Box>
        <Typography variant="body2">
          Engine pick:{" "}
          <strong>{row.engineEncounterId ?? "no encounter assigned"}</strong>
        </Typography>
        {row.rationale ? (
          <Typography variant="caption" color="text.secondary">
            Why: {row.rationale}
          </Typography>
        ) : null}
      </Box>

      <ButtonGroup
        size="small"
        variant="outlined"
        aria-label={`Reviewer actions for ${row.label}`}
        disabled={disabled || isLocked}
      >
        {(Object.keys(ACTION_LABELS) as ReconcileActionType[]).map((a) => (
          <Button
            key={a}
            data-testid={`slot-${row.slot}-action-${a}`}
            variant={staged?.action === a ? "contained" : "outlined"}
            onClick={() => handle(a)}
          >
            {ACTION_LABELS[a]}
          </Button>
        ))}
      </ButtonGroup>

      {staged ? (
        <Typography
          variant="caption"
          color="text.secondary"
          data-testid={`slot-${row.slot}-staged-summary`}
        >
          {actionDescription(staged)}
        </Typography>
      ) : null}

      {isLocked ? (
        <Typography variant="caption" color="text.secondary">
          Already confirmed by a reviewer. Release the lock to change it.
        </Typography>
      ) : null}
    </Box>
  );
}
