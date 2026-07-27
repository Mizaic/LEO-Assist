/**
 * EditRuleDialog "jump to issue" integration tests -- verifies the
 * issue-count banner (ValidationIssueBanner) replacing the old single
 * generic warning, and that "Take me there" reaches the offending row
 * regardless of which outer step (Who / Save) the reviewer clicked it
 * from.
 *
 * Per the highlight-to-build wizard plan's Phase 4
 * `issue-banner-with-jump` / `wizard-jump-navigation` todos.
 */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import EditRuleDialog from "..";

// jsdom does not implement scrollIntoView -- see
// HighlightWizard/index.tsx's useJumpScrollAndFlash doc comment.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = jest.fn();
}

const EMPTY_GROUP_NODE_ID = "empty-group-1";

const RULE_WITH_EMPTY_GROUP = {
  rule_id: "rule:NG12:empty-group",
  name: "Rule with an abandoned empty group",
  strength: "offer",
  guideline_id: "NG12",
  recommendation_text: "Offer an urgent chest X-ray for people aged 40 or over with cough.",
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
        node_id: EMPTY_GROUP_NODE_ID,
        kind: "AND",
        children: [],
      },
    ],
  },
};

function mockSearch() {
  jest.spyOn(global, "fetch").mockImplementation(() =>
    Promise.resolve({ ok: true, json: async () => [], text: async () => "[]" } as Response),
  );
}

function goToStep(stepNumber: 1 | 2 | 3) {
  const stepper = screen.getAllByRole("button", {
    name: new RegExp(`^Step ${stepNumber} of 3`, "i"),
  });
  fireEvent.click(stepper[0]);
}

afterEach(() => {
  jest.restoreAllMocks();
  window.localStorage.clear();
});

describe("EditRuleDialog: jump-to-issue banner", () => {
  it("shows an issue-count banner (not the old generic warning) naming the empty group", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={RULE_WITH_EMPTY_GROUP} open onClose={() => {}} onSave={jest.fn()} />,
    );

    expect(screen.getByText("We found 1 problem.")).toBeInTheDocument();
    // Shown twice: once inside ValidationIssueBanner, once inside the
    // Step 1 always-visible ProblemNodeRow for the same empty group.
    expect(screen.getAllByText(/one of the groups is empty/i).length).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: /remove this problem/i }),
    ).toBeInTheDocument();
  });

  it("'Take me there' from the Who step scrolls to the problem row already on screen", async () => {
    mockSearch();
    const scrollSpy = jest.fn();
    Element.prototype.scrollIntoView = scrollSpy;
    render(
      <EditRuleDialog rule={RULE_WITH_EMPTY_GROUP} open onClose={() => {}} onSave={jest.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /take me there/i }));

    await waitFor(() => expect(scrollSpy).toHaveBeenCalled());
    expect(
      screen.getByTestId(`wizard-problem-row-${EMPTY_GROUP_NODE_ID}`),
    ).toBeInTheDocument();
  });

  it("'Take me there' from the Save step switches back to Who and shows the problem row", async () => {
    mockSearch();
    const scrollSpy = jest.fn();
    Element.prototype.scrollIntoView = scrollSpy;
    render(
      <EditRuleDialog rule={RULE_WITH_EMPTY_GROUP} open onClose={() => {}} onSave={jest.fn()} />,
    );

    goToStep(3);
    expect(screen.getByLabelText(/why are you changing this rule/i)).toBeInTheDocument();
    // Step 4's own banner (rendered via Step4Save's treeIssues prop),
    // independent of Step 1's copy of the same banner.
    expect(screen.getByText("We found 1 problem.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /take me there/i }));

    await waitFor(() =>
      expect(screen.queryByLabelText(/why are you changing this rule/i)).not.toBeInTheDocument(),
    );
    expect(
      await screen.findByTestId(`wizard-problem-row-${EMPTY_GROUP_NODE_ID}`),
    ).toBeInTheDocument();
    await waitFor(() => expect(scrollSpy).toHaveBeenCalled());
  });
});
