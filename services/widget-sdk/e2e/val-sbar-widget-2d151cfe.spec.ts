/**
 * VAL-2D151CFE -- SBAR widget surfaces CDS output for safe clinician review.
 *
 * Records automated Atlas evidence for embed/render and WCAG checks on the
 * widget demo host page. Manual clinician and host-integration steps remain
 * outside this spec.
 */

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  finishValPass,
  runValTest,
} from "./helpers/validation-spec-runner";
import {
  atlasValidationSkipReason,
  isAtlasValidationConfigured,
  loadPlaywrightEnv,
} from "./helpers/validation-env";

loadPlaywrightEnv();

const HOST = "/demo/host-pages/dual-variant.html";
const VAL_ID = "VAL-2D151CFE";
const UN_ID = "UN-AE38FB27";
const TARGET_URL = process.env.PW_BASE_URL ?? "http://localhost:5173";

const PROTOCOL = [
  "Step 1: Embed <leo-sbar assessment-id='...'> in the host test page. Confirm the S, B, A, and R sections render with advisory disclaimer visible.",
  "Step 2: For a scenario with missing and unclear fields, confirm the completeness panel renders those findings.",
  "Step 3: Confirm the widget emits leo:completeness-incomplete before any DOM mutation when fields are missing.",
  "Step 4: For a scenario with no completeness findings, confirm no completeness event is fired.",
  "Step 5: For a scenario with matched guideline rules, confirm each rule renders its recommendation text.",
  "Step 6: Ask a clinician to read the recommendation verbatim text. Record whether they understood it without jargon.",
  "Step 7: Ask a host developer to wire the leo:completeness-incomplete event to a host confirmation step.",
  "Step 8: Run axe-core against the rendered widget page. Confirm zero critical or serious WCAG 2.1 AA violations.",
  "Step 9: Record pass or fail for each acceptance criterion and capture evidence via record_validation_run.",
] as const;

test.describe("VAL-2D151CFE SBAR widget @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records widget render and accessibility evidence",
    {
      tag: ["@UN-AE38FB27", "@VAL-2D151CFE"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-2D151CFE - SBAR widget surfaces CDS output for safe clinician review",
        },
      ],
    },
    async ({ page, request }, testInfo) => {
      await runValTest(page, request, testInfo, {
        valId: VAL_ID,
        targetUrl: TARGET_URL,
        metadata: {
          atlas_un_id: UN_ID,
          automated_steps: ["0", "7"],
        },
        protocol: PROTOCOL,
        body: async (ctx) => {
          await ctx.page.goto(HOST);
          const widget = ctx.page.locator("leo-sbar[data-leo-state='loaded']").first();
          await widget.waitFor({ timeout: 15_000 });

          const loadedDetail = await ctx.page.evaluate(async () => {
            const wc = document.getElementById("wc-widget");
            if (!wc) {
              return null;
            }
            return new Promise<{ assessmentId?: string; width: number; height: number }>(
              (resolve) => {
                const finish = () => {
                  const rect = wc.getBoundingClientRect();
                  resolve({
                    assessmentId: wc.getAttribute("assessment-id") ?? undefined,
                    width: rect.width,
                    height: rect.height,
                  });
                };
                const timer = window.setTimeout(finish, 2_000);
                wc.addEventListener(
                  "leo:loaded",
                  (event) => {
                    window.clearTimeout(timer);
                    resolve({
                      assessmentId: (event as CustomEvent<{ assessmentId?: string }>).detail
                        ?.assessmentId,
                      width: wc.getBoundingClientRect().width,
                      height: wc.getBoundingClientRect().height,
                    });
                  },
                  { once: true },
                );
              },
            );
          });
          expect(loadedDetail?.assessmentId).toBe("ass-2WW-001");
          expect(loadedDetail?.width ?? 0).toBeGreaterThan(0);
          expect(loadedDetail?.height ?? 0).toBeGreaterThan(0);

          const iframe = ctx.page.frameLocator("#iframe-widget");
          await expect(iframe.getByTestId("leo-stage-situation")).toBeVisible({
            timeout: 15_000,
          });
          await expect(iframe.getByTestId("leo-stage-background")).toBeVisible();
          await expect(iframe.getByTestId("leo-stage-assessment")).toBeVisible();
          await expect(iframe.getByTestId("leo-stage-recommendation")).toBeVisible();
          await expect(iframe.getByTestId("leo-ai-disclaimer")).toBeVisible();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 0,
            screenshotTarget: ctx.page.locator("#web-component-frame"),
            notes:
              "Web component variant rendered SBAR sections on hostile host page.",
          });
          ctx.lastCompletedStep.value = 0;

          const results = await new AxeBuilder({ page: ctx.page })
            .include("leo-sbar")
            .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
            .analyze();
          const blockers = results.violations.filter(
            (v) => v.impact === "critical" || v.impact === "serious",
          );
          expect(blockers).toEqual([]);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 7,
            screenshotTarget: ctx.page.locator("#web-component-frame"),
            notes: "axe-core reported zero critical or serious WCAG violations.",
          });
          ctx.lastCompletedStep.value = 7;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "Automated widget render and axe evidence recorded. Steps 2-7 and 9 remain manual or host-integration witness work.",
          );
        },
      });
    },
  );
});
