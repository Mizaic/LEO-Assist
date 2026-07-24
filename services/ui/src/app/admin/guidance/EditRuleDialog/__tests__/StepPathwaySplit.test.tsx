/**
 * Live-render tests for StepPathwaySplit -- Step 2 of the
 * highlight-to-build wizard ("Does this split into different
 * situations?"). Covers the structure-preferred rendering, the
 * heuristic fallback, merge/split editing of the proposed boundaries,
 * "Looks right, continue", and the "doesn't split" empty state.
 *
 * Per the highlight-to-build wizard plan's `step-pathway-split` todo.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StepPathwaySplit from "../HighlightWizard/StepPathwaySplit";
import type { RecommendationStructure } from "../SentenceEditor/pathwayTextSplit";

const HEURISTIC_TEXT =
  "In people aged 55 or over with: upper abdominal pain, or " +
  "indigestion with any of the following: nausea, vomiting or " +
  "weight loss, or nausea with any of the following: weight loss, " +
  "heartburn or indigestion.";

const NO_SPLIT_TEXT = "In people aged 55 or over with upper abdominal pain.";

const STRUCTURE: RecommendationStructure = {
  lead_text: "In people aged 55 or over with:",
  items: [
    { text: "upper abdominal pain", start: 32, end: 53 },
    {
      text: "indigestion with any of the following:",
      start: 57,
      end: 96,
      children: [
        { text: "nausea", start: 97, end: 103 },
        { text: "vomiting", start: 105, end: 113 },
      ],
    },
  ],
};

describe("StepPathwaySplit: structure-preferred rendering", () => {
  it("states the guideline's own boundaries as a fact, not a question", () => {
    render(
      <StepPathwaySplit
        recommendationText={null}
        recommendationStructure={STRUCTURE}
        onConfirm={jest.fn()}
        onNoSplit={jest.fn()}
      />,
    );

    expect(
      screen.getByText("The guideline lists 2 situations. Here they are."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/found from the guideline's own list formatting/i),
    ).toBeInTheDocument();
  });

  it("renders nested structure children as indented bullets", () => {
    render(
      <StepPathwaySplit
        recommendationText={null}
        recommendationStructure={STRUCTURE}
        onConfirm={jest.fn()}
        onNoSplit={jest.fn()}
      />,
    );

    expect(screen.getByText("nausea")).toBeInTheDocument();
    expect(screen.getByText("vomiting")).toBeInTheDocument();
  });

  it("calls onConfirm with the structure-derived boundaries on Looks right, continue", async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn();
    render(
      <StepPathwaySplit
        recommendationText={null}
        recommendationStructure={STRUCTURE}
        onConfirm={onConfirm}
        onNoSplit={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /looks right, continue/i }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const passed = onConfirm.mock.calls[0][0];
    expect(passed).toHaveLength(2);
    expect(passed[0].source).toBe("structure");
  });
});

describe("StepPathwaySplit: heuristic fallback", () => {
  it("shows the lower-confidence question copy and count when there is no structure", () => {
    render(
      <StepPathwaySplit
        recommendationText={HEURISTIC_TEXT}
        recommendationStructure={null}
        onConfirm={jest.fn()}
        onNoSplit={jest.fn()}
      />,
    );

    expect(
      screen.getByText(/does this apply the same way to everyone/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/we think we found 3 possible situations/i),
    ).toBeInTheDocument();
  });

  it("renders each heuristic row with a dashed border, not a solid one", () => {
    render(
      <StepPathwaySplit
        recommendationText={HEURISTIC_TEXT}
        recommendationStructure={null}
        onConfirm={jest.fn()}
        onNoSplit={jest.fn()}
      />,
    );

    const rows = document.querySelectorAll('[data-source="heuristic"]');
    expect(rows.length).toBe(3);
  });
});

describe("StepPathwaySplit: merge editing", () => {
  it("merges two selected rows into one on Confirm merge", async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn();
    render(
      <StepPathwaySplit
        recommendationText={HEURISTIC_TEXT}
        recommendationStructure={null}
        onConfirm={onConfirm}
        onNoSplit={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /merge two rows/i }));
    const rows = screen.getAllByTestId(/^pathway-boundary-row-/);
    expect(rows).toHaveLength(3);
    await user.click(rows[0]);
    await user.click(rows[1]);
    await user.click(screen.getByRole("button", { name: /confirm merge/i }));

    await user.click(screen.getByRole("button", { name: /looks right, continue/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm.mock.calls[0][0]).toHaveLength(2);
  });

  it("disables Confirm merge until exactly two rows are selected", async () => {
    const user = userEvent.setup();
    render(
      <StepPathwaySplit
        recommendationText={HEURISTIC_TEXT}
        recommendationStructure={null}
        onConfirm={jest.fn()}
        onNoSplit={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /merge two rows/i }));
    expect(screen.getByRole("button", { name: /confirm merge/i })).toBeDisabled();

    const rows = screen.getAllByTestId(/^pathway-boundary-row-/);
    await user.click(rows[0]);
    expect(screen.getByRole("button", { name: /confirm merge/i })).toBeDisabled();
  });

  it("Cancel returns to idle without changing the rows", async () => {
    const user = userEvent.setup();
    render(
      <StepPathwaySplit
        recommendationText={HEURISTIC_TEXT}
        recommendationStructure={null}
        onConfirm={jest.fn()}
        onNoSplit={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /merge two rows/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(screen.getAllByTestId(/^pathway-boundary-row-/)).toHaveLength(3);
    expect(
      screen.getByRole("button", { name: /looks right, continue/i }),
    ).toBeInTheDocument();
  });
});

describe("StepPathwaySplit: split editing", () => {
  it("splits a row into two at the confirmed word selection", async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn();
    render(
      <StepPathwaySplit
        recommendationText={HEURISTIC_TEXT}
        recommendationStructure={null}
        onConfirm={onConfirm}
        onNoSplit={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /split a row/i }));
    const rows = screen.getAllByTestId(/^pathway-boundary-row-/);
    await user.click(rows[0]);

    // The clicked row now renders its own text as focusable word
    // chunks; select the first word and confirm.
    const firstWord = screen.getByText(/^In$/);
    await user.click(firstWord);
    await user.click(screen.getByRole("button", { name: /confirm selection/i }));

    await user.click(screen.getByRole("button", { name: /looks right, continue/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm.mock.calls[0][0]).toHaveLength(4);
  });
});

describe("StepPathwaySplit: no split found", () => {
  it("shows the doesn't-split state and calls onNoSplit", async () => {
    const user = userEvent.setup();
    const onNoSplit = jest.fn();
    render(
      <StepPathwaySplit
        recommendationText={NO_SPLIT_TEXT}
        recommendationStructure={null}
        onConfirm={jest.fn()}
        onNoSplit={onNoSplit}
      />,
    );

    expect(
      screen.getByText(/couldn't find more than one situation/i),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /doesn't split/i }),
    );
    expect(onNoSplit).toHaveBeenCalledTimes(1);
  });
});
