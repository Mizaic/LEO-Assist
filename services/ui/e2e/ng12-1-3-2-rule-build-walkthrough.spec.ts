/**
 * End-to-end walkthrough: build NG12 recommendation 1.3.2 (refer on
 * FIT result of at least 10 ug Hb/g) in the guided EditRuleDialog.
 *
 * Exercises OBSERVATION (lab value) criteria -- operator "is at least",
 * threshold 10 -- plus adult age and a colorectal 2WW referral action.
 * Every user click and typed value is captured as a numbered screenshot
 * under e2e/screenshots/ng12-1-3-2/.
 *
 * Atlas trace: UN-49C83395 / DI-42246DA7 / DO-F8C56339 / VAL-8AB4C593
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-3-2-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "path";
import {
  btnByLabel,
  confirmSituation,
  fillSaveReason,
  openEditDialog,
  pickSuggestAction,
} from "./helpers/ng12-walkthrough-actions";
import {
  createWalkthroughEvidence,
  type Evidence,
} from "./helpers/walkthrough-evidence";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-3-2");

/** NICE wording uses a non-breaking space before "micrograms". */
const REC_TEXT =
  "1.3.2 Refer adults using a suspected cancer pathway referral for " +
  "colorectal cancer if they have a FIT result of at least 10\u00a0micrograms " +
  "of haemoglobin per gram of faeces. [2023]";

const FIT_OBS_ID = "1049361000000101";
const FIT_OBS_TERM = "Quantitative faecal immunochemical test";
const REFERRAL_ID = "276401000000108";

const SEARCH_HITS: Record<
  string,
  Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>
> = {
  fit: [
    {
      snomed_concept_id: FIT_OBS_ID,
      term: FIT_OBS_TERM,
      semantic_tag: "observable entity",
    },
  ],
  "faecal immunochemical": [
    {
      snomed_concept_id: FIT_OBS_ID,
      term: FIT_OBS_TERM,
      semantic_tag: "observable entity",
    },
  ],
  referral: [
    {
      snomed_concept_id: REFERRAL_ID,
      term: "Fast track referral for suspected colorectal cancer",
      semantic_tag: "procedure",
    },
  ],
  colorectal: [
    {
      snomed_concept_id: REFERRAL_ID,
      term: "Fast track referral for suspected colorectal cancer",
      semantic_tag: "procedure",
    },
  ],
};

const RULE = {
  rule_id: "e2e-ng12-1-3-2-walkthrough",
  name: "NG12 1.3.2 -- FIT at least 10 then refer (walkthrough)",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: REC_TEXT,
  recommendation_structure: null,
  plain_english:
    "Adults with FIT at least 10 ug Hb/g: refer on suspected colorectal pathway.",
  present_criteria: [],
  absent_criteria: [],
  // Seed age + FIT observation at value 0 so Who opens the lab editor
  // and the walkthrough can set the threshold to 10.
  logic_tree: {
    node_id: "root",
    kind: "AND",
    children: [
      {
        node_id: "age",
        kind: "DEMOGRAPHIC",
        field: "age",
        operator: ">=",
        value: "18",
        unit: "years",
      },
      {
        node_id: "fit-obs",
        kind: "OBSERVATION",
        source_row_text:
          "FIT result of at least 10 micrograms of haemoglobin per gram of faeces",
        observation: {
          kind: "OBSERVATION",
          observable_id: FIT_OBS_ID,
          observable_term: `${FIT_OBS_TERM} (observable entity)`,
          operator: ">=",
          value: 0,
          unit: "",
          within_days: 365,
        },
      },
    ],
  },
  action: {
    snomed_concept_id: "",
    preferred_term: "",
    semantic_tag: "procedure",
  },
  has_predecessor: false,
  updated_at: "2026-07-01T09:00:00Z",
};

