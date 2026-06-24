import type { APIRequestContext } from "@playwright/test";
import {
  completeBlockedRun,
  recordStep,
  ValidationBlockedError,
} from "./atlas-validation-runs";

export async function blockRun(
  request: APIRequestContext,
  runId: string,
  step: string,
  reason: string,
): Promise<never> {
  await recordStep(request, runId, 0, step, "blocked", reason);
  await completeBlockedRun(request, runId, {
    summary: reason,
    failureReason: reason,
  });
}

export function isValidationBlockedError(
  error: unknown,
): error is ValidationBlockedError {
  return error instanceof ValidationBlockedError;
}
