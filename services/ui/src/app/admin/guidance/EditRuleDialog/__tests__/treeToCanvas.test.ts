/**
 * Phase 3 unit tests for treeToCanvas.
 *
 * Atlas trace:
 *   UN: UN-26E57FA1
 *   DI: DI-C46DDFA3
 *   DO: DO-D4D4CAA8
 *   Risk: R-5F11517C
 *   VT: VT-123BDE46
 *
 * Acceptance criteria covered:
 *   AC-3a  Recognises the canonical NG12-style shape:
 *          AND[ DEMOGRAPHIC, OR[ AND(CONCEPT*), AND(CONCEPT*) ] ]
 *          and emits a WhoCard + two PathwayCards.
 *   AC-3b  Surfaces optional pathway names on the PathwayCard, falling
 *          back to positional "Pathway A/B/C" when name is missing.
 *   AC-3c  Recognises a top-level NOT-CONCEPT and emits a NoneOfCard.
 *   AC-3d  Falls back to "unsupported" for shapes the canvas cannot
 *          render in-place (multiple top-level OR groups, nested OR
 *          inside a pathway, complex NOT bodies). The reason string is
 *          shown verbatim in the canvas's "Open Advanced view" prompt.
 *   AC-3e  Single CONCEPT / DEMOGRAPHIC / AT_LEAST roots become a
 *          single-row WhoCard so the canvas is never empty for trees
 *          that the operator-tree editor would render fine.
 */

import { assignNodeIds } from "../treeOps";
import { treeToCanvas } from "../treeToCanvas";
import type { EditableLogicNode } from "../types";

function buildNg12Tree(opts: {
  pathwayAName?: string;
  pathwayBName?: string;
} = {}): EditableLogicNode {
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
            kind: "AND",
            name: opts.pathwayAName,
            children: [
              {
                kind: "AT_LEAST",
                min: 2,
                children: [
                  {
                    kind: "CONCEPT",
                    criterion: {
                      snomed_concept_id: "1",
                      preferred_term: "Cough",
                    },
                  },
                  {
                    kind: "CONCEPT",
                    criterion: {
                      snomed_concept_id: "2",
                      preferred_term: "Fatigue",
                    },
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
    ],
  });
}

describe("treeToCanvas (Phase 3 sentence canvas)", () => {
  it("AC-3a: recognises NG12-style AND[demographic, OR[pathway, pathway]] and emits WhoCard + two PathwayCards", () => {
    const tree = buildNg12Tree();
    const model = treeToCanvas(tree);

    expect(model.kind).toBe("canvas");
    if (model.kind !== "canvas") return;

    expect(model.whoCard).toBeDefined();
    expect(model.whoCard?.rows).toHaveLength(1);
    expect(model.whoCard?.rows[0].variant).toBe("demographic");

    expect(model.pathways).toHaveLength(2);
    expect(model.pathwayParentNodeId).toBeDefined();
    expect(model.pathways?.[0].hasAndWrapper).toBe(true);
    expect(model.pathways?.[0].rows).toHaveLength(1);
    expect(model.pathways?.[0].rows[0].variant).toBe("at_least");
    expect(model.pathways?.[1].rows[0].variant).toBe("concept");
  });

  it("AC-3b: surfaces optional pathway names on PathwayCard, with positional fallback", () => {
    const tree = buildNg12Tree({ pathwayAName: "Persistent cough" });
    const model = treeToCanvas(tree);
    if (model.kind !== "canvas") throw new Error("expected canvas");

    expect(model.pathways?.[0].name).toBe("Persistent cough");
    expect(model.pathways?.[0].positional).toBe("Pathway A");
    // Pathway B has no name -> positional fallback only
    expect(model.pathways?.[1].name).toBeUndefined();
    expect(model.pathways?.[1].positional).toBe("Pathway B");
  });

  it("AC-3b: trims whitespace-only names back to undefined", () => {
    const tree = buildNg12Tree({ pathwayAName: "   " });
    const model = treeToCanvas(tree);
    if (model.kind !== "canvas") throw new Error("expected canvas");
    expect(model.pathways?.[0].name).toBeUndefined();
  });

  it("AC-3c: top-level AND with NOT(CONCEPT) emits a NoneOfCard", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
        },
        {
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
        },
      ],
    });
    const model = treeToCanvas(tree);
    if (model.kind !== "canvas") throw new Error("expected canvas");

    expect(model.noneOf).toBeDefined();
    expect(model.noneOf?.rows).toHaveLength(1);
    expect(model.noneOf?.rows[0].variant).toBe("concept");
  });

  it("AC-3d: more than one top-level OR returns unsupported with a stable reason", () => {
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
    const model = treeToCanvas(tree);
    expect(model.kind).toBe("unsupported");
    if (model.kind !== "unsupported") return;
    expect(model.reason).toMatch(/more than one alternative pathway/i);
  });

  it("AC-3d: nested OR inside a pathway returns unsupported", () => {
    const tree = assignNodeIds({
      kind: "OR",
      children: [
        {
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
          ],
        },
      ],
    });
    const model = treeToCanvas(tree);
    expect(model.kind).toBe("unsupported");
    if (model.kind !== "unsupported") return;
    expect(model.reason).toMatch(/nested or/i);
  });

  it("AC-3d: NOT wrapping a complex inner shape returns unsupported", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "NOT",
          children: [
            {
              kind: "AT_LEAST",
              min: 2,
              children: [
                {
                  kind: "CONCEPT",
                  criterion: { snomed_concept_id: "1", preferred_term: "A" },
                },
              ],
            },
          ],
        },
      ],
    });
    const model = treeToCanvas(tree);
    expect(model.kind).toBe("unsupported");
  });

  it("AC-3e: single CONCEPT root becomes a one-row WhoCard", () => {
    const tree = assignNodeIds({
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
    });
    const model = treeToCanvas(tree);
    if (model.kind !== "canvas") throw new Error("expected canvas");
    expect(model.whoCard?.rows).toHaveLength(1);
    expect(model.whoCard?.rows[0].variant).toBe("concept");
  });

  it("AC-3e: single AT_LEAST(all-CONCEPT) root becomes a one-row WhoCard", () => {
    const tree = assignNodeIds({
      kind: "AT_LEAST",
      min: 2,
      children: [
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "1", preferred_term: "A" },
        },
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "2", preferred_term: "B" },
        },
      ],
    });
    const model = treeToCanvas(tree);
    if (model.kind !== "canvas") throw new Error("expected canvas");
    expect(model.whoCard?.rows[0].variant).toBe("at_least");
  });
});
