/**
 * VT-LEO-AI-511 -- TC-005 (save gating) and TC-010 (Cancel discards).
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
  recommendation_text: "Offer urgent chest X-ray.",
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

function mockSearch() {
  jest.spyOn(global, "fetch").mockImplementation(() =>
    Promise.resolve({
      ok: true,
      json: async () => [],
      text: async () => "[]",
    } as Response),
  );
}



afterEach(() => {
  jest.restoreAllMocks();
});

describe("EditRuleDialog save gating -- VT-511-TC-005", () => {
  it("Save changes is disabled until reason length >= 3 AND tree is valid", () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );

    const save = screen.getByRole("button", { name: /save your changes/i });
    expect(save).toBeDisabled();

    goToEditorStep(3);
    const reason = screen.getByLabelText(
      /why are you changing this rule/i,
    ) as HTMLInputElement;

    fireEvent.change(reason, { target: { value: "AB" } });
    expect(save).toBeDisabled();

    fireEvent.change(reason, { target: { value: "ABC" } });
    expect(save).not.toBeDisabled();

    fireEvent.change(reason, { target: { value: "" } });
    expect(save).toBeDisabled();
  });
});

describe("EditRuleDialog Cancel discards -- VT-511-TC-010", () => {
  it("clicking Cancel calls onClose and never calls onSave", () => {
    mockSearch();
    const onClose = jest.fn();
    const onSave = jest.fn();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={onClose}
        onSave={onSave}
      />,
    );

    goToEditorStep(3);
    fireEvent.change(screen.getByLabelText(/why are you changing this rule/i), {
      target: { value: "Half-finished edit" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Cancel$/i }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onSave).not.toHaveBeenCalled();
  });
});
