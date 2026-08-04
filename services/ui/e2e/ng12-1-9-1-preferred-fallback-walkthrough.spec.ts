/**
 * End-to-end walkthrough: NG12 1.9.1 preferred-then-fallback actions.
 *
 * NICE: urgent direct-access MRI of the brain (or CT if MRI is
 * contraindicated) for progressive sub-acute loss of central
 * neurological function in adults.
 *
 * Evidence at each Suggest click/type. Numbered screenshots under
 * e2e/screenshots/ng12-1-9-1/.
 *
 * Atlas trace: UN-49C83395 / DI-42246DA7 / DO-F8C56339 / VAL-8672AC7E
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-9-1-preferred-fallback-walkthrough --project=chromium
 */
import { test, expect, type Page } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import path from "path";
import {
  btnByLabel,
  fillSaveReason,
  openEditDialog,
  pickSuggestAction,
  typeSuggestProcedure,
} from "./helpers/ng12-walkthrough-actions";
import { createWalkthroughEvidence } from "./helpers/walkthrough-evidence";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-9-1");

const REC_TEXT =
  "1.9.1 Consider an urgent, direct access, MRI scan of the brain " +
  "(or CT scan if MRI is contraindicated) to assess for brain or " +
  "central nervous system cancer in adults with progressive, " +
  "sub-acute loss of central neurological function. [2015]";

const SEARCH_HITS: Record<
  string,
  Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>
> = {
  "mri brain": [
    {
      snomed_concept_id: "816077007",
      term: "MRI of brain",
      semantic_tag: "procedure",
    },
  ],
  mri: [
    {
      snomed_concept_id: "816077007",
      term: "MRI of brain",
      semantic_tag: "procedure",
    },
  ],
  "ct head": [
    {
      snomed_concept_id: "303653007",
      term: "CT of head",
      semantic_tag: "procedure",
    },
  ],
  "ct of head": [
    {
      snomed_concept_id: "303653007",
      term: "CT of head",
      semantic_tag: "procedure",
    },
  ],
};

const RULE = {
  rule_id: "e2e-ng12-1-9-1-walkthrough",
  name: "NG12 1.9.1 -- MRI brain or CT if contraindicated",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: REC_TEXT,
  recommendation_structure: null,
  plain_english:
    "Urgent MRI brain for CNS cancer assessment; CT if MRI contraindicated.",
  present_criteria: [],
  absent_criteria: [],
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
        node_id: "neuro",
        kind: "CONCEPT",
        criterion: {
          snomed_concept_id: "230690007",
          preferred_term: "Cerebrovascular accident",
          semantic_tag: "disorder",
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

type DecisionAction = {
  strength?: string;
  group_id?: string;
  group_mode?: string;
  group_rank?: number;
  criterion?: { snomed_concept_id?: string };
};

type DecisionBody = {
  action?: string;
  updates?: { actions?: DecisionAction[] };
};

async function installFixtures(
  page: Page,
  captured: { decision: DecisionBody | null },
) {
  await page.route("**/api/guidance/rules/review*status=pending_review*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([RULE]),
    }),
  );
  for (const status of ["active", "superseded", "rejected"]) {
    await page.route(`**/api/guidance/rules/review*status=${status}*`, (route) =>
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
      Object.entries(SEARCH_HITS).find(([k]) => q.includes(k) || k.includes(q))?.[1] ??
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

test.describe("NG12 1.9.1 preferred-fallback walkthrough (DI-42246DA7)", () => {
  test("builds MRI then CT if MRI contraindicated", async ({ page }) => {
    test.setTimeout(240_000);
    const ev = createWalkthroughEvidence(page, SCREENSHOT_DIR);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page, RULE, ev);
    await ev.shot("who-seeded");

    await dialog
      .getByRole("button", {
        name: /step 2 of 3: what should the system suggest/i,
      })
      .click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await ev.shot("suggest-uncoded");

    await pickSuggestAction(
      page,
      dialog,
      "mri brain",
      /Use MRI of brain/i,
      ev,
      "suggest-mri",
    );
    await expect(
      dialog.getByRole("button", { name: /mri of brain/i }),
    ).toBeVisible({ timeout: 10000 });
    await ev.shot("mri-coded-confirmed");

    await dialog
      .getByRole("button", {
        name: /If not available, add another procedure after row 1/i,
      })
      .click();
    await expect(
      dialog.getByText(/Prefer the first\. If it is not available/i),
    ).toBeVisible({ timeout: 10000 });
    await ev.shot("fallback-row-added");

    await typeSuggestProcedure(
      page,
      dialog,
      "ct head",
      /Use CT of head/i,
      ev,
      "suggest-ct",
    );
    await expect(
      dialog.getByRole("button", { name: /ct of head/i }),
    ).toBeVisible({ timeout: 10000 });
    await ev.shot("both-coded");

    for (const id of [
      "#edit-rule-action-strength-0",
      "#edit-rule-action-strength-1",
    ]) {
      const strength = dialog.locator(id);
      await strength.scrollIntoViewIfNeeded();
      await strength.click();
      await page
        .getByRole("option", { name: /Think about this test or referral/i })
        .click();
    }
    await ev.shot("strengths-set");

    await expect(
      dialog.getByText(/If that is not available:/i),
    ).toBeVisible({ timeout: 10000 });
    await expect(dialog.getByText(/MRI of brain/i).first()).toBeVisible();
    await expect(dialog.getByText(/CT of head/i).first()).toBeVisible();
    await ev.shot("live-preview-fallback");

    await btnByLabel(dialog, /^Next/i).click();
    await fillSaveReason(
      dialog,
      "Walkthrough: NG12 1.9.1 MRI preferred, CT if MRI contraindicated.",
      ev,
    );

    await btnByLabel(dialog, /approve and save/i).click();
    await expect(dialog).toBeHidden({ timeout: 15000 });
    await ev.shot("saved-dialog-closed");

    expect(captured.decision?.action).toBe("edit");
    const actions = captured.decision?.updates?.actions ?? [];
    expect(actions).toHaveLength(2);
    expect(actions[0].criterion?.snomed_concept_id).toBe("816077007");
    expect(actions[1].criterion?.snomed_concept_id).toBe("303653007");
    expect(actions[0].group_mode).toBe("preferred_fallback");
    expect(actions[1].group_mode).toBe("preferred_fallback");
    expect(actions[0].group_id).toBe(actions[1].group_id);
    expect(actions.map((a) => a.group_rank)).toEqual([0, 1]);
  });
});
