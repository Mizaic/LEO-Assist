/**
 * Live-render tests for StepPathwayConditions -- Step 3 of the
 * highlight-to-build wizard, repeated once per confirmed pathway
 * ("Within this situation, what must ALL be true?"). Covers the
 * lead-row + nested-cluster rendering for both structure- and
 * heuristic-sourced boundaries, the AT_LEAST-vs-AND grouping choice,
 * the resolved-row gate on "Confirm situation X", and the collapsed
 * "already confirmed" summary.
 *
 * Per the highlight-to-build wizard plan's `step-pathway-conditions`
 * todo.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StepPathwayConditions from "../HighlightWizard/StepPathwayConditions";
import { buildPathwayRows } from "../HighlightWizard/wizardMapping";
import type { ListRowResolution } from "../SentenceEditor/ListRecommendationView";
import type {
  PathwayTextBoundary,
  RecommendationStructureItem,
} from "../SentenceEditor/pathwayTextSplit";
import type { LogicCriterion } from "../types";

const STRUCTURE_BOUNDARY: PathwayTextBoundary = {
  text: "indigestion with any of the following:",
  start: 40,
  end: 80,
  source: "structure",
  structureChildren: [
    { text: "upper abdominal pain", start: 81, end: 102 },
    { text: "nausea", start: 104, end: 110 },
    { text: "vomiting", start: 112, end: 120 },
  ],
};

const SINGLE_LEAF_BOUNDARY: PathwayTextBoundary = {
  text: "upper abdominal pain",
  start: 0,
  end: 21,
  source: "structure",
};

const HEURISTIC_CLUSTER_BOUNDARY: PathwayTextBoundary = {
  text:
    "nausea with any of the following: weight loss, heartburn or " +
    "indigestion",
  start: 0,
  end: 74,
  source: "heuristic",
};

function makeCriterion(overrides: Partial<LogicCriterion> = {}): LogicCriterion {
  return { snomed_concept_id: "1", preferred_term: "Indigestion (finding)", ...overrides };
}

function resolveNothing(): ListRowResolution | undefined {
  return undefined;
}

describe("StepPathwayConditions: buildPathwayRows", () => {
  it("preserves real structureChildren offsets for a structure-sourced boundary", () => {
    const { items, hasCluster } = buildPathwayRows(STRUCTURE_BOUNDARY);
    expect(hasCluster).toBe(true);
    expect(items).toHaveLength(1);
    expect(items[0].text).toBe("indigestion with any of the following:");
    expect(items[0].children).toEqual(STRUCTURE_BOUNDARY.structureChildren);
  });

  it("returns a single leaf row with no cluster for a plain pathway", () => {
    const { items, hasCluster } = buildPathwayRows(SINGLE_LEAF_BOUNDARY);
    expect(hasCluster).toBe(false);
    expect(items).toEqual([
      { text: "upper abdominal pain", start: 0, end: 20 },
    ]);
  });

  it("locates cluster items with stable, non-colliding local offsets for a heuristic boundary", () => {
    const { items, hasCluster } = buildPathwayRows(HEURISTIC_CLUSTER_BOUNDARY);
    expect(hasCluster).toBe(true);
    expect(items).toHaveLength(1);
    expect(items[0].text).toBe("nausea");
    const children = items[0].children as RecommendationStructureItem[];
    expect(children.map((c) => c.text)).toEqual([
      "weight loss",
      "heartburn",
      "indigestion",
    ]);
    const starts = children.map((c) => c.start);
    expect(new Set(starts).size).toBe(starts.length);
  });
});

describe("StepPathwayConditions: rendering", () => {
  it("shows the situation progress header and helper", () => {
    render(
      <StepPathwayConditions
        pathwayIndex={2}
        pathwayCount={6}
        pathwayLetter="B"
        boundary={STRUCTURE_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
      />,
    );

    expect(screen.getByText("Situation B (2 of 6)")).toBeInTheDocument();
    expect(
      screen.getByText(/within this situation, what must all be true/i),
    ).toBeInTheDocument();
  });

  it("renders the lead row and its nested cluster children", () => {
    render(
      <StepPathwayConditions
        pathwayIndex={2}
        pathwayCount={6}
        pathwayLetter="B"
        boundary={STRUCTURE_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
      />,
    );

    expect(screen.getByText(/indigestion with any of the following/i)).toBeInTheDocument();
    expect(screen.getByText("nausea")).toBeInTheDocument();
    expect(screen.getByText("vomiting")).toBeInTheDocument();
  });

  it("forwards row clicks with the clicked row's own item", async () => {
    const user = userEvent.setup();
    const onRowClick = jest.fn();
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={2}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={onRowClick}
        onConfirmPathway={jest.fn()}
      />,
    );

    await user.click(screen.getByTestId("list-row-0-20"));
    expect(onRowClick).toHaveBeenCalledWith({ text: "upper abdominal pain", start: 0, end: 20 });
  });

  it("shows the already-confirmed summary for prior pathways", () => {
    render(
      <StepPathwayConditions
        pathwayIndex={2}
        pathwayCount={6}
        pathwayLetter="B"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        confirmedSummaries={[{ letter: "A", summary: "upper abdominal pain" }]}
      />,
    );

    expect(screen.getByTestId("confirmed-pathway-A")).toHaveTextContent(
      "A: upper abdominal pain",
    );
  });
});

describe("StepPathwayConditions: the cluster grouping question", () => {
  it("asks only when a cluster was detected", () => {
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={2}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
      />,
    );

    expect(screen.queryByText(/any of the following/i)).not.toBeInTheDocument();
  });

  it("calls onChooseGrouping with AT_LEAST for the recommended option", async () => {
    const user = userEvent.setup();
    const onChooseGrouping = jest.fn();
    render(
      <StepPathwayConditions
        pathwayIndex={2}
        pathwayCount={6}
        pathwayLetter="B"
        boundary={STRUCTURE_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        onChooseGrouping={onChooseGrouping}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: /only one needs to match/i }),
    );
    expect(onChooseGrouping).toHaveBeenCalledWith("AT_LEAST");
  });

  it("shows the confirmed choice with a Change action once grouping is set", async () => {
    const user = userEvent.setup();
    const onChooseGrouping = jest.fn();
    render(
      <StepPathwayConditions
        pathwayIndex={2}
        pathwayCount={6}
        pathwayLetter="B"
        boundary={STRUCTURE_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        clusterGrouping="AT_LEAST"
        onChooseGrouping={onChooseGrouping}
      />,
    );

    expect(screen.getByText(/only one of these needs to match/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /change/i }));
    expect(onChooseGrouping).toHaveBeenCalledWith("AND");
  });
});

describe("StepPathwayConditions: the resolved-row gate", () => {
  it("disables Confirm until every row is resolved", () => {
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={1}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: /confirm situation a/i }),
    ).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(
      /one row still needs a match/i,
    );
  });

  it("enables Confirm once the leaf row resolves", () => {
    const resolved: ListRowResolution = {
      criterion: makeCriterion(),
      preferredTerm: "Upper abdominal pain (finding)",
    };
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={1}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={() => resolved}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: /confirm situation a/i }),
    ).toBeEnabled();
  });

  it("calls onConfirmPathway when Confirm is clicked while enabled", async () => {
    const user = userEvent.setup();
    const onConfirmPathway = jest.fn();
    const resolved: ListRowResolution = {
      criterion: makeCriterion(),
      preferredTerm: "Upper abdominal pain (finding)",
    };
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={2}
        pathwayLetter="A"
        nextPathwayLetter="B"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={() => resolved}
        onRowClick={jest.fn()}
        onConfirmPathway={onConfirmPathway}
      />,
    );

    const button = screen.getByRole("button", {
      name: /confirm situation a, next -> b/i,
    });
    await user.click(button);
    expect(onConfirmPathway).toHaveBeenCalledTimes(1);
  });

  it("stays disabled when an external confirmBlockedReason is set, even if every row resolved", () => {
    const resolved: ListRowResolution = {
      criterion: makeCriterion(),
      preferredTerm: "Upper abdominal pain (finding)",
    };
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={1}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={() => resolved}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        confirmBlockedReason="One row still needs your check before you can continue."
      />,
    );

    expect(
      screen.getByRole("button", { name: /confirm situation a/i }),
    ).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(/needs your check/i);
  });
});
