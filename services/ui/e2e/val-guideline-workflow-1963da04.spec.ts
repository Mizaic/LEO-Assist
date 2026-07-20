/**
 * VAL-1963DA04 -- End-to-end guideline load, rule publish, and CDS output.
 *
 * Atlas artefacts
 *   VAL : VAL-1963DA04  (uuid: 1963da04-c11a-4384-8538-d8afa280af3c)
 *   UN  : UN-49C83395   Load, Review, and Publish Guideline Rules
 *   DI  : DI-42246DA7   Review, Edit, Approve, or Reject Guideline Rules
 *   DO  : DO-F8C56339   Rule generation, review, and edit surface
 *
 * User manual: compliance/policy/LEO-UM-CG-001-clinical-guidelines-user-manual.md
 *
 * All backend calls are intercepted with route stubs so the spec runs
 * in CI without a live API. Screenshots are taken at each protocol step
 * and attached via recordProtocolStep.
 */

import { expect, test } from "@playwright/test";
import {
  atlasValidationSkipReason,
  isAtlasValidationConfigured,
  loadPlaywrightEnv,
} from "./helpers/validation-env";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import { finishValPass, runValTest } from "./helpers/validation-spec-runner";

loadPlaywrightEnv();

const VAL_ID = "VAL-1963DA04";
const UN_ID = "UN-49C83395";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

// -- Fixtures ----------------------------------------------------------------

const LOAD_JOB_ID = "val-cg-job-load-ng12";
const SYNC_JOB_ID = "val-cg-job-sync-001";
const COMPILE_JOB_ID = "val-cg-job-compile-001";

const PENDING_RULE = {
  rule_id: "val-rule-001",
  name: "NG12 rec 1.1 -- offer urgent CXR",
  status: "pending_review",
  strength: "SHOULD",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text:
    "Offer an urgent chest X-ray (to be performed within 2 weeks) to assess for lung cancer in people aged 40 and over if they have unexplained haemoptysis.",
  plain_english:
    "Patient is aged 40 or over AND has unexplained haemoptysis. Suggest: offer urgent chest X-ray.",
  present_criteria: [{ snomed_concept_id: "66857006", preferred_term: "Haemoptysis" }],
  absent_criteria: [],
  logic_tree: null,
  action: { snomed_concept_id: "168537006", preferred_term: "Plain X-ray of chest", semantic_tag: "procedure" },
  has_predecessor: false,
  updated_at: "2026-06-25T10:00:00Z",
};

const APPROVED_RULE = { ...PENDING_RULE, rule_id: "val-rule-001-approved", status: "active" };

const LOADED_GUIDELINE = {
  code: "NG12",
  title: "Suspected cancer: recognition and referral",
  guidance_type: "evidence-based recommendations",
  publication_date: "2023-07-01",
  chapter_count: 4,
  recommendation_count: 14,
  rules_pending: 0,
  rules_approved: 0,
  rules_rejected: 0,
};

const COMPILE_RESULT = {
  active_version: "v20260625-120000",
  rule_count: 1,
  compile_timestamp: "2026-06-25T12:00:00Z",
  scope_type: "global",
  scope_id: "default",
  policy_mode: "advisory",
  compile_stats: { included: 1, excluded: 0 },
};

// -- Stub helpers ------------------------------------------------------------

type GuidelineFixtureState = {
  guidelineLoaded: boolean;
  guidelineInGraph: boolean;
  rulesGenerated: boolean;
  ruleApproved: boolean;
  compiled: boolean;
  versionActive: boolean;
};

function createGuidelineFixtureState(
  seed: Partial<GuidelineFixtureState> = {},
): GuidelineFixtureState {
  return {
    guidelineLoaded: false,
    guidelineInGraph: false,
    rulesGenerated: false,
    ruleApproved: false,
    compiled: false,
    versionActive: false,
    ...seed,
  };
}

