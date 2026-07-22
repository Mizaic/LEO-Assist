/**
 * Support-call context helpers for the Validation Lab run sheet.
 *
 * Atlas: DI-FE423B8D / DO-158BE606
 */

import { formatAgentName } from "./agentRoster";
import type { PhaseOutput, StageProgress } from "./labApi";
import { taskRowsFromSheet } from "./RunSheetTasks";

export interface SupportContextInput {
  caseId: string;
  title: string;
  runId?: string;
  status: string;
  error?: string;
  stages?: StageProgress[];
  phases: PhaseOutput[];
  terminal: boolean;
}

/** Plain-text block for pasting into a support / incident call log. */
export function buildSupportContext(input: SupportContextInput): string {
  const rows = taskRowsFromSheet(input);
  const stageLines =
    rows.length === 0
      ? ["  (no stages reported yet)"]
      : rows.map((row) => {
          if (!row.workerId) {
            return `  - ${row.label}: ${row.status}`;
          }
          const agent = formatAgentName(row.workerId);
          return (
            `  - ${row.label}: ${row.status}` +
            ` agent=${agent} worker=${row.workerId}`
          );
        });
  const lines = [
    "Validation Lab pipeline support context",
    `case_id: ${input.caseId}`,
    `title: ${input.title || "(none)"}`,
    `run_id: ${input.runId || "(none)"}`,
    `status: ${input.status}`,
    `error: ${input.error || "(none)"}`,
    "stages:",
    ...stageLines,
  ];
  return lines.join("\n");
}
