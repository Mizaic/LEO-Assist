/**
 * Result-banner sub-components for MilestoneCurationDialog. Split
 * out of MilestoneCurationParts so that file stays under the
 * 500-LOC budget after the multi-slot picker landed (DI-F5E030ED).
 *
 * Atlas trace:
 *   DO: DO-128CB534 (multi-slot picker)
 *   DI: DI-F5E030ED
 */
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type {
  MilestoneDayResult,
  MilestoneMultiSlotResult,
} from "@/lib/missionControlApi";
import { shortDate } from "./encounterTextUtils";
import { milestoneLabel } from "./milestoneOptions";

// Soft notice for context-tier slots that already exist on the
// episode on a different day. Context tags (related GP visit,
// primary care investigations, etc.) are descriptive and may
// legitimately repeat across many days, so the picker confirms
// "adding another" instead of forcing a Replace flow that would
// silently undo the existing curation. DI-50C7E89C, DI-F5E030ED.
export function NoticeAlert({
  notices,
}: {
  notices: { milestoneType: string; otherDays: string[] }[];
}) {
  if (notices.length === 0) return null;
  return (
    <Alert severity="info" data-testid="milestone-dialog-notice">
      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
        {notices.length === 1
          ? "This tag is already on this episode for other days:"
          : `${notices.length} of the picked tags are already on this episode for other days:`}
      </Typography>
      <Box component="ul" sx={{ pl: 2, mt: 0.5, mb: 0.5 }}>
        {notices.map((n) => (
          <li
            key={n.milestoneType}
            data-testid={`milestone-dialog-notice-item-${n.milestoneType}`}
          >
            <Typography variant="body2">
              <strong>{milestoneLabel(n.milestoneType)}</strong> already on{" "}
              {n.otherDays.map((d) => shortDate(d)).join(", ")} ({n.otherDays.length}{" "}
              {n.otherDays.length === 1 ? "day" : "days"})
            </Typography>
          </li>
        ))}
      </Box>
      <Typography variant="caption" sx={{ display: "block", mt: 0.5 }}>
        These tags are descriptive and can repeat. Choose Add anyway to add
        another day, or Pick a different slot to drop them from your
        selection. Existing days will not be detached.
      </Typography>
    </Alert>
  );
}

// Result banner for the multi-slot day attach flow. Aggregates the
// per-slot MilestoneDayResult list returned by the orchestrator and
// shows one summary line plus a per-slot breakdown so the reviewer
// can tell new attaches apart from idempotent no-ops.
export function MultiSlotResultAlert({
  result,
}: {
  result: MilestoneMultiSlotResult;
}) {
  const slotsWithFailures = result.perSlot.filter(
    (r) => r.failed.length > 0
  ).length;
  const severity =
    slotsWithFailures > 0 ? "error" : result.allSucceeded ? "success" : "info";
  return (
    <Alert severity={severity} data-testid="milestone-dialog-result">
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        {result.newlyLinked} new link
        {result.newlyLinked === 1 ? "" : "s"}, {result.alreadyLinked}{" "}
        already linked, {result.failed} failed.
      </Typography>
      <Box sx={{ mt: 0.5 }}>
        {result.perSlot.map((r) => {
          const newCount = r.succeeded.length - r.alreadyLinked.length;
          return (
            <Typography
              key={r.milestone_type}
              variant="caption"
              sx={{ display: "block" }}
              data-testid={`milestone-dialog-result-slot-${r.milestone_type}`}
            >
              {milestoneLabel(r.milestone_type)}: {newCount} new,{" "}
              {r.alreadyLinked.length} already linked, {r.failed.length} failed
            </Typography>
          );
        })}
      </Box>
    </Alert>
  );
}

// Single-slot legacy banner. Used by the per-chip remove flow which
// still calls the legacy day-detach helper.
export function ResultAlert({ result }: { result: MilestoneDayResult }) {
  return (
    <Alert
      severity={result.success ? "success" : "error"}
      data-testid="milestone-dialog-result"
    >
      {result.success
        ? `Done. ${result.succeeded.length} encounter(s) updated.`
        : `Partial update: ${result.succeeded.length} succeeded, ${result.failed.length} failed.`}
      {result.failed.length > 0 && (
        <Box sx={{ mt: 0.5 }}>
          {result.failed.map((f) => (
            <Typography
              key={f.encounter_id}
              variant="caption"
              sx={{ display: "block" }}
            >
              {f.encounter_id}: {f.error}
            </Typography>
          ))}
        </Box>
      )}
    </Alert>
  );
}
