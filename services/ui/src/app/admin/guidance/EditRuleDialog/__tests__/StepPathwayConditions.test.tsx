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
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StepPathwayConditions from "../HighlightWizard/StepPathwayConditions";
import { buildPathwayRows } from "../HighlightWizard/wizardMapping";
import type { ListRowResolution } from "../SentenceEditor/ListRecommendationView";
import type {
  PathwayTextBoundary,
  RecommendationStructureItem,
} from "../SentenceEditor/pathwayTextSplit";
import type { EditableLogicNode, LogicCriterion } from "../types";

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

// NG12 1.2.9 pathway D -- "nausea or vomiting" is a marker-less
// lead-or cluster ahead of the trailing "any of the following" list.
const TWO_CLUSTER_BOUNDARY: PathwayTextBoundary = {
  text:
    "nausea or vomiting with any of the following: weight loss, " +
    "reflux, dyspepsia, upper abdominal pain.",
  start: 0,
  end: 91,
  source: "heuristic",
};

function makeCriterion(overrides: Partial<LogicCriterion> = {}): LogicCriterion {
  return { snomed_concept_id: "1", preferred_term: "Indigestion (finding)", ...overrides };
}

function resolveNothing(): ListRowResolution | undefined {
  return undefined;
}

function makeAgeLeaf(): EditableLogicNode {
  return {
    node_id: "n-age-1",
    kind: "DEMOGRAPHIC",
    field: "age",
    operator: ">=",
    value: 55,
    unit: "years",
  } as EditableLogicNode;
}

function resolveTo(node: EditableLogicNode): () => ListRowResolution {
  return () => ({ nodeId: node.node_id, preferredTerm: "is 55 years or older" });
}

function mockSearch(hits: unknown[] = []) {
  jest.spyOn(global, "fetch").mockImplementation((url) => {
    if (String(url).includes("/api/terminology/search")) {
      return Promise.resolve({ ok: true, json: async () => hits } as Response);
    }
    return Promise.resolve({ ok: true, json: async () => [] } as Response);
  });
}

function getWordChunk(word: string) {
  return screen.getByText(word, { selector: "[data-word-index]" });
}

