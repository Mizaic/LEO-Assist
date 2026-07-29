/**
 * VT-LEO-AI-511 -- TC-002 rail navigation.
 *
 * Verifies the flat stepper is jump-able and that clicking Suggest /
 * Save swaps the visible step canvas. Slot count grows with
 * situations, so tests assert by slot title rather than "of 3".
 */

import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import EditRuleDialog from "../app/admin/guidance/EditRuleDialog";
import { goToEditorStep } from "../app/admin/guidance/EditRuleDialog/__tests__/goToEditorStep";

const SAMPLE_RULE = {
  rule_id: "rule:NG12:abc",
  name: "Mesothelioma urgent X-ray",
  strength: "offer",
  guideline_id: "NG12",
  chapter_title: "Recommendations organised by site of cancer",
  recommendation_text: "Offer an urgent chest X-ray for mesothelioma.",
  logic_tree: {
    kind: "AND",
    children: [
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

function mockSearch(hits: unknown[] = []) {
  jest.spyOn(global, "fetch").mockImplementation((url) => {
    if (String(url).includes("/api/terminology/search")) {
      return Promise.resolve({
        ok: true,
        json: async () => hits,
        text: async () => JSON.stringify(hits),
      } as Response);
    }
    return Promise.resolve({
      ok: true,
      json: async () => [],
      text: async () => "[]",
    } as Response);
  });
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("EditRuleDialog stepped rail -- VT-511-TC-002", () => {
  it("renders jump-able Suggest and Save slots and navigates on click", () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );

    expect(
      screen.getByRole("navigation", { name: /steps to change this rule/i }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", {
        name: /Step \d+ of \d+: What should the system suggest/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /Step \d+ of \d+: Save your change/i,
      }),
    ).toBeInTheDocument();

    goToEditorStep(3);
    expect(
      screen.getByLabelText(/why are you changing this rule/i),
    ).toBeInTheDocument();

    goToEditorStep(2);
    expect(
      screen.getAllByLabelText(/short name for this rule/i)[0],
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText(/why are you changing this rule/i),
    ).not.toBeInTheDocument();
  });
});
