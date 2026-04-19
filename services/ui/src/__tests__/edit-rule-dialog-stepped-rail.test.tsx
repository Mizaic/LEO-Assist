/**
 * VT-LEO-AI-511 -- TC-002 rail navigation.
 *
 * Verifies that the StepRail renders four numbered jump-able steps and
 * that clicking a rail item swaps the visible step canvas.
 */

import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import EditRuleDialog from "../app/admin/guidance/EditRuleDialog";

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
  it("renders four numbered jump-able steps with state chips and navigates on click", () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );

    // The rail nav region carries the canonical aria-label.
    expect(
      screen.getByRole("navigation", { name: /steps to change this rule/i }),
    ).toBeInTheDocument();

    // Four numbered step buttons are present.
    for (const n of [1, 2, 3, 4]) {
      const btn = screen.getByRole("button", {
        name: new RegExp(`^Step ${n} of 4`, "i"),
      });
      expect(btn).toBeInTheDocument();
    }

    // Step 1 starts current; the canvas region is "Step 1 of 4".
    expect(
      screen.getByRole("region", { name: /^Step 1 of 4$/i }),
    ).toBeInTheDocument();

    // Click step 4: the Save reason field appears (only on step 4).
    fireEvent.click(
      screen.getByRole("button", { name: /^Step 4 of 4/i }),
    );
    expect(
      screen.getByLabelText(/why are you changing this rule/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: /^Step 4 of 4$/i }),
    ).toBeInTheDocument();

    // Jump back to step 2: action chip and strength dropdown appear.
    fireEvent.click(
      screen.getByRole("button", { name: /^Step 2 of 4/i }),
    );
    expect(
      screen.getAllByLabelText(/short name for this rule/i)[0],
    ).toBeInTheDocument();
    // The reason field is no longer in the DOM (single-step canvas).
    expect(
      screen.queryByLabelText(/why are you changing this rule/i),
    ).not.toBeInTheDocument();
  });
});
