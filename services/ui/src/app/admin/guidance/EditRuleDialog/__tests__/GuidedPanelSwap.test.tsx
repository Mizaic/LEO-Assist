/**
 * When a multi-pathway tree is already filled, Guided opens on Review
 * with the live preview (reopen after save) -- not Step 1 again.
 *
 * Quote-while-building swap is covered by EditRuleDialog.coach and
 * HighlightWizard tests (fresh startMode).
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { render, screen } from "@testing-library/react";

import EditRuleDialog from "..";

const TEXT = "In people aged 55 or over with weight loss, or nausea and vomiting.";

const FILLED_RULE = {
  rule_id: "rule:NG12:abc",
  name: "Upper GI cancer red flags",
  strength: "offer",
  guideline_id: "NG12",
  chapter_title: "Recommendations organised by site of cancer",
  recommendation_text: TEXT,
  logic_tree: {
    kind: "AND",
    children: [
      { kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: 55, unit: "years" },
      {
        kind: "OR",
        children: [
          {
            kind: "AND",
            pathway_key: "pw_a",
            children: [
              {
                kind: "CONCEPT",
                criterion: { snomed_concept_id: "wl", preferred_term: "Weight loss" },
              },
            ],
          },
          {
            kind: "AND",
            pathway_key: "pw_b",
            children: [
              {
                kind: "CONCEPT",
                criterion: { snomed_concept_id: "na", preferred_term: "Nausea" },
              },
              {
                kind: "CONCEPT",
                criterion: { snomed_concept_id: "vo", preferred_term: "Vomiting" },
              },
            ],
          },
        ],
      },
    ],
  },
};

function mockSearch() {
  jest.spyOn(global, "fetch").mockImplementation(() =>
    Promise.resolve({ ok: true, json: async () => [], text: async () => "[]" } as Response),
  );
}

beforeEach(() => {
  mockSearch();
});

afterEach(() => {
  jest.restoreAllMocks();
  window.localStorage.clear();
});

describe("EditRuleDialog: guided reopen after a filled multi-pathway save", () => {
  it("opens on Review with the live preview instead of forcing Step 1", () => {
    render(
      <EditRuleDialog rule={FILLED_RULE} open onClose={() => {}} onSave={() => {}} />,
    );

    expect(screen.getByTestId("wizard-review")).toBeInTheDocument();
    expect(screen.getByText(/check the live preview/i)).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: /live preview of this rule/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: /nice guideline wording for this rule/i }),
    ).toBeInTheDocument();
  });
});
