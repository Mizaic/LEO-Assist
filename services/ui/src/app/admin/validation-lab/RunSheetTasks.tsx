/**
 * Task-by-task stage rows for the Validation Lab run sheet.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-020F98AE, DI-12D40786, DI-2289D095, DI-43E908C6, DI-62175179, DI-9138BAC9, DI-A898556B, DI-FE423B8D
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { motion as fm } from "framer-motion";

import { formatAgentName } from "./agentRoster";
import type { PhaseOutput, StageProgress } from "./labApi";
import { formatStageLabel } from "./labRunFormat";

export interface TaskRow {
  key: string;
  label: string;
  status: string;
  workerId?: string;
}

export const DONE_STATUSES = new Set([
  "completed",
  "failed",
  "skipped_persist",
]);

export function taskRowsFromSheet(input: {
  stages?: StageProgress[];
  phases: PhaseOutput[];
  terminal: boolean;
  status: string;
}): TaskRow[] {
  if (input.stages && input.stages.length > 0) {
    return input.stages.map((s) => ({
      key: s.step_id,
      label: formatStageLabel(s.step_id),
      status: s.status,
      workerId: (s.worker_id || "").trim() || undefined,
    }));
  }
  return (input.phases || []).map((p, index) => ({
    key: p.phase_id,
    label: p.phase_id,
    status: input.terminal
      ? input.status === "failed"
        ? "failed"
        : "completed"
      : p.status === "skipped_persist"
        ? "skipped_persist"
        : p.status === "queued" ||
            p.status === "running" ||
            p.status === "failed" ||
            p.status === "completed"
          ? p.status
          : input.status === "queued" && index === 0
            ? "queued"
            : input.status === "queued"
              ? "pending"
              : "waiting",
  }));
}

export function stageProgressCounts(rows: TaskRow[]): {
  value: number;
  total: number;
} {
  const total = Math.max(rows.length, 1);
  const value = rows.filter((r) => DONE_STATUSES.has(r.status)).length;
  return { value, total };
}

export function statusColor(
  status: string,
): "error" | "success.main" | "warning.main" | "text.secondary" | "info.main" {
  if (status === "failed") return "error";
  if (status === "completed" || status === "skipped_persist") {
    return "success.main";
  }
  if (status === "running") return "info.main";
  if (status === "queued" || status === "pending") return "warning.main";
  return "text.secondary";
}

export function TaskList({ rows }: { rows: TaskRow[] }) {
  return (
    <Stack
      spacing={0.5}
      sx={{ maxHeight: 240, overflow: "auto" }}
      data-testid="validation-lab-run-sheet-tasks"
    >
      {rows.map((row, index) => (
        <fm.div
          key={row.key}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: Math.min(index, 12) * 0.03 }}
        >
          <Box
            sx={{
              display: "flex",
              justifyContent: "space-between",
              gap: 1,
              py: 0.5,
              borderBottom: "1px solid",
              borderColor: "divider",
              alignItems: "baseline",
            }}
            data-testid={`validation-lab-run-sheet-task-${row.key}`}
          >
            <Stack spacing={0} sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" noWrap>
                {row.label}
              </Typography>
              {row.workerId ? (
                <Typography
                  variant="caption"
                  color="text.secondary"
                  noWrap
                  title={row.workerId}
                  data-testid={`validation-lab-run-sheet-worker-${row.key}`}
                >
                  Agent: {formatAgentName(row.workerId)}
                </Typography>
              ) : null}
            </Stack>
            <Typography variant="caption" color={statusColor(row.status)}>
              {row.status}
            </Typography>
          </Box>
        </fm.div>
      ))}
    </Stack>
  );
}
