/**
 * Atlas trace:
 *   DO: DO-E647765A
 *   DI: DI-0C8FBAF7
 */
"use client";

import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { SegmentedTabs } from "@leo/design-system";
import type { RuleStatusFilter } from "./ruleReviewTypes";

const FILTER_TABS = [
  { id: "pending_review" as const, label: "Pending review", helper: "Rules waiting for a reviewer to approve, edit, or reject." },
  { id: "active" as const, label: "Active", helper: "Rules currently used by the live ruleset." },
  { id: "superseded" as const, label: "Superseded", helper: "Older versions replaced by an edit. Read-only history." },
];

interface Props {
  statusFilter: RuleStatusFilter;
  onFilterChange: (filter: RuleStatusFilter) => void;
  visibleCount: number;
  busy: string | null;
  onApproveAll: () => void;
}

export default function RuleReviewToolbar({ statusFilter, onFilterChange, visibleCount, busy, onApproveAll }: Props) {
  const helperText = FILTER_TABS.find((t) => t.id === statusFilter)?.helper ?? "";
  const statusLabel = statusFilter === "pending_review" ? "rule" : statusFilter === "active" ? "active rule" : "superseded rule";
  const suffix = statusFilter === "pending_review" ? " to check -- click a row to read in full" : " -- click a row to read in full";

  return (
    <Stack spacing={1} sx={{ mb: 1.5 }}>
      <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap">
        <SegmentedTabs
          tabs={FILTER_TABS.map((t) => ({ id: t.id, label: t.label }))}
          value={statusFilter}
          onChange={(id) => onFilterChange(id as RuleStatusFilter)}
          aria-label="Filter rules by status"
        />
        <Typography variant="caption" color="text.secondary">{helperText}</Typography>
      </Stack>

      {visibleCount > 0 && (
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {visibleCount} {statusLabel}{visibleCount !== 1 ? "s" : ""}{suffix}
          </Typography>
          {statusFilter === "pending_review" && (
            <Tooltip title="Approve every pending rule in one click. Only use after reading them all.">
              <span>
                <Button variant="outlined" size="small" disabled={busy === "all"} onClick={onApproveAll} aria-label="Approve all rules">
                  Approve all
                </Button>
              </span>
            </Tooltip>
          )}
        </Stack>
      )}
    </Stack>
  );
}