type DecisionBody = {
  action?: string;
  updates?: {
    priority?: string;
    due_days?: number | null;
    actions?: Array<{
      strength?: string;
      criterion?: { snomed_concept_id?: string };
    }>;
    logic_tree?: Record<string, unknown>;
  };
};

type TreeNode = {
  kind?: string;
  observation?: {
    observable_id?: string;
    operator?: string;
    value?: number | number[];
    unit?: string;
  };
  children?: TreeNode[];
};

function findObservation(node: TreeNode | undefined): TreeNode["observation"] {
  if (!node) return undefined;
  if (node.kind === "OBSERVATION") return node.observation;
  for (const child of node.children ?? []) {
    const found = findObservation(child);
    if (found) return found;
  }
  return undefined;
}

async function installFixtures(
  page: Page,
  captured: { decision: DecisionBody | null },
) {
  await page.route(
    "**/api/guidance/rules/review*status=pending_review*",
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([RULE]),
      }),
  );
  for (const status of ["active", "superseded", "rejected"]) {
    await page.route(
      `**/api/guidance/rules/review*status=${status}*`,
      (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        }),
    );
  }
  await page.route("**/api/guidance/rules/review/*/decision", async (route) => {
    const raw = route.request().postData();
    captured.decision = raw ? (JSON.parse(raw) as DecisionBody) : null;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ rule_id: `${RULE.rule_id}:edited` }),
    });
  });
  await page.route("**/api/terminology/prior-resolutions*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await page.route("**/api/terminology/descendants*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await page.route("**/api/terminology/search*", (route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const hits =
      SEARCH_HITS[q] ??
      Object.entries(SEARCH_HITS).find(
        ([k]) => q.includes(k) || k.includes(q),
      )?.[1] ??
      [];
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(hits),
    });
  });
  await page.route("**/api/nice/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
}

async function runAxeDialog(page: Page) {
  const results = await new AxeBuilder({ page })
    .include('[role="dialog"]')
    .withTags([...WCAG_TAGS])
    .analyze();
  const blockers = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(
    blockers,
    JSON.stringify(
      blockers.map((v) => ({ id: v.id, impact: v.impact, help: v.help })),
      null,
      2,
    ),
  ).toEqual([]);
}

async function setFitThresholdToTen(dialog: Locator, ev: Evidence) {
  const obsRow = dialog.getByTestId("prerequisite-row-fit-obs");
  await expect(obsRow).toBeVisible({ timeout: 10000 });
  const editOrDone = obsRow.getByText(/^(Edit|Done|Tap to place it manually)$/);
  if ((await obsRow.getByText("Done").count()) === 0) {
    await ev.shot("who-fit-edit-before");
    await editOrDone.first().click();
  }
  await expect(
    dialog.getByLabel(/how to compare the lab value/i),
  ).toBeVisible({ timeout: 10000 });
  await expect(dialog.getByLabel(/how to compare the lab value/i)).toHaveText(
    /is at least/i,
  );
  await ev.shot("who-fit-editor-open");

  const valueField = dialog.getByLabel(/^value$/i);
  await valueField.fill("10");
  await expect(valueField).toHaveValue("10");
  await ev.shot("who-fit-value-10");

  const unitField = dialog.getByLabel(/^unit$/i);
  await unitField.fill("ug/g");
  await expect(unitField).toHaveValue("ug/g");
  await ev.shot("who-fit-unit-ug-g");

  await obsRow.getByText("Done").click();
  await ev.shot("who-fit-threshold-10");
}

