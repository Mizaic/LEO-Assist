/**
 * Shared status chrome for the Validation Lab pipeline wizard.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
 */
"use client";

import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import SkipNextIcon from "@mui/icons-material/SkipNext";

export type StageColor = "success" | "error" | "warning" | "default";

export function stageColor(status: string): StageColor {
  if (status === "completed" || status === "success") return "success";
  if (status === "failed" || status === "poisoned") return "error";
  if (status === "skipped" || status === "skipped_persist") return "warning";
  return "default";
}

export function StageIcon({ status }: { status: string }) {
  const color = stageColor(status);
  if (color === "success") {
    return <CheckCircleOutlineIcon fontSize="small" sx={{ color: "#166534" }} />;
  }
  if (color === "error") {
    return <ErrorOutlineIcon fontSize="small" sx={{ color: "#991B1B" }} />;
  }
  if (color === "warning") {
    return <SkipNextIcon fontSize="small" sx={{ color: "#854D0E" }} />;
  }
  return (
    <RadioButtonUncheckedIcon
      fontSize="small"
      sx={{ color: "#94A3B8", animation: "spin 1.5s linear infinite" }}
    />
  );
}

export function formatMs(ms: number | undefined): string {
  if (ms === undefined) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function watchStepId(spans: { step_id: string; status: string }[]): string {
  const running = [...spans]
    .reverse()
    .find((s) => s.status === "running" || s.status === "pending");
  if (running) return running.step_id;
  const failed = [...spans]
    .reverse()
    .find((s) => s.status === "failed" || s.status === "poisoned");
  if (failed) return failed.step_id;
  return spans[spans.length - 1]?.step_id || "";
}