describe("StepPathwayConditions: buildPathwayRows", () => {
  it("preserves real structureChildren offsets for a structure-sourced boundary", () => {
    const { items, hasCluster } = buildPathwayRows(STRUCTURE_BOUNDARY);
    expect(hasCluster).toBe(true);
    expect(items).toHaveLength(1);
    // The marker phrase is stripped from the item's own text -- see
    // `resolveAtLeastCluster`'s doc comment: `nice_list_parser.py`
    // keeps "with any of the following:" IN the item's own `<li>`
    // paragraph, so it must be stripped here, not pre-excluded.
    expect(items[0].text).toBe("indigestion");
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

    expect(screen.getByText("indigestion")).toBeInTheDocument();
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
    expect(onRowClick).toHaveBeenCalledWith(
      { text: "upper abdominal pain", start: 0, end: 20 },
      expect.any(HTMLElement),
    );
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
    expect(onChooseGrouping).toHaveBeenCalledWith("AT_LEAST", 1);
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

    expect(screen.getByTestId("lead-either-of-layout")).toBeInTheDocument();
    expect(screen.getByText(/required in this situation/i)).toBeInTheDocument();
    expect(screen.getByText(/plus either of these/i)).toBeInTheDocument();
    expect(
      screen.getByText(
        /only one of upper abdominal pain, nausea, and vomiting needs to match/i,
      ),
    ).toBeInTheDocument();
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

describe("StepPathwayConditions: two clusters in the same pathway (NG12 1.2.9 pathway D)", () => {
  it("asks the lead-or grouping question separately from the trailing one", () => {
    render(
      <StepPathwayConditions
        pathwayIndex={4}
        pathwayCount={4}
        pathwayLetter="D"
        boundary={TWO_CLUSTER_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
      />,
    );

    expect(
      screen.getByRole("group", { name: /nausea or vomiting/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: /any of the following/i }),
    ).toBeInTheDocument();
  });

  it("blocks Confirm with a short choose-above hint, not a second copy of the prompt", () => {
    render(
      <StepPathwayConditions
        pathwayIndex={4}
        pathwayCount={4}
        pathwayLetter="D"
        boundary={TWO_CLUSTER_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        clusterGrouping="AT_LEAST"
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      /choose how many need to match above/i,
    );
    // Prompt card still names the lead findings once -- not twice under Confirm.
    expect(screen.getAllByText(/nausea or vomiting/i)).toHaveLength(1);
  });

  it("calls onChooseLeadGrouping and onChooseGrouping independently", async () => {
    const user = userEvent.setup();
    const onChooseLeadGrouping = jest.fn();
    const onChooseGrouping = jest.fn();
    render(
      <StepPathwayConditions
        pathwayIndex={4}
        pathwayCount={4}
        pathwayLetter="D"
        boundary={TWO_CLUSTER_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        onChooseLeadGrouping={onChooseLeadGrouping}
        onChooseGrouping={onChooseGrouping}
      />,
    );

    const leadGroup = screen.getByRole("group", { name: /nausea or vomiting/i });
    await user.click(
      within(leadGroup).getByRole("button", { name: /only one needs to match/i }),
    );
    expect(onChooseLeadGrouping).toHaveBeenCalledWith("AT_LEAST", 1);
    expect(onChooseGrouping).not.toHaveBeenCalled();
  });

  it("recommends at-least-N when the guideline says N or more", async () => {
    const user = userEvent.setup();
    const onChooseGrouping = jest.fn();
    const ng112A: PathwayTextBoundary = {
      text:
        "if they have 2 or more of the following unexplained symptoms",
      start: 0,
      end: 60,
      source: "heuristic",
      structureChildren: [
        { text: "cough", start: 70, end: 75 },
        { text: "fatigue", start: 77, end: 84 },
        { text: "chest pain", start: 86, end: 96 },
      ],
    };
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={2}
        pathwayLetter="A"
        boundary={ng112A}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        onChooseGrouping={onChooseGrouping}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: /at least 2 need to match/i }),
    );
    expect(onChooseGrouping).toHaveBeenCalledWith("AT_LEAST", 2);
  });

  it("enables Confirm only once BOTH clusters' groupings are chosen and every row resolves", () => {
    const resolved: ListRowResolution = {
      criterion: makeCriterion(),
      preferredTerm: "Nausea (finding)",
    };
    render(
      <StepPathwayConditions
        pathwayIndex={4}
        pathwayCount={4}
        pathwayLetter="D"
        boundary={TWO_CLUSTER_BOUNDARY}
        getRowResolution={() => resolved}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        clusterGrouping="AT_LEAST"
        leadClusterGrouping="AT_LEAST"
      />,
    );

    expect(
      screen.getByRole("button", { name: /confirm situation d/i }),
    ).toBeEnabled();
  });
});

describe("StepPathwayConditions: highlight-a-word multi-code picker", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("does not render the highlight affordance when onAddMultiConcept is not supplied", () => {
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
      screen.queryByRole("button", { name: /highlight text for more codes/i }),
    ).not.toBeInTheDocument();
  });

  it("renders a highlight affordance per row when onAddMultiConcept is supplied", () => {
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={1}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        onAddMultiConcept={jest.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: /highlight text for more codes/i }),
    ).toBeInTheDocument();
  });

  it("forwards the highlighted row's item plus the picked multi-seed criterion", async () => {
    const user = userEvent.setup();
    mockSearch([
      { snomed_concept_id: "422587007", term: "Nausea", semantic_tag: "finding" },
    ]);
    const onAddMultiConcept = jest.fn();
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={1}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        onAddMultiConcept={onAddMultiConcept}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: /highlight text for more codes/i }),
    );
    const upper = getWordChunk("upper");
    await user.pointer([
      { keys: "[MouseLeft>]", target: upper },
      { keys: "[/MouseLeft]", target: upper },
    ]);
    await user.click(screen.getByRole("button", { name: /confirm selection/i }));

    await user.click(await screen.findByRole("checkbox", { name: /select nausea/i }));
    await user.click(screen.getByRole("button", { name: "Add 1 code" }));

    expect(onAddMultiConcept).toHaveBeenCalledWith(
      { text: "upper abdominal pain", start: 0, end: 20 },
      expect.objectContaining({ snomed_concept_id: "422587007" }),
    );
  });
});

