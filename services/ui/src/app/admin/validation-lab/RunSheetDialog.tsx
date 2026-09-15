/**
 * Focused run sheet for Validation Lab single / multi pipeline runs.
 *
 * Atlas: DI-FE423B8D / DI-62175179 / DO-158BE606
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { motion as fm } from "framer-motion";
import { ProgressStrip, useMotion } from "@leo/design-system";

import type { LabRunLlmUsage, PhaseOutput, StageProgress } from "./labApi";
import {
  formatTokens,
  formatUsd,
  sumBatchCostUsd,
  usageFromRunOutputs,
} from "./labRunFormat";
import {
  stageProgressCounts,
  statusColor,
  TaskList,
  taskRowsFromSheet,
} from "./RunSheetTasks";
import { buildSupportContext } from "./runSheetSupport";
import { RunSheetSbarActions } from "./RunSheetSbar";
import { RunInspectorPanel } from "./inspector/RunInspectorPanel";
import type { LabTraceSpan } from "./inspectorTypes";
import type { UseLabRunInspectorReturn } from "@/hooks/useLabRunInspector";
import {
  useLabRunInspector,
  useLabRunStagePoll,
} from "@/hooks/useLabRunInspector";

export interface SingleRunSheet {
  mode: "single";
  caseId: string;
  title: string;
  runId?: string;
  status: string;
  phases: PhaseOutput[];
  stages?: StageProgress[];
  llmUsage?: LabRunLlmUsage | null;
  /** Compiled guideline bitmap version this run evaluated against. */
  rulesetVersion?: string | null;
  error?: string;
  terminal: boolean;
  /** Known SBAR id from a Care document run (skips the Lab lookup). */
  assessmentId?: string | null;
  /** Pipeline run id when there is no Validation Lab case. */
  pipelineRunId?: string;
}

export type MultiItemStatus =
  | "pending"
  | "queued"
  | "running"
  | "completed"
  | "failed";

export interface MultiRunSheetItem {
  caseId: string;
  title: string;
  status: MultiItemStatus;
  runId?: string;
  error?: string;
  costUsd?: number | null;
}

export interface MultiRunSheet {
  mode: "multi";
  items: MultiRunSheetItem[];
  phase: "queueing" | "watching";
  done: boolean;
}

export type RunSheetState = SingleRunSheet | MultiRunSheet;

interface Props {
  sheet: RunSheetState | null;
  onClose: () => void;
  showSbarActions?: boolean;
}

function CopySupportDetails({ sheet }: { sheet: SingleRunSheet }) {
  const [notice, setNotice] = useState<string | null>(null);
  if (!sheet.terminal && sheet.status !== "failed") return null;

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(buildSupportContext(sheet));
      setNotice("Support details copied.");
    } catch {
      setNotice("Could not copy. Copy failed.");
    }
  }

  return (
    <Stack spacing={0.5}>
      <Button
        size="small"
        variant="outlined"
        onClick={onCopy}
        data-testid="validation-lab-run-sheet-copy-support"
      >
        Copy support details
      </Button>
      <Typography variant="caption" color="text.secondary">
        {notice ||
          "Includes run id, stage status, and worker identity for a support call."}
      </Typography>
    </Stack>
  );
}

