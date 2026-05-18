/**
 * Phase 1 safety + copy fix -- VT-D7B8FBA9 (Atlas).
 *
 * Pins three behaviours that together guarantee the rule editor
 * cannot ship a misleading "Live results" surface or a "Save means
 * live" assumption:
 *
 *   1. Step 3 is named "Test your change safely" and its helper text
 *      says explicitly that production is never touched.
 *   2. The TestPatientsPanel offers a sandbox-only test surface; no
 *      "Test against live" button or live banner appears.
 *   3. The Step 4 Save panel shows the "Saved, but not live yet"
 *      banner pointing the reviewer at Bitmap Lifecycle.
 *
 * If any of these regress, CI fails -- because each one was a
 * standalone clinical-safety risk in the previous design.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";

import EditRuleDialog from "..";
import {
  NOT_LIVE_YET_BANNER,
  SANDBOX_PANEL,
  STEP_HELPERS,
  STEP_TITLES,
} from "../copy";

const SAMPLE_RULE = {
  rule_id: "rule:NG12:abc",
  name: "Mesothelioma urgent X-ray",
  strength: "offer",
  guideline_id: "NG12",
  chapter_title: "Recommendations organised by site of cancer",
  recommendation_text:
    "Offer an urgent chest X-ray (to be done within 2 weeks) for mesothelioma.",
  logic_tree: {
    kind: "AND",
    children: [
      {
        kind: "DEMOGRAPHIC",
        field: "age",
        operator: ">=",
        value: 40,
        unit: "years",
      },
      {
        kind: "CONCEPT",
        criterion: {
          snomed_concept_id: "49727002",
          preferred_term: "Cough (finding)",
          semantic_tag: "finding",
        },
      },
    ],
  },
};

function mockSearch() {
  jest.spyOn(global, "fetch").mockImplementation((url) => {
    if (String(url).includes("/api/terminology/search")) {
      return Promise.resolve({
        ok: true,
        json: async () => [],
        text: async () => "[]",
      } as Response);
    }
    if (String(url).includes("/api/guidance/test-patients?")) {
      return Promise.resolve({
        ok: true,
        json: async () => [],
        text: async () => "[]",
      } as Response);
    }
    return Promise.resolve({
      ok: true,
      json: async () => [],
      text: async () => "[]",
    } as Response);
  });
}

function goToStep(stepNumber: 1 | 2 | 3 | 4) {
  const stepper = screen.getAllByRole("button", {
    name: new RegExp(`^Step ${stepNumber} of 4`, "i"),
  });
  stepper[0].click();
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("Phase 1 -- safety and copy fix", () => {
  it("uses the new Step 3 title and helper that say production is never touched", () => {
    expect(STEP_TITLES.try).toBe("Test your change safely");
    expect(STEP_HELPERS.try.toLowerCase()).toContain("sandbox");
    expect(STEP_HELPERS.try.toLowerCase()).toContain("production is never");
  });

  it("Step 4 helper points the reviewer at Bitmap Lifecycle", () => {
    expect(STEP_HELPERS.save.toLowerCase()).toContain("bitmap lifecycle");
  });

  it("renders the renamed Step 3 heading and sandbox-only intro in the editor", async () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );
    goToStep(3);
    expect(
      await screen.findByRole("heading", { name: STEP_TITLES.try, level: 3 }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText((t) => t.includes("Production is never touched"))
        .length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByText(SANDBOX_PANEL.heading),
    ).toBeInTheDocument();
  });

  it("does not render any 'live' test surface inside the editor", async () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );
    goToStep(3);
    await screen.findByText(SANDBOX_PANEL.heading);
    expect(
      screen.queryByRole("button", { name: /test against live/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: /test the saved rule against the production ruleset/i,
      }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/Test against the live ruleset/i)).toBeNull();
  });

  it("renders the 'Saved, but not live yet' banner on Step 4", async () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );
    goToStep(4);
    expect(
      await screen.findByRole("status", {
        name: NOT_LIVE_YET_BANNER.title,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(NOT_LIVE_YET_BANNER.body)).toBeInTheDocument();
    const cta = screen.getByRole("link", {
      name: NOT_LIVE_YET_BANNER.actionLabel,
    });
    expect(cta).toBeInTheDocument();
    expect(cta.getAttribute("href")).toMatch(/bitmap-lifecycle/);
  });

  it("shows the brand-new-draft empty state on Step 3 when rule_id is missing", async () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={{ ...SAMPLE_RULE, rule_id: "" }}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );
    goToStep(3);
    expect(
      await screen.findByRole("status", {
        name: SANDBOX_PANEL.ruleNotSavedTitle,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(SANDBOX_PANEL.ruleNotSavedBody),
    ).toBeInTheDocument();
  });

  it("does not import StepRail (file is gone in Phase 1)", async () => {
    // Pin: importing the deleted StepRail must throw.
    await expect(
      // @ts-expect-error -- module deliberately removed in Phase 1
      import("../StepRail"),
    ).rejects.toBeTruthy();
  });
});

describe("Phase 1 -- TestPatientsPanel sandbox-only", () => {
  it("shows the sandbox heading and intro text", async () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );
    goToStep(3);
    await screen.findByText(SANDBOX_PANEL.heading);
    expect(screen.getByText(SANDBOX_PANEL.intro)).toBeInTheDocument();
  });

  it("shows the 'no saved test patients' empty state on a saved rule with zero patients", async () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );
    goToStep(3);
    await waitFor(() =>
      expect(
        screen.getByText(SANDBOX_PANEL.noPatientsTitle),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(SANDBOX_PANEL.noPatientsBody)).toBeInTheDocument();
  });
});
