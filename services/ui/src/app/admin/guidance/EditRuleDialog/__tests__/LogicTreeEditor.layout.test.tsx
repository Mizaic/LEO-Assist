/**
 * Layout tests for the refactored LogicTreeEditor (vertical-pathway design).
 *
 * Verifies:
 *   - OR root with children renders as PathwayList (vertical stacked cards).
 *   - AT-LEAST groups whose children are all CONCEPTs render inline.
 *   - Non-root groups are collapsible via a chevron and show a summary.
 *   - The root group does not show a collapse chevron.
 *   - Auto-collapse at depth >= 2.
 */

import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LogicTreeEditor from "../LogicTreeEditor";
import { assignNodeIds } from "../treeOps";
import type { EditableLogicNode } from "../types";
import { makeNg12129Tree } from "./fixtures/ng12129";

function makeAtLeastTree(): EditableLogicNode {
  return assignNodeIds({
    kind: "AT_LEAST",
    min: 2,
    children: [
      {
        kind: "CONCEPT",
        criterion: { snomed_concept_id: "1", preferred_term: "Cough (finding)" },
      },
      {
        kind: "CONCEPT",
        criterion: { snomed_concept_id: "2", preferred_term: "Fatigue (finding)" },
      },
      {
        kind: "CONCEPT",
        criterion: { snomed_concept_id: "3", preferred_term: "Dyspnea (finding)" },
      },
    ],
  });
}

function makeNestedTree(): EditableLogicNode {
  return assignNodeIds({
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
        kind: "OR",
        children: [
          {
            kind: "AT_LEAST",
            min: 2,
            children: [
              {
                kind: "CONCEPT",
                criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
              },
              {
                kind: "CONCEPT",
                criterion: { snomed_concept_id: "2", preferred_term: "Fatigue" },
              },
            ],
          },
        ],
      },
    ],
  });
}

const noop = () => {};