function SingleBody({
  sheet,
  liveSpans,
  inspector,
}: {
  sheet: SingleRunSheet;
  liveSpans?: LabTraceSpan[];
  inspector?: UseLabRunInspectorReturn;
}) {
  const usage = usageFromRunOutputs(sheet.llmUsage);
  const rows = taskRowsFromSheet({ ...sheet, liveSpans });
  const progress = stageProgressCounts(rows);
  const tone =
    sheet.status === "failed"
      ? "danger"
      : sheet.status === "completed"
        ? "positive"
        : "neutral";
  return (
    <Stack spacing={2} data-testid="validation-lab-run-sheet-single">
      <Typography variant="body2" color="text.secondary">
        {sheet.title}
      </Typography>
      <Typography variant="body2">
        Status: <strong>{sheet.status}</strong>
        {sheet.runId ? ` · ${sheet.runId.slice(0, 8)}` : ""}
      </Typography>
      {sheet.rulesetVersion ? (
        <Typography
          variant="body2"
          color="text.secondary"
          data-testid="validation-lab-run-sheet-bitmap"
          sx={{ fontFamily: "monospace" }}
        >
          Bitmap version: {sheet.rulesetVersion}
        </Typography>
      ) : null}
      {sheet.status === "queued" && !(sheet.stages && sheet.stages.length) ? (
        <Typography
          variant="body2"
          color="text.secondary"
          data-testid="validation-lab-run-sheet-queued-hint"
        >
          Waiting for the pipeline worker to pick up this run from the queue.
          The stage list updates once processing starts (this can take several
          minutes when the queue is busy).
        </Typography>
      ) : null}
      <ProgressStrip
        label="Pipeline stages"
        value={
          sheet.terminal && sheet.status === "completed"
            ? progress.total
            : progress.value
        }
        total={progress.total}
        subtitle={
          sheet.terminal
            ? sheet.status
            : `${progress.value} of ${progress.total} done`
        }
        tone={tone}
      />
      <TaskList rows={rows} />
      {usage ? (
        <Stack
          direction="row"
          spacing={2}
          data-testid="validation-lab-run-sheet-cost"
        >
          <Typography variant="body2">
            Cost: <strong>{formatUsd(usage.cost_usd)}</strong>
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {formatTokens(usage.total_tokens)} tokens · {usage.llm_calls || 0}{" "}
            calls
          </Typography>
        </Stack>
      ) : sheet.terminal ? (
        <Typography
          variant="body2"
          color="text.secondary"
          data-testid="validation-lab-run-sheet-cost-na"
        >
          Cost n/a -- no LLM telemetry on this run yet.
        </Typography>
      ) : null}
      {sheet.error ? (
        <Typography variant="body2" color="error">
          {sheet.error}
        </Typography>
      ) : null}
      <CopySupportDetails sheet={sheet} />
      {sheet.runId && inspector ? (
        <RunInspectorPanel
          runId={sheet.runId}
          runStatus={sheet.status}
          terminal={sheet.terminal}
          inspector={inspector}
        />
      ) : null}
    </Stack>
  );
}

