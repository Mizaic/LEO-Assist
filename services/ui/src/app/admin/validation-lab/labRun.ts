/**
 * Shared Lab pipeline run defaults for wizard and patient-card Test.
 *
 * Atlas: DI-12D40786 / DI-2289D095
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
import { pollRunUntilTerminal, startRun, type LabRun } from "./labApi";

export const DEFAULT_LAB_PLAN_ID = "pd-referral-assessment";

export const DEFAULT_LAB_PHASES = [
  "extraction",
  "verification",
  "persist",
  "guidance",
  "sbar",
];

/** Start a production Lab run and poll until terminal. */
export async function runCasePipeline(
  caseId: string,
  planId?: string | null,
): Promise<LabRun> {
  const started = await startRun(caseId, {
    plan_id: planId || DEFAULT_LAB_PLAN_ID,
    phase_ids: DEFAULT_LAB_PHASES,
    persist_mode: "production",
  });
  return pollRunUntilTerminal(caseId, started.run.id);
}
