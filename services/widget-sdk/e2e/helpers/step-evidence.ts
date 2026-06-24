import { expect, type Locator, type Page, type TestInfo } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";

type StepEvidenceOptions = {
  valId: string;
  stepIndex: number;
  stepName: string;
  page: Page;
  testInfo: TestInfo;
  screenshotTarget?: Locator;
};

const DEFAULT_READY_TIMEOUT_MS = 15_000;

export async function attachStepScreenshot({
  valId,
  stepIndex,
  stepName,
  page,
  testInfo,
  screenshotTarget,
}: StepEvidenceOptions): Promise<string> {
  const protocolStepNumber = stepIndex + 1;
  const safeStepName = stepName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
  const attachmentName = `${valId}-step-${protocolStepNumber}-${safeStepName}`;
  const screenshotPath = testInfo.outputPath(`${attachmentName}.png`);
  const stableEvidencePath = path.join(
    process.cwd(),
    "evidence-artifacts",
    valId,
    `${attachmentName}.png`,
  );

  await waitForScreenshotReady(page, screenshotTarget);

  if (screenshotTarget) {
    await screenshotTarget.screenshot({ path: screenshotPath });
  } else {
    await page.screenshot({ path: screenshotPath, fullPage: true });
  }

  await fs.mkdir(path.dirname(stableEvidencePath), { recursive: true });
  await fs.copyFile(screenshotPath, stableEvidencePath);

  await testInfo.attach(attachmentName, {
    path: screenshotPath,
    contentType: "image/png",
  });

  return stableEvidencePath;
}

async function waitForScreenshotReady(
  page: Page,
  screenshotTarget?: Locator,
): Promise<void> {
  await waitForEvidencePaint(page);
  if (screenshotTarget) {
    await expect(screenshotTarget).toBeVisible({ timeout: DEFAULT_READY_TIMEOUT_MS });
    return;
  }
  await expect
    .poll(async () => page.evaluate(() => document.readyState), {
      timeout: DEFAULT_READY_TIMEOUT_MS,
    })
    .toMatch(/^(interactive|complete)$/);
  await waitForEvidencePaint(page);
}

async function waitForEvidencePaint(page: Page): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
}