function MultiBody({ sheet }: { sheet: MultiRunSheet }) {
  const terminal = sheet.items.filter(
    (i) => i.status === "completed" || i.status === "failed",
  ).length;
  const running = sheet.items.filter((i) => i.status === "running").length;
  const queued = sheet.items.filter((i) => i.status === "queued").length;
  const failed = sheet.items.filter((i) => i.status === "failed").length;
  const batchCost = sumBatchCostUsd(sheet.items);
  const priced = sheet.items.filter(
    (i) => i.costUsd != null && Number(i.costUsd) > 0,
  ).length;
  const label =
    sheet.phase === "queueing" ? "Queueing runs" : "Live pipeline progress";
  const subtitle =
    sheet.phase === "queueing"
      ? `${queued + terminal} started · ${sheet.items.length - queued - terminal} pending`
      : `${terminal} done · ${running} running · ${queued} queued · ${failed} failed`;

  return (
    <Stack spacing={2} data-testid="validation-lab-run-sheet-multi">
      <ProgressStrip
        label={label}
        value={sheet.phase === "queueing" ? queued + terminal : terminal}
        total={Math.max(sheet.items.length, 1)}
        subtitle={subtitle}
        tone={failed > 0 ? "warning" : sheet.done ? "positive" : "neutral"}
      />
      {batchCost != null ? (
        <Typography
          variant="body2"
          data-testid="validation-lab-run-sheet-batch-cost"
        >
          Batch cost: <strong>{formatUsd(batchCost)}</strong>
          <Typography
            component="span"
            variant="body2"
            color="text.secondary"
            sx={{ ml: 1 }}
          >
            ({priced} of {sheet.items.length} with telemetry)
          </Typography>
        </Typography>
      ) : sheet.phase === "watching" || sheet.done ? (
        <Typography
          variant="body2"
          color="text.secondary"
          data-testid="validation-lab-run-sheet-batch-cost-na"
        >
          Batch cost n/a -- waiting for LLM telemetry.
        </Typography>
      ) : null}
      <Stack spacing={0.75} sx={{ maxHeight: 280, overflow: "auto" }}>
        {sheet.items.map((item, index) => (
          <fm.div
            key={item.caseId}
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
              }}
              data-testid={`validation-lab-run-sheet-item-${item.caseId}`}
            >
              <Typography variant="body2" noWrap sx={{ flex: 1 }}>
                {item.title || item.caseId}
              </Typography>
              <Stack direction="row" spacing={1} alignItems="center">
                {item.costUsd != null && item.costUsd > 0 ? (
                  <Typography variant="caption" color="text.secondary">
                    {formatUsd(item.costUsd)}
                  </Typography>
                ) : null}
                <Typography
                  variant="caption"
                  color={statusColor(item.status)}
                >
                  {item.status}
                </Typography>
              </Stack>
            </Box>
          </fm.div>
        ))}
      </Stack>
      {sheet.phase === "watching" && !sheet.done ? (
        <Typography variant="body2" color="text.secondary">
          Polling workers every few seconds. Dismiss to keep working while runs
          continue in the background.
        </Typography>
      ) : null}
      {sheet.done ? (
        <Typography variant="body2" color="text.secondary">
          Batch watch finished. Card costs refresh from the case list.
        </Typography>
      ) : null}
    </Stack>
  );
}

export default function RunSheetDialog({
  sheet,
  onClose,
  showSbarActions = true,
}: Props) {
  const { reducedMotion } = useMotion();
  const single = sheet?.mode === "single" ? sheet : null;
  const polledStages = useLabRunStagePoll(
    single?.caseId || "",
    single?.runId || "",
    Boolean(single?.runId),
    Boolean(single?.terminal),
  );
  const mergedStages =
    single?.stages && single.stages.length > 0 ? single.stages : polledStages;
  const inspector = useLabRunInspector({
    caseId: single?.caseId || "",
    runId: single?.runId || "",
    pipelineRunId: single?.pipelineRunId,
    enabled: Boolean(single?.runId || single?.pipelineRunId),
    pollStages: mergedStages,
    terminal: Boolean(single?.terminal),
  });
  if (!sheet) return null;
  const watching =
    sheet.mode === "single"
      ? !sheet.terminal
      : sheet.phase === "watching" && !sheet.done;
  const title =
    sheet.mode === "single" ? "Pipeline run" : "Pipeline batch progress";
  const dismissLabel = watching ? "Work in background" : "Dismiss";

  return (
    <Dialog
      open
      onClose={onClose}
      fullWidth
      maxWidth="lg"
      data-testid="validation-lab-run-sheet"
    >
      <fm.div
        initial={reducedMotion ? false : { opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: reducedMotion ? 0 : 0.18 }}
      >
        <DialogTitle>{title}</DialogTitle>
        <DialogContent sx={{ pb: 1 }}>
          {sheet.mode === "single" ? (
            <SingleBody
              sheet={sheet}
              liveSpans={inspector.spans}
              inspector={inspector}
            />
          ) : (
            <MultiBody sheet={sheet} />
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2, gap: 1, flexWrap: "wrap" }}>
          {sheet.mode === "single" && showSbarActions ? (
            <RunSheetSbarActions sheet={sheet} />
          ) : null}
          <Button
            onClick={onClose}
            variant="contained"
            data-testid="validation-lab-run-sheet-dismiss"
          >
            {dismissLabel}
          </Button>
        </DialogActions>
      </fm.div>
    </Dialog>
  );
}
