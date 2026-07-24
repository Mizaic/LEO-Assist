/**
 * Unit tests for the shared pathway-split heuristic -- VT parity task
 * for the sentence-style rule builder plan.
 *
 * The critical case: NG12 1.2.9's actual tree shape is
 * `AND[DEMOGRAPHIC(age>=55), OR[6 pathways]]` -- the OR sits at depth 1,
 * not at the literal root. Any consumer that only checks the literal
 * root (as LogicTreeEditor/index.tsx's old isPathwayRoot() did) misses
 * this shape entirely.
 */
import { isPathwaySplit, type PathwaySplitNode } from "../pathwayDetection";
import { makeNg12129Tree } from "./fixtures/ng12129";

function concept(): PathwaySplitNode {
  return { kind: "CONCEPT" };
}

describe("isPathwaySplit", () => {
  it("returns true for an OR at depth 0 with 2+ children", () => {
    expect(
      isPathwaySplit({ kind: "OR", children: [concept(), concept()] }, 0),
    ).toBe(true);
  });

  it("returns true for an OR at depth 1 with 2+ children", () => {
    expect(
      isPathwaySplit({ kind: "OR", children: [concept(), concept()] }, 1),
    ).toBe(true);
  });

  it("returns false for an OR deeper than depth 1", () => {
    expect(
      isPathwaySplit({ kind: "OR", children: [concept(), concept()] }, 2),
    ).toBe(false);
  });

  it("returns false for a single-child OR", () => {
    expect(isPathwaySplit({ kind: "OR", children: [concept()] }, 0)).toBe(
      false,
    );
  });

  it("returns false for a non-OR group", () => {
    expect(
      isPathwaySplit({ kind: "AND", children: [concept(), concept()] }, 0),
    ).toBe(false);
  });

  it("is case-insensitive on kind", () => {
    expect(
      isPathwaySplit({ kind: "or", children: [concept(), concept()] }, 0),
    ).toBe(true);
  });

  it("NG12 1.2.9: detects the OR nested one level inside the demographic AND", () => {
    const tree = makeNg12129Tree();
    expect(tree.kind).toBe("AND");
    expect(tree.children).toHaveLength(2);

    const [demographic, or] = tree.children!;
    expect(demographic.kind).toBe("DEMOGRAPHIC");
    expect(or.kind).toBe("OR");
    expect(or.children).toHaveLength(6);

    // The literal root (the AND) is not itself a pathway split...
    expect(isPathwaySplit(tree, 0)).toBe(false);
    // ...but the OR one level down is, which is exactly the shape a
    // literal-root-only check like the old isPathwayRoot() would miss.
    expect(isPathwaySplit(or, 1)).toBe(true);
  });
});
