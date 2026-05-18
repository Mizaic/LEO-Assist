/**
 * LockChip -- a tiny status chip showing that an entity is locked
 * (or, in some surfaces, that it is unlocked but lockable).
 *
 * Used by:
 *   - MilestoneSlotRow (every reconciled slot)
 *   - EpisodeTimeline (small lock glyph on locked milestone nodes)
 *   - EncounterTextTab (lock chip on locked encounter cards)
 *
 * Atlas trace:
 *   DO: services/ui/src/components/mission-control/LockChip.tsx
 *   DI: DI-C424BB44 (VerificationLock cross-entity primitive)
 *   DI: DI-9DCC9F84 (Reconcile pathway)
 */
"use client";

import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import LockOutlined from "@mui/icons-material/LockOutlined";
import LockOpenOutlined from "@mui/icons-material/LockOpenOutlined";
import type { VerificationLockSummary } from "@/lib/missionControlApi";

interface Props {
  /** When provided, renders the locked chip with reviewer info in
   * the tooltip; when null/undefined renders an "Unlocked" placeholder
   * chip used in surfaces that always render the slot. */
  lock?: VerificationLockSummary | null;
  /** Some surfaces (timeline) only want the icon. */
  iconOnly?: boolean;
  size?: "small" | "medium";
}

function describe(lock: VerificationLockSummary): string {
  const role =
    lock.locked_by_role === "qa_ra_lead" ? "QA / RA lead" : "clinician";
  const when = lock.locked_at?.slice(0, 10) ?? "today";
  return `Locked by ${role} ${lock.locked_by} on ${when}. Reason: ${lock.lock_reason}`;
}

export default function LockChip({ lock, iconOnly = false, size = "small" }: Props) {
  if (!lock) {
    return (
      <Chip
        size={size}
        variant="outlined"
        icon={<LockOpenOutlined fontSize="small" />}
        label={iconOnly ? undefined : "Unlocked"}
        aria-label="Unlocked"
        sx={{ color: "text.secondary", borderStyle: "dashed" }}
      />
    );
  }
  const tooltip = describe(lock);
  return (
    <Tooltip title={tooltip} arrow>
      <Chip
        size={size}
        color="success"
        variant="filled"
        icon={<LockOutlined fontSize="small" />}
        label={iconOnly ? undefined : "Locked"}
        aria-label={tooltip}
      />
    </Tooltip>
  );
}
