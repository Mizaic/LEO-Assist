/**
 * Phase 3 integration tests for SentenceCanvas.
 *
 * Atlas trace:
 *   UN: UN-26E57FA1
 *   DI: DI-C46DDFA3
 *   DO: DO-D4D4CAA8
 *   Risk: R-5F11517C
 *   VT: VT-123BDE46
 *
 * Acceptance criteria covered:
 *   AC-3f  Renders WhoCard, PathwayCards, and NoneOfCard sections
 *          for the canonical NG12-style tree, each as a labelled
 *          region (a11y).
 *   AC-3g  Soft-cased "Any N or more of these" badge shows wherever
 *          an AT_LEAST cluster is rendered (no leftover "AT LEAST"
 *          all-caps copy).
 *   AC-3h  When treeToCanvas reports an unsupported shape, the
 *          canvas renders an "Open Advanced view" prompt instead of
 *          silently dropping rows. The prompt is wired to the
 *          parent-supplied open-advanced-view callback.
 *   AC-3i  Pathway cards display the optional name when present and
 *          fall back to "Pathway A/B/..." otherwise (Phase 2 carried
 *          forward into the canvas).
 */

import React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";

import SentenceCanvas from "../SentenceCanvas";
import { assignNodeIds } from "../treeOps";
import type { EditableLogicNode } from "../types";

const noop = () => {};

function ng12Tree(opts: {
  pathwayAName?: string;
  pathwayBName?: string;
  withNot?: boolean;
} = {}): EditableLogicNode {
  const children: Array<Partial<EditableLogicNode> & { kind: string }> = [
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
          kind: "AND",
          name: opts.pathwayAName,
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
        {
          kind: "AND",
          name: opts.pathwayBName,
          children: [
            {
              kind: "CONCEPT",
              criterion: {
                snomed_concept_id: "3",
                preferred_term: "Haemoptysis",
              },
            },
          ],
        },
      ],
    },
  ];
  if (opts.withNot) {
    children.push({
      kind: "NOT",
      children: [
        {
          kind: "CONCEPT",
          criterion: {
            snomed_concept_id: "9",
            preferred_term: "Recent chest X-ray",
          },
        },
      ],
    });
  }
  return assignNodeIds({ kind: "AND", children } as EditableLogicNode);
}

function renderCanvas(
  tree: EditableLogicNode,
  onOpenAdvancedView?: () => void,
) {
  return render(
    <SentenceCanvas
      tree={tree}
      selectedNodeId={null}
      onSelectNode={noop}
      onUpdate={noop}
      onRequestAdd={noop}
      onRequestCoach={noop}
      onOpenAdvancedView={onOpenAdvancedView}
    />,
  );
}

describe("SentenceCanvas (Phase 3)", () => {
  it("AC-3f: renders WhoCard, PathwayCards and NoneOfCard regions for the NG12-style tree", () => {
    renderCanvas(ng12Tree({ withNot: true }));
    // Top-level region wrapping the whole canvas.
    expect(
      screen.getByRole("region", { name: /sentence canvas/i }),
    ).toBeInTheDocument();
    // WhoCard, PathwaysSection, NoneOfCard
    expect(
      screen.getByRole("region", { name: /patient must have/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", {
        name: /patient must match one of these pathways/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", {
        name: /patient must not have any of these/i,
      }),
    ).toBeInTheDocument();
  });

  it("AC-3g: AT_LEAST cluster renders the soft-cased 'Any N or more of these' badge (no all-caps AT LEAST)", () => {
    renderCanvas(ng12Tree());
    // The soft-cased label is the only AT-LEAST chrome the canvas
    // emits. Phase 3 retired the all-caps "AT LEAST" badge.
    expect(screen.getByText(/or more of these/i)).toBeInTheDocument();
    expect(screen.queryByText(/^AT LEAST/)).not.toBeInTheDocument();
  });

  it("AC-3h: unsupported shape renders the 'Open Advanced view' prompt and wires the callback", () => {
    // Two top-level OR groups is an unsupported canvas shape.
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "OR",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "1", preferred_term: "A" },
            },
          ],
        },
        {
          kind: "OR",
          children: [
            {
              kind: "CONCEPT",
              criterion: { snomed_concept_id: "2", preferred_term: "B" },
            },
          ],
        },
      ],
    });
    const onOpenAdvancedView = jest.fn();
    renderCanvas(tree, onOpenAdvancedView);

    const prompt = screen.getByRole("status", {
      name: /this rule has a complex shape/i,
    });
    expect(prompt).toBeInTheDocument();
    // The reason string from treeToCanvas is shown verbatim so the
    // user knows why the canvas cannot edit this rule in-place.
    expect(
      within(prompt).getByText(/more than one alternative pathway/i),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /open advanced view/i }),
    );
    expect(onOpenAdvancedView).toHaveBeenCalledTimes(1);
  });

  it("AC-3i: pathway cards show the optional name when present and the positional fallback otherwise", () => {
    renderCanvas(
      ng12Tree({ pathwayAName: "Persistent cough" }),
    );
    // Pathway A: the name lives in an inline text field, prefilled
    // with the optional name. The aria-label is "Name for Pathway A.
    // Optional. ..." (carried over from the editor) so we can target
    // it independently of the rendered letter chip.
    const inputs = screen.getAllByLabelText(/name for pathway [ab]/i);
    expect(inputs.length).toBeGreaterThanOrEqual(2);
    expect((inputs[0] as HTMLInputElement).value).toBe("Persistent cough");
    expect((inputs[1] as HTMLInputElement).value).toBe("");
    // The positional letter chip is always shown so the user can tell
    // pathways apart even before they type a name. Pathway B's letter
    // chip is the visible fallback.
    expect(
      screen.getByRole("button", { name: /^remove pathway b$/i }),
    ).toBeInTheDocument();
  });
});