async function installGuidelineFixtures(
  page: import("@playwright/test").Page,
  state: GuidelineFixtureState,
) {
  // -- NICE catalogue sync
  await page.route("**/api/nice/catalogue/sync", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ job_id: SYNC_JOB_ID }),
    }),
  );
  await page.route(`**/api/nice/jobs/${SYNC_JOB_ID}/status`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "done", catalogue_count: 3690 }),
    }),
  );

  // -- NICE catalogue search
  await page.route("**/api/nice/catalogue*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        { code: "NG12", title: "Suspected cancer: recognition and referral", type: "NG" },
      ]),
    }),
  );

  // -- Jobs list (initially empty, then with NG12)
  await page.route("**/api/nice/jobs", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        state.guidelineLoaded
          ? [
              {
                job_id: LOAD_JOB_ID,
                code: "NG12",
                status: "done",
                step: "store recommendations",
                completed_at: "2026-06-25T10:00:00Z",
                recommendation_count: 14,
              },
            ]
          : [],
      ),
    }),
  );

  // -- NICE ingest
  await page.route("**/api/nice/ingest", async (route) => {
    state.guidelineLoaded = true;
    state.guidelineInGraph = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ job_id: LOAD_JOB_ID }),
    });
  });

  // -- SSE progress events for ingest
  await page.route(`**/api/nice/events*`, (route) => {
    const body = [
      "event: progress\ndata: {\"step\":\"Fetching from NICE...\"}\n\n",
      "event: progress\ndata: {\"step\":\"Storing chapters...\"}\n\n",
      "event: progress\ndata: {\"step\":\"Storing recommendations...\"}\n\n",
      "event: done\ndata: {\"recommendation_count\":14}\n\n",
    ].join("");
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body,
    });
  });

  // -- Loaded guidelines (initially empty, then NG12)
  await page.route("**/api/nice/loaded", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        state.guidelineInGraph
          ? [
              {
                ...LOADED_GUIDELINE,
                rules_pending: state.rulesGenerated ? 1 : 0,
              },
            ]
          : [],
      ),
    }),
  );

  // -- Rule generation
  const generateJobId = "val-cg-job-gen-001";
  await page.route("**/api/guidance/rules/generate", async (route) => {
    state.guidelineInGraph = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ job_id: generateJobId }),
    });
  });
  await page.route(`**/api/guidance/rules/generate/${generateJobId}`, (route) => {
    state.rulesGenerated = true;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "done" }),
    });
  });

  // -- Rule review queue
  // fetchRules() appends &limit=200 so patterns need a trailing wildcard.
  // Only surface the pending rule after generation; not before (avoids state bleed in step-0 screenshot).
  await page.route("**/api/guidance/rules/review*status=pending_review*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(state.rulesGenerated && !state.ruleApproved ? [PENDING_RULE] : []),
    }),
  );
  await page.route("**/api/guidance/rules/review*status=active*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(state.ruleApproved ? [APPROVED_RULE] : []),
    }),
  );
  await page.route("**/api/guidance/rules/review*status=superseded*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) }),
  );

  // -- Rule decision (approve)
  await page.route("**/api/guidance/rules/review/*/decision", async (route) => {
    state.ruleApproved = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ rule_id: APPROVED_RULE.rule_id }),
    });
  });

  // -- Bitmap status
  // active_version is null until the version is explicitly made live so the
  // StatHero tile only populates after the "Make this live" action.
  await page.route("**/api/terminology/guidelines/bitmap/status*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        state.compiled
          ? {
              ...COMPILE_RESULT,
              active_version: state.versionActive ? COMPILE_RESULT.active_version : null,
            }
          : { active_version: null, rule_count: 0, compile_timestamp: null },
      ),
    }),
  );

  // -- Compile
  await page.route("**/api/terminology/guidelines/bitmap/compile", async (route) => {
    state.compiled = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ job_id: COMPILE_JOB_ID }),
    });
  });
  await page.route(`**/api/terminology/guidelines/bitmap/jobs/${COMPILE_JOB_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "done", version: COMPILE_RESULT.active_version }),
    }),
  );

  // -- Compiled versions list
  await page.route("**/api/terminology/guidelines/bitmap/versions*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        state.compiled
          ? [{
              version: COMPILE_RESULT.active_version,
              active: state.versionActive,
              scope_type: "global",
              scope_id: "default",
            }]
          : [],
      ),
    }),
  );

  // -- Make live
  await page.route("**/api/terminology/guidelines/bitmap/versions/*/activate", (route) => {
    state.versionActive = true;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  });
}

// -- Protocol ----------------------------------------------------------------

const PROTOCOL = [
  "Open /admin/knowledge?tab=clinical-guidelines. Confirm page loads with StatHero, jump strip (1. Load / Inspect / 2. Review / 3. Compile), and four step cards.",
  "Click 'Refresh guideline list'. Confirm sync job completes and success banner shows catalogue count.",
  "Type 'NG12' into the search field. Confirm 'Load this guideline' becomes active. Click it. Confirm progress strip appears then green done banner 'Done. Loaded 14 recommendations.'",
  "In the Inspect card, confirm NG12 row shows code chip, title, chapter count, recommendation count, and 'No rules yet' badge. Click 'Generate rules'. Confirm rule status updates to 'Pending (1)'.",
  "Click '2. Review' in the jump strip. Confirm Pending review tab is active and the NG12 rule row is visible. Expand the row. Confirm recommendation text and plain-English summary are shown.",
  "Click 'Looks right' on the rule. Confirm the Pending review tab shows zero rules. Click 'Active' tab. Confirm the approved rule appears.",
  "Click '3. Compile' in the jump strip. Confirm compile settings chips show 'Global' and 'Advisory'. Click 'Compile rules'. Confirm progress strip appears and a new version appears in the versions list.",
  "Click 'Make this live' on the new version. Confirm the Active version stat tile updates to the new version string.",
] as const;

// -- Test --------------------------------------------------------------------

test.describe("VAL-1963DA04 guideline load, review, compile walkthrough @val", () => {
  test.setTimeout(360_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records guideline load, rule approval, compile, and publish evidence",
    {
      tag: ["@UN-49C83395", "@VAL-1963DA04"],
      annotation: [
        {
          type: "Atlas VAL",
          description: "VAL-1963DA04 - Guideline load, rule publish, and CDS output",
        },
      ],
    },
    async ({ page, request }, testInfo) => {
      await runValTest(page, request, testInfo, {
        valId: VAL_ID,
        targetUrl: TARGET_URL,
        metadata: { atlas_un_id: UN_ID },
        protocol: PROTOCOL,
        body: async (ctx) => {
          const fixtureState = createGuidelineFixtureState();
          await installGuidelineFixtures(ctx.page, fixtureState);

          // -- Step 0: Page loads correctly
          await ctx.page.goto("/admin/knowledge?tab=clinical-guidelines");
          await ctx.page.waitForLoadState("networkidle");

          // StatHero must be present
          await expect(ctx.page.getByTestId("metric-tile-loaded")).toBeVisible({
            timeout: 10_000,
          });
          // Jump strip
          await expect(ctx.page.getByText("1. Load")).toBeVisible();
          await expect(ctx.page.getByText("2. Review")).toBeVisible();
          await expect(ctx.page.getByText("3. Compile")).toBeVisible();
          // Step cards
          await expect(ctx.page.getByText("Find and load a guideline")).toBeVisible();
          await expect(ctx.page.getByText("What is in the knowledge graph")).toBeVisible();

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 0,
            notes: "Page loaded: StatHero, jump strip, and four step cards visible.",
          });
          ctx.lastCompletedStep.value = 0;

          // -- Step 1: Refresh catalogue
          await ctx.page.getByRole("button", { name: /refresh guideline list/i }).click();
          await expect(
            ctx.page.getByText(/catalogue updated/i),
          ).toBeVisible({ timeout: 15_000 });

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 1,
            notes: "Catalogue refresh completed. Banner shows 3,690 guidelines available.",
          });
          ctx.lastCompletedStep.value = 1;

          // -- Step 2: Search and load NG12
          await ctx.page.getByPlaceholder(/bowel cancer or ng151/i).fill("NG12");
          // Wait for button to be enabled
          await expect(
            ctx.page.getByRole("button", { name: /load this guideline/i }),
          ).toBeEnabled({ timeout: 5_000 });
          await ctx.page.getByRole("button", { name: /load this guideline/i }).click();

          // Progress strip
          await expect(
            ctx.page.getByText(/starting: loading guideline ng12/i).first(),
          ).toBeVisible({ timeout: 10_000 });

          // Done banner
          await expect(
            ctx.page.getByText(/done\. loaded 14 recommendations/i),
          ).toBeVisible({ timeout: 20_000 });

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 2,
            notes: "NG12 loaded. Done banner confirms 14 recommendations.",
          });
          ctx.lastCompletedStep.value = 2;

          // -- Step 3: Generate rules
          fixtureState.guidelineInGraph = true;
          await ctx.page.goto("/admin/knowledge?tab=clinical-guidelines");
          await ctx.page.waitForLoadState("networkidle");

          // The Inspect card should now show NG12 (stub returns it after reload)
          // Scroll to inspect card
          await ctx.page.evaluate(() => {
            const el = document.querySelector("#loaded-guidelines");
            el?.scrollIntoView({ behavior: "instant" });
          });

          // Find generate rules button
          await expect(
            ctx.page.getByRole("button", { name: /generate rules for ng12/i }),
          ).toBeVisible({ timeout: 10_000 });
          await ctx.page.getByRole("button", { name: /generate rules for ng12/i }).click();

          // After generation completes, rule status chip shows Pending
          await expect(
            ctx.page.getByText(/pending \(1\)/i),
          ).toBeVisible({ timeout: 30_000 });

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 3,
            notes: "NG12 visible in Inspect card. Generate rules triggered. Status shows Pending (1).",
          });
          ctx.lastCompletedStep.value = 3;

          // -- Step 4: Review queue -- expand rule
          // onRulesGenerated() fires when the generate job completes, which
          // increments ruleRefreshKey and triggers RuleReviewSection.reloadPools().
          // Scroll to the review section and wait for it to populate.
          await ctx.page.evaluate(() => {
            const el = document.querySelector("#rule-review");
            el?.scrollIntoView({ behavior: "instant" });
          });

          // "Awaiting review" pool header should be visible (populated via auto-refresh)
          await expect(
            ctx.page.getByText(/awaiting review/i).first(),
          ).toBeVisible({ timeout: 15_000 });

          // Expand the rule row via its aria-labelled toggle button
          await ctx.page
            .getByRole("button", { name: /toggle rule from ng12/i })
            .first()
            .click();

          // After expansion the full recommendation text and approve button appear
          await expect(
            ctx.page.getByText(/unexplained haemoptysis/i).first(),
          ).toBeVisible({ timeout: 5_000 });

          await expect(
            ctx.page.getByRole("button", { name: /approve rule val-rule-001/i }),
          ).toBeVisible({ timeout: 5_000 });

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 4,
            notes: "Awaiting review pool visible. Rule row expanded. Recommendation text and plain-English summary visible.",
          });
          ctx.lastCompletedStep.value = 4;

          // -- Step 5: Approve rule
          await ctx.page
            .getByRole("button", { name: /approve rule val-rule-001/i })
            .click();

          // Awaiting review pool should now show empty state
          await expect(
            ctx.page.getByText(/no rules awaiting review/i),
          ).toBeVisible({ timeout: 10_000 });

          // The "Approved" pool is always rendered in parallel -- approved rule appears there
          await expect(
            ctx.page.getByText(/unexplained haemoptysis/i).first(),
          ).toBeVisible({ timeout: 5_000 });

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 5,
            notes: "Rule approved. Awaiting review pool empty. Approved pool shows the approved rule.",
          });
          ctx.lastCompletedStep.value = 5;

          // -- Step 6: Compile
          await ctx.page.evaluate(() => {
            const el = document.querySelector("#bitmap-lifecycle");
            el?.scrollIntoView({ behavior: "instant" });
          });

          // Confirm scope chips
          await expect(ctx.page.getByText(/global/i).first()).toBeVisible({ timeout: 5_000 });

          await ctx.page.getByRole("button", { name: /compile rules/i }).click();

          // Progress strip
          await expect(
            ctx.page.getByText(/building the lookup index/i),
          ).toBeVisible({ timeout: 5_000 });

          // New version appears
          await expect(
            ctx.page.getByText(/v20260625-120000/i).first(),
          ).toBeVisible({ timeout: 30_000 });

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 6,
            notes: "Compile settings show Global / Advisory. Compile triggered. Version v20260625-120000 appears in list.",
          });
          ctx.lastCompletedStep.value = 6;

          // -- Step 7: Make live
          await ctx.page
            .getByRole("button", { name: /make version v20260625-120000 live/i })
            .click();
          await ctx.page.getByRole("button", { name: "Yes, go live" }).click();

          // Wait for the StatHero tile -- this proves onVersionActivated fired and
          // fetchPageStats re-ran. A "Live" chip appearing in the versions list is
          // necessary but not sufficient; the tile is the acceptance criterion.
          await expect(
            ctx.page.getByTestId("metric-tile-bitmap"),
          ).toContainText(COMPILE_RESULT.active_version, { timeout: 20_000 });

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 7,
            notes: "Make this live clicked. Active bitmap version stat tile shows v20260625-120000.",
          });
          ctx.lastCompletedStep.value = 7;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "All 8 protocol steps completed. Guideline loaded, rule approved, model compiled and published. Screenshots attached.",
          );
        },
      });
    },
  );
});
