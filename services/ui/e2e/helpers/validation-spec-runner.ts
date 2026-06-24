import type { APIRequestContext, Page, TestInfo } from "@playwright/test";
import {
  completeRun,
  createValidationRun,
  ensureRunNotLeftRunning,
  failAndComplete,
} from "./atlas-validation-runs";
import { isValidationBlockedError } from "./validation-blocked";

export type ValRunContext = {
  page: Page;
  request: APIRequestContext;
  testInfo: TestInfo;
  runId: string;
  valId: string;
  protocol: readonly string[];
  lastCompletedStep: { value: number };
};

export type ValRunOptions = {
  valId: string;
  targetUrl: string;
  metadata: Record<string, unknown> & { atlas_un_id: string };
  protocol: readonly string[];
  body: (ctx: ValRunContext) => Promise<void>;
};

export async function runValTest(
  page: Page,
  request: APIRequestContext,
  testInfo: TestInfo,
  options: ValRunOptions,
): Promise<void> {
  const lastCompletedStep = { value: -1 };
  let runId: string | undefined;

  try {
    runId = await createValidationRun(request, {
      valTestId: options.valId,
      targetUrl: options.targetUrl,
      metadata: options.metadata,
    });

    await options.body({
      page,
      request,
      testInfo,
      runId,
      valId: options.valId,
      protocol: options.protocol,
      lastCompletedStep,
    });
  } catch (error) {
    if (runId && !isValidationBlockedError(error)) {
      await failAndComplete(
        request,
        runId,
        error,
        lastCompletedStep.value + 1,
      );
    }
    if (isValidationBlockedError(error)) {
      return;
    }
    throw error;
  } finally {
    if (runId) {
      await ensureRunNotLeftRunning(request, runId, lastCompletedStep.value);
    }
  }
}

export async function finishValPass(
  request: APIRequestContext,
  runId: string,
  summary: string,
): Promise<void> {
  await completeRun(request, runId, "pass", { summary });
}