describe("StepPathwayConditions: inline age/sex editor for an already-resolved DEMOGRAPHIC row", () => {
  it("does not render the inline editor when no row is expanded", () => {
    const ageLeaf = makeAgeLeaf();
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={1}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveTo(ageLeaf)}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        onUpdatePathway={jest.fn()}
      />,
    );

    expect(screen.queryByLabelText(/how to compare age/i)).not.toBeInTheDocument();
  });

  it("renders the inline age editor for the expandedDemographicNode", () => {
    const ageLeaf = makeAgeLeaf();
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={1}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveTo(ageLeaf)}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        onUpdatePathway={jest.fn()}
        expandedDemographicNode={ageLeaf}
      />,
    );

    expect(screen.getByLabelText(/how to compare age/i)).toBeInTheDocument();
  });

  it("dispatches set_demographic through onUpdatePathway when the inline editor's operator changes", async () => {
    const user = userEvent.setup();
    const ageLeaf = makeAgeLeaf();
    const onUpdatePathway = jest.fn();
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={1}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveTo(ageLeaf)}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        onUpdatePathway={onUpdatePathway}
        expandedDemographicNode={ageLeaf}
      />,
    );

    await user.click(screen.getByLabelText(/how to compare age/i));
    await user.click(await screen.findByRole("option", { name: /is at most/i }));

    expect(onUpdatePathway).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "set_demographic",
        nodeId: ageLeaf.node_id,
        operator: "<=",
      }),
    );
  });

  it("clicking the already-resolved row calls onRowClick, leaving expand/collapse to the caller", async () => {
    // StepPathwayConditions is presentation-only -- it does not decide
    // whether a click should toggle the inline editor. That decision
    // (and the resulting expandedDemographicNodeId) belongs to
    // PathwayConditionsStage, which owns the tree.
    const user = userEvent.setup();
    const ageLeaf = makeAgeLeaf();
    const onRowClick = jest.fn();
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={1}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveTo(ageLeaf)}
        onRowClick={onRowClick}
        onConfirmPathway={jest.fn()}
        onUpdatePathway={jest.fn()}
      />,
    );

    await user.click(screen.getByText(SINGLE_LEAF_BOUNDARY.text));

    expect(onRowClick).toHaveBeenCalledTimes(1);
  });
});

describe("StepPathwayConditions: the copy-across offer", () => {
  it("does not render a banner when there is nothing to offer", () => {
    render(
      <StepPathwayConditions
        pathwayIndex={2}
        pathwayCount={2}
        pathwayLetter="B"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
      />,
    );

    expect(screen.queryByText(/copy your codes across/i)).not.toBeInTheDocument();
  });

  it("shows the offer and forwards accept / dismiss clicks", async () => {
    const user = userEvent.setup();
    const onAcceptCopyAcross = jest.fn();
    const onDismissCopyAcross = jest.fn();
    render(
      <StepPathwayConditions
        pathwayIndex={2}
        pathwayCount={2}
        pathwayLetter="B"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        copyAcrossOffer={{ sourceLetter: "A", count: 6 }}
        onAcceptCopyAcross={onAcceptCopyAcross}
        onDismissCopyAcross={onDismissCopyAcross}
      />,
    );

    expect(
      screen.getByText(/situation a asked about the same 6 findings/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /copy them across/i }));
    expect(onAcceptCopyAcross).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: /i'll do this one myself/i }));
    expect(onDismissCopyAcross).toHaveBeenCalledTimes(1);
  });
});

describe("StepPathwayConditions: adding a per-situation lab-value condition", () => {
  it("hides the Add lab value button when onAddPathwayObservation is not provided", () => {
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

    expect(
      screen.queryByRole("button", { name: /add a lab value or reading for this situation only/i }),
    ).not.toBeInTheDocument();
  });

  it("calls onAddPathwayObservation when Add lab value is clicked", async () => {
    const user = userEvent.setup();
    const onAddPathwayObservation = jest.fn();
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={2}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        onAddPathwayObservation={onAddPathwayObservation}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: /add a lab value or reading for this situation only/i }),
    );

    expect(onAddPathwayObservation).toHaveBeenCalledTimes(1);
  });
});

describe("StepPathwayConditions: Patient should not have", () => {
  it("hides the Patient should not have button when onAddPathwayShouldNotHave is not provided", () => {
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

    expect(
      screen.queryByRole("button", {
        name: /add a finding that must not be present for this situation/i,
      }),
    ).not.toBeInTheDocument();
  });

  it("calls onAddPathwayShouldNotHave when Patient should not have is clicked", async () => {
    const user = userEvent.setup();
    const onAddPathwayShouldNotHave = jest.fn();
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={2}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        onAddPathwayShouldNotHave={onAddPathwayShouldNotHave}
      />,
    );

    await user.click(
      screen.getByRole("button", {
        name: /add a finding that must not be present for this situation/i,
      }),
    );

    expect(onAddPathwayShouldNotHave).toHaveBeenCalledTimes(1);
  });

  it("lists a NOT-group finding as something the patient must not have", () => {
    const excluded: EditableLogicNode = {
      node_id: "hrt",
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "266717002", preferred_term: "HRT" },
    };
    render(
      <StepPathwayConditions
        pathwayIndex={1}
        pathwayCount={1}
        pathwayLetter="A"
        boundary={SINGLE_LEAF_BOUNDARY}
        getRowResolution={resolveNothing}
        onRowClick={jest.fn()}
        onConfirmPathway={jest.fn()}
        shouldNotHaveLeaves={[excluded]}
        onEditConfirmedLeaf={jest.fn()}
      />,
    );

    expect(screen.getByTestId("should-not-have-section")).toBeInTheDocument();
    expect(screen.getByText(/patient must not have hrt/i)).toBeInTheDocument();
  });
});