describe("LogicTreeEditor phase 1 layout", () => {
  it("renders AT-LEAST with all-CONCEPT children inline (single 'Any N or more of these' header)", () => {
    render(
      <LogicTreeEditor
        root={makeAtLeastTree()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    // The inline cluster is signalled by the soft-cased "Any" +
    // "or more of these" labels (Phase 3 of the wizard redesign;
    // the legacy "AT LEAST" / "At least" all-caps badge was retired).
    expect(screen.getByText("Any")).toBeInTheDocument();
    expect(screen.getByText(/or more of these/i)).toBeInTheDocument();
    // All three concept chips appear once each.
    expect(screen.getByText("Cough")).toBeInTheDocument();
    expect(screen.getByText("Fatigue")).toBeInTheDocument();
    expect(screen.getByText("Dyspnea")).toBeInTheDocument();
    // The "Add" affordance is the inline plus chip, not the verbose bar.
    expect(
      screen.getByRole("button", { name: /add a symptom.*to this group/i }),
    ).toBeInTheDocument();
  });

  it("does not render the inline cluster for AT-LEAST with mixed children", () => {
    const tree = assignNodeIds({
      kind: "AT_LEAST",
      min: 1,
      children: [
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
        },
        {
          kind: "AND",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "2", preferred_term: "Smoker" },
            },
          ],
        },
      ],
    });
    render(
      <LogicTreeEditor
        root={tree}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    // Mixed-child clusters fall back to the standard selector + add bar
    // (the inline "Any N or more of these" header is only emitted
    // when every child is a CONCEPT).
    expect(screen.queryByText("or more of these")).not.toBeInTheDocument();
    // Both the root AT-LEAST and the nested AND are rendered as standard
    // groups, each with its own kind selector.
    expect(
      screen.getAllByLabelText(/what this group means/i).length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("non-root groups expose a collapse chevron and summarise contents when collapsed", () => {
    render(
      <LogicTreeEditor
        root={makeNestedTree()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    // Find the OR sub-group's collapse button.
    const collapseBtn = screen.getByRole("button", { name: /collapse group/i });
    expect(collapseBtn).toBeInTheDocument();
    fireEvent.click(collapseBtn);

    // After collapse, the chevron flips to "expand" and a contents
    // summary appears.
    expect(screen.getByRole("button", { name: /expand group/i })).toBeInTheDocument();
    expect(screen.getByText(/sub-group/i)).toBeInTheDocument();

    // Concept chips inside the collapsed branch should disappear.
    expect(screen.queryByText("Cough")).not.toBeInTheDocument();
    expect(screen.queryByText("Fatigue")).not.toBeInTheDocument();
  });

  it("root group never shows a collapse chevron", () => {
    render(
      <LogicTreeEditor
        root={makeNestedTree()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    // There is exactly one collapse-able group in the tree (the OR sub-group),
    // not two. The root AND must not be collapsible because collapsing it
    // would empty the editor.
    const collapseButtons = screen.queryAllByRole("button", { name: /collapse group/i });
    const expandButtons = screen.queryAllByRole("button", { name: /expand group/i });
    expect(collapseButtons.length + expandButtons.length).toBe(1);
  });

  it("auto-collapses groups at depth >= 2 by default", () => {
    // Build a 3-level tree: AND > OR > AND > [Cough]
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "OR",
          children: [
            {
              kind: "AND",
              children: [
                {
                  kind: "CONCEPT",
                  criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
                },
              ],
            },
          ],
        },
      ],
    });
    render(
      <LogicTreeEditor
        root={tree}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    // Depth-2 group (the inner AND) starts collapsed, hiding the leaf.
    expect(screen.queryByText("Cough")).not.toBeInTheDocument();
    // Depth-1 group (OR) starts expanded so the user sees the structure.
    expect(screen.getByRole("button", { name: /expand group/i })).toBeInTheDocument();
  });

  it("inline AT-LEAST counter clamps to the number of children", () => {
    const tree = makeAtLeastTree();
    render(
      <LogicTreeEditor
        root={tree}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    const counter = screen.getByLabelText(
      /how many of these/i,
    ) as HTMLInputElement;
    expect(counter.value).toBe("2");
    expect(counter.max).toBe("3");
    // The "of N" caption shows the current child count.
    const cluster = counter.closest("[role='group']");
    expect(cluster).not.toBeNull();
    expect(within(cluster as HTMLElement).getByText(/of 3/)).toBeInTheDocument();
  });
});

describe("LogicTreeEditor -- OR-root pathway list layout", () => {
  function makeOrRoot(): EditableLogicNode {
    return assignNodeIds({
      kind: "OR",
      children: [
        {
          kind: "AND",
          name: "Possible cancer",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "1", preferred_term: "Haemoptysis (finding)" },
            },
          ],
        },
        {
          kind: "AND",
          name: "Symptom watch",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "2", preferred_term: "Weight loss (finding)" },
            },
          ],
        },
      ],
    });
  }

  it("renders pathway cards vertically with data-testid per letter", () => {
    render(
      <LogicTreeEditor
        root={makeOrRoot()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    expect(screen.getByTestId("pathway-card-A")).toBeInTheDocument();
    expect(screen.getByTestId("pathway-card-B")).toBeInTheDocument();
  });

  it("renders an Add pathway dashed button at the bottom", () => {
    render(
      <LogicTreeEditor
        root={makeOrRoot()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    expect(
      screen.getByRole("button", { name: /add another pathway/i }),
    ).toBeInTheDocument();
  });

  it("renders inline Preview sentence for each pathway", () => {
    render(
      <LogicTreeEditor
        root={makeOrRoot()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    const previews = screen.getAllByLabelText(/plain-english preview/i);
    expect(previews.length).toBe(2);
  });

  it("renders AddBar dashed buttons inside each pathway card", () => {
    render(
      <LogicTreeEditor
        root={makeOrRoot()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    const addSymptomBtns = screen.getAllByRole("button", { name: /add.*symptom/i });
    expect(addSymptomBtns.length).toBeGreaterThanOrEqual(2);
  });

  it("renders an 'Add condition group' button inside each pathway card so AND pathways can nest a set of OR's", () => {
    render(
      <LogicTreeEditor
        root={makeOrRoot()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    const addGroupBtns = screen.getAllByRole("button", { name: /add.*condition group/i });
    expect(addGroupBtns.length).toBe(2);
  });

  it("clicking 'Add condition group' dispatches add_group with groupKind OR against the pathway's own node id", () => {
    const tree = makeOrRoot();
    const pathwayA = tree.children?.[0];
    const onUpdate = jest.fn();
    render(
      <LogicTreeEditor
        root={tree}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={onUpdate}
        onRequestAdd={noop}
      />,
    );
    const addGroupBtns = screen.getAllByRole("button", { name: /add.*condition group/i });
    fireEvent.click(addGroupBtns[0]);
    expect(onUpdate).toHaveBeenCalledWith({
      kind: "add_group",
      parentNodeId: pathwayA?.node_id,
      groupKind: "OR",
    });
  });

  it("clicking 'Patient should not have' dispatches add_group with groupKind NOT", () => {
    const tree = makeOrRoot();
    const pathwayA = tree.children?.[0];
    const onUpdate = jest.fn();
    render(
      <LogicTreeEditor
        root={tree}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={onUpdate}
        onRequestAdd={noop}
      />,
    );
    const shouldNotBtns = screen.getAllByRole("button", {
      name: /patient should not have/i,
    });
    fireEvent.click(shouldNotBtns[0]);
    expect(onUpdate).toHaveBeenCalledWith({
      kind: "add_group",
      parentNodeId: pathwayA?.node_id,
      groupKind: "NOT",
    });
  });
});

describe("LogicTreeEditor -- pathway split nested inside a demographic AND (NG12 1.2.9)", () => {
  // Regression test for the pathway-detection consistency fix: before
  // this fix, LogicTreeEditor/index.tsx's isPathwayRoot() only checked
  // the literal root node, so a real rule shaped
  // AND[DEMOGRAPHIC(age>=55), OR[6 pathways]] rendered as one nested
  // blob here even though the read-only Check & approve view
  // (RuleLogicView.tsx) already rendered it as 6 lettered cards.
  it("renders 6 lettered pathway cards, not a nested blob", () => {
    render(
      <LogicTreeEditor
        root={makeNg12129Tree()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    for (const letter of ["A", "B", "C", "D", "E", "F"]) {
      expect(screen.getByTestId(`pathway-card-${letter}`)).toBeInTheDocument();
    }
  });

  it("renders the demographic prerequisite once above the pathway list, not inside pathway card A", () => {
    render(
      <LogicTreeEditor
        root={makeNg12129Tree()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    const lead = screen.getByRole("group", {
      name: /applies to every pathway below/i,
    });
    expect(within(lead).getByText(/age/i)).toBeInTheDocument();

    const cardA = screen.getByTestId("pathway-card-A");
    expect(within(cardA).queryByText(/age/i)).not.toBeInTheDocument();
  });
});

describe("LogicTreeEditor -- bare-leaf pathway (NG12 1.2.1-shaped OR child with no AND wrapper)", () => {
  // Regression test: a saved rule can have a single-condition pathway
  // stored as a bare CONCEPT (or DEMOGRAPHIC) child of the situations
  // OR instead of a 1-child AND wrapper. PathwayCard used to guard on
  // GROUP_KINDS.includes(node.kind) and return null for this shape,
  // so the whole pathway -- SNOMED code included -- silently vanished
  // from the Advanced editor with no way to see or remove it.
  function makeBareLeafOrRoot(): EditableLogicNode {
    return assignNodeIds({
      kind: "OR",
      children: [
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "123456", preferred_term: "Abdominal mass" },
        },
        {
          kind: "AND",
          name: "Symptom watch",
          children: [
            { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Weight loss" } },
          ],
        },
      ],
    });
  }

  it("renders the bare-leaf pathway card instead of vanishing", () => {
    render(
      <LogicTreeEditor
        root={makeBareLeafOrRoot()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    expect(screen.getByTestId("pathway-card-A")).toBeInTheDocument();
    expect(screen.getByTestId("pathway-card-B")).toBeInTheDocument();
    expect(within(screen.getByTestId("pathway-card-A")).getByText("Abdominal mass")).toBeInTheDocument();
  });

  it("offers a Remove control for the bare-leaf pathway", () => {
    render(
      <LogicTreeEditor
        root={makeBareLeafOrRoot()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    const cardA = screen.getByTestId("pathway-card-A");
    expect(within(cardA).getByRole("button", { name: /remove pathway a/i })).toBeInTheDocument();
  });

  it("lets a second condition be added to the bare-leaf pathway, promoting it into an AND group", () => {
    const tree = makeBareLeafOrRoot();
    const leaf = tree.children?.[0];
    const onUpdate = jest.fn();
    render(
      <LogicTreeEditor
        root={tree}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={onUpdate}
        onRequestAdd={noop}
      />,
    );
    const cardA = screen.getByTestId("pathway-card-A");
    const addDemographicBtn = within(cardA).getByRole("button", { name: /add.*patient detail/i });
    fireEvent.click(addDemographicBtn);
    expect(onUpdate).toHaveBeenCalledWith({
      kind: "add_demographic",
      parentNodeId: leaf?.node_id,
    });
  });
});

describe("AIDraftButton integration", () => {
  beforeEach(() => {
    jest.resetAllMocks();
    (global.fetch as jest.Mock) = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("calls onDraft with the logic_tree on success", async () => {
    const mockTree = assignNodeIds({
      kind: "OR",
      children: [
        {
          kind: "AND",
          children: [
            { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Cough" } },
          ],
        },
      ],
    });
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ logic_tree: mockTree, errors: [] }),
    });

    const onDraft = jest.fn();
    const { AIDraftButton } = await import("../AIDraftButton").then(
      (m) => ({ AIDraftButton: m.default }),
    );

    render(
      <AIDraftButton ruleId="rule:NG12:abc" onDraft={onDraft} variant="primary-cta" />,
    );

    const btn = screen.getByRole("button", { name: /draft from nice text/i });
    await userEvent.click(btn);

    await waitFor(() => expect(onDraft).toHaveBeenCalledWith(mockTree));
  });

  it("shows an error when the fetch fails", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: "Pipeline error" }),
    });

    const { AIDraftButton } = await import("../AIDraftButton").then(
      (m) => ({ AIDraftButton: m.default }),
    );

    render(
      <AIDraftButton ruleId="rule:NG12:abc" onDraft={jest.fn()} variant="primary-cta" />,
    );

    await userEvent.click(screen.getByRole("button", { name: /draft from nice text/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