test.describe("NG12 1.3.2 rule-build walkthrough (DI-42246DA7)", () => {
  test("builds 1.3.2 with FIT observation threshold and colorectal referral", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const ev = createWalkthroughEvidence(page, SCREENSHOT_DIR);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page, RULE, ev);

    // -- Who: age + edit FIT lab value --------------------------------
    await expect(dialog.getByText("Always true")).toBeVisible();
    await expect(dialog.getByTestId("prerequisite-row-age")).toBeVisible();
    await expect(dialog.getByTestId("prerequisite-row-fit-obs")).toBeVisible();
    await runAxeDialog(page);
    await ev.shot("who-always-true");

    await setFitThresholdToTen(dialog, ev);
    await runAxeDialog(page);

    await btnByLabel(dialog, /No, nothing else/i).click();
    await ev.shot("who-after-nothing-else");

    // -- Situations: single-sentence rec does not split ---------------
    await expect(
      dialog.getByText(/couldn't find more than one situation/i),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await ev.shot("situations-no-split");
    await btnByLabel(
      dialog,
      /Doesn't split -- one set of rules for everyone/i,
    ).click();

    // -- One situation: confirm FIT wording is covered ----------------
    await expect(dialog.getByText(/situation a/i).first()).toBeVisible({
      timeout: 15000,
    });
    await ev.shot("situation-a-open");
    const confirmA = btnByLabel(dialog, /^confirm situation a$/i);
    if (await confirmA.isVisible().catch(() => false)) {
      await confirmSituation(dialog, "a", ev);
    } else {
      await ev.shot("situation-a-ready-to-confirm");
      await btnByLabel(dialog, /confirm situation/i).first().click();
    }

    // -- Wizard Review ------------------------------------------------
    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    const preview = dialog.locator('[data-tour="er-06-preview"]');
    await expect(preview).toBeVisible();
    await expect(
      preview.getByText(/faecal immunochemical|FIT|10/i).first(),
    ).toBeVisible();
    await runAxeDialog(page);
    await ev.shot("wizard-review-live-preview");

    // -- Suggest: colorectal 2WW referral -----------------------------
    await btnByLabel(dialog, /^Next/i).click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 15000 });
    await ev.shot("suggest-uncoded-action");

    await pickSuggestAction(
      page,
      dialog,
      "colorectal",
      /Use Fast track referral for suspected colorectal cancer/i,
      ev,
      "suggest",
    );
    await expect(
      dialog.getByRole("button", {
        name: /fast track referral for suspected colorectal cancer/i,
      }),
    ).toBeVisible({ timeout: 10000 });

    const prioritySelect = dialog.locator("#edit-rule-priority");
    await prioritySelect.scrollIntoViewIfNeeded();
    await prioritySelect.click();
    await ev.shot("suggest-priority-menu");
    await page
      .getByRole("option", { name: /^Urgent\b|2.?week/i })
      .first()
      .click();
    await ev.shot("suggest-priority-set");

    const strengthSelect = dialog.locator("#edit-rule-action-strength-0");
    await strengthSelect.scrollIntoViewIfNeeded();
    await strengthSelect.click();
    await ev.shot("suggest-strength-menu");
    await page
      .getByRole("option", { name: /Offer this test or referral/i })
      .click();
    await ev.shot("suggest-referral-coded");

    await btnByLabel(dialog, /^Next/i).click();

    // -- Save ---------------------------------------------------------
    await fillSaveReason(
      dialog,
      "Walkthrough: NG12 1.3.2 FIT observation >= 10 ug/g and colorectal referral.",
      ev,
    );
    await btnByLabel(dialog, /approve and save/i).click();
    await expect(dialog).toBeHidden({ timeout: 15000 });

    expect(captured.decision?.action).toBe("edit");
    const obs = findObservation(
      captured.decision?.updates?.logic_tree as TreeNode | undefined,
    );
    expect(obs?.observable_id).toBe(FIT_OBS_ID);
    expect(obs?.operator).toBe(">=");
    expect(obs?.value).toBe(10);
    expect(obs?.unit).toBe("ug/g");

    const actions = captured.decision?.updates?.actions ?? [];
    expect(actions[0]?.criterion?.snomed_concept_id).toBe(REFERRAL_ID);
    expect(actions[0]?.strength).toBe("offer");

    await ev.shot("review-pool-after-save");
    expect(ev.count()).toBeGreaterThan(15);
  });
});
