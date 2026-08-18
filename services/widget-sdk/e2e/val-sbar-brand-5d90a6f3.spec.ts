/**
 * VAL-5D90A6F3 -- SBAR widget shows official Mizaic brand.
 *
 * User need: UN-DA0B165F
 * Design input: DI-E5FEF0AE
 *
 * Visual snapshots plus Atlas validation-run screenshot evidence.
 */

import { expect, test, type Page } from "@playwright/test";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import { finishValPass, runValTest } from "./helpers/validation-spec-runner";
import {
  atlasValidationSkipReason,
  isAtlasValidationConfigured,
  loadPlaywrightEnv,
} from "./helpers/validation-env";

loadPlaywrightEnv();

const HOST = "/demo/host-pages/dual-variant.html";
const VAL_ID = "VAL-5D90A6F3";
const UN_ID = "UN-DA0B165F";
const TARGET_URL = process.env.PW_BASE_URL ?? "http://localhost:5173";

const PROTOCOL = [
  "Open the dual-variant demo host. Confirm the iframe SBAR header shows LEO by Mizaic and the LeoO mark.",
  "Confirm the header font is Overpass or Albert Sans and is not restyled by hostile host CSS.",
  "Confirm Situation, Background, Assessment, and Recommendation cards are visible.",
  "Capture a screenshot of the iframe SBAR and compare it to the locked brand snapshot.",
  "Capture a screenshot of the web-component SBAR and compare it to the locked brand snapshot.",
] as const;

const SNAPSHOT = {
  maxDiffPixelRatio: 0.03,
  animations: "disabled" as const,
};

async function openDemo(page: Page) {
  await page.goto(HOST);
  await page.locator("leo-sbar[data-leo-state='loaded']").first().waitFor({
    timeout: 15_000,
  });
}

async function assertIframeHeader(page: Page) {
  const iframe = page.frameLocator("#iframe-widget");
  const header = iframe.getByTestId("leo-header");
  await expect(header).toBeVisible({ timeout: 15_000 });
  await expect(iframe.getByText("LEO by Mizaic")).toBeVisible();
  await expect(header.locator("svg[aria-label='LEO by Mizaic']")).toBeVisible();
  return header;
}

async function assertHeaderFonts(page: Page) {
  const iframe = page.frameLocator("#iframe-widget");
  const styles = await iframe.getByTestId("leo-header").evaluate((el) => {
    const mark = el.querySelector(".leo-mark") as HTMLElement | null;
    const product = el.querySelector(".leo-product") as HTMLElement | null;
    const markStyle = mark ? window.getComputedStyle(mark) : null;
    const productStyle = product ? window.getComputedStyle(product) : null;
    return {
      markColor: markStyle?.color ?? "",
      productFont: productStyle?.fontFamily ?? "",
      productColor: productStyle?.color ?? "",
    };
  });
  expect(styles.productFont.toLowerCase()).toMatch(/overpass|albert sans/);
  expect(styles.productFont.toLowerCase()).not.toContain("comic");
  expect(styles.markColor.toLowerCase()).not.toContain("magenta");
  expect(styles.productColor.toLowerCase()).not.toContain("magenta");
}

async function assertStages(page: Page) {
  const iframe = page.frameLocator("#iframe-widget");
  await expect(iframe.getByTestId("leo-stage-situation")).toBeVisible();
  await expect(iframe.getByTestId("leo-stage-background")).toBeVisible();
  await expect(iframe.getByTestId("leo-stage-assessment")).toBeVisible();
  await expect(iframe.getByTestId("leo-stage-recommendation")).toBeVisible();
}

type AtlasRecord = {
  request: Parameters<typeof recordProtocolStep>[0]["request"];
  runId: string;
  testInfo: Parameters<typeof recordProtocolStep>[0]["testInfo"];
  lastCompletedStep: { value: number };
};

async function recordStepShot(
  page: Page,
  record: AtlasRecord | undefined,
  stepIndex: number,
  notes: string,
  screenshotTarget: Parameters<typeof recordProtocolStep>[0]["screenshotTarget"],
) {
  if (!record) return;
  await recordProtocolStep({
    request: record.request,
    runId: record.runId,
    valId: VAL_ID,
    page,
    testInfo: record.testInfo,
    protocol: PROTOCOL,
    stepIndex,
    screenshotTarget,
    notes,
  });
  record.lastCompletedStep.value = stepIndex;
}

async function runBrandChecks(page: Page, record?: AtlasRecord) {
  const iframeFrame = page.locator("#iframe-frame");
  const wcFrame = page.locator("#web-component-frame");

  await openDemo(page);
  await assertIframeHeader(page);
  await recordStepShot(
    page,
    record,
    0,
    "Iframe header shows LEO by Mizaic and the LeoO mark.",
    iframeFrame,
  );

  await assertHeaderFonts(page);
  await recordStepShot(
    page,
    record,
    1,
    "Header font is Overpass or Albert Sans. Host CSS did not win.",
    iframeFrame,
  );

  await assertStages(page);
  await recordStepShot(
    page,
    record,
    2,
    "All four SBAR stage cards are visible.",
    iframeFrame,
  );

  await expect(iframeFrame).toHaveScreenshot("sbar-iframe-brand.png", SNAPSHOT);
  await recordStepShot(
    page,
    record,
    3,
    "Iframe SBAR snapshot matches the locked Mizaic brand.",
    iframeFrame,
  );

  await expect(wcFrame).toHaveScreenshot("sbar-web-component-brand.png", SNAPSHOT);
  await recordStepShot(
    page,
    record,
    4,
    "Web-component SBAR snapshot matches the locked Mizaic brand.",
    wcFrame,
  );
}

test.describe("VAL-5D90A6F3 SBAR Mizaic brand @val", () => {
  test.setTimeout(300_000);

  test(
    "SBAR widget shows official Mizaic brand",
    {
      tag: ["@UN-DA0B165F", "@VAL-5D90A6F3"],
      annotation: [
        {
          type: "Atlas VAL",
          description: "VAL-5D90A6F3 - SBAR widget shows official Mizaic brand",
        },
      ],
    },
    async ({ page, request }, testInfo) => {
      const recordAtlas = isAtlasValidationConfigured();
      if (recordAtlas) {
        assertValidationRunConfig();
      } else {
        testInfo.annotations.push({
          type: "Atlas VAL",
          description: atlasValidationSkipReason() ?? "Atlas env missing",
        });
      }

      if (!recordAtlas) {
        await runBrandChecks(page);
        return;
      }

      await runValTest(page, request, testInfo, {
        valId: VAL_ID,
        targetUrl: TARGET_URL,
        metadata: {
          atlas_un_id: UN_ID,
          automated_steps: ["0", "1", "2", "3", "4"],
        },
        protocol: PROTOCOL,
        body: async (ctx) => {
          await runBrandChecks(ctx.page, {
            request: ctx.request,
            runId: ctx.runId,
            testInfo: ctx.testInfo,
            lastCompletedStep: ctx.lastCompletedStep,
          });
          await finishValPass(
            ctx.request,
            ctx.runId,
            "SBAR widget header, fonts, stages, and brand snapshots passed for UN-DA0B165F.",
          );
        },
      });
    },
  );
});
