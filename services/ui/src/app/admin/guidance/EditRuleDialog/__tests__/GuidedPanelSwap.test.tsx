/**
 * The guided wizard's right-column panel should show the pinned NICE
 * guideline quote while the wizard is still building the tree, then
 * swap to the normal live-preview summary once the wizard reaches
 * Review -- see GuidelineQuotePanel's and Step1Who's doc comments.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import EditRuleDialog from "..";

const TEXT = "In people aged 55 or over with weight loss, or nausea and vomiting.";

const SAMPLE_RULE = {
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
  // Guided is the default view -- this suite is specifically about it.
  window.localStorage.removeItem("leo.editRuleDialog.viewMode");
  mockSearch();
});

afterEach(() => {
  jest.restoreAllMocks();
  window.localStorage.clear();
});

describe("EditRuleDialog: guided wizard right-column panel swap", () => {
  it("pins the NICE quote while the wizard builds, then swaps to the live preview at Review", () => {
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={() => {}} />,
    );

    // Step 1 of the wizard: the right column shows the guideline
    // quote, not a half-built live summary.
    expect(
      screen.getByRole("region", { name: /nice guideline wording for this rule/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: /live preview of this rule/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /no, nothing else/i }));
    fireEvent.click(screen.getByRole("button", { name: /looks right, continue/i }));
    // Still building (Step 3) -- the quote panel stays pinned.
    expect(
      screen.getByRole("region", { name: /nice guideline wording for this rule/i }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /confirm situation a/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirm situation b/i }));

    // Review: the panel swaps back to the normal live preview.
    expect(screen.getByText(/here's the rule you built/i)).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: /live preview of this rule/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: /nice guideline wording for this rule/i }),
    ).not.toBeInTheDocument();
  });
});
