import type { APIRequestContext, Locator, Page, TestInfo } from "@playwright/test";
import { recordStep, uploadEvidence } from "./atlas-validation-runs";
import { attachStepScreenshot } from "./step-evidence";

type RecordProtocolStepOptions = {
  request: APIRequestContext;
  runId: string;
  valId: string;
  page: Page;
  testInfo: TestInfo;
  protocol: readonly string[];
  stepIndex: number;
  screenshotTarget?: Locator;
  notes?: string;
  evidenceCaption?: string;
  /** When set, upload this file instead of capturing a fresh screenshot. */
  evidencePath?: string;
};

export async function recordProtocolStep(
  options: RecordProtocolStepOptions,
): Promise<void> {
  const stepText = options.protocol[options.stepIndex];
  const screenshotPath =
    options.evidencePath ??
    (await attachStepScreenshot({
      valId: options.valId,
      stepIndex: options.stepIndex,
      stepName: stepText,
      page: options.page,
      testInfo: options.testInfo,
      screenshotTarget: options.screenshotTarget,
    }));

  await recordStep(
    options.request,
    options.runId,
    options.stepIndex,
    stepText,
    "pass",
    options.notes,
  );
  await uploadEvidence(
    options.request,
    options.runId,
    options.stepIndex,
    screenshotPath,
    options.evidenceCaption ?? options.notes ?? stepText,
  );
}
