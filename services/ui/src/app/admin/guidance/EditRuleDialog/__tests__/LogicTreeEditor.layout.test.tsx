/**
 * Phase 1 layout tests for LogicTreeEditor -- VT-LEO-AI-152.
 *
 * Verifies:
 *   - AT-LEAST groups whose children are all CONCEPTs render inline
 *     ("At least N of these: [chip] [chip] ...") rather than as a stacked
 *     selector + separate chip rows.
 *   - Non-root groups are collapsible via a chevron and show a summary of
 *     their contents when collapsed.
 *   - The root group does not show a collapse chevron.
 */

import React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";

import LogicTreeEditor from "../LogicTreeEditor";
import { assignNodeIds } from "../treeOps";
import type { EditableLogicNode } from "../types";

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
  it("renders AT-LEAST with all-CONCEPT children inline (single 'At least' header)", () => {
    render(
      <LogicTreeEditor
        root={makeAtLeastTree()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    // The inline cluster is signalled by literal "At least" + "of these:"
    // text rather than the dropdown selector that the legacy stacked
    // layout emits.
    expect(screen.getByText("At least")).toBeInTheDocument();
    expect(screen.getByText(/of these:/i)).toBeInTheDocument();
    // All three concept chips appear once each.
    expect(screen.getByText("Cough")).toBeInTheDocument();
    expect(screen.getByText("Fatigue")).toBeInTheDocument();
    expect(screen.getByText("Dyspnea")).toBeInTheDocument();
    // The "Add" affordance is the inline plus chip, not the verbose bar.
    expect(
      screen.getByRole("button", { name: /add a symptom or sign to this group/i }),
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
    // Mixed-child clusters fall back to the standard selector + add bar.
    expect(screen.queryByText("At least")).not.toBeInTheDocument();
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
      /how many of these the patient must have/i,
    ) as HTMLInputElement;
    expect(counter.value).toBe("2");
    expect(counter.max).toBe("3");
    // The "of N" caption shows the current child count.
    const cluster = counter.closest("[role='treeitem']");
    expect(cluster).not.toBeNull();
    expect(within(cluster as HTMLElement).getByText(/of 3/)).toBeInTheDocument();
  });
});
